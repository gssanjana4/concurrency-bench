"""Run a grid of model-agent episodes on the concurrency benchmark.

Example (no network, deterministic fake model):

    python3 run4.py --models claude-haiku-4-5-20251001 --configs all --tasks pilot \\
        --agents 2 --seeds 0,1 --out results4/pilot --dry-run

Grid = models x configs x tasks [x instances] x seeds (x prompt variants with
--aware both). Episodes are visited seed-major (seed, task, instance, config,
prompt, model) so a run stopped by the cost cap still has balanced coverage.

Task instances (``--instances K``): with K > 0 each task name must be one of
the eight registered templates (:data:`instances4.TEMPLATES`) and expands to
the full-run instances 0 .. K-1 from :mod:`instances4` (seeded, disjoint from
the pilot). With K = 0 (default) the canonical catalog task is used (this is
what the pilot ran; instance ``pilot`` in the CSV).

Concurrency-aware prompt (``--aware off|on|both``): the only prompt
difference is the one sentence :data:`world4.CONCURRENCY_NOTICE`.

Outputs in ``--out`` (``--out``/dry_run with ``--dry-run``, so fake
transcripts can never make a real run skip episodes):

    transcripts/<episode_id>.json   one per episode: every agent's messages,
                                    tool calls, results, per-completion token
                                    usage and cost, the ledger, the final
                                    store, the scorer output
    results.csv                     one row per episode
    spend.jsonl                     one line per completion (cost source:
                                    OpenRouter usage.cost or prices.json)
    failures.jsonl                  provider failures (episode not written)

Resumable: an episode whose transcript exists is skipped (a missing CSV row
is restored from the transcript). Transcripts are written atomically.

Cost cap (``--max-usd``): spend = everything in spend.jsonl, including
aborted episodes, earlier runs and preflight. Before each episode the runner
estimates its cost (1.5 x the most expensive finished episode of that model,
or a conservative token bound when none has finished) and stops cleanly if
spend + estimate would pass the cap. A hard in-episode guard aborts (without
writing) the moment spend passes the cap. ``--extra-spend-logs`` names other
spend.jsonl files (other phases, preflight) that count toward the same cap,
so one total cap can span several output directories.

Exit codes: 0 grid finished; 2 cost cap reached; 3 provider failures (rerun
to retry; finished episodes are kept); 4 OpenRouter credit/key limit; 1 usage
errors (including unconfirmed prices on a real run).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import instances4 as I
import tasks4 as T
from model_agent4 import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TURN_CAP,
    TEMPERATURE,
    BudgetExceeded,
    ModelRunConfig,
    PriceTable,
    ProviderFailure,
    SpendTracker,
    make_provider,
    model_agent_spec,
    now_utc,
)
from records import to_json_value
from scheduler import ScheduleConfig, run_episode
from score4 import score_episode
from world4 import PRESET_NAMES, world_config

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRICES = os.path.join(HERE, "prices.json")

# Pilot subset: every record kind (inventory, seat, ticket, account, budget),
# every intent type (Decrement, Claim, Transfer, GuardedSpend, JointWithdraw)
# and every category (conflict, still_valid, write_skew, control).
PILOT_TASKS: Tuple[str, ...] = (
    "inventory_last_unit",       # conflict     Decrement     inventory
    "inventory_still_valid",     # still_valid  Decrement     inventory
    "seat_same",                 # conflict     Claim         seat
    "ticket_same",               # conflict     Claim         ticket
    "transfer_shared_source",    # conflict     Transfer      account (2 records)
    "budget_write_skew",         # write_skew   GuardedSpend  budget
    "joint_account_write_skew",  # write_skew   JointWithdraw account
    "budget_control",            # control      GuardedSpend  budget
)

# The integrity column is ``non_serializable`` (renamed from ``lost_update`` on
# 2026-10-31). ``primary_label`` is exactly one of stale_overwrite /
# partial_action / write_skew on non-serializable rows, empty otherwise.
# ``n_conflict_agents`` and ``n_abandon_eligible`` are the per-episode
# denominators of the unnecessary_give_up and abandoned rates.
CSV_FIELDS = [
    "episode_id", "model", "config", "aware_prompt", "task", "instance", "wording", "category", "kind", "n_agents", "seed",
    "non_serializable", "primary_label", "stale_overwrite", "partial_action", "write_skew", "graph_cycle",
    "n_stale_writes", "invariant_violation", "conflict_observed",
    "stall", "n_committed", "n_fulfilled", "n_abandoned", "n_abandon_eligible", "n_unnecessary_give_up",
    "n_conflict_agents", "n_lock_leak",
    "choices", "end_reasons", "completions", "multi_tool_turns", "invalid_calls", "truncated_agents",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "cost_usd", "rounds",
    "temperature_effective", "model_served", "dry_run",
]

CREDIT_LIMIT_MARKERS = ("OpenRouter HTTP 402", "insufficient credits", "openrouter_key_limit", "openrouter_credits")


def safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in s)


def episode_id(model: str, config: str, aware: bool, task: str, n: int, seed: int, instance: Optional[int] = None) -> str:
    """Episode id; full-run instances add ``@i<k>`` to the task (pilot ids have no suffix)."""
    tname = task if instance is None else f"{task}@i{instance}"
    return "__".join([safe_name(model), safe_name(config) + ("+aware" if aware else ""), tname, f"n{n}", f"s{seed}"])


def parse_list(s: str) -> List[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def resolve_configs(spec: str) -> List[str]:
    names = list(PRESET_NAMES) if spec == "all" else parse_list(spec)
    for n in names:
        world_config(n)  # validates
    return names


def resolve_tasks(spec: str) -> List[str]:
    if spec == "pilot":
        return list(PILOT_TASKS)
    names = list(T.CATALOG) if spec == "all" else parse_list(spec)
    unknown = [n for n in names if n not in T.CATALOG]
    if unknown:
        raise SystemExit(f"unknown task(s) {unknown}; known: {list(T.CATALOG)}")
    return names


def resolve_seeds(spec: str) -> List[int]:
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in parse_list(spec)]


def build_grid(models, configs, tasks, seeds, n_agents, awares, k_instances: int = 0) -> List[Dict[str, Any]]:
    """Grid cells; ``k_instances`` > 0 expands each template into instances 0 .. k-1."""
    inst: List[Optional[int]] = list(range(k_instances)) if k_instances > 0 else [None]
    if k_instances > 0:
        bad = [t for t in tasks if t not in I.TEMPLATES]
        if bad:
            raise SystemExit(f"--instances needs registered templates; not templates: {bad}")
    grid = []
    for seed in seeds:
        for task in tasks:
            for i in inst:
                for config in configs:
                    for aware in awares:
                        for model in models:
                            grid.append({
                                "model": model, "config": config, "aware": aware, "task": task, "instance": i,
                                "n_agents": n_agents, "seed": seed,
                                "id": episode_id(model, config, aware, task, n_agents, seed, i),
                            })
    return grid


def cell_task(cell: Dict[str, Any]) -> T.Task:
    """The task a grid cell runs: a full-run instance, or the catalog task (pilot)."""
    if cell.get("instance") is None:
        return T.CATALOG[cell["task"]](cell["n_agents"])
    return I.build(cell["task"], cell["instance"], cell["n_agents"])


# --------------------------------------------------------------------------
# One episode
# --------------------------------------------------------------------------


def snapshot_json(store) -> Dict[str, Any]:
    return {rid: {"value": to_json_value(v), "version": ver} for rid, (v, ver) in store.snapshot().items()}


def ledger_json(ledger) -> Dict[str, Any]:
    return {
        "effects": [e.to_dict() for e in ledger.effects],
        "calls": [c.to_dict() for c in ledger.calls],
        "agent_ends": [e.to_dict() for e in ledger.agent_ends],
        "flags": to_json_value(ledger.flags),
    }


def run_one(cell: Dict[str, Any], provider: Any, probe: Any, schedule_kw: Dict[str, Any], *, turn_cap: int,
            max_tokens: int, temperature: Optional[float], prices: Optional[PriceTable], spend: Optional[SpendTracker],
            dry_run: bool, prompt_caching: bool = True) -> Dict[str, Any]:
    """Run one episode and return its transcript (not yet written)."""
    task = cell_task(cell)
    wc = world_config(cell["config"], concurrency_aware_prompt=cell["aware"])
    schedule = ScheduleConfig(seed=cell["seed"], turn_cap=turn_cap, **schedule_kw)
    rc = ModelRunConfig(
        model=cell["model"], provider=provider, world_config=wc, turn_cap=turn_cap, max_tokens=max_tokens,
        temperature=temperature, prompt_caching=prompt_caching, prices=prices, spend=spend, usage_probe=probe,
        episode_id=cell["id"],
    )
    records: Dict[str, Dict[str, Any]] = {}
    started, t0 = now_utc(), time.monotonic()
    episode = run_episode(task, model_agent_spec(rc, records), wc, schedule)
    score = score_episode(episode)
    agents = {a: records[a] for a in task.agent_ids if a in records}
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    for rec in agents.values():
        for k in totals:
            totals[k] += rec["usage"][k]
    return {
        "episode_id": cell["id"],
        "dry_run": dry_run,
        "model": cell["model"],
        "provider": getattr(provider, "name", "?"),
        "config": wc.coordination.name,
        "concurrency_aware_prompt": cell["aware"],
        "task": {"factory": cell["task"], "name": task.name, "category": task.category, "kind": task.kind,
                 "instance": I.PILOT_INSTANCE if cell.get("instance") is None else cell["instance"],
                 "wording": getattr(next(iter(task.intents.values())), "wording", 0),
                 "fingerprint": I.fingerprint(task),
                 "description": task.description, "initial": to_json_value(dict(task.initial)),
                 "intents": {a: i.describe() for a, i in task.intents.items()}},
        "n_agents": cell["n_agents"],
        "seed": cell["seed"],
        "schedule": {"seed": schedule.seed, "read_write_gap": schedule.read_write_gap, "start_jitter": schedule.start_jitter,
                     "turn_cap": schedule.turn_cap, "stall_rounds": schedule.stall_rounds, "max_rounds": schedule.max_rounds},
        "world": {"lock_expiry": wc.lock_expiry, "max_lease_steps": wc.max_lease_steps},
        "generation": {"max_tokens": max_tokens, "temperature_requested": temperature, "prompt_caching": rc.prompt_caching},
        "run_info": {"started_utc": started, "finished_utc": now_utc(), "wall_seconds": round(time.monotonic() - t0, 3)},
        "agents": agents,
        "ledger": ledger_json(episode.ledger),
        "final_store": snapshot_json(episode.store),
        "score": score.to_dict(),
        "totals": {
            "usage": totals,
            "cost_usd": sum(r["cost_usd"] for r in agents.values()),
            "completions": sum(r["completions"] for r in agents.values()),
            "multi_tool_turns": sum(r["multi_tool_turns"] for r in agents.values()),
            "invalid_calls": sum(len(r["invalid_calls"]) for r in agents.values()),
            "truncated_agents": [a for a, r in agents.items() if r["truncated"]],
        },
    }


def csv_row(tr: Dict[str, Any]) -> Dict[str, Any]:
    sc, tot = tr["score"], tr["totals"]
    ag = sc["agents"]
    temps = sorted({str(t.get("temperature_effective")) for r in tr["agents"].values() for t in r["turns"]})
    served = sorted({str(t.get("model_served")) for r in tr["agents"].values() for t in r["turns"]})
    return {
        "episode_id": tr["episode_id"], "model": tr["model"], "config": tr["config"],
        "aware_prompt": int(tr["concurrency_aware_prompt"]), "task": tr["task"]["factory"],
        "instance": tr["task"].get("instance", I.PILOT_INSTANCE), "wording": tr["task"].get("wording", 0),
        "category": tr["task"]["category"], "kind": tr["task"]["kind"], "n_agents": tr["n_agents"], "seed": tr["seed"],
        "non_serializable": int(sc["non_serializable"]), "primary_label": sc["primary_label"] or "",
        "stale_overwrite": int(sc["stale_overwrite"]), "partial_action": int(sc["partial_action"]),
        "write_skew": int(sc["write_skew"]), "graph_cycle": int(sc["graph_cycle"]),
        "n_stale_writes": len(sc["stale_overwrite_seqs"]),
        "invariant_violation": int(sc["invariant_violation"]), "conflict_observed": int(sc["conflict_observed"]),
        "stall": int(sc["stall"]), "n_committed": len(sc["committed_agents"]),
        "n_fulfilled": sum(1 for s in ag.values() if s["fulfilled"]), "n_abandoned": len(sc["abandoned"]),
        "n_abandon_eligible": sum(1 for s in ag.values() if s["end_reason"] != "running" and (s["valid_at_end"] or s["fulfilled"])),
        "n_unnecessary_give_up": len(sc["unnecessary_give_ups"]),
        "n_conflict_agents": sum(1 for s in ag.values() if s["conflicts_seen"] > 0), "n_lock_leak": len(sc["lock_leaks"]),
        "choices": ";".join(f"{a}:{'|'.join(s['choices'])}" for a, s in ag.items()),
        "end_reasons": ";".join(f"{a}:{s['end_reason']}" for a, s in ag.items()),
        "completions": tot["completions"], "multi_tool_turns": tot["multi_tool_turns"],
        "invalid_calls": tot["invalid_calls"], "truncated_agents": "|".join(tot["truncated_agents"]),
        "input_tokens": tot["usage"]["input"], "output_tokens": tot["usage"]["output"],
        "cache_read_tokens": tot["usage"]["cache_read"], "cache_write_tokens": tot["usage"]["cache_write"],
        "cost_usd": f"{tot['cost_usd']:.6f}", "rounds": sc["rounds"],
        "temperature_effective": "|".join(temps), "model_served": "|".join(served), "dry_run": int(tr["dry_run"]),
    }


def write_json_atomic(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def append_csv(path: str, row: Dict[str, Any]) -> None:
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


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
# Grid runner
# --------------------------------------------------------------------------


def run_grid(argv: Optional[Sequence[str]] = None, fake_policy=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", required=True, help="comma list; 'openrouter:<slug>' for OpenRouter")
    p.add_argument("--configs", default="all", help="comma list of coordination specs (presets joined by '+'), or 'all' (the six presets)")
    p.add_argument("--tasks", default="pilot", help="'pilot', 'all', or comma list of catalog names")
    p.add_argument("--instances", type=int, default=0,
                   help="K > 0: run full-run instances 0..K-1 of each template (instances4); 0: catalog task (pilot)")
    p.add_argument("--agents", type=int, default=2)
    p.add_argument("--seeds", default="0,1", help="comma list or range like 0-4")
    p.add_argument("--aware", choices=("off", "on", "both"), default="off", help="concurrency-aware one-sentence prompt")
    p.add_argument("--out", required=True)
    p.add_argument("--max-usd", type=float, default=None)
    p.add_argument("--extra-spend-logs", default="",
                   help="comma list of other spend.jsonl files that count toward --max-usd (one cap across output dirs)")
    p.add_argument("--turn-cap", type=int, default=DEFAULT_TURN_CAP)
    p.add_argument("--max-tokens", type=int, default=int(os.environ.get("IBENCH_MAX_TOKENS", DEFAULT_MAX_TOKENS)))
    p.add_argument("--temperature", type=float, default=TEMPERATURE)
    p.add_argument("--gap", type=int, default=2, help="scheduler read_write_gap (think-time rounds)")
    p.add_argument("--jitter", type=int, default=0, help="scheduler start_jitter")
    p.add_argument("--stall-rounds", type=int, default=6)
    p.add_argument("--max-rounds", type=int, default=2000)
    p.add_argument("--no-cache", action="store_true", help="disable Anthropic cache_control breakpoints")
    p.add_argument("--prices", default=DEFAULT_PRICES)
    p.add_argument("--allow-unconfirmed-prices", action="store_true", help="real run even if prices.json entries are placeholders")
    p.add_argument("--dry-run", action="store_true", help="deterministic fake provider, no network; output under OUT/dry_run")
    p.add_argument("--limit", type=int, default=0, help="run at most this many new episodes (0 = all)")
    p.add_argument("--max-consecutive-failures", type=int, default=3)
    p.add_argument("--prior-input-tokens", type=int, default=4000,
                   help="input tokens per completion assumed by the cost estimate before a model has a finished episode")
    args = p.parse_args(argv)

    models = parse_list(args.models)
    configs = resolve_configs(args.configs)
    tasks = resolve_tasks(args.tasks)
    seeds = resolve_seeds(args.seeds)
    awares = {"off": [False], "on": [True], "both": [False, True]}[args.aware]
    out = os.path.join(args.out, "dry_run") if args.dry_run else args.out
    tdir = os.path.join(out, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    csv_path = os.path.join(out, "results.csv")
    header = csv_header(csv_path)
    if header is not None and header != CSV_FIELDS:
        print(f"Refusing to append: {csv_path} has a different header (older run4 version?). "
              f"Use a new --out directory.", file=sys.stderr)
        return 1

    prices = PriceTable.load(args.prices) if os.path.exists(args.prices) else PriceTable({})
    if not args.dry_run and not args.allow_unconfirmed_prices:
        problems = prices.problems(models)
        if problems:
            print("Refusing a real run: prices are not confirmed:\n  " + "\n  ".join(problems), file=sys.stderr)
            print(f"Edit {args.prices}: check each number, then set \"confirmed\": true.", file=sys.stderr)
            return 1
    own_spend = os.path.abspath(os.path.join(out, "spend.jsonl"))
    extra_logs = [p for p in parse_list(args.extra_spend_logs) if os.path.abspath(p) != own_spend]
    extra = sum(SpendTracker(p).total for p in extra_logs)
    cap = None if args.max_usd is None else args.max_usd - extra
    if extra_logs:
        print(f"spend in other logs counted toward the cap: ${extra:.4f} ({len(extra_logs)} files); "
              f"cap left for this directory: ${cap:.4f}" if cap is not None else f"spend in other logs: ${extra:.4f}")
    spend = SpendTracker(own_spend, cap)

    grid = build_grid(models, configs, tasks, seeds, args.agents, awares, args.instances)
    schedule_kw = {"read_write_gap": args.gap, "start_jitter": args.jitter, "stall_rounds": args.stall_rounds, "max_rounds": args.max_rounds}
    print(f"grid: {len(grid)} episodes = {len(models)} models x {len(configs)} configs x {len(awares)} prompts x "
          f"{len(tasks)} tasks x {max(args.instances, 1)} instances x {len(seeds)} seeds (n={args.agents}); out={out}")
    print(f"spend so far: ${spend.total:.4f}" + (f" of cap ${cap:.2f}" if cap is not None else ""))

    # Resume: restore CSV rows for transcripts written just before a crash; gather per-model cost history.
    have_rows = csv_ids(csv_path)
    observed: Dict[str, List[float]] = {}
    todo = []
    for cell in grid:
        path = os.path.join(tdir, cell["id"] + ".json")
        if os.path.exists(path):
            with open(path) as f:
                tr = json.load(f)
            observed.setdefault(cell["model"], []).append(float(tr["totals"]["cost_usd"]))
            if cell["id"] not in have_rows:
                append_csv(csv_path, csv_row(tr))
        else:
            todo.append(cell)
    print(f"done already: {len(grid) - len(todo)}; to run: {len(todo)}")

    provs: Dict[str, Tuple[Any, Any]] = {}
    ran = failures = consecutive = 0
    exit_code = 0
    for k, cell in enumerate(todo, 1):
        if args.limit and ran >= args.limit:
            break
        model = cell["model"]
        hist = observed.get(model)
        estimate = 1.5 * max(hist) if hist else prices.episode_bound(model, args.agents, args.turn_cap, args.max_tokens, args.prior_input_tokens)
        if cap is not None and spend.total + estimate > cap:
            print(f"COST CAP: stopping before {cell['id']}: spend ${spend.total:.4f} + estimate ${estimate:.4f} "
                  f"> cap ${cap:.2f}. {len(todo) - k + 1} episodes not run.")
            exit_code = 2
            break
        if model not in provs:
            provs[model] = make_provider(model, dry_run=args.dry_run, fake_policy=fake_policy)
        provider, probe = provs[model]
        try:
            tr = run_one(cell, provider, probe, schedule_kw, turn_cap=args.turn_cap, max_tokens=args.max_tokens,
                         temperature=args.temperature, prices=prices, spend=spend, dry_run=args.dry_run,
                         prompt_caching=not args.no_cache)
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
        write_json_atomic(os.path.join(tdir, cell["id"] + ".json"), tr)
        append_csv(csv_path, csv_row(tr))
        observed.setdefault(model, []).append(tr["totals"]["cost_usd"])
        sc = tr["score"]
        print(f"[{k}/{len(todo)}] {cell['id']}: non_serializable={int(sc['non_serializable'])} "
              f"label={sc['primary_label'] or '-'} inv={int(sc['invariant_violation'])} "
              f"committed={len(sc['committed_agents'])} completions={tr['totals']['completions']} "
              f"cost=${tr['totals']['cost_usd']:.4f} spend=${spend.total:.4f}")
    if failures and exit_code == 0:
        exit_code = 3
    print(f"finished: ran {ran}, failed {failures}; spend so far ${spend.total:.4f}"
          + (f" of cap ${cap:.2f}" if cap is not None else ""))
    return exit_code


if __name__ == "__main__":
    sys.exit(run_grid())
