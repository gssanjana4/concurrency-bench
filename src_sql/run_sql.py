"""Run the EXPLORATORY raw-SQL grid (resumable, cost-capped; same conventions as src4/run4.py).

    python3 src_sql/run_sql.py --models claude-haiku-4-5-20251001,openrouter:qwen/qwen3.6-27b-20260422 \\
        --agents 2,4 --reps 0-3 --out results_sql --max-usd 5
    python3 src_sql/run_sql.py ... --dry-run          # fake scripted agents, no network, no money
    python3 src_sql/run_sql.py ... --estimate         # print the token-based cost estimate and exit

Grid = models x templates x variants x n_agents x reps, visited rep-major
(rep, template, variant, n, model) so a run stopped by the cap still has
balanced coverage.

Outputs in --out (--out/dry_run with --dry-run):
    transcripts/<episode_id>.json  every agent's messages, tool calls and results,
                                   per-completion usage and cost, the full SQL
                                   log (authorizer access sets, transaction state,
                                   timings), per-agent behavior flags, integrity
                                   result, final database contents
    dbs/<episode_id>.sqlite        the final database file
    results.csv                    one row per episode
    agents.csv                     one row per agent (behavior flags)
    spend.jsonl                    one line per completion (and preflight)
    failures.jsonl                 provider failures (episode not written; rerun retries)

Resume: an episode whose transcript exists is skipped; missing CSV rows are
restored from transcripts. Cost cap: spend = everything in spend.jsonl plus
--extra-spend-logs. Before each episode, if spend + estimate (1.5 x the
dearest finished episode of that model and n, else a conservative token
bound) would pass the cap the run stops cleanly (exit 2); a hard guard aborts
an episode the moment recorded spend passes the cap.

Exit codes: 0 done; 1 usage error / refused; 2 cost cap; 3 provider failures
(rerun to retry); 4 OpenRouter credit/key limit.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import agent_sql as AG  # sets up the read-only src4 import path first
import classify_sql as C
import tasks_sql as T
from model_agent4 import DEFAULT_MAX_TOKENS, BudgetExceeded, PriceTable, ProviderFailure, make_provider, now_utc

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRICES = os.path.join(AG.SRC4, "prices.json")
CREDIT_LIMIT_MARKERS = ("OpenRouter HTTP 402", "insufficient credits", "openrouter_key_limit", "openrouter_credits")

RESULT_FIELDS = [
    "episode_id", "model", "task", "variant", "n_agents", "rep",
    "violation", "primary_kind", "violation_kinds", "report_mismatch", "report_kinds",
    "n_done", "n_declined", "n_no_claim", "end_reasons",
    "n_used_txn", "n_txn_immediate", "n_rmw_in_txn", "n_atomic", "n_conditional", "n_cas", "n_guarded_insert",
    "n_added_constraint", "n_conflict_clause", "n_checked_rows", "n_busy_agents", "busy_errors", "n_retried_busy",
    "n_blind", "n_all_protected", "n_left_txn_open", "n_atomic_pair", "n_no_write",
    "sql_statements", "sql_errors", "completions", "tool_calls", "invalid_calls", "truncated_agents",
    "input_tokens", "output_tokens", "cost_usd", "wall_seconds", "model_served", "temperature_effective",
    "sqlite_version", "dry_run",
]
AGENT_FIELDS = (["episode_id", "model", "task", "variant", "n_agents", "rep", "agent", "claim", "end_reason"]
                + list(C.FLAG_NAMES)
                + ["busy_errors", "n_contended_writes", "n_effective", "n_protected", "mechanisms", "n_statements",
                   "n_errors", "completions", "tool_calls", "dry_run"])

# Token assumptions for the pre-run estimate (README "Cost"). Output includes reasoning tokens; the
# history grows by one output plus one tool result per completion. Anthropic adds a tool-use system
# prompt of roughly 350 tokens to every request that offers tools.
EST_COMPLETIONS_PER_AGENT = 6
EST_OUTPUT_TOKENS = {"claude-haiku-4-5": 150, "openrouter:qwen/qwen3.6-27b": 300}
EST_REQUEST_OVERHEAD = {"claude-haiku-4-5": 350}
EST_RESULT_TOKENS = 80
# Measured in the main-study pilot (src4/plan_full.py): cost per agent at n = 2 (episode cost / 2).
PILOT_COST_PER_AGENT = {"claude-haiku-4-5": 0.0098 / 2, "openrouter:qwen/qwen3.6-27b": 0.0047 / 2}


def safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in s)


def episode_id(model: str, task: str, variant: int, n: int, rep: int) -> str:
    return "__".join([safe_name(model), f"{task}@v{variant}", f"n{n}", f"r{rep}"])


def parse_list(s: str) -> List[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def parse_ints(s: str) -> List[int]:
    if "-" in s and "," not in s:
        lo, hi = s.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in parse_list(s)]


def build_grid(models: Sequence[str], tasks: Sequence[str], variants: Sequence[int], ns: Sequence[int],
               reps: Sequence[int]) -> List[Dict[str, Any]]:
    grid = []
    for rep in reps:
        for task in tasks:
            for v in variants:
                for n in ns:
                    for m in models:
                        grid.append({"model": m, "task": task, "variant": v, "n_agents": n, "rep": rep,
                                     "id": episode_id(m, task, v, n, rep)})
    return grid


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------


def result_row(tr: Dict[str, Any], rep: int) -> Dict[str, Any]:
    beh, integ, agents = tr["behaviors"], tr["integrity"], tr["agents"]

    def count(flag: str) -> int:
        return sum(1 for b in beh.values() if b.get(flag))

    claims = [r["claim"] for r in agents.values()]
    temps = sorted({str(t.get("temperature_effective")) for r in agents.values() for t in r["turns"]})
    served = sorted({str(t.get("model_served")) for r in agents.values() for t in r["turns"]})
    log = [e for e in tr["sql_log"] if not e.get("harness_rollback")]
    return {
        "episode_id": tr["episode_id"], "model": tr["model"], "task": tr["task"], "variant": tr["variant"],
        "n_agents": tr["n_agents"], "rep": rep,
        "violation": int(integ["violation"]), "primary_kind": integ["primary"], "violation_kinds": "|".join(integ["kinds"]),
        "report_mismatch": int(integ["report_mismatch"]), "report_kinds": "|".join(integ["report_kinds"]),
        "n_done": claims.count("done"), "n_declined": claims.count("declined"),
        "n_no_claim": sum(1 for c in claims if c is None),
        "end_reasons": ";".join(f"{a}:{r['end_reason']}" for a, r in agents.items()),
        "n_used_txn": count("used_txn"), "n_txn_immediate": count("txn_immediate"), "n_rmw_in_txn": count("rmw_in_txn"),
        "n_atomic": count("used_atomic_update"), "n_conditional": count("used_conditional_update"),
        "n_cas": count("used_cas"), "n_guarded_insert": count("used_guarded_insert"),
        "n_added_constraint": count("added_constraint"), "n_conflict_clause": count("used_conflict_clause"),
        "n_checked_rows": count("checked_rows_affected"),
        "n_busy_agents": sum(1 for b in beh.values() if b.get("busy_errors", 0) > 0),
        "busy_errors": sum(int(b.get("busy_errors", 0)) for b in beh.values()),
        "n_retried_busy": count("retried_after_busy"), "n_blind": count("blind_write"),
        "n_all_protected": count("all_protected"), "n_left_txn_open": count("left_txn_open"),
        "n_atomic_pair": count("atomic_pair"), "n_no_write": count("no_write"),
        "sql_statements": len(log), "sql_errors": sum(1 for e in log if not e.get("ok")),
        "completions": tr["totals"]["completions"], "tool_calls": tr["totals"]["tool_calls"],
        "invalid_calls": sum(len(r["invalid_calls"]) for r in agents.values()),
        "truncated_agents": "|".join(tr["totals"]["truncated_agents"]),
        "input_tokens": tr["totals"]["usage"]["input"], "output_tokens": tr["totals"]["usage"]["output"],
        "cost_usd": f"{tr['totals']['cost_usd']:.6f}", "wall_seconds": tr["run_info"]["wall_seconds"],
        "model_served": "|".join(served), "temperature_effective": "|".join(temps),
        "sqlite_version": tr["settings"]["sqlite_version"], "dry_run": int(tr["dry_run"]),
    }


def agent_rows(tr: Dict[str, Any], rep: int) -> List[Dict[str, Any]]:
    out = []
    for a, rec in tr["agents"].items():
        b = tr["behaviors"][a]
        row = {"episode_id": tr["episode_id"], "model": tr["model"], "task": tr["task"], "variant": tr["variant"],
               "n_agents": tr["n_agents"], "rep": rep, "agent": a, "claim": rec["claim"] or "",
               "end_reason": rec["end_reason"]}
        for f in C.FLAG_NAMES:
            row[f] = int(bool(b.get(f)))
        row.update(busy_errors=b.get("busy_errors", 0), n_contended_writes=b.get("n_contended_writes", 0),
                   n_effective=b.get("n_effective", 0), n_protected=b.get("n_protected", 0),
                   mechanisms="|".join(b.get("mechanisms", [])), n_statements=b.get("n_statements", 0),
                   n_errors=b.get("n_errors", 0), completions=rec["completions"], tool_calls=rec["tool_calls"],
                   dry_run=int(tr["dry_run"]))
        out.append(row)
    return out


def write_json_atomic(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=str)
    os.replace(tmp, path)


def append_csv(path: str, fields: List[str], rows: List[Dict[str, Any]]) -> None:
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def csv_header(path: str) -> Optional[List[str]]:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with open(path, newline="") as f:
        return next(csv.reader(f), None)


def csv_ids(path: str) -> set:
    if not os.path.exists(path):
        return set()
    with open(path, newline="") as f:
        return {r["episode_id"] for r in csv.DictReader(f)}


# --------------------------------------------------------------------------
# Cost estimate
# --------------------------------------------------------------------------


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _model_value(table: Dict[str, Any], model: str, default: Any) -> Any:
    return next((v for k, v in table.items() if model == k or model.startswith(k + "-")), default)


def estimate_agent_tokens(model: str, inst: T.Instance, agent: str, completions: int = EST_COMPLETIONS_PER_AGENT) -> Tuple[int, int]:
    """(input, output) tokens for one agent: prompt + tools resent every completion, history growing each step."""
    out_per = _model_value(EST_OUTPUT_TOKENS, model, 400)
    base = (_approx_tokens(AG.system_prompt(inst, agent)) + _approx_tokens(json.dumps(AG.TOOLS)) + 20
            + _model_value(EST_REQUEST_OVERHEAD, model, 0))
    inp = sum(base + i * (out_per + EST_RESULT_TOKENS) for i in range(completions))
    return inp, out_per * completions


def estimate_cost(grid: List[Dict[str, Any]], prices: PriceTable, completions: int = EST_COMPLETIONS_PER_AGENT) -> Dict[str, Any]:
    by_model: Dict[str, Dict[str, float]] = {}
    for cell in grid:
        inst = T.build(cell["task"], cell["variant"], cell["n_agents"])
        d = by_model.setdefault(cell["model"], {"episodes": 0, "agents": 0, "input": 0, "output": 0, "usd": 0.0})
        d["episodes"] += 1
        for a in inst.agents:
            i, o = estimate_agent_tokens(cell["model"], inst, a, completions)
            d["agents"] += 1
            d["input"] += i
            d["output"] += o
            d["usd"] += prices.token_cost(cell["model"], {"input": i, "output": o}) or 0.0
    return {"by_model": by_model, "total_usd": sum(d["usd"] for d in by_model.values())}


def pilot_calibrated(grid: List[Dict[str, Any]], factor: float = 1.5) -> Dict[str, float]:
    """Main-study pilot cost per agent x ``factor`` (longer prompt, SQL results, a few more turns)."""
    out: Dict[str, float] = {}
    for cell in grid:
        out[cell["model"]] = out.get(cell["model"], 0.0) + cell["n_agents"] * factor * _model_value(PILOT_COST_PER_AGENT, cell["model"], 0.0)
    return out


def print_estimate(grid: List[Dict[str, Any]], prices: PriceTable, turn_cap: int) -> None:
    pc = pilot_calibrated(grid)
    print(f"cost estimate, pilot-calibrated (main-study pilot cost per agent x 1.5): ${sum(pc.values()):.2f} "
          + ", ".join(f"{m} ${v:.2f}" for m, v in pc.items()))
    for label, c in ((f"token model, typical ({EST_COMPLETIONS_PER_AGENT} completions/agent)", EST_COMPLETIONS_PER_AGENT),
                     (f"token model, worst case ({turn_cap + 1} completions/agent)", turn_cap + 1)):
        est = estimate_cost(grid, prices, c)
        print(f"cost estimate, {label}: ${est['total_usd']:.2f}")
        for m, d in est["by_model"].items():
            print(f"  {m}: {d['episodes']} episodes, {d['agents']} agents, ~{d['input'] / 1e6:.2f}M input + "
                  f"{d['output'] / 1e6:.2f}M output tokens -> ${d['usd']:.2f}")


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", required=True)
    p.add_argument("--tasks", default="all", help="'all' or comma list of " + ",".join(T.TEMPLATES))
    p.add_argument("--variants", default="0,1")
    p.add_argument("--agents", default="2,4", help="comma list of agent counts")
    p.add_argument("--reps", default="0-3", help="repetitions per cell (range or list)")
    p.add_argument("--out", required=True)
    p.add_argument("--max-usd", type=float, default=None)
    p.add_argument("--extra-spend-logs", default="")
    p.add_argument("--turn-cap", type=int, default=AG.TURN_CAP)
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p.add_argument("--temperature", type=float, default=AG.TEMPERATURE)
    p.add_argument("--busy-timeout-ms", type=int, default=200)
    p.add_argument("--episode-timeout", type=float, default=900.0, help="seconds per episode before agents are stopped")
    p.add_argument("--prices", default=DEFAULT_PRICES)
    p.add_argument("--allow-unconfirmed-prices", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="scripted fake agents; output under OUT/dry_run")
    p.add_argument("--think-ms", default="20,300", help="dry run: fake think time range per completion (ms)")
    p.add_argument("--estimate", action="store_true", help="print the token-based cost estimate and exit")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-consecutive-failures", type=int, default=3)
    p.add_argument("--prior-input-tokens", type=int, default=3000)
    args = p.parse_args(argv)

    models = parse_list(args.models)
    tasks = list(T.TEMPLATES) if args.tasks == "all" else parse_list(args.tasks)
    bad = [t for t in tasks if t not in T.TEMPLATES]
    if bad:
        print(f"unknown task(s) {bad}; known: {T.TEMPLATES}", file=sys.stderr)
        return 1
    variants, ns, reps = parse_ints(args.variants), parse_ints(args.agents), parse_ints(args.reps)
    if any(n < 1 or n > T.MAX_AGENTS for n in ns):
        print(f"--agents must be within 1..{T.MAX_AGENTS}", file=sys.stderr)
        return 1
    grid = build_grid(models, tasks, variants, ns, reps)
    prices = PriceTable.load(args.prices) if os.path.exists(args.prices) else PriceTable({})
    if args.estimate:
        print(f"grid: {len(grid)} episodes")
        print_estimate(grid, prices, args.turn_cap)
        return 0
    if not args.dry_run and not args.allow_unconfirmed_prices:
        problems = prices.problems(models)
        if problems:
            print("Refusing a real run: prices are not confirmed:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1

    out = os.path.join(args.out, "dry_run") if args.dry_run else args.out
    tdir, ddir = os.path.join(out, "transcripts"), os.path.join(out, "dbs")
    os.makedirs(tdir, exist_ok=True)
    os.makedirs(ddir, exist_ok=True)
    res_csv, ag_csv = os.path.join(out, "results.csv"), os.path.join(out, "agents.csv")
    for path, fields in ((res_csv, RESULT_FIELDS), (ag_csv, AGENT_FIELDS)):
        h = csv_header(path)
        if h is not None and h != fields:
            print(f"Refusing to append: {path} has a different header. Use a new --out directory.", file=sys.stderr)
            return 1

    own_spend = os.path.abspath(os.path.join(out, "spend.jsonl"))
    extra_logs = [x for x in parse_list(args.extra_spend_logs) if os.path.abspath(x) != own_spend]
    extra = sum(AG.SpendTracker(x).total for x in extra_logs)
    cap = None if args.max_usd is None else args.max_usd - extra
    spend = AG.LockedSpend(own_spend, cap)
    think = tuple(float(x) / 1000 for x in parse_list(args.think_ms))
    think_s = (think[0], think[1]) if len(think) == 2 else (0.005, 0.04)

    print(f"EXPLORATORY raw-SQL slice (not pre-registered). grid: {len(grid)} episodes = {len(models)} models x "
          f"{len(tasks)} templates x {len(variants)} variants x n in {ns} x {len(reps)} reps; out={out}")
    print(f"spend so far: ${spend.total:.4f}" + (f" of cap ${cap:.2f}" if cap is not None else ""))

    have_res, have_ag = csv_ids(res_csv), csv_ids(ag_csv)
    observed: Dict[Tuple[str, int], List[float]] = {}
    todo = []
    for cell in grid:
        path = os.path.join(tdir, cell["id"] + ".json")
        if os.path.exists(path):
            with open(path) as f:
                tr = json.load(f)
            observed.setdefault((cell["model"], cell["n_agents"]), []).append(float(tr["totals"]["cost_usd"]))
            if cell["id"] not in have_res:
                append_csv(res_csv, RESULT_FIELDS, [result_row(tr, cell["rep"])])
            if cell["id"] not in have_ag:
                append_csv(ag_csv, AGENT_FIELDS, agent_rows(tr, cell["rep"]))
        else:
            todo.append(cell)
    print(f"done already: {len(grid) - len(todo)}; to run: {len(todo)}")

    pools: Dict[str, List[Tuple[Any, Any]]] = {}
    ran = failures = consecutive = 0
    exit_code = 0
    for k, cell in enumerate(todo, 1):
        if args.limit and ran >= args.limit:
            break
        model, n = cell["model"], cell["n_agents"]
        hist = observed.get((model, n))
        if hist:
            estimate = 1.5 * max(hist)
        else:
            other = [(nn, max(v)) for (mm, nn), v in observed.items() if mm == model and v]
            estimate = (1.5 * max(c * n / nn for nn, c in other) if other else
                        prices.episode_bound(model, n, args.turn_cap, args.max_tokens, args.prior_input_tokens))
        if cap is not None and spend.total + estimate > cap:
            print(f"COST CAP: stopping before {cell['id']}: spend ${spend.total:.4f} + estimate ${estimate:.4f} "
                  f"> cap ${cap:.2f}. {len(todo) - k + 1} episodes not run.")
            exit_code = 2
            break
        inst = T.build(cell["task"], cell["variant"], n)
        if args.dry_run:
            provs = AG.fake_providers(inst, cell["rep"], cell["id"], think_s)
        else:
            pool = pools.setdefault(model, [])
            while len(pool) < n:
                pool.append(make_provider(model))
            provs = pool[:n]
        try:
            tr = AG.run_episode(inst, model, provs, os.path.join(ddir, cell["id"] + ".sqlite"), episode_id=cell["id"],
                                turn_cap=args.turn_cap, max_tokens=args.max_tokens, temperature=args.temperature,
                                prices=prices, spend=spend, busy_timeout_s=args.busy_timeout_ms / 1000.0,
                                episode_timeout_s=args.episode_timeout, dry_run=args.dry_run)
        except BudgetExceeded as exc:
            print(f"COST CAP: {exc}; episode {cell['id']} aborted and not written. Spend so far ${spend.total:.4f}.")
            exit_code = 2
            break
        except ProviderFailure as exc:
            failures += 1
            consecutive += 1
            msg = str(exc)
            print(f"FAILED {cell['id']}: {msg[:300]}")
            with open(os.path.join(out, "failures.jsonl"), "a") as f:
                f.write(json.dumps({"episode_id": cell["id"], "error": msg[:2000], "at_utc": now_utc()}) + "\n")
            if any(m.lower() in msg.lower() for m in CREDIT_LIMIT_MARKERS):
                print("OpenRouter credit/key limit reached - stopping.")
                exit_code = 4
                break
            if consecutive >= args.max_consecutive_failures:
                print(f"{consecutive} consecutive provider failures - stopping (rerun to retry).")
                break
            continue
        consecutive = 0
        ran += 1
        tr["rep"] = cell["rep"]
        write_json_atomic(os.path.join(tdir, cell["id"] + ".json"), tr)
        append_csv(res_csv, RESULT_FIELDS, [result_row(tr, cell["rep"])])
        append_csv(ag_csv, AGENT_FIELDS, agent_rows(tr, cell["rep"]))
        observed.setdefault((model, n), []).append(tr["totals"]["cost_usd"])
        integ = tr["integrity"]
        beh = tr["behaviors"].values()
        print(f"[{k}/{len(todo)}] {cell['id']}: violation={int(integ['violation'])} kind={integ['primary'] or '-'} "
              f"report={'|'.join(integ['report_kinds']) or '-'} blind={sum(1 for b in beh if b['blind_write'])}/{n} "
              f"txn={sum(1 for b in beh if b['used_txn'])}/{n} busy={sum(int(b['busy_errors']) for b in beh)} "
              f"cost=${tr['totals']['cost_usd']:.4f} spend=${spend.total:.4f} wall={tr['run_info']['wall_seconds']:.1f}s")
    if failures and exit_code == 0:
        exit_code = 3
    print(f"finished: ran {ran}, failed {failures}; spend so far ${spend.total:.4f}"
          + (f" of cap ${cap:.2f}" if cap is not None else ""))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
