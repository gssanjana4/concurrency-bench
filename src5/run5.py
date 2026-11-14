"""Run a grid of model-agent episodes for Study 2 (sync path; the batch path is src5_batch/batch_driver.py).

    python3 run5.py --models claude-haiku-4-5-20251001 --configs none,cas_available,locks,all_available \\
        --tasks inventory_last_unit,inventory_last_unit_ctrl --instances 4 --seeds 0,1 --agents 2 --aware off \\
        --out results5/study2/n2 --dry-run

Same command-line names, outputs and exit codes as src4/run4.py, with Study 2 semantics:

* ``--tasks``: Study 2 templates (``instances5.TEMPLATES``: 7 contended + their ``*_ctrl`` controls), or
  ``families:a,b`` for contended + control of each family.
* ``--seeds``: *schedule indices*. The scheduler seed is ``schedule_seed(SCHEDULE_SPACE, family, instance,
  index, n)`` -- a different random environment per (instance, index); a contended task and its control share
  it (paired design). Episode id: ``<model>__<config>[+aware]__<template>@i<k>__n<n>__s<index>``.
* ``--turn-cap 0`` (default): the per-cell cap ``design5.call_cap(n, config)``.
* ``--probe`` (V2, review V2 §7): *first-reply probes* instead of episodes. Each agent makes one completion from its
  initial prompt and tool menu; nothing is executed (no world beyond the prompt). For a control template only the
  agents whose prompt differs from the contended one are probed (a0's prompt is identical in both arms, so a0 is
  probed once, under the contended template). Episode id suffix ``__probe``.
* Spend caps: ``--max-usd`` is the total cap; ``--family-cap anthropic=19`` (repeatable) the per-provider caps
  (defaults in budget5). Every log in ``--extra-spend-logs`` counts. Before each matched pair (a contended
  episode and its control, adjacent in the grid; Round 3) the estimate of both (per episode: 1.5 x the dearest
  finished episode of the model in the same configuration in this run, else the larger of 3 x plan5's
  Study-1-based estimate and 1.5 x the model's dearest episode) must fit in what is left for the model's
  provider family and in the total; an episode is written only together with its partner (``commit_episode``).

Outputs in ``--out`` (``--out``/dry_run with ``--dry-run``): transcripts/<episode_id>.json, results.csv,
spend.jsonl, failures.jsonl -- as run4. Exit codes: 0 done; 2 cost cap; 3 provider failures; 4 OpenRouter
credit/key limit; 1 usage errors.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import instances5 as I
import tasks5 as T
from budget5 import Budget, BudgetTracker, parse_family_caps, spend_by_family
from design5 import CONFIGS, SCHEDULE_DEFAULTS, SCHEDULE_SPACE, call_cap
from model_agent5 import (
    DEFAULT_MAX_TOKENS, TEMPERATURE, BudgetExceeded, ModelRunConfig, PriceTable, ProviderFailure, SpendTracker,
    make_provider, model_agent_spec, now_utc, provider_family,
)
from records5 import to_json_value
from scheduler5 import ScheduleConfig, run_episode, schedule_seed
from score5 import score_episode
from world5 import PRESET_NAMES, ALIASES, build_system_prompt, world_config

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRICES = os.path.join(HERE, "prices.json")
STUDY = 2

CSV_FIELDS = [
    "episode_id", "study", "model", "provider_family", "config", "aware_prompt", "task", "family", "category", "instance",
    "wording", "kind", "n_agents", "seed", "schedule_seed", "turn_cap",
    "outcome", "primary_label", "fs_nonserializable", "dsg_cycle", "dsg_g1c", "dsg_cycle_committed",
    "missing_leg", "compensated", "compensated_after_violation", "compensation_exposed", "guard_violation", "wrong_value",
    "out_of_intent_write", "stale_overwrite", "lost_update", "laundered_cas", "write_skew", "ever_violated",
    "violated_at_end", "n_stale_writes", "n_lost_updates", "cross_agent_edges", "conflict_observed", "stall",
    "n_committed", "n_rolled_back", "n_fulfilled", "n_abandoned", "n_abandon_eligible", "n_unnecessary_give_up",
    "n_conflict_agents", "n_lock_leak", "cap_endings",
    "first_mover", "reads_overlap", "interleaving",
    "choices", "end_reasons", "completions", "multi_tool_turns", "invalid_calls", "truncated_agents",
    "probe", "first_replies", "lock_attempt_agents", "lock_granted_agents", "lock_committed_agents", "lock_effective_agents", "lock_waits",
    "lock_waits_423", "fenced_stale_basis", "n_fenced_stale_basis", "first_protective", "protect_before_contention",
    "dsg_basis_cycle", "cross_agent_record_edges", "messages_delivered", "deadlock", "deadlock_rounds", "agent_errors",
    "outcome_stratum", "cap_truncated", "contention_exposed_agents", "contention_signals", "lock_after_contention",
    "n_fenced_unread_basis",
    "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens", "thinking_blocks",
    "max_tokens_exceeded", "cost_usd", "rounds", "temperature_effective", "model_served", "served_hosts", "dry_run",
]

CREDIT_LIMIT_MARKERS = ("OpenRouter HTTP 402", "insufficient credits", "openrouter_key_limit", "openrouter_credits")


def safe_name(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in s)


def episode_id(model: str, config: str, aware: bool, task: str, n: int, seed: int, instance: Optional[int] = None,
               probe: bool = False) -> str:
    tname = task if instance is None else f"{task}@i{instance}"
    parts = [safe_name(model), safe_name(config) + ("+aware" if aware else ""), tname, f"n{n}", f"s{seed}"]
    return "__".join(parts + (["probe"] if probe else []))


def parse_list(s: str) -> List[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def resolve_configs(spec: str) -> List[str]:
    names = list(CONFIGS) if spec in ("all", "study2") else parse_list(spec)
    for n in names:
        world_config(n)
    return names


def resolve_tasks(spec: str) -> List[str]:
    if spec in ("all", "study2"):
        return list(I.TEMPLATES)
    if spec.startswith("families:"):
        fams = parse_list(spec[len("families:"):])
        bad = [f for f in fams if f not in I.CONTENDED]
        if bad:
            raise SystemExit(f"unknown families {bad}; known: {list(I.CONTENDED)}")
        return [t for f in fams for t in (f, f + I.CONTROL_SUFFIX)]
    names = parse_list(spec)
    unknown = [n for n in names if n not in I.TEMPLATES]
    if unknown:
        raise SystemExit(f"unknown task(s) {unknown}; known: {list(I.TEMPLATES)}")
    return names


def resolve_seeds(spec: str) -> List[int]:
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in parse_list(spec)]


def pair_key(cell: Dict[str, Any]) -> str:
    """The matched pair a cell belongs to: same model, config, prompt, family, instance and schedule index; the
    contended template and its control differ only in the arm."""
    return "|".join(str(x) for x in (cell["model"], cell["config"], int(cell["aware"]), I.family_of(cell["task"]),
                                     cell["instance"], cell["n_agents"], cell["seed"], int(bool(cell.get("probe")))))


def build_grid(models, configs, tasks, seeds, n_agents, awares, k_instances: int = 1, probe: bool = False) -> List[Dict[str, Any]]:
    """Cells, visited schedule-major, then instance, family, config, prompt, model, arm (Round 3, review V2b
    finding 4 / task item 5): a contended cell is immediately followed by its matched control (``pair_key``), so
    the runners admit and submit the two together and a cap stop falls between pairs, removing whole replicates
    (later instances of the last schedule) evenly across families. Aware on and off of the same cell are adjacent,
    so ``--aware both`` interleaves them in every batch wave."""
    fams: Dict[str, List[str]] = {}
    for t in tasks:
        fams.setdefault(I.family_of(t), []).append(t)
    for f in fams:
        fams[f].sort(key=lambda t: t.endswith(I.CONTROL_SUFFIX))  # contended first, then its control
    grid = []
    for seed in seeds:
        for i in range(max(k_instances, 1)):
            for fam, fam_tasks in fams.items():
                for config in configs:
                    for aware in awares:
                        for model in models:
                            for task in fam_tasks:
                                cell = {"model": model, "config": config, "aware": aware, "task": task, "instance": i,
                                        "n_agents": n_agents, "seed": seed,
                                        "id": episode_id(model, config, aware, task, n_agents, seed, i, probe)}
                                if probe:
                                    cell["probe"] = True
                                cell["pair"] = pair_key(cell)
                                grid.append(cell)
    return grid


def pair_groups(cells: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Consecutive cells with the same ``pair_key`` (a contended cell and its control), in order."""
    out: List[List[Dict[str, Any]]] = []
    for c in cells:
        if out and out[-1][0].get("pair", pair_key(out[-1][0])) == c.get("pair", pair_key(c)):
            out[-1].append(c)
        else:
            out.append([c])
    return out


def unpaired(rows: Sequence[Dict[str, Any]]) -> List[str]:
    """Episode ids (results.csv rows or transcripts) of a contended episode without its finished matched control, or
    the reverse, among templates that have a control (the analysis drops them; a cap stop should leave none)."""
    groups: Dict[str, List[str]] = {}
    for r in rows:
        task = r["task"] if isinstance(r["task"], str) else r["task"]["factory"]
        cell = {"model": r["model"], "config": r["config"],
                "aware": int(r.get("aware_prompt", r.get("concurrency_aware_prompt", 0)) in (1, "1", True)),
                "task": task, "instance": int(r["instance"] if "instance" in r else r["task"]["instance"]),
                "n_agents": int(r["n_agents"]), "seed": int(r["seed"]), "probe": str(r.get("probe", 0)) in ("1", "True")}
        groups.setdefault(pair_key(cell), []).append(r["episode_id"])
    return sorted(e for ids in groups.values() if len(ids) == 1 for e in ids)


def probe_agents(template: str, instance: int, n: int, config: str, aware: bool) -> Tuple[str, ...]:
    """Agents probed for a template: all for a contended template; for a control, those whose system prompt differs
    from their prompt in the contended template (the tool menu is the same in both arms)."""
    task = I.build(template, instance, n)
    if not task.is_control:
        return task.agent_ids
    cont = I.build(I.family_of(template), instance, n)
    wc = world_config(config, concurrency_aware_prompt=aware)

    def prompt(t: T.Task, a: str) -> str:
        return build_system_prompt(a, tuple(x for x in t.agent_ids if x != a), t.intents[a].describe(), wc)

    return tuple(a for a in task.agent_ids if prompt(task, a) != prompt(cont, a))


def cell_task(cell: Dict[str, Any]) -> T.Task:
    task = I.build(cell["task"], cell["instance"], cell["n_agents"])
    if cell.get("probe"):
        task = task.restrict(probe_agents(cell["task"], cell["instance"], cell["n_agents"], cell["config"], cell["aware"]))
    return task


def cell_schedule(cell: Dict[str, Any], turn_cap: int, schedule_kw: Optional[Dict[str, Any]] = None) -> ScheduleConfig:
    kw = dict(SCHEDULE_DEFAULTS)
    kw.update({k: v for k, v in (schedule_kw or {}).items() if v is not None})
    cap = turn_cap or call_cap(cell["n_agents"], cell["config"])
    seed = schedule_seed(SCHEDULE_SPACE, I.family_of(cell["task"]), cell["instance"], cell["seed"], cell["n_agents"])
    return ScheduleConfig(seed=seed, turn_cap=cap, **kw)


def snapshot_json(store) -> Dict[str, Any]:
    return {rid: {"value": to_json_value(v), "version": ver} for rid, (v, ver) in store.snapshot().items()}


def ledger_json(ledger) -> Dict[str, Any]:
    return {"effects": [e.to_dict() for e in ledger.effects], "calls": [c.to_dict() for c in ledger.calls],
            "agent_ends": [e.to_dict() for e in ledger.agent_ends], "flags": to_json_value(ledger.flags)}


def run_one(cell: Dict[str, Any], provider: Any, probe: Any, schedule_kw: Dict[str, Any], *, turn_cap: int,
            max_tokens: int, temperature: Optional[float], prices: Optional[PriceTable], spend: Optional[SpendTracker],
            dry_run: bool, prompt_caching: bool = True) -> Dict[str, Any]:
    """Run one episode and return its transcript (not yet written)."""
    task = cell_task(cell)
    wc = world_config(cell["config"], concurrency_aware_prompt=cell["aware"])
    schedule = cell_schedule(cell, turn_cap, schedule_kw)
    rc = ModelRunConfig(model=cell["model"], provider=provider, world_config=wc, turn_cap=schedule.turn_cap,
                        max_tokens=max_tokens, temperature=temperature, prompt_caching=prompt_caching, prices=prices,
                        spend=spend, usage_probe=probe, episode_id=cell["id"], probe=bool(cell.get("probe")))
    records: Dict[str, Dict[str, Any]] = {}
    started, t0 = now_utc(), time.monotonic()
    episode = run_episode(task, model_agent_spec(rc, records), wc, schedule)
    score = score_episode(episode)
    agents = {a: records[a] for a in task.agent_ids if a in records}
    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    for rec in agents.values():
        for k in totals:
            totals[k] += rec["usage"][k]
    turns = [t for r in agents.values() for t in r["turns"]]
    first = next(iter(task.intents.values()))
    return {
        "episode_id": cell["id"], "study": STUDY, "dry_run": dry_run, "model": cell["model"], "probe": bool(cell.get("probe")),
        "provider": getattr(provider, "name", "?"), "provider_family": provider_family(cell["model"]),
        "config": wc.coordination.name, "concurrency_aware_prompt": cell["aware"],
        "task": {"factory": cell["task"], "name": task.name, "family": task.family, "category": task.category,
                 "kind": task.kind, "instance": cell["instance"], "wording": getattr(first, "wording", 0),
                 "fingerprint": I.fingerprint(task), "description": task.description,
                 "initial": to_json_value(dict(task.initial)), "intents": {a: i.describe() for a, i in task.intents.items()}},
        "n_agents": cell["n_agents"], "seed": cell["seed"],
        "schedule": schedule.as_dict(),
        "world": {"lock_expiry": wc.lock_expiry, "max_lease_calls": wc.max_lease_calls, "lock_wait_rounds": wc.lock_wait_rounds},
        "generation": {"max_tokens": max_tokens, "temperature_requested": temperature, "prompt_caching": rc.prompt_caching},
        "run_info": {"started_utc": started, "finished_utc": now_utc(), "wall_seconds": round(time.monotonic() - t0, 3)},
        "agents": agents, "ledger": ledger_json(episode.ledger), "final_store": snapshot_json(episode.store),
        "score": score.to_dict(),
        "totals": {
            "usage": totals, "cost_usd": sum(r["cost_usd"] for r in agents.values()),
            "completions": sum(r["completions"] for r in agents.values()),
            "multi_tool_turns": sum(r["multi_tool_turns"] for r in agents.values()),
            "invalid_calls": sum(len(r["invalid_calls"]) for r in agents.values()),
            "truncated_agents": [a for a, r in agents.items() if r["truncated"]],
            "reasoning_tokens": sum(int(t.get("reasoning_tokens") or 0) for t in turns),
            "thinking_blocks": sum(int(t.get("thinking_blocks") or 0) for t in turns),
            "max_tokens_exceeded": sum(1 for t in turns if t.get("max_tokens_exceeded")),
        },
    }


def csv_row(tr: Dict[str, Any]) -> Dict[str, Any]:
    sc, tot = tr["score"], tr["totals"]
    ag, fl = sc["agents"], sc["flags"]
    turns = [t for r in tr["agents"].values() for t in r["turns"]]
    temps = sorted({str(t.get("temperature_effective")) for t in turns})
    served = sorted({str(t.get("model_served")) for t in turns})
    hosts = sorted({str(t.get("served_host")) for t in turns})
    row = {
        "episode_id": tr["episode_id"], "study": tr.get("study", STUDY), "model": tr["model"],
        "provider_family": tr.get("provider_family", provider_family(tr["model"])), "config": tr["config"],
        "aware_prompt": int(tr["concurrency_aware_prompt"]), "task": tr["task"]["factory"], "family": tr["task"]["family"],
        "category": tr["task"]["category"], "instance": tr["task"]["instance"], "wording": tr["task"]["wording"],
        "kind": tr["task"]["kind"], "n_agents": tr["n_agents"], "seed": tr["seed"], "schedule_seed": tr["schedule"]["seed"],
        "turn_cap": tr["schedule"]["turn_cap"],
        "outcome": sc["outcome"], "primary_label": sc["primary_label"] or "", "fs_nonserializable": int(sc["fs_nonserializable"]),
        "dsg_cycle": int(sc["dsg_cycle"]), "dsg_g1c": int(sc["dsg_g1c"]), "dsg_cycle_committed": int(sc["dsg_cycle_committed"]),
        "n_stale_writes": len(sc["stale_overwrite_seqs"]), "n_lost_updates": len(sc["lost_update_seqs"]),
        "cross_agent_edges": sc["cross_agent_edges"], "conflict_observed": int(sc["conflict_observed"]), "stall": int(sc["stall"]),
        "n_committed": len(sc["committed_agents"]), "n_rolled_back": len(sc["rolled_back_agents"]),
        "n_fulfilled": sum(1 for s in ag.values() if s["fulfilled"]), "n_abandoned": sum(1 for s in ag.values() if s["abandoned"]),
        "n_abandon_eligible": sum(1 for s in ag.values() if s["end_reason"] != "running" and (s["valid_at_end"] or s["fulfilled"])),
        "n_unnecessary_give_up": sum(1 for s in ag.values() if s["unnecessary_give_up"]),
        "n_conflict_agents": sum(1 for s in ag.values() if s["conflicts_seen"] > 0),
        "n_lock_leak": sum(1 for s in ag.values() if s["lock_leak"]), "cap_endings": sc["cap_endings"],
        "first_mover": sc["interleaving"]["first_mover"] or "", "reads_overlap": int(sc["interleaving"]["reads_overlap"]),
        "interleaving": sc["interleaving"]["pattern"],
        "choices": ";".join(f"{a}:{'|'.join(s['choices'])}" for a, s in ag.items()),
        "probe": int(bool(tr.get("probe"))),
        "first_replies": ";".join(f"{a}:{r.get('first_reply')}" for a, r in tr["agents"].items()),
        "lock_attempt_agents": sum(1 for s in ag.values() if s["lock"]),
        "lock_granted_agents": sum(1 for s in ag.values() if s.get("lock_granted")),
        "lock_committed_agents": sum(1 for s in ag.values() if s.get("lock_effective") is not None),
        "lock_effective_agents": sum(1 for s in ag.values() if s.get("lock_effective")),
        "lock_waits": sum(int(s.get("lock_waits") or 0) for s in ag.values()),
        "lock_waits_423": sum(int(s.get("lock_waits_423") or 0) for s in ag.values()),
        "n_fenced_stale_basis": len(sc.get("fenced_stale_basis_seqs") or []),
        "first_protective": ";".join(f"{a}:{s.get('first_protective')}" for a, s in ag.items()),
        "protect_before_contention": ";".join(f"{a}:{s.get('protect_before_contention')}" for a, s in ag.items()),
        "dsg_basis_cycle": int(bool(sc.get("dsg_basis_cycle"))),
        "cross_agent_record_edges": sc.get("cross_agent_record_edges", 0), "messages_delivered": sc.get("messages_delivered", 0),
        "deadlock": int(bool(sc.get("deadlock"))), "deadlock_rounds": sc.get("deadlock_rounds", 0),
        "agent_errors": sc.get("agent_errors", 0),
        "outcome_stratum": sc.get("outcome_stratum") or sc["outcome"], "cap_truncated": int(bool(sc.get("cap_truncated"))),
        "contention_exposed_agents": sum(1 for s in ag.values() if s.get("contention_signals")),
        "contention_signals": ";".join(f"{a}:{s.get('contention_signals', 0)}" for a, s in ag.items()),
        "lock_after_contention": ";".join(f"{a}:{s.get('lock_after_contention')}" for a, s in ag.items()),
        "n_fenced_unread_basis": len(sc.get("fenced_unread_basis_seqs") or []),
        "end_reasons": ";".join(f"{a}:{s['end_reason']}" for a, s in ag.items()),
        "completions": tot["completions"], "multi_tool_turns": tot["multi_tool_turns"], "invalid_calls": tot["invalid_calls"],
        "truncated_agents": "|".join(tot["truncated_agents"]),
        "input_tokens": tot["usage"]["input"], "output_tokens": tot["usage"]["output"],
        "cache_read_tokens": tot["usage"]["cache_read"], "cache_write_tokens": tot["usage"]["cache_write"],
        "reasoning_tokens": tot.get("reasoning_tokens", 0), "thinking_blocks": tot.get("thinking_blocks", 0),
        "max_tokens_exceeded": tot.get("max_tokens_exceeded", 0),
        "cost_usd": f"{tot['cost_usd']:.6f}", "rounds": sc["rounds"],
        "temperature_effective": "|".join(temps), "model_served": "|".join(served), "served_hosts": "|".join(hosts),
        "dry_run": int(tr["dry_run"]),
    }
    for k in ("missing_leg", "compensated", "compensated_after_violation", "compensation_exposed", "guard_violation",
              "wrong_value", "out_of_intent_write", "stale_overwrite", "lost_update", "laundered_cas", "write_skew",
              "ever_violated", "violated_at_end", "fenced_stale_basis"):
        row[k] = int(fl.get(k, False))
    return row


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


def cost_key(cell: Dict[str, Any]) -> str:
    return f"{cell['model']}|{cell['config']}|{int(bool(cell.get('probe')))}"


def episode_estimate(observed: Dict[str, List[float]], cell: Dict[str, Any]) -> float:
    """Round 3: 1.5 x the dearest finished episode of the same model *and configuration* (lock configurations cost
    more than none / cas), else the larger of the prior and 1.5 x the model's dearest finished episode."""
    same = observed.get(cost_key(cell))
    if same:
        return 1.5 * max(same)
    hist = [v for k, vs in observed.items() if k.split("|", 1)[0] == cell["model"] for v in vs]
    return max(prior_estimate(cell), 1.5 * max(hist) if hist else 0.0)


def prior_estimate(cell: Dict[str, Any]) -> float:
    """3 x plan5's Study-1-based estimate (before any episode of the model has finished in this run)."""
    try:
        import plan5  # noqa: PLC0415
        if cell.get("probe"):
            return 3.0 * plan5.probe_estimate(plan5.load_costs(), cell["model"], cell["config"], "dec") * \
                len(probe_agents(cell["task"], cell["instance"], cell["n_agents"], cell["config"], cell["aware"]))
        return 3.0 * plan5.estimate(plan5.load_costs(), cell["model"], cell["n_agents"], cell["config"], cell["task"],
                                    cell["aware"], "dec")
    except Exception:  # noqa: BLE001 - unknown model (fake, new): no prior
        return 0.0


def add_grid_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--models", required=True)
    p.add_argument("--configs", default="study2")
    p.add_argument("--tasks", default="study2")
    p.add_argument("--instances", type=int, default=4)
    p.add_argument("--agents", type=int, default=2)
    p.add_argument("--seeds", default="0,1", help="schedule indices")
    p.add_argument("--aware", choices=("off", "on", "both"), default="off")
    p.add_argument("--out", required=True)
    p.add_argument("--max-usd", type=float, default=None, help="total cap over every spend log")
    p.add_argument("--family-cap", action="append", default=[], help="provider=USD (anthropic, openrouter, gemini)")
    p.add_argument("--model-cap", type=float, default=None, help="cap on this model's own spend over every log (one model only)")
    p.add_argument("--extra-spend-logs", default="")
    p.add_argument("--turn-cap", type=int, default=0, help="0 = design5.call_cap(n, config)")
    p.add_argument("--max-tokens", type=int, default=int(os.environ.get("IBENCH_MAX_TOKENS", DEFAULT_MAX_TOKENS)))
    p.add_argument("--temperature", type=float, default=TEMPERATURE)
    p.add_argument("--gap-min", type=int, default=None)
    p.add_argument("--gap-max", type=int, default=None)
    p.add_argument("--jitter", type=int, default=None)
    p.add_argument("--latency-p", type=float, default=None)
    p.add_argument("--latency-max", type=int, default=None)
    p.add_argument("--stall-rounds", type=int, default=None)
    p.add_argument("--max-rounds", type=int, default=None)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--prices", default=DEFAULT_PRICES)
    p.add_argument("--allow-unconfirmed-prices", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-consecutive-failures", type=int, default=3)
    p.add_argument("--prior-input-tokens", type=int, default=4000)
    p.add_argument("--probe", action="store_true", help="first-reply probes (one completion per agent, nothing executed)")


def schedule_kw_from(a: argparse.Namespace) -> Dict[str, Any]:
    return {"gap_min": a.gap_min, "gap_max": a.gap_max, "start_jitter": a.jitter, "latency_p": a.latency_p,
            "latency_max": a.latency_max, "stall_rounds": a.stall_rounds, "max_rounds": a.max_rounds}


HELD_DIR = "held_for_pair"


def commit_episode(out: str, tdir: str, csv_path: str, tr: Dict[str, Any], pair: Sequence[Dict[str, Any]]) -> List[str]:
    """Round 3 (task item 5): an episode is written to ``transcripts/`` and ``results.csv`` only together with its
    matched partner. It first goes to ``<out>/held_for_pair/``; once every cell of its pair (``pair_groups`` of the
    grid) is finished, the held transcripts are moved in, in grid order. A cap stop or a provider failure between the
    two arms therefore never leaves a contended episode without its control in the results (the held one is kept and
    completed by the next run). Returns the ids moved into ``transcripts/``."""
    held = os.path.join(out, HELD_DIR)
    os.makedirs(held, exist_ok=True)
    write_json_atomic(os.path.join(held, tr["episode_id"] + ".json"), tr)
    return finalize_pair(out, tdir, csv_path, pair)


def finalize_pair(out: str, tdir: str, csv_path: str, pair: Sequence[Dict[str, Any]]) -> List[str]:
    held = os.path.join(out, HELD_DIR)
    done = lambda c: os.path.exists(os.path.join(tdir, c["id"] + ".json"))  # noqa: E731
    is_held = lambda c: os.path.exists(os.path.join(held, c["id"] + ".json"))  # noqa: E731
    if not all(done(c) or is_held(c) for c in pair):
        return []
    moved = []
    have = csv_ids(csv_path)
    for c in pair:
        if is_held(c) and not done(c):
            src = os.path.join(held, c["id"] + ".json")
            with open(src) as f:
                tr = json.load(f)
            write_json_atomic(os.path.join(tdir, c["id"] + ".json"), tr)
            if c["id"] not in have:
                append_csv(csv_path, csv_row(tr))
            os.remove(src)
            moved.append(c["id"])
        elif is_held(c):
            os.remove(os.path.join(held, c["id"] + ".json"))
    return moved


def report_unpaired(out: str, tdir: str = "") -> List[str]:
    """After a stop: the finished episodes held back because their matched partner is not finished yet."""
    held = os.path.join(out, HELD_DIR)
    bad = sorted(f[:-5] for f in os.listdir(held) if f.endswith(".json")) if os.path.isdir(held) else []
    print(f"episodes held for their matched partner (not in results.csv; the next run completes the pair): {len(bad)}"
          + (f" e.g. {bad[:3]}" if bad else ""))
    return bad


def run_grid(argv: Optional[Sequence[str]] = None, fake_policy=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_grid_args(p)
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
        print(f"Refusing to append: {csv_path} has a different header. Use a new --out directory.", file=sys.stderr)
        return 1
    prices = PriceTable.load(args.prices) if os.path.exists(args.prices) else PriceTable({})
    if not args.dry_run and not args.allow_unconfirmed_prices:
        problems = prices.problems([m for m in models if not m.startswith("ollama:")])  # local models cost nothing
        if problems:
            print("Refusing a real run: prices are not confirmed:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
    own_spend = os.path.abspath(os.path.join(out, "spend.jsonl"))
    extra_logs = [x for x in parse_list(args.extra_spend_logs) if os.path.abspath(x) != own_spend]
    if args.model_cap is not None and len(models) != 1:
        print("--model-cap needs exactly one model", file=sys.stderr)
        return 1
    budget = Budget(args.max_usd, parse_family_caps(args.family_cap) if (args.family_cap or args.max_usd is not None) else {},
                    models[0] if args.model_cap is not None else None, args.model_cap)
    spend = BudgetTracker(own_spend, extra_logs, budget)
    grid = build_grid(models, configs, tasks, seeds, args.agents, awares, args.instances, probe=args.probe)
    schedule_kw = schedule_kw_from(args)
    print(f"grid: {len(grid)} episodes = {len(models)} models x {len(configs)} configs x {len(awares)} prompts x "
          f"{len(tasks)} templates x {args.instances} instances x {len(seeds)} schedules (n={args.agents}); out={out}")
    print(f"spend so far: {budget.describe(spend.spent())}")
    have_rows = csv_ids(csv_path)
    observed: Dict[str, List[float]] = {}
    todo = []
    pairs = {c["id"]: g for g in pair_groups(grid) for c in g}
    for cell in grid:
        path = os.path.join(tdir, cell["id"] + ".json")
        held = os.path.join(out, HELD_DIR, cell["id"] + ".json")
        if os.path.exists(path) or os.path.exists(held):
            with open(path if os.path.exists(path) else held) as f:
                tr = json.load(f)
            observed.setdefault(cost_key(cell), []).append(float(tr["totals"]["cost_usd"]))
            if os.path.exists(path) and cell["id"] not in have_rows:
                append_csv(csv_path, csv_row(tr))
        else:
            todo.append(cell)
    for g in pair_groups(grid):
        finalize_pair(out, tdir, csv_path, g)
    print(f"done already: {len(grid) - len(todo)}; to run: {len(todo)}")
    provs: Dict[str, Tuple[Any, Any]] = {}
    ran = failures = consecutive = 0
    exit_code = 0
    group_of = {c["id"]: g for g in pair_groups(todo) for c in g}
    for k, cell in enumerate(todo, 1):
        if args.limit and ran >= args.limit:
            break
        model = cell["model"]
        group = group_of[cell["id"]]
        if cell is group[0]:
            # Round 3 (task item 5): a pair starts only if the estimate of every member still to run fits, so a cap
            # stop never falls between a contended episode and its matched control
            estimate = sum(episode_estimate(observed, c) for c in group)
            left = budget.left(provider_family(model), spend.spent())
            if estimate > left:
                print(f"COST CAP: stopping before {cell['id']} (pair of {len(group)}): estimate ${estimate:.4f} > left "
                      f"${left:.4f} ({budget.describe(spend.spent())}). {len(todo) - k + 1} episodes not run.")
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
            print(f"COST CAP: {exc}; episode {cell['id']} aborted and not written.")
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
        commit_episode(out, tdir, csv_path, tr, pairs[cell["id"]])
        observed.setdefault(cost_key(cell), []).append(tr["totals"]["cost_usd"])
        sc = tr["score"]
        print(f"[{k}/{len(todo)}] {cell['id']}: outcome={sc['outcome']} label={sc['primary_label'] or '-'} "
              f"fs={int(sc['fs_nonserializable'])} dsg={int(sc['dsg_cycle'])} caps={sc['cap_endings']} "
              f"completions={tr['totals']['completions']} cost=${tr['totals']['cost_usd']:.4f}")
    if failures and exit_code == 0:
        exit_code = 3
    if exit_code:
        report_unpaired(out, tdir)
    print(f"finished: ran {ran}, failed {failures}; {budget.describe(spend.spent())}")
    return exit_code


if __name__ == "__main__":
    sys.exit(run_grid())
