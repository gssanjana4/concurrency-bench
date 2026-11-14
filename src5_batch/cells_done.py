"""Print "<done> <total>" for one model's cells in one phase (used by run_rest.sh's retry loop).

    python3 src5_batch/cells_done.py --model M --out results4/full/phase1 <run5 grid args>

A cell is done when its transcript exists (the same test run5.py uses to skip it on resume).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional, Sequence

import harness  # noqa: F401
import run5


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--out", required=True, help="the directory holding transcripts/ (add /dry_run yourself)")
    p.add_argument("--configs", required=True)
    p.add_argument("--aware", choices=("off", "on", "both"), required=True)
    p.add_argument("--tasks", required=True)
    p.add_argument("--instances", type=int, required=True)
    p.add_argument("--seeds", required=True)
    p.add_argument("--agents", type=int, required=True)
    p.add_argument("--probe", action="store_true")
    a = p.parse_args(argv)
    awares = {"off": [False], "on": [True], "both": [False, True]}[a.aware]
    grid = run5.build_grid([a.model], run5.resolve_configs(a.configs), run5.resolve_tasks(a.tasks),
                           run5.resolve_seeds(a.seeds), a.agents, awares, a.instances, probe=a.probe)
    tdir = os.path.join(a.out, "transcripts")
    done = sum(1 for c in grid if os.path.exists(os.path.join(tdir, c["id"] + ".json")))
    print(done, len(grid))
    return 0


if __name__ == "__main__":
    sys.exit(main())
