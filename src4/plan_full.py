"""Grid size, cost estimate and budget check for one phase of the full run (used by run_full.sh).

    python3 plan_full.py --phase 1 --models M1,M2 --configs all --aware both --instances 4 --seeds 0,1 \\
        --agents 2 --out results4/full/phase1 --max-usd 330 --spend-logs a/spend.jsonl,b/spend.jsonl

Estimate per episode = (pilot-measured cost per episode at n = 2) x (n_agents / 2)
x 1.1 ** log2(n_agents / 2). Pilot measurements: Haiku 4.5 $0.0098, Qwen3.6-27B
$0.0047 per episode at n = 2. Other models are set relative to Haiku
(:data:`HAIKU_MULTIPLIER`; their list prices are 2x, 10x and about 3x Haiku's).

Prints the phase grid size, the estimate for the whole phase and for the
episodes not yet done, total spend so far (sum of every spend log given) and
the budget left. Exit 0 if the budget left covers the estimate for the
remaining episodes, 5 if not (run_full.sh then stops before the phase).
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from typing import Dict, List, Optional, Sequence

import run4
from model_agent4 import SpendTracker, model_key_matches

PILOT_COST_N2: Dict[str, float] = {"claude-haiku-4-5": 0.0098, "openrouter:qwen/qwen3.6-27b": 0.0047}
HAIKU_MULTIPLIER: Dict[str, float] = {
    "claude-sonnet-5": 2.0,
    "claude-fable-5": 10.0,
    "openrouter:openai/gpt-5.5": 3.0,
    "openrouter:google/gemini-4-argon": 3.0,
}
LONGER_EPISODE_FACTOR = 1.1  # per doubling of n_agents beyond 2


def cost_n2(model: str) -> float:
    """Estimated cost of one n = 2 episode (exact id or dated prefix, as in prices.json)."""
    table = dict(PILOT_COST_N2)
    table.update({k: v * PILOT_COST_N2["claude-haiku-4-5"] for k, v in HAIKU_MULTIPLIER.items()})
    best = next((k for k in table if model_key_matches(k, model)), None)
    if best is None:
        raise SystemExit(f"no cost estimate for model {model!r}")
    return table[best]


def episode_estimate(model: str, n_agents: int) -> float:
    """Estimated cost of one episode with ``n_agents`` agents."""
    doublings = math.log2(n_agents / 2)
    return cost_n2(model) * (n_agents / 2) * LONGER_EPISODE_FACTOR ** doublings


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--phase", required=True)
    p.add_argument("--models", required=True)
    p.add_argument("--configs", required=True)
    p.add_argument("--aware", choices=("off", "on", "both"), required=True)
    p.add_argument("--tasks", default=",".join(run4.PILOT_TASKS))
    p.add_argument("--instances", type=int, required=True)
    p.add_argument("--seeds", required=True)
    p.add_argument("--agents", type=int, required=True)
    p.add_argument("--out", required=True, help="the phase's run4 --out (add /dry_run yourself for dry runs)")
    p.add_argument("--max-usd", type=float, required=True)
    p.add_argument("--spend-logs", default="", help="comma list of every spend.jsonl counting toward the total cap")
    a = p.parse_args(argv)

    models = run4.parse_list(a.models)
    configs = run4.resolve_configs(a.configs)
    tasks = run4.resolve_tasks(a.tasks)
    seeds = run4.resolve_seeds(a.seeds)
    awares = {"off": [False], "on": [True], "both": [False, True]}[a.aware]
    grid = run4.build_grid(models, configs, tasks, seeds, a.agents, awares, a.instances)
    tdir = os.path.join(a.out, "transcripts")
    done = {fn[:-5] for fn in os.listdir(tdir) if fn.endswith(".json")} if os.path.isdir(tdir) else set()
    per_model = len(grid) // max(len(models), 1)
    print(f"== phase {a.phase}: n_agents={a.agents}, {len(grid)} episodes = {len(models)} models x {len(configs)} configs "
          f"x {len(awares)} aware x {len(tasks)} templates x {a.instances} instances x {len(seeds)} seeds "
          f"({per_model} per model)")
    full = remaining = 0.0
    for m in models:
        cells = [c for c in grid if c["model"] == m]
        left = sum(1 for c in cells if c["id"] not in done)
        est = episode_estimate(m, a.agents)
        full += est * len(cells)
        remaining += est * left
        print(f"   {m:45s} ${est:.4f}/episode x {len(cells)} = ${est * len(cells):8.2f}   (not done: {left}, ${est * left:.2f})")
    logs: List[str] = run4.parse_list(a.spend_logs)
    spent = sum(SpendTracker(x).total for x in logs if os.path.exists(x))
    left_budget = a.max_usd - spent
    print(f"   phase estimate ${full:.2f}; not yet run ${remaining:.2f}; total spend so far ${spent:.4f}; "
          f"budget left ${left_budget:.2f} of ${a.max_usd:.2f}")
    if remaining > 0 and remaining > left_budget:
        print(f"!! budget left ${left_budget:.2f} < estimate ${remaining:.2f} for phase {a.phase}: SKIPPING phase {a.phase}")
        return 5
    return 0


if __name__ == "__main__":
    sys.exit(main())
