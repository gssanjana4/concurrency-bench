"""Study 4 planner: the registered grid, its cost estimate and the spend caps (src7).

    python3 plan7.py --plan plan_study4.json          # writes plan_study4.json and plan_study4.txt
    python3 plan7.py --blocks plan_study4.json        # the runner's block list (tab-separated, one block per line)

Grid (registration PREREGISTRATION_STUDY4.md, "Study design"): four models (Qwen3.6-27B on OpenRouter, sync; Claude
Haiku 4.5, Claude Sonnet 5 and Claude Fable 5 on Anthropic Message Batches), n = 2, aware off, the four lock
configurations of ``design7.CONDITIONS`` (together start), the eight contended families of ``instances7.CONTENDED``
without controls, 16 instances, one schedule (index 0): 4 x 8 x 16 = 512 episodes per model, 2,048 in all. One block
per model, priority 1.

Cost model. An episode's estimate is the **observed Study 3 mean cost** of the same model, family and lock config
(``study3_costs.json``, contended, together start; ``locks_instr`` and ``locks_signals`` take the larger of the
``locks_s2text`` and ``locks`` means of the family). Claude Fable 5 did not run in Study 3: its estimate is the Claude
Sonnet 5 estimate times ``FABLE_FACTOR`` (7.0: its list price is 5 x Sonnet's, and in Study 2 its observed cost per
lock episode was 6.7 x Sonnet's). The planner multiplies by ``SAFETY`` (1.15) and checks that every provider stays at
least ``MARGIN`` (8 %) below its cap and the total below the total cap.

Caps (USD, set before any Study 4 call; approved by the author on 2026-11-15): Anthropic ``CAPS['anthropic']`` (paid
from the API credit already on the account), OpenRouter ``CAPS['openrouter']`` (the balance already on the key),
total ``TOTAL_CAP``. Each model's block has a sub-cap of ``SUBCAP_FACTOR`` x its estimate, never above its lane cap.
Lane order: Haiku, Sonnet, then Fable in the Anthropic lane, so a Fable overrun cannot take the smaller models' share.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import instances7 as I
from design7 import CONDITIONS, call_cap, condition_name
from model_agent7 import provider_family

HERE = os.path.dirname(os.path.abspath(__file__))
COSTS_FILE = os.path.join(HERE, "study3_costs.json")

QWEN = "openrouter:qwen/qwen3.6-27b-20260422"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"
FABLE = "claude-fable-5"
MODELS: Tuple[str, ...] = (QWEN, HAIKU, SONNET, FABLE)
LANE_ORDER = {"anthropic": (HAIKU, SONNET, FABLE), "openrouter": (QWEN,)}
INSTANCES = 16
SCHEDULES = 1
N_AGENTS = 2
FABLE_FACTOR = 7.0
SAFETY = 1.15
MARGIN = 0.08  # the OpenRouter lane is capped at the balance the author approved ($9.50 of $10.91)
CAPS: Dict[str, float] = {"anthropic": 100.0, "openrouter": 9.5}
TOTAL_CAP = 109.5
BUDGET_APPROVED = 109.5
SUBCAP_FACTOR = 1.6
BASE_CONFIG = {"locks_s2text": ("locks_s2text",), "locks": ("locks",), "locks_instr": ("locks_s2text", "locks"),
               "locks_signals": ("locks_s2text", "locks")}


def load_costs(path: str = COSTS_FILE) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)["rows"]


def episode_cost(costs: Dict[str, Any], model: str, config: str, task: str, start: str = "together") -> float:
    """Estimated USD of one Study 4 episode (module docstring)."""
    fam = I.family_of(task)
    base, factor = (SONNET, FABLE_FACTOR) if model == FABLE else (model, 1.0)
    # a config outside the Study 4 grid (harness tests only) is priced like the dearer Study 3 lock config
    return factor * max(float(costs[f"{base}|{c}|{fam}"]["mean_usd"]) for c in BASE_CONFIG.get(config, ("locks_s2text", "locks")))


FABLE_STAGE1 = ("locks_s2text",)  # registered Fable stage rule (src7/floor_gate7.py): stage 2 = the other configs


def block_estimate(costs: Dict[str, Any], model: str, configs: Optional[Tuple[str, ...]] = None) -> Tuple[float, int]:
    total, n = 0.0, 0
    for config, start in CONDITIONS:
        if configs is not None and config not in configs:
            continue
        for fam in I.CONTENDED:
            total += INSTANCES * SCHEDULES * episode_cost(costs, model, config, fam, start)
            n += INSTANCES * SCHEDULES
    return total, n


def make_plan() -> Dict[str, Any]:
    costs = load_costs()
    blocks = []
    by_family: Dict[str, float] = {}
    for model in MODELS:
        est, n = block_estimate(costs, model)
        fam = provider_family(model)
        by_family[fam] = by_family.get(fam, 0.0) + est
        stages = [(None, "episodes")]
        if model == FABLE:  # stage 1 (locks_s2text), then stage 2 only above the floor; one sub-cap over both
            stages = [(FABLE_STAGE1, "episodes"), (tuple(c for c, _ in CONDITIONS if c not in FABLE_STAGE1), "floor_gated")]
        for stage, (cfgs, mode) in enumerate(stages, 1):
            e, k = block_estimate(costs, model, cfgs)
            blocks.append({"priority": 1, "mode": mode, "stage": stage, "model": model, "provider_family": fam, "n": N_AGENTS,
                           "conditions": [condition_name(c, s) for c, s in CONDITIONS if cfgs is None or c in cfgs],
                           "families": list(I.CONTENDED), "instances": INSTANCES, "schedules": SCHEDULES, "aware": [False],
                           "episodes": k, "est_usd": round(e, 2), "model_cap": round(SUBCAP_FACTOR * est, 2)})
    headroom = {f: round(1 - SAFETY * v / CAPS[f], 3) for f, v in by_family.items()}
    total = sum(by_family.values())
    problems = [f"{f}: {SAFETY} x estimate ${SAFETY * v:.2f} leaves {headroom[f]:.1%} of the ${CAPS[f]:.2f} cap (< {MARGIN:.0%})"
                for f, v in by_family.items() if headroom[f] < MARGIN]
    if SAFETY * total > TOTAL_CAP * (1 - MARGIN):
        problems.append(f"total: {SAFETY} x ${total:.2f} above {1 - MARGIN:.0%} of the ${TOTAL_CAP} total cap")
    if sum(CAPS.values()) > TOTAL_CAP + 1e-9 or TOTAL_CAP > BUDGET_APPROVED:
        problems.append("caps: the provider caps must sum to at most the total cap, within the approved budget")
    for b in blocks:  # a sub-cap never above its lane cap
        b["model_cap"] = min(b["model_cap"], CAPS[b["provider_family"]])
    return {"study": 4, "blocks": blocks, "caps": dict(CAPS), "total_cap": TOTAL_CAP, "budget_approved": BUDGET_APPROVED,
            "safety": SAFETY, "margin": MARGIN, "estimate_by_family": {k: round(v, 2) for k, v in by_family.items()},
            "estimate_total": round(total, 2), "headroom_by_family": headroom,
            "cost_model": {"source": "study3_costs.json", "fable_factor": FABLE_FACTOR, "base_config": BASE_CONFIG},
            "call_caps": {c: call_cap(N_AGENTS, c) for c, _ in CONDITIONS}, "problems": problems}


def render(plan: Dict[str, Any]) -> str:
    L = ["Study 4 plan (src7/plan7.py)", "",
         f"{'model':40s} {'episodes':>8s} {'est $':>8s} {'sub-cap $':>9s}"]
    for b in plan["blocks"]:
        name = b["model"] + (f" stage {b['stage']}" if b["mode"] == "floor_gated" or (b["model"] == FABLE) else "")
        L.append(f"{name:40s} {b['episodes']:8d} {b['est_usd']:8.2f} {b['model_cap']:9.2f}")
    L += ["", "FINAL COST TABLE", f"{'provider':12s} {'estimate':>9s} {'x' + str(plan['safety']):>9s} {'cap':>7s} {'headroom':>9s}"]
    for f, v in plan["estimate_by_family"].items():
        L.append(f"{f:12s} {v:9.2f} {v * plan['safety']:9.2f} {plan['caps'][f]:7.2f} {plan['headroom_by_family'][f]:9.1%}")
    t = plan["estimate_total"]
    L.append(f"{'total':12s} {t:9.2f} {t * plan['safety']:9.2f} {plan['total_cap']:7.2f} "
             f"{1 - plan['safety'] * t / plan['total_cap']:9.1%}")
    L += ["", f"approved budget ${plan['budget_approved']:.2f}; reserve above the total cap "
              f"${plan['budget_approved'] - plan['total_cap']:.2f}",
          f"problems: {plan['problems'] or 'none'}", ""]
    return "\n".join(L)


def blocks_lines(plan: Dict[str, Any]) -> List[str]:
    """prio, provider, model, n, conditions, tasks, instances, seeds, aware, model cap, mode (run_conc_study4.sh); tasks are the contended templates only."""
    out = []
    order = [m for lane in ("anthropic", "openrouter") for m in LANE_ORDER[lane]]
    for b in sorted(plan["blocks"], key=lambda b: (b["priority"], order.index(b["model"]), b.get("stage", 1))):
        seeds = ",".join(str(s) for s in range(int(b["schedules"])))
        out.append("\t".join([str(b["priority"]), b["provider_family"], b["model"], str(b["n"]), ",".join(b["conditions"]),
                              ",".join(b["families"]), str(b["instances"]), seeds, "off",
                              f"{b['model_cap']:.2f}", b["mode"]]))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plan", help="write the plan JSON here (and the .txt next to it)")
    p.add_argument("--blocks", help="print the block list of this plan JSON")
    a = p.parse_args(argv)
    if a.blocks:
        with open(a.blocks) as f:
            print("\n".join(blocks_lines(json.load(f))))
        return 0
    plan = make_plan()
    txt = render(plan)
    print(txt)
    if a.plan:
        with open(a.plan, "w") as f:
            json.dump(plan, f, indent=1, sort_keys=True)
            f.write("\n")
        with open(os.path.splitext(a.plan)[0] + ".txt", "w") as f:
            f.write(txt)
    return 1 if plan["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
