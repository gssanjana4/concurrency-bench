"""Study 3 planner: the registered grid, its cost estimate and the spend caps (src6).

    python3 plan6.py --plan plan_study3.json          # writes plan_study3.json and plan_study3.txt
    python3 plan6.py --blocks plan_study3.json        # the runner's block list (tab-separated, one block per line)

Grid (registration PREREGISTRATION_STUDY3.md, "Study design"): three confirmatory models (Qwen3.6-27B on OpenRouter,
sync; Claude Haiku 4.5 and Claude Sonnet 5 on Anthropic Message Batches), n = 2, aware off, the seven conditions of
``design6.CONDITIONS``, the eight families of ``instances6.CONTENDED`` with their controls, 8 instances, one schedule
(index 0) per start mode: 7 x 8 x 8 x 2 = 896 episodes per model, 2,688 in all. One block per model, priority 1. No
probes, no descriptive models.

Cost model. An episode's estimate is the **observed Study 2 mean cost** of the same model, the matching Study 2
config (``locks_s2text`` and ``locks`` -> Study 2 ``locks``; ``all_available`` -> ``all_available``), the matching
family (``transfer_same_amount`` -> ``transfer_shared_source``) and arm (``study2_costs.json``, built from the Study 2
results files by ``tools/make_study2_costs.py``; Study 2 paid the same paths and prices), plus the input cost of the
longer Study 3 tool text and responses: (``json.dumps(tool_schemas(config))`` minus the Study 2 menu of the matching
config, ``study2_lock_schemas.json``) / 3.5 characters per token + ``RESPONSE_EXTRA_TOKENS`` for the reported waits and
locked reads, times the Study 2 mean completions of the cell, times the uncached input price on the path (batch 0.5
for the Claude models), with no cache discount. A staggered episode is priced at ``STAGGER_FACTOR`` x its together
estimate (a late agent may make more calls after a wait). The planner multiplies by ``SAFETY`` (1.15) and checks
that every provider stays at least ``MARGIN`` (10 %) below its cap and the total below the total cap.

Caps (USD, set before any Study 3 call): Anthropic ``CAPS['anthropic']``, OpenRouter ``CAPS['openrouter']``, total
``TOTAL_CAP``; the Study 3 budget the author approved is $50, so at least $5 stays in reserve. Each model's block has
a sub-cap of ``SUBCAP_FACTOR`` x its estimate (Haiku runs before Sonnet in the Anthropic lane, so a Haiku overrun
cannot take Sonnet's share).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import instances6 as I
from design6 import CONDITIONS, call_cap, condition_name
from model_agent6 import provider_family

HERE = os.path.dirname(os.path.abspath(__file__))
COSTS_FILE = os.path.join(HERE, "study2_costs.json")
S2_SCHEMAS_FILE = os.path.join(HERE, "study2_lock_schemas.json")
PRICES_FILE = os.path.join(HERE, "prices.json")

QWEN = "openrouter:qwen/qwen3.6-27b-20260422"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"
MODELS: Tuple[str, ...] = (QWEN, HAIKU, SONNET)
LANE_ORDER = {"anthropic": (HAIKU, SONNET), "openrouter": (QWEN,)}
INSTANCES = 8
SCHEDULES = 1
N_AGENTS = 2
PRICE_FACTOR = {"anthropic": 0.5, "openrouter": 1.0}  # Anthropic Message Batches discount; Qwen sync
CHARS_PER_TOKEN = 3.5
RESPONSE_EXTRA_TOKENS = 150  # per completion under the Study 3 lock text: reported waits and locked reads, generous
STAGGER_FACTOR = 1.10
SAFETY = 1.15
MARGIN = 0.10
CAPS: Dict[str, float] = {"anthropic": 29.5, "openrouter": 15.5}
TOTAL_CAP = 45.0
BUDGET_APPROVED = 50.0
SUBCAP_FACTOR = 1.6
S2_CONFIG = {"none": "none", "cas_available": "cas_available", "locks_s2text": "locks", "locks": "locks",
             "all_available": "all_available"}
S2_FAMILY = {"transfer_same_amount": "transfer_shared_source"}


def load_costs(path: str = COSTS_FILE) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)["rows"]


def _prices() -> Dict[str, Any]:
    with open(PRICES_FILE) as f:
        return json.load(f)["models"]


def input_price_per_token(model: str) -> float:
    """Uncached input USD per token on the model's Study 3 path (batch discount for the Claude models)."""
    table = _prices()
    key = next(k for k in sorted(table, key=len, reverse=True) if model == k or model.startswith(k + "-")
               or model.startswith(k))
    return float(table[key]["input"]) / 1e6 * PRICE_FACTOR[provider_family(model)]


def extra_menu_tokens(config: str) -> float:
    """Tokens the Study 3 tool menu of ``config`` adds over the Study 2 menu of its matching config."""
    from world6 import CoordinationConfig, tool_schemas  # noqa: PLC0415
    with open(S2_SCHEMAS_FILE) as f:
        s2 = json.load(f)["schemas"]
    new = len(json.dumps(tool_schemas(CoordinationConfig.from_names(config))))
    old = len(json.dumps(s2[S2_CONFIG[config]]))
    return max(0.0, (new - old) / CHARS_PER_TOKEN)


def episode_cost(costs: Dict[str, Any], model: str, config: str, task: str, start: str = "together") -> float:
    """Estimated USD of one Study 3 episode (module docstring)."""
    fam = I.family_of(task)
    arm = "control" if task.endswith(I.CONTROL_SUFFIX) else "contended"
    row = costs[f"{model}|{S2_CONFIG[config]}|{S2_FAMILY.get(fam, fam)}|{arm}"]
    extra = extra_menu_tokens(config) + (RESPONSE_EXTRA_TOKENS if config in ("locks", "all_available") else 0.0)
    est = float(row["mean_usd"]) + float(row["mean_completions"]) * extra * input_price_per_token(model)
    return est * (STAGGER_FACTOR if start == "staggered" else 1.0)


def block_estimate(costs: Dict[str, Any], model: str) -> Tuple[float, int]:
    total, n = 0.0, 0
    for config, start in CONDITIONS:
        for fam in I.CONTENDED:
            for task in (fam, fam + I.CONTROL_SUFFIX):
                total += INSTANCES * SCHEDULES * episode_cost(costs, model, config, task, start)
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
        blocks.append({"priority": 1, "mode": "episodes", "model": model, "provider_family": fam, "n": N_AGENTS,
                       "conditions": [condition_name(c, s) for c, s in CONDITIONS], "families": list(I.CONTENDED),
                       "instances": INSTANCES, "schedules": SCHEDULES, "aware": [False], "episodes": n,
                       "est_usd": round(est, 2), "model_cap": round(SUBCAP_FACTOR * est, 2)})
    headroom = {f: round(1 - SAFETY * v / CAPS[f], 3) for f, v in by_family.items()}
    total = sum(by_family.values())
    problems = [f"{f}: {SAFETY} x estimate ${SAFETY * v:.2f} leaves {headroom[f]:.1%} of the ${CAPS[f]:.2f} cap (< {MARGIN:.0%})"
                for f, v in by_family.items() if headroom[f] < MARGIN]
    if SAFETY * total > TOTAL_CAP * (1 - MARGIN):
        problems.append(f"total: {SAFETY} x ${total:.2f} above {1 - MARGIN:.0%} of the ${TOTAL_CAP} total cap")
    if sum(CAPS.values()) > TOTAL_CAP + 1e-9 or TOTAL_CAP > BUDGET_APPROVED - 5:
        problems.append("caps: the provider caps must sum to at most the total cap, and the total cap must leave $5 of "
                        "the approved budget in reserve")
    for b in blocks:  # a sub-cap never above its lane cap
        b["model_cap"] = min(b["model_cap"], CAPS[b["provider_family"]])
    return {"study": 3, "blocks": blocks, "caps": dict(CAPS), "total_cap": TOTAL_CAP, "budget_approved": BUDGET_APPROVED,
            "safety": SAFETY, "margin": MARGIN, "estimate_by_family": {k: round(v, 2) for k, v in by_family.items()},
            "estimate_total": round(total, 2), "headroom_by_family": headroom,
            "cost_model": {"source": "study2_costs.json", "chars_per_token": CHARS_PER_TOKEN,
                           "response_extra_tokens": RESPONSE_EXTRA_TOKENS, "stagger_factor": STAGGER_FACTOR,
                           "extra_menu_tokens": {c: round(extra_menu_tokens(c), 1) for c in S2_CONFIG},
                           "price_factor": PRICE_FACTOR},
            "call_caps": {c: call_cap(N_AGENTS, c) for c in S2_CONFIG}, "problems": problems}


def render(plan: Dict[str, Any]) -> str:
    L = ["Study 3 plan (src6/plan6.py)", "",
         f"{'model':40s} {'episodes':>8s} {'est $':>8s} {'sub-cap $':>9s}"]
    for b in plan["blocks"]:
        L.append(f"{b['model']:40s} {b['episodes']:8d} {b['est_usd']:8.2f} {b['model_cap']:9.2f}")
    L += ["", "FINAL COST TABLE", f"{'provider':12s} {'estimate':>9s} {'x' + str(plan['safety']):>9s} {'cap':>7s} {'headroom':>9s}"]
    for f, v in plan["estimate_by_family"].items():
        L.append(f"{f:12s} {v:9.2f} {v * plan['safety']:9.2f} {plan['caps'][f]:7.2f} {plan['headroom_by_family'][f]:9.1%}")
    t = plan["estimate_total"]
    L.append(f"{'total':12s} {t:9.2f} {t * plan['safety']:9.2f} {plan['total_cap']:7.2f} "
             f"{1 - plan['safety'] * t / plan['total_cap']:9.1%}")
    L += ["", f"approved budget ${plan['budget_approved']:.2f}; reserve above the total cap "
              f"${plan['budget_approved'] - plan['total_cap']:.2f}",
          f"extra menu tokens per completion: {plan['cost_model']['extra_menu_tokens']}",
          f"problems: {plan['problems'] or 'none'}", ""]
    return "\n".join(L)


def blocks_lines(plan: Dict[str, Any]) -> List[str]:
    """prio, provider, model, n, conditions, tasks, instances, seeds, aware, model cap, mode (run_conc_study3.sh)."""
    out = []
    order = [m for lane in ("anthropic", "openrouter") for m in LANE_ORDER[lane]]
    for b in sorted(plan["blocks"], key=lambda b: (b["priority"], order.index(b["model"]))):
        seeds = ",".join(str(s) for s in range(int(b["schedules"])))
        out.append("\t".join([str(b["priority"]), b["provider_family"], b["model"], str(b["n"]), ",".join(b["conditions"]),
                              "families:" + ",".join(b["families"]), str(b["instances"]), seeds, "off",
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
