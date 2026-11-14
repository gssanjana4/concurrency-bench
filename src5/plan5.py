"""Study 2 planner: cost estimates from Study 1's OBSERVED per-episode costs, the grid that fits the prepaid
credit (per provider), and the power of the main contrasts.

    python3 plan5.py --study1 ../results4/full --write-costs study1_costs.json   # refresh the cost table
    python3 plan5.py --plan plan_study2.json                                    # choose the grid, print costs

Cost model (per episode, USD):

    est(model, n, config, template, aware) = base x exec x cap_uplift x menu x control

* ``base``: mean ``cost_usd`` of Study 1 episodes of the same model, n, aware arm, the Study 1 config that
  matches (none, cas_available, locks; ``all_available`` = the dearer of Study 1 locks/messages) and the same
  template family (Study 1 results.csv, phases 1-3; n = 4 uses phase 2, which has 2 instances and no aware
  split per template -- the model's phase 2 mean for that config is used).
* ``exec``: execution-path price ratio Study 2 / Study 1 -- Haiku 0.5 (Study 1 sync, Study 2 Message
  Batches), Gemini 1.0 at the November batch price ($1/$5) and 2.0 from 2026-12-01 ($2/$10); others 1.0
  (Sonnet and Fable were batched in Study 1 too; Qwen and GPT stay sync on OpenRouter).
* ``cap_uplift``: Study 2's call cap is larger (design5.call_cap). An agent that ended at Study 1's 12-call cap
  is assumed to run to the new cap, and its cost to grow as (completions ratio)^1.5 (context grows with every
  turn): ``1 + p_cap x (((cap2 + 1) / 13) ** 1.5 - 1)``, with ``p_cap`` the share of that model's Study 1
  agents in the matching cell that ended at the cap.
* ``control`` = 1.0 (no discount assumed).
* *Round 3* (review V2b finding 3, task item 4): the Study 2 tool text is longer than Study 1's (fenced lock tools,
  the 150-round wait, the CAS text), so every completion carries extra input tokens. Instead of V2's flat
  ``menu`` = 1.10 for all_available only, each estimate adds ``completions x extra_tokens x input price``:
  ``extra_tokens`` = (characters of ``json.dumps(world5.tool_schemas(config))``, computed from the code, minus the
  Study 1 menu of the matching config, ``study1_menu_chars`` in study1_costs.json) / 3.5 characters per token;
  ``completions`` = Study 1 completions per agent of that model and config (``completions_per_agent``) x n x the
  completions cap uplift ``1 + p_cap x ((cap2 + 1) / 13 - 1)``; the price is the uncached input price on the Study 2
  path (``INPUT_USD_PER_MTOK``) x the model's Study 1 cache mix (``study1_input_cache_factor``: Sonnet 0.86, Fable
  0.53, 1.0 for the uncached models; the tool prefix is the most cacheable part of a request, so the average mix
  overstates its price). GPT-5.5 estimates also carry
  its Study 1 re-run waste (``RERUN_WASTE``, aborted sync episodes). Probes add one completion's extra tokens.

A further ``--safety`` factor (default 1.15) is applied when choosing the grid, and every provider family must keep
a ``--margin`` (default 10 %) below its cap after the safety factor. The runners enforce the real caps on actual
spend in any case (budget5).

V2 grid (review V2 §7, §9; adopted as given, not searched): the four full-grid models (Qwen, Haiku, Sonnet, Gemini)
keep 4 configs x 7 families x (contended + control) x 4 instances x 2 schedules, aware off; Gemini aware on only for
``locks`` and ``all_available``, in the same block as their aware-off cells (``--aware both``: interleaved in the
same batch waves, review V2 F9); GPT-5.5 96 episodes (3 families x 2 instances x 2 schedules); Fable 5 24 episodes
(3 families x 1 instance x 1 schedule; descriptive only). New priority-0 block per model: *first-reply probes*
(``run5 --probe``): one completion per agent for 4 configs x aware off/on x 7 families x K instances, the
contended prompts of a0 and a1 plus the control prompt of a1 (a0's control prompt is identical to its contended
one); K is fixed per model (``PROBE_K``; Round 3: GPT-5.5 cut from 4 to 2, review V2b finding 3: GPT is at the lock
ceiling in Study 1, first-reply lock 0.98-1.00); ``choose`` refuses a plan that does not keep every provider family
inside its cap and margin, and then cuts the descriptive-only models (GPT-5.5, Fable) first (``DESCRIPTIVE_CUTS``). Probe cost =
Study 1's mean cost of an agent's *first* completion for the matching model and config (``first_completion`` in
study1_costs.json, from the Study 1 spend logs) x exec ratio x menu factor.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import instances5 as I
from budget5 import DEFAULT_FAMILY_CAPS, DEFAULT_TOTAL_CAP, FAMILIES
from design5 import CONFIGS, call_cap
from model_agent5 import provider_family

HERE = os.path.dirname(os.path.abspath(__file__))
COSTS_PATH = os.path.join(HERE, "study1_costs.json")

MODELS: Tuple[str, ...] = (
    "openrouter:qwen/qwen3.6-27b-20260422",
    "claude-haiku-4-5-20251001",
    "openrouter:openai/gpt-5.5-20260423",
    "openrouter:google/gemini-4-argon-20261013",
    "claude-sonnet-5",
    "claude-fable-5",
)
SHORT = {"openrouter:qwen/qwen3.6-27b-20260422": "qwen", "claude-haiku-4-5-20251001": "haiku",
         "openrouter:openai/gpt-5.5-20260423": "gpt", "openrouter:google/gemini-4-argon-20261013": "gemini",
         "claude-sonnet-5": "sonnet", "claude-fable-5": "fable"}
BATCH_MODELS = ("claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-fable-5", "openrouter:google/gemini-4-argon-20261013")
EXEC_RATIO = {"claude-haiku-4-5-20251001": 0.5}
STUDY1_CONFIG = {"none": ["none"], "cas_available": ["cas_available"], "locks": ["locks"],
                 "all_available": ["locks", "cas_available"]}  # V2: all_available = cas + locks (no messages)
# Round 3 (task item 4): the tool text's extra input tokens, priced explicitly (module docstring)
CHARS_PER_TOKEN = 3.5
# uncached input USD per million tokens on the Study 2 execution path (November): prices.json input x 0.5 for the
# Anthropic batch models; prices.json for the OpenRouter sync models; Gemini 4 Argon batch_published input (Nov) from
# src5_batch/prices_batch.json (x gemini_ratio for December). Checked against the price files by tests5.
INPUT_USD_PER_MTOK = {
    "openrouter:qwen/qwen3.6-27b-20260422": 0.45,
    "claude-haiku-4-5-20251001": 0.5,
    "openrouter:openai/gpt-5.5-20260423": 2.5,
    "openrouter:google/gemini-4-argon-20261013": 1.0,
    "claude-sonnet-5": 1.0,
    "claude-fable-5": 5.0,
}
RERUN_WASTE = {"openrouter:openai/gpt-5.5-20260423": 1.04}  # Study 1: 3.4-4.1 % of GPT spend on aborted re-runs
# A model may spend at most this multiple of its planned blocks' cumulative estimate while running them (per-model
# sub-cap in the runner, counted over every log); extension
# blocks (priority 4) have no sub-cap, only the family and total caps.
MODEL_CAP_FACTOR = 1.3

# Families in priority order: which a smaller per-model grid keeps first.
FAMILY_PRIORITY = ("inventory_last_unit", "transfer_shared_source", "budget_write_skew", "seat_same",
                   "joint_account_write_skew", "inventory_still_valid", "ticket_same")
# V2 fixed design (review V2 §9): model -> (level name, families kept, instances, schedules)
V2_CORE: Dict[str, Tuple[str, int, int, int]] = {
    "openrouter:qwen/qwen3.6-27b-20260422": ("L7x4x2", 7, 4, 2),
    "claude-haiku-4-5-20251001": ("L7x4x2", 7, 4, 2),
    "openrouter:openai/gpt-5.5-20260423": ("L3x2x2", 3, 2, 2),
    "openrouter:google/gemini-4-argon-20261013": ("L7x4x2", 7, 4, 2),
    "claude-sonnet-5": ("L7x4x2", 7, 4, 2),
    "claude-fable-5": ("L3x1x1", 3, 1, 1),
}
GEMINI_AWARE_CONFIGS = ("locks", "all_available")
GEMINI_MODEL_ID = "openrouter:google/gemini-4-argon-20261013"  # aware on only here, interleaved with aware off
PROBE_LEVELS = (8, 6, 4, 3, 2, 1)
# Round 3: probe instances per model, fixed (V2's max-min allocation gave Qwen 6, Haiku 4, GPT 4, Gemini 8, Sonnet 4,
# Fable 1; GPT is cut to 2, task item 4). The confirmatory models' probes are not changed.
PROBE_K: Dict[str, int] = {
    "openrouter:qwen/qwen3.6-27b-20260422": 6,
    "claude-haiku-4-5-20251001": 4,
    "openrouter:openai/gpt-5.5-20260423": 2,
    "openrouter:google/gemini-4-argon-20261013": 8,
    "claude-sonnet-5": 4,
    "claude-fable-5": 1,
}
DESCRIPTIVE_MODELS = ("openrouter:openai/gpt-5.5-20260423", "claude-fable-5")
# If a family does not keep its margin, these cuts are applied in order (descriptive-only models first; the
# confirmatory cells of Qwen, Haiku and Sonnet are never cut by the planner): (model, "probe" K) or (model, core level)
DESCRIPTIVE_CUTS: Tuple[Tuple[str, str, Any], ...] = (
    ("openrouter:openai/gpt-5.5-20260423", "probe", 1),
    ("claude-fable-5", "probe", 0),
    ("claude-fable-5", "core", ("L2x1x1", 2, 1, 1)),
    ("openrouter:openai/gpt-5.5-20260423", "core", ("L3x2x1", 3, 2, 1)),
    ("openrouter:openai/gpt-5.5-20260423", "core", ("L3x1x1", 3, 1, 1)),
    ("claude-fable-5", "core", ("L1x1x1", 1, 1, 1)),
)
# Size levels (families kept, instances, schedules); a model gets the largest level its provider budget allows.
LEVELS: Tuple[Tuple[str, int, int, int], ...] = (
    ("L7x4x2", 7, 4, 2),
    ("L5x4x2", 5, 4, 2),
    ("L4x4x2", 4, 4, 2),
    ("L4x3x2", 4, 3, 2),
    ("L3x3x2", 3, 3, 2),
    ("L4x2x2", 4, 2, 2),
    ("L3x2x2", 3, 2, 2),
    ("L3x1x2", 3, 1, 2),
    ("L3x1x1", 3, 1, 1),
)


# --------------------------------------------------------------------------
# Study 1 observed costs
# --------------------------------------------------------------------------


def build_costs(study1_dir: str) -> Dict[str, Any]:
    cells: Dict[str, List[float]] = defaultdict(list)
    caps: Dict[str, List[float]] = defaultdict(list)
    for ph in ("phase1", "phase2", "phase3"):
        p = os.path.join(study1_dir, ph, "results.csv")
        if not os.path.exists(p):
            continue
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("dry_run") == "1":
                    continue
                n, cfg, aw, task = r["n_agents"], r["config"], r["aware_prompt"], r["task"]
                c = float(r["cost_usd"])
                ends = [e.split(":", 1)[1] for e in r["end_reasons"].split(";") if ":" in e]
                pc = sum(e == "turn_cap" for e in ends) / max(len(ends), 1)
                for key in (f"{r['model']}|{n}|{cfg}|{aw}|{task}", f"{r['model']}|{n}|{cfg}|*|*"):
                    cells[key].append(c)
                    caps[key].append(pc)
    return {"source": os.path.abspath(study1_dir),
            "cells": {k: {"mean": statistics.fmean(v), "n": len(v), "p_cap": statistics.fmean(caps[k])} for k, v in sorted(cells.items())},
            "first_completion": build_first_costs(study1_dir), **build_menu_stats(study1_dir)}


def build_menu_stats(study1_dir: str, src4_dir: Optional[str] = None) -> Dict[str, Any]:
    """Round 3: Study 1 completions per agent (n = 2, phase 1) per model and config, and the Study 1 tool-menu size
    per config (``json.dumps(world4.tool_schemas(...))``; src4 is imported read-only, no bytecode written)."""
    comp: Dict[str, List[float]] = defaultdict(list)
    p = os.path.join(study1_dir, "phase1", "results.csv")
    with open(p, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("dry_run") != "1" and r["n_agents"] == "2":
                comp[f"{r['model']}|{r['config']}"].append(int(r["completions"]) / 2)
    src4 = os.path.abspath(src4_dir or os.path.join(study1_dir, "..", "..", "src4"))
    import importlib  # noqa: PLC0415
    saved = {k: sys.modules.pop(k) for k in ("records", "world4") if k in sys.modules}
    dwb, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    sys.path.insert(0, src4)
    try:
        w4 = importlib.import_module("world4")
        menu = {c: len(json.dumps(w4.tool_schemas(w4.CoordinationConfig.from_names(c))))
                for c in ("none", "cas_available", "locks", "messages")}
    finally:
        sys.path.remove(src4)
        sys.dont_write_bytecode = dwb
        for k in ("records", "world4"):
            sys.modules.pop(k, None)
        sys.modules.update(saved)
    # cache mix of Study 1 input tokens per model (spend logs): the effective input price relative to the uncached
    # one, (input + 1.25 cache_write + 0.1 cache_read) / all input tokens (Anthropic cache prices; 1.0 elsewhere)
    tok: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ph in ("phase1", "phase2", "phase3"):
        sp = os.path.join(study1_dir, ph, "spend.jsonl")
        if not os.path.exists(sp):
            continue
        with open(sp) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                u = e.get("usage") or {}
                for k in ("input", "cache_read", "cache_write"):
                    tok[str(e.get("model"))][k] += int(u.get(k) or 0)
    mix = {}
    for m, t in sorted(tok.items()):
        allin = t["input"] + t["cache_read"] + t["cache_write"]
        if allin:
            mix[m] = round((t["input"] + 1.25 * t["cache_write"] + 0.1 * t["cache_read"]) / allin, 4) \
                if m.startswith("claude-") else 1.0
    return {"completions_per_agent": {k: round(statistics.fmean(v), 4) for k, v in sorted(comp.items())},
            "study1_menu_chars": menu, "study1_input_cache_factor": mix}


def build_first_costs(study1_dir: str) -> Dict[str, Any]:
    """Mean cost of an agent's first completion (spend entry ``completion`` == 1) per model and Study 1 config, n = 2."""
    vals: Dict[str, List[float]] = defaultdict(list)
    for ph in ("phase1", "phase2", "phase3"):
        p = os.path.join(study1_dir, ph, "spend.jsonl")
        if not os.path.exists(p):
            continue
        with open(p) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                parts = str(e.get("episode_id", "")).split("__")
                if e.get("completion") != 1 or len(parts) < 5 or parts[3] != "n2":
                    continue
                vals[f"{e['model']}|{parts[1].replace('+aware', '')}"].append(float(e.get("cost_usd") or 0.0))
    return {k: {"mean": statistics.fmean(v), "n": len(v), "max": max(v)} for k, v in sorted(vals.items())}


def load_costs(path: str = COSTS_PATH) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Estimates
# --------------------------------------------------------------------------


def gemini_ratio(period: str) -> float:
    return 2.0 if period == "dec" else 1.0


def menu_chars(config: str) -> int:
    """Characters of the Study 2 tool menu for ``config``, from the code (so any change of tool text is priced)."""
    from world5 import CoordinationConfig, tool_schemas  # noqa: PLC0415
    return len(json.dumps(tool_schemas(CoordinationConfig.from_names(config))))


def menu_usd_per_completion(costs: Dict[str, Any], model: str, config: str, c1: str, gemini_period: str = "nov") -> float:
    """Input cost of the Study 2 menu's extra tokens over the Study 1 ``c1`` menu, per completion."""
    extra = max(0, menu_chars(config) - int(costs["study1_menu_chars"][c1])) / CHARS_PER_TOKEN
    gem = gemini_ratio(gemini_period) if provider_family(model) == "gemini" else 1.0
    cache = float((costs.get("study1_input_cache_factor") or {}).get(model, 1.0))
    return extra * INPUT_USD_PER_MTOK[model] * cache * gem / 1e6


def estimate(costs: Dict[str, Any], model: str, n: int, config: str, template: str, aware: bool,
             gemini_period: str = "nov") -> float:
    fam = I.family_of(template)
    cells = costs["cells"]
    cap2 = call_cap(n, config)
    ex = EXEC_RATIO.get(model, 1.0) * (gemini_ratio(gemini_period) if provider_family(model) == "gemini" else 1.0)
    out = []
    for c1 in STUDY1_CONFIG[config]:
        k = f"{model}|{n}|{c1}|{int(aware)}|{fam}"
        k2 = f"{model}|{n}|{c1}|*|*"
        d = cells.get(k) or cells.get(k2)
        if d is None and n != 2:
            d = cells.get(f"{model}|2|{c1}|*|*")
            if d is not None:
                d = dict(d, mean=d["mean"] * n / 2 * 1.1)
        if d is None:
            raise KeyError(f"no Study 1 cost for {model} n={n} {c1}")
        uplift = 1.0 + d["p_cap"] * (((cap2 + 1) / 13.0) ** 1.5 - 1.0)
        completions = n * float(costs["completions_per_agent"][f"{model}|{c1}"]) * (1.0 + d["p_cap"] * ((cap2 + 1) / 13.0 - 1.0))
        out.append(d["mean"] * ex * uplift + completions * menu_usd_per_completion(costs, model, config, c1, gemini_period))
    return max(out) * RERUN_WASTE.get(model, 1.0)


def probe_estimate(costs: Dict[str, Any], model: str, config: str, gemini_period: str = "nov") -> float:
    """Cost of one first-reply probe (one completion) for ``model`` under ``config``."""
    fc = costs.get("first_completion") or {}
    ex = EXEC_RATIO.get(model, 1.0) * (gemini_ratio(gemini_period) if provider_family(model) == "gemini" else 1.0)
    vals = [fc[f"{model}|{c1}"]["mean"] * ex + menu_usd_per_completion(costs, model, config, c1, gemini_period)
            for c1 in STUDY1_CONFIG[config] if f"{model}|{c1}" in fc]
    if not vals:
        raise KeyError(f"no Study 1 first-completion cost for {model} {config}")
    return max(vals) * RERUN_WASTE.get(model, 1.0)


def probes_per_cell(n: int = 2) -> Dict[str, int]:
    """Probed agents per (family, instance, config, aware): all n under the contended template, n - 1 under the
    control (a0's control prompt is identical to its contended prompt)."""
    return {"contended": n, "control": n - 1}


def block_cells(model: str, n: int, configs: Sequence[str], families: Sequence[str], aware: Sequence[bool], k: int, s: int):
    for fam in families:
        for t in (fam, fam + I.CONTROL_SUFFIX):
            for cfg in configs:
                for aw in aware:
                    for i in range(k):
                        for sc in range(s):
                            yield {"model": model, "n": n, "config": cfg, "template": t, "aware": aw, "instance": i, "schedule": sc}


def block_cost(costs, blk: Dict[str, Any], period: str) -> Tuple[int, float]:
    cnt = tot = 0
    per = probes_per_cell(blk["n"])
    for c in block_cells(blk["model"], blk["n"], blk["configs"], blk["families"], blk["aware"], blk["instances"], blk["schedules"]):
        cnt += 1
        if blk.get("mode") == "probe":
            tot += probe_estimate(costs, c["model"], c["config"], period) * per["control" if c["template"].endswith(I.CONTROL_SUFFIX) else "contended"]
        else:
            tot += estimate(costs, c["model"], c["n"], c["config"], c["template"], c["aware"], period)
    return cnt, tot


# --------------------------------------------------------------------------
# Power (minimum detectable differences)
# --------------------------------------------------------------------------


def mdd(n_per_arm: float, p: float = 0.5, alpha: float = 0.05, power: float = 0.8, paired_r: float = 0.0) -> float:
    """Minimum detectable difference in a proportion between two arms of ``n_per_arm`` independent units each
    (two-sided normal approximation; ``paired_r`` = correlation of paired units, 0 for independent)."""
    za, zb = 1.959964, 0.841621
    if n_per_arm <= 0:
        return float("nan")
    return (za + zb) * math.sqrt(2 * p * (1 - p) * (1 - paired_r) / n_per_arm)


def power_report(blk: Dict[str, Any]) -> Dict[str, Any]:
    """MDDs for the main contrasts of one model's n = 2 aware-off episode block.

    The pre-registered unit is the *cluster* (family x instance; review V1 text 4): schedules, agents and arms within
    a cluster are correlated, and the two agents of a contended episode interact. Agent/episode-level figures are
    listed for reference only. Lock use contended vs control measures reactive locking (the first reply sees the
    same input in both arms), so it is an equivalence/bounding analysis, not a superiority test (review V2 M1)."""
    fams, k, s, n = len(blk["families"]), blk["instances"], blk["schedules"], blk["n"]
    eps_per_cell = fams * k * s                  # episodes per (config, contended|control)
    agents_per_cell = eps_per_cell * n
    clusters = fams * k
    return {
        "episodes_per_config_and_arm": eps_per_cell,
        "clusters (family x instance)": clusters,
        "lock_use_contended_vs_control (clusters, PRIMARY)": round(mdd(clusters), 3),
        "integrity_fail_config_vs_none (clusters, paired r=0.3, PRIMARY)": round(mdd(clusters, paired_r=0.3), 3),
        "lock_use_contended_vs_control (agents, reference)": round(mdd(agents_per_cell), 3),
        "integrity_fail_config_vs_none (episodes, paired r=0.3, reference)": round(mdd(eps_per_cell, paired_r=0.3), 3),
        "contended_vs_control_failure (episodes, reference)": round(mdd(eps_per_cell), 3),
    }


def probe_power(blk: Dict[str, Any]) -> Dict[str, Any]:
    """MDDs for a probe block: per (config, aware) cell, a0 probes (one per family x instance) are the units for the
    aware on vs off contrast (paired by prompt; r = 0.3) and for first-reply lock/CAS shares."""
    units = len(blk["families"]) * blk["instances"]
    return {"a0_probes_per_config_and_aware": units, "probes_per_config_and_aware": units * 3,
            "aware_on_vs_off_first_reply (a0 probes, paired r=0.3)": round(mdd(units, paired_r=0.3), 3),
            "aware_on_vs_off_first_reply (all probes, paired r=0.3)": round(mdd(units * 3, paired_r=0.3), 3)}


# --------------------------------------------------------------------------
# Grid choice
# --------------------------------------------------------------------------


def _core_block(m: str, configs: Sequence[str], aware: Sequence[bool], priority: int = 1) -> Dict[str, Any]:
    name, nf, k, s = V2_CORE[m]
    return {"model": m, "n": 2, "configs": list(configs), "families": list(FAMILY_PRIORITY[:nf]), "aware": list(aware),
            "instances": k, "schedules": s, "level": name, "priority": priority, "mode": "episodes"}


def _probe_block(m: str, k: int) -> Dict[str, Any]:
    return {"model": m, "n": 2, "configs": list(CONFIGS), "families": list(FAMILY_PRIORITY), "aware": [False, True],
            "instances": k, "schedules": 1, "level": f"P7x{k}", "priority": 0, "mode": "probe"}


def choose(costs, caps: Dict[str, float], total_cap: float, safety: float, period: str, n4: bool = False,
           margin: float = 0.10, probe_k: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """The Round 3 grid (module docstring): fixed core blocks and fixed probe levels (``PROBE_K``); if a provider
    family's ``estimate x safety`` exceeds ``(1 - margin) x cap`` (or the total its share), the descriptive-only
    models are cut first (``DESCRIPTIVE_CUTS``); the confirmatory cells are never cut here (SystemExit instead).
    Then priority-4 extensions (not in the estimate, run only while real spend leaves room)."""
    pk = dict(probe_k or PROBE_K)
    core_level = {m: V2_CORE[m] for m in MODELS}
    cuts_applied: List[str] = []

    def build() -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        for m in MODELS:
            name, nf, k, s_ = core_level[m]
            mk = lambda cfgs, aw: {"model": m, "n": 2, "configs": list(cfgs), "families": list(FAMILY_PRIORITY[:nf]),  # noqa: E731
                                   "aware": list(aw), "instances": k, "schedules": s_, "level": name, "priority": 1,
                                   "mode": "episodes"}
            if provider_family(m) == "gemini":
                blocks.append(mk([c for c in CONFIGS if c not in GEMINI_AWARE_CONFIGS], [False]))
                blocks.append(mk(list(GEMINI_AWARE_CONFIGS), [False, True]))
            else:
                blocks.append(mk(CONFIGS, [False]))
            if pk[m] > 0:
                blocks.append(_probe_block(m, pk[m]))
        for b in blocks:
            b["episodes"], cost = block_cost(costs, b, period)
            b["est_usd"] = round(cost, 2)
        return blocks

    limit = {f: (1.0 - margin) * caps[f] for f in FAMILIES}
    total_limit = (1.0 - margin) * total_cap

    def by_family(blocks) -> Dict[str, float]:
        out: Dict[str, float] = defaultdict(float)
        for b in blocks:
            out[provider_family(b["model"])] += b["est_usd"]
        return out

    def over(blocks) -> List[str]:
        fam = by_family(blocks)
        bad = [f for f in FAMILIES if fam[f] * safety > limit[f] + 1e-9]
        if sum(fam.values()) * safety > total_limit + 1e-9:
            bad.append("total")
        return bad

    blocks = build()
    for m, what, val in DESCRIPTIVE_CUTS:
        bad = over(blocks)
        if not bad:
            break
        if "total" not in bad and provider_family(m) not in bad:
            continue
        if what == "probe":
            pk[m] = val
        else:
            core_level[m] = val
        cuts_applied.append(f"{SHORT[m]} {what} -> {val if what == 'probe' else val[0]}")
        blocks = build()
    bad = over(blocks)
    if bad:
        raise SystemExit(f"the grid does not keep {margin:.0%} headroom in {bad} even after cutting the descriptive "
                         f"models; the confirmatory cells would have to shrink (not done automatically)")
    # extensions (priority 4, not in the estimate): GPT and Fable next size levels, aware off
    for m, levels in (("openrouter:openai/gpt-5.5-20260423", (("L3x3x2", 3, 3, 2), ("L4x3x2", 4, 3, 2))),
                      ("claude-fable-5", (("L3x1x2", 3, 1, 2), ("L3x2x2", 3, 2, 2)))):
        for name, nf, k, s_ in levels:
            blocks.append({"model": m, "n": 2, "configs": list(CONFIGS), "families": list(FAMILY_PRIORITY[:nf]),
                           "aware": [False], "instances": k, "schedules": s_, "level": name, "priority": 4,
                           "mode": "episodes", "episodes": nf * 2 * len(CONFIGS) * k * s_, "est_usd": None, "if_budget": True})
    by_fam = by_family([b for b in blocks if b.get("est_usd") is not None])
    blocks.sort(key=lambda b: (b["priority"], MODELS.index(b["model"])))
    return {"blocks": blocks, "estimate_by_family": {f: round(by_fam[f], 2) for f in FAMILIES},
            "estimate_total": round(sum(by_fam.values()), 2), "safety": safety, "margin": margin, "gemini_period": period,
            "caps": caps, "total_cap": total_cap, "probe_instances": pk, "descriptive_cuts": cuts_applied,
            "headroom_by_family": {f: round(1.0 - by_fam[f] * safety / caps[f], 3) for f in FAMILIES}}


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--study1", default=os.path.join(HERE, "..", "results4", "full"))
    p.add_argument("--write-costs", default=None, help="rebuild the Study 1 cost table from --study1 into this file")
    p.add_argument("--costs", default=COSTS_PATH)
    p.add_argument("--plan", default=None, help="write the chosen grid here (JSON)")
    p.add_argument("--safety", type=float, default=1.15)
    p.add_argument("--margin", type=float, default=0.10, help="headroom every provider family keeps below its cap")
    p.add_argument("--gemini-period", choices=("nov", "dec"), default="nov")
    p.add_argument("--family-cap", action="append", default=[])
    p.add_argument("--total-cap", type=float, default=DEFAULT_TOTAL_CAP)
    p.add_argument("--blocks", default=None, help="print the blocks of a plan file as runner lines (TSV) and exit")
    p.add_argument("--add-menu-stats", action="store_true",
                   help="add Study 1 completions per agent and menu sizes to --costs (from --study1 and ../src4)")
    a = p.parse_args(argv)
    if a.blocks:
        with open(a.blocks) as f:
            plan = json.load(f)
        cum: Dict[str, float] = defaultdict(float)
        for b in sorted(plan["blocks"], key=lambda b: (b["priority"], MODELS.index(b["model"]))):
            if b.get("est_usd") is not None:
                cum[b["model"]] += b["est_usd"]
            aw = b["aware"]
            print("\t".join([str(b["priority"]), provider_family(b["model"]), b["model"], str(b["n"]), ",".join(b["configs"]),
                             "families:" + ",".join(b["families"]), str(b["instances"]),
                             ",".join(str(i) for i in range(b["schedules"])),
                             "both" if len(aw) == 2 else ("on" if aw[0] else "off"),
                             f"{MODEL_CAP_FACTOR * cum[b['model']]:.2f}" if b.get("est_usd") is not None else "-",
                             b.get("mode", "episodes")]))
        return 0
    if a.add_menu_stats:
        data = load_costs(a.costs)
        data.update(build_menu_stats(a.study1))
        with open(a.costs, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        print(f"added completions_per_agent ({len(data['completions_per_agent'])}) and study1_menu_chars to {a.costs}")
        return 0
    if a.write_costs:
        data = build_costs(a.study1)
        with open(a.write_costs, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        print(f"wrote {len(data['cells'])} cost cells and {len(data['first_completion'])} first-completion cells to {a.write_costs}")
        return 0
    from budget5 import parse_family_caps  # noqa: PLC0415
    costs = load_costs(a.costs)
    caps = parse_family_caps(a.family_cap)
    plan = choose(costs, caps, a.total_cap, a.safety, a.gemini_period, margin=a.margin)
    print(f"== Study 2 grid, Round 3 (safety x{a.safety}, margin {a.margin:.0%}, Gemini {a.gemini_period} batch price); "
          f"caps {caps}, total ${a.total_cap}")
    print(f"{'model':8s} {'prio':4s} {'mode':8s} {'level':7s} {'aware':5s} {'configs':45s} {'families':12s} {'eps':>5s} {'est $':>7s}")
    for b in plan["blocks"]:
        aw = "both" if len(b["aware"]) == 2 else ("on" if b["aware"][0] else "off")
        print(f"{SHORT[b['model']]:8s} {b['priority']:<4d} {b.get('mode', 'episodes'):8s} {b['level']:7s} {aw:5s} "
              f"{','.join(b['configs']):45s} {len(b['families']):>2d} families {b['episodes']:5d} "
              + (f"{b['est_usd']:7.2f}" if b.get("est_usd") is not None else "  (if budget allows)"))
    print(f"estimate by provider: {plan['estimate_by_family']}  total ${plan['estimate_total']} "
          f"(x{a.safety} safety = ${plan['estimate_total'] * a.safety:.2f}); probe instances per model "
          f"{ {SHORT[m]: k for m, k in plan['probe_instances'].items()} }")
    print("headroom below cap after safety: " + ", ".join(f"{f} {h:.1%}" for f, h in plan["headroom_by_family"].items()))
    print("descriptive-model cuts applied to keep the margin: " + ("; ".join(plan["descriptive_cuts"]) or "none"))
    print("tool menu characters (Study 2, from the code): " + ", ".join(f"{c} {menu_chars(c)}" for c in CONFIGS)
          + f"; Study 1: {costs['study1_menu_chars']}")
    print("\nper-episode estimates (n=2, aware off, contended mean over all families); per-probe estimate:")
    for m in MODELS:
        row = [f"{c}={statistics.fmean(estimate(costs, m, 2, c, f, False, a.gemini_period) for f in FAMILY_PRIORITY):.4f}" for c in CONFIGS]
        pr = [f"{c}={probe_estimate(costs, m, c, a.gemini_period):.5f}" for c in CONFIGS]
        print(f"   {SHORT[m]:7s} " + "  ".join(row) + "   | probe " + "  ".join(pr))
    plan["power"] = {SHORT[b["model"]]: power_report(b) for b in plan["blocks"]
                     if b["priority"] == 1 and b["aware"] == [False]}
    plan["probe_power"] = {SHORT[b["model"]]: probe_power(b) for b in plan["blocks"] if b.get("mode") == "probe"}
    print("\nminimum detectable differences (80% power, alpha 0.05 two-sided, p=0.5 worst case); clusters are primary:")
    for m, d in plan["power"].items():
        print(f"   {m:7s} " + "; ".join(f"{k}: {v}" for k, v in d.items()))
    for m, d in plan["probe_power"].items():
        print(f"   {m:7s} probes: " + "; ".join(f"{k}: {v}" for k, v in d.items()))
    print_final_tables(costs, plan, a.safety)
    if a.plan:
        with open(a.plan, "w") as f:
            json.dump(plan, f, indent=1, sort_keys=True)
        print(f"\nwrote {a.plan}")
    return 0


def print_final_tables(costs: Dict[str, Any], plan: Dict[str, Any], safety: float) -> None:
    """Round 3: the per-provider cost table with headroom and the per-cell n (quoted by the pre-registration)."""
    caps, est = plan["caps"], plan["estimate_by_family"]
    print("\n== FINAL COST TABLE (Round 3; tool-text tokens priced from the code, GPT re-run waste 1.04, safety x"
          f"{safety}; Gemini at the November batch price)")
    print(f"{'provider':11s} {'estimate $':>10s} {'x' + str(safety):>8s} {'cap $':>6s} {'90% cap':>8s} {'headroom':>9s}")
    for f in FAMILIES:
        print(f"{f:11s} {est[f]:10.2f} {est[f] * safety:8.2f} {caps[f]:6.1f} {0.9 * caps[f]:8.2f} {plan['headroom_by_family'][f]:9.1%}")
    tot = plan["estimate_total"]
    print(f"{'total':11s} {tot:10.2f} {tot * safety:8.2f} {plan['total_cap']:6.1f} {0.9 * plan['total_cap']:8.2f} "
          f"{1 - tot * safety / plan['total_cap']:9.1%}")
    gem_dec = sum(block_cost(costs, b, "dec")[1] for b in plan["blocks"]
                  if provider_family(b["model"]) == "gemini" and b.get("est_usd") is not None)
    print(f"Gemini risk: at the December price (batches ending after 2026-11-30T00:00Z) the Gemini blocks cost "
          f"${gem_dec:.2f} (x{safety} = ${gem_dec * safety:.2f}) against the ${caps['gemini']:.0f} cap; the runner "
          f"starts the Gemini lane first.")
    print("descriptive-model cuts applied: " + ("; ".join(plan["descriptive_cuts"]) or "none"))
    print("\n== PER-CELL n (n = 2 agents; arm = contended or matched control; episodes are run in contended/control pairs)")
    print(f"{'model':8s} {'core episodes':>13s} {'eps per config x arm':>21s} {'clusters per config x arm':>26s} "
          f"{'aware on':>18s} {'probe K':>8s} {'a0 probes per config x aware':>29s}")
    for m in MODELS:
        core = [b for b in plan["blocks"] if b["model"] == m and b["priority"] == 1]
        probe = [b for b in plan["blocks"] if b["model"] == m and b.get("mode") == "probe"]
        b0 = core[0]
        per = len(b0["families"]) * b0["instances"] * b0["schedules"]
        aware_on = ",".join(c for b in core if True in b["aware"] for c in b["configs"]) or "-"
        k = probe[0]["instances"] if probe else 0
        print(f"{SHORT[m]:8s} {sum(b['episodes'] for b in core):13d} {per:21d} {len(b0['families']) * b0['instances']:26d} "
              f"{aware_on:>18s} {k:8d} {len(FAMILY_PRIORITY) * k:29d}")
    print("Confirmatory cells (Qwen, Haiku, Sonnet; Gemini for aware on): 56 episodes per config x arm, unchanged from V2.")


if __name__ == "__main__":
    sys.exit(main())
