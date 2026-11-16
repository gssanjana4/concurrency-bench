"""Study 4, the registered Fable stage rule (PREREGISTRATION_STUDY4.md, Starting and stopping rules).

Claude Fable 5 runs in two stages: stage 1 is ``locks_s2text`` for all 128 clusters; stage 2 (the other three configs)
runs only if at least ``MIN_FAILED`` (5) of those 128 episodes failed (``fs_nonserializable``). Below that the model is
at the floor, and stage 2 would buy tests that cannot show a drop. The rule reads only the stage-1 transcripts and only
that count; run_conc_study4.sh calls it and nobody reads the episodes.

    python3 src7/floor_gate7.py --out results7/study4/n2-anthropic --model claude-fable-5 --instances 16 \
        --record results7/study4/floor_gate.json

Exit 0: above the floor (stage 2 runs). Exit 10: at the floor (stage 2 is not run). Exit 11: stage 1 is incomplete
(fewer than 128 stage-1 episodes, for example after a cap stop; stage 2 is not run). The decision is appended to
``--record``.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict

import instances7 as I

STAGE1_CONFIG = "locks_s2text"
MIN_FAILED = 5


def count(out: str, model: str, instances: int) -> Dict[str, Any]:
    eps: Dict[str, int] = {}
    for path in sorted(glob.glob(os.path.join(out, "transcripts", "*.json"))):
        with open(path) as f:
            tr = json.load(f)
        t = tr.get("task") or {}
        if (tr.get("model") != model or tr.get("config") != STAGE1_CONFIG or tr.get("study") not in (4, "4")
                or str(t.get("factory", "")).endswith("_ctrl") or int(t.get("instance", -1)) >= instances):
            continue
        key = f"{t.get('factory')}|{t.get('instance')}"
        eps.setdefault(key, int(bool((tr.get("score") or {}).get("fs_nonserializable"))))  # first transcript only
    return {"episodes": len(eps), "expected": len(I.CONTENDED) * instances, "failed": sum(eps.values())}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True, help="the lane's output directory (with transcripts/)")
    p.add_argument("--model", required=True)
    p.add_argument("--instances", type=int, required=True)
    p.add_argument("--record", required=True)
    a = p.parse_args(argv)
    c = count(a.out, a.model, a.instances)
    if c["episodes"] < c["expected"]:
        decision, rc = "stage1_incomplete", 11
    elif c["failed"] < MIN_FAILED:
        decision, rc = "floor", 10
    else:
        decision, rc = "above_floor", 0
    rec = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": a.model, "stage1_config": STAGE1_CONFIG,
           "min_failed": MIN_FAILED, **c, "decision": decision}
    with open(a.record, "a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    print(f"floor gate: {a.model} {STAGE1_CONFIG}: {c['failed']} failed of {c['episodes']} (expected {c['expected']}) -> {decision}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
