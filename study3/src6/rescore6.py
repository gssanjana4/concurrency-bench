"""Sensitivity re-score of finished Study 2 episodes at a lower call cap (Round 3; reviews V1b N7, V2b note 10).

    python3 src6/rescore6.py --cap 24 --configs locks,all_available --out cap24.csv results5/study2/*/transcripts

``locks`` and ``all_available`` run at a cap of 28 calls, ``none`` and ``cas_available`` at 24 (design6.call_cap).
The pre-registered sensitivity analysis re-scores the lock configurations as if their cap had been 24, from the
logged ledgers only (nothing is re-run): every agent that made more than ``--cap`` calls is cut after its
``cap``-th call (it ends ``turn_cap``; its locks are released there) and the episode is re-scored with
``score6.score``. When another agent's later calls touched a record the cut agent changed, locked or held after its
cut, the lower-cap episode cannot be reconstructed and is reported ``indeterminate`` (counted, never imputed).
See ``score6.rescore_at_cap``.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from typing import Any, Dict, List, Mapping, Tuple

import instances6 as I
from records6 import AgentEnd, CallRecord, Ledger, WriteEffect, coerce_value, kind_of
from score6 import rescore_at_cap

FIELDS = ["episode_id", "model", "config", "aware_prompt", "task", "family", "category", "instance", "seed", "cap",
          "status", "truncated_agents", "reason", "outcome", "outcome_stratum", "primary_label", "n_fulfilled",
          "cap_endings", "lock_attempt_agents", "lock_effective_agents", "orig_outcome", "orig_cap_endings"]


def _value(rid: str, v: Any) -> Any:
    return coerce_value(kind_of(rid), v)


def ledger_from_transcript(tr: Mapping[str, Any]) -> Tuple[Ledger, Dict[str, Tuple[Any, int]]]:
    """The episode's ledger and final store, rebuilt from a transcript (values back in their stored types)."""
    led = Ledger()
    led.effects = [WriteEffect(**{**e, "old_value": _value(e["record_id"], e["old_value"]),
                                  "new_value": _value(e["record_id"], e["new_value"])}) for e in tr["ledger"]["effects"]]
    led.calls = [CallRecord(**c) for c in tr["ledger"]["calls"]]
    led.agent_ends = [AgentEnd(**{**e, "locks_held": tuple(e.get("locks_held") or ())}) for e in tr["ledger"]["agent_ends"]]
    led.flags = dict(tr["ledger"]["flags"])
    snap = {rid: (_value(rid, d["value"]), int(d["version"])) for rid, d in tr["final_store"].items()}
    return led, snap


def rescore_transcript(tr: Mapping[str, Any], cap: int = 24) -> Dict[str, Any]:
    task = I.build(tr["task"]["factory"], tr["task"]["instance"], tr["n_agents"])
    led, snap = ledger_from_transcript(tr)
    r = rescore_at_cap(task, led, snap, cap, config_name=tr["config"])
    sc = r.score
    row: Dict[str, Any] = {
        "episode_id": tr["episode_id"], "model": tr["model"], "config": tr["config"],
        "aware_prompt": int(bool(tr["concurrency_aware_prompt"])), "task": tr["task"]["factory"],
        "family": tr["task"]["family"], "category": tr["task"]["category"], "instance": tr["task"]["instance"],
        "seed": tr["seed"], "cap": cap, "status": r.status, "truncated_agents": "|".join(r.truncated_agents),
        "reason": r.reason, "orig_outcome": tr["score"]["outcome"], "orig_cap_endings": tr["score"]["cap_endings"],
    }
    if sc is not None:
        row.update({"outcome": sc.outcome, "outcome_stratum": sc.outcome_stratum, "primary_label": sc.primary_label or "",
                    "n_fulfilled": sum(a.fulfilled for a in sc.agents.values()), "cap_endings": sc.cap_endings,
                    "lock_attempt_agents": sum(a.lock for a in sc.agents.values()),
                    "lock_effective_agents": sum(bool(a.lock_effective) for a in sc.agents.values())})
    return row


def main(argv: List[str] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dirs", nargs="+", help="transcript directories")
    p.add_argument("--cap", type=int, default=24)
    p.add_argument("--configs", default="locks,all_available")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    configs = {c.strip() for c in a.configs.split(",") if c.strip()}
    rows = []
    for d in a.dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.json"))):
            with open(path) as f:
                tr = json.load(f)
            if tr.get("probe") or tr["config"] not in configs:
                continue
            rows.append(rescore_transcript(tr, a.cap))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    st: Dict[str, int] = {}
    for r in rows:
        st[r["status"]] = st.get(r["status"], 0) + 1
    print(f"rescored {len(rows)} episodes at cap {a.cap}: {st} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
