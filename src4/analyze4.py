"""Frozen analysis of run4 results (stdlib only, deterministic).

    python3 analyze4.py results4/full/phase1/results.csv results4/full/phase2/results.csv ... --out analysis

Writes ``<out>/numbers.json`` (every number) and ``<out>/tables.md``.

Rows and exclusions (every count is reported under ``exclusions``)
    * ``dry_run`` rows are dropped.
    * Episodes with a provider failure that was never recovered are not in
      results.csv (run4 writes nothing for an aborted episode); they are
      counted from the ``failures.jsonl`` next to each CSV as
      ``provider_failure_missing``. Episodes that failed and later completed
      on a retry are complete episodes and are kept
      (``provider_failure_recovered``, reported).
    * Pilot rows (``instance`` == ``pilot``, or a legacy CSV without an
      ``instance`` column) are dropped unless ``--include-pilot``.
    * A repeated ``episode_id`` keeps its first row (``duplicate_episode_id``).
    * Legacy (pilot) CSVs with a ``lost_update`` column are read through a
      deprecated alias: ``non_serializable`` = ``lost_update`` and the primary
      sub-label is rebuilt exactly from the old columns (old
      ``stale_overwrite`` meant "some stale write", old ``write_skew`` already
      excluded stale and partial episodes). They lack the per-episode
      denominators of the give-up and abandoned rates, which are then
      undefined for those rows.

Cells and scopes
    A cell is (model, config, aware, n_agents). Each cell is reported for two
    scopes: ``all`` templates and ``contended`` (category != control).

Rates and 95% intervals (unit = task instance)
    A task instance is (template, instance index); the same index at another
    n is another cell, so the unit never spans cells. Within a cell, seeds
    (and, for agent-level metrics, agents) are aggregated per instance first:
    instance value = sum of numerators / sum of denominators over its
    episodes. The estimate is the unweighted mean of instance values over the
    ``m`` instances with a non-zero denominator, and the interval is the
    Wilson score interval for that proportion with ``m`` as the sample size
    (z = 1.959964). Episode-level metrics: ``non_serializable``, its three
    primary sub-labels, ``invariant_violation`` (denominator: episodes).
    Agent-level: coordination choices ``reread``, ``cas``, ``lock``,
    ``message``, ``none`` (denominator: agents), ``unnecessary_give_up``
    (denominator: agents that observed a concurrency conflict) and
    ``abandoned`` (denominator: ended agents whose intent was still valid).
    Raw pooled counts are reported alongside.

Paired comparisons (permutation test over task instances)
    * ``aware``: aware on minus aware off, within (model, config, n_agents).
    * ``config``: each config minus ``none``, within (model, aware, n_agents).
    Episodes are paired exactly on (instance, seed); unpaired seeds are
    dropped. Each instance contributes one difference d = (instance value
    under treatment) - (instance value under control), computed over its
    paired seeds. Statistic: mean of d. Two-sided p-value from the sign-flip
    permutation distribution: exact (all 2^m sign vectors) when at most
    :data:`EXACT_MAX` differences are non-zero, otherwise :data:`N_PERM`
    random sign vectors from ``random.Random`` seeded with
    :data:`PERM_SEED` and the comparison key, p = (1 + #{|mean*| >= |mean|})
    / (N_PERM + 1). One-sided p-values (treatment > control and <) are also
    reported. Scope: contended templates only.
    Holm correction within each hypothesis family, a family being
    (comparison, metric, n_agents): all models x configs (``aware``) or all
    models x aware levels x configs (``config``) for that metric at that n.
    Holm is applied to the two-sided p-values.

    Everything above is EXPLORATORY (labelled so in tables.md and
    numbers.json): the Wilson interval on a mean of instance rates is an
    approximation used only for descriptive tables, and the permutation
    comparisons support no confirmatory claim.

Confirmatory (pre-registered; :func:`confirmatory`, written to
``confirmatory.json`` and ``confirmatory.md``)
    Models: :data:`REGISTERED_MODELS` (requested ids, as in run_full.sh).
    Unit: task instance (template, instance index). A cluster contributes
    only if every episode the hypothesis needs for it is present ("complete
    cluster"); within a cluster, seeds, agents and paired conditions are
    aggregated first (sum of numerators / sum of denominators per
    condition). Clusters, per model:

    * H1: contended templates x instances 0-3; config ``none``, aware off,
      n = 2, seeds 0, 1. Value: share of episodes ``non_serializable``.
      H0 theta <= 0.50.
    * H2: same clusters, config ``locks``. Value: share of agents with
      ``lock`` (a successful ``acquire_lock``). H0 theta >= 0.25.
    * H3: same clusters, configs ``locks`` and ``messages`` pooled, aware on
      and off. Value: share of agents using the offered option (``lock``
      under ``locks``, ``message`` under ``messages``) with aware on, minus
      the same with aware off (pairs on (instance, seed, config) are complete
      by construction). H0 theta <= 0.
    * H4a: single-record templates (:data:`SINGLE_RECORD_TEMPLATES`) x
      instances 0-3; ``none`` and ``cas_available``, aware off, n = 2,
      seeds 0, 1. Value: primary-label ``stale_overwrite`` rate under
      ``none`` minus under ``cas_available``. H0 theta <= 0.
    * H4b: write-skew templates x instances 0-3 (8 clusters), same
      conditions. (i) primary-label ``write_skew`` rate under
      ``cas_available``, H0 theta <= 0.50; (ii) that rate under ``none``
      minus under ``cas_available``, H0 theta >= :data:`H4B_MARGIN`. Per-model
      p = max(p_i, p_ii) (intersection-union).
    * H6: contended templates x instances 0, 1 (14 clusters);
      ``cas_available``, aware off, seed 0, n = 2, 4, 8. Value: OLS slope of
      ``non_serializable`` (0/1) on log2(n). Every cluster has the same
      design points, so the mean of per-cluster slopes equals the pooled
      OLS slope. H0 theta <= 0.

    Test: the estimate is the mean of cluster values. Cluster bootstrap with
    :data:`N_BOOT` resamples of clusters with replacement, drawn from
    ``random.Random(f"{BOOT_SEED}|{hypothesis}|{model}[|i or |ii]")``.
    One-sided p for H0 theta <= theta0 is (1 + #{theta* <= theta0}) /
    (B + 1), and (1 + #{theta* >= theta0}) / (B + 1) for H0 theta >= theta0;
    95% percentile interval. If all cluster values are equal (always the case
    when an observed rate is 0 or 1, or a difference is +-1) the bootstrap
    distribution is a single point and the decision p-value is instead the
    exact one-sided sign test of cluster values against theta0 (ties
    dropped). The sign test is reported for every test. Holm across the
    tested models of each hypothesis, alpha = :data:`ALPHA`. Decision
    rules: H1 supported iff all six models reject; H2 iff at least
    :data:`H2_MIN_REJECT` reject; H3 reports which reject; H4a, H4b, H6:
    supported for each model that rejects.

    Missing data: a cluster whose missing episodes are all unrecovered
    provider failures (``failures.jsonl``) is dropped and counted. If any
    registered episode a hypothesis needs was never run (e.g. the budget cap
    stopped the run), the hypothesis is ``not_tested`` for that model: it
    leaves the Holm family, counts as not rejecting in "k of 6" rules, and
    is never reported as a null result. Sensitivity: everything is rerun
    with episodes that have a truncated agent treated as missing
    (``sensitivity_exclude_truncated``).

    H5 (descriptive, :func:`h5_agents`, read from transcripts): agents in
    ``transfer_shared_source`` under ``cas_available``, ``cas_required`` or
    ``locks``, n = 2, both aware levels, with a write (``update_record`` or
    ``claim``) to a record their intent writes rejected as
    ``version_conflict`` (409) or ``locked_by_other`` (423). Numerator: those
    that committed an action, ended and did not fulfil their intent. Count
    and 95% Wilson interval per model.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import sys
from collections import OrderedDict, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

Z95 = 1.959963984540054
N_PERM = 10000
EXACT_MAX = 16
PERM_SEED = 20261031
CHOICES = ("reread", "cas", "lock", "message", "none")
SUB_LABELS = ("stale_overwrite", "partial_action", "write_skew")
EPISODE_METRICS = ("non_serializable",) + SUB_LABELS + ("invariant_violation",)
AGENT_METRICS = CHOICES + ("unnecessary_give_up", "abandoned")
METRICS = EPISODE_METRICS + AGENT_METRICS
SCOPES = ("all", "contended")
PILOT = "pilot"


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


def wilson(p: float, n: float, z: float = Z95) -> Tuple[float, float]:
    """Wilson score interval for proportion ``p`` with sample size ``n`` (> 0)."""
    if n <= 0:
        raise ValueError("n must be positive")
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def holm(pvalues: Sequence[Optional[float]]) -> List[Optional[float]]:
    """Holm step-down adjusted p-values (``None`` entries are skipped and stay ``None``)."""
    idx = sorted((i for i, p in enumerate(pvalues) if p is not None), key=lambda i: (pvalues[i], i))
    m = len(idx)
    out: List[Optional[float]] = [None] * len(pvalues)
    running = 0.0
    for rank, i in enumerate(idx):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))  # type: ignore[operator]
        out[i] = running
    return out


def sign_flip_test(diffs: Sequence[float], key: str = "", n_perm: int = N_PERM, exact_max: int = EXACT_MAX) -> Dict[str, Any]:
    """Paired permutation (sign-flip) test of mean(diffs) = 0.

    Returns ``mean``, ``p_two_sided``, ``p_greater`` (mean > 0), ``p_less``
    and ``method`` (``exact`` or ``monte_carlo``). Zero differences do not
    change the permutation distribution and are kept in the mean.
    """
    m = len(diffs)
    if m == 0:
        return {"mean": None, "p_two_sided": None, "p_greater": None, "p_less": None, "method": None}
    obs = sum(diffs) / m
    eps = 1e-12
    nz = [d for d in diffs if d != 0]
    if not nz:
        return {"mean": obs, "p_two_sided": 1.0, "p_greater": 1.0, "p_less": 1.0, "method": "exact"}
    zero_sum = 0.0
    if len(nz) <= exact_max:
        two = ge = le = 0
        total = 1 << len(nz)
        for mask in range(total):
            s = zero_sum
            for j, d in enumerate(nz):
                s += -d if (mask >> j) & 1 else d
            mean = s / m
            two += abs(mean) >= abs(obs) - eps
            ge += mean >= obs - eps
            le += mean <= obs + eps
        return {"mean": obs, "p_two_sided": two / total, "p_greater": ge / total, "p_less": le / total, "method": "exact"}
    rng = random.Random(f"{PERM_SEED}|{key}")
    two = ge = le = 0
    for _ in range(n_perm):
        s = sum(d if rng.random() < 0.5 else -d for d in nz)
        mean = s / m
        two += abs(mean) >= abs(obs) - eps
        ge += mean >= obs - eps
        le += mean <= obs + eps
    k = n_perm + 1
    return {"mean": obs, "p_two_sided": (1 + two) / k, "p_greater": (1 + ge) / k, "p_less": (1 + le) / k, "method": "monte_carlo"}


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def _int(x: Any, default: Optional[int] = 0) -> Optional[int]:
    if x is None or x == "":
        return default
    return int(float(x))


def _parse_choices(s: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for part in (s or "").split(";"):
        if ":" in part:
            agent, cs = part.split(":", 1)
            out[agent] = [c for c in cs.split("|") if c]
    return out


def normalize_row(raw: Dict[str, str]) -> Dict[str, Any]:
    """One CSV row -> analysis record (handles the deprecated ``lost_update`` schema)."""
    legacy = "non_serializable" not in raw and "lost_update" in raw
    if legacy:
        ns = _int(raw["lost_update"])
        old_stale, old_skew = _int(raw.get("stale_overwrite")), _int(raw.get("write_skew"))
        label = "" if not ns else ("stale_overwrite" if old_stale else ("write_skew" if old_skew else "partial_action"))
    else:
        ns = _int(raw["non_serializable"])
        label = raw.get("primary_label") or ""
    choices = _parse_choices(raw.get("choices", ""))
    n_agents = _int(raw.get("n_agents"))
    return {
        "episode_id": raw["episode_id"],
        "model": raw["model"],
        "config": raw["config"],
        "aware": _int(raw.get("aware_prompt")),
        "task": raw["task"],
        "instance": raw.get("instance") or PILOT,
        "category": raw.get("category", ""),
        "n_agents": n_agents,
        "seed": _int(raw.get("seed")),
        "dry_run": _int(raw.get("dry_run")),
        "legacy": legacy,
        "non_serializable": ns,
        "label": label,
        "invariant_violation": _int(raw.get("invariant_violation")),
        "choices": choices,
        "n_choice_agents": len(choices) or n_agents,
        "n_unnecessary_give_up": _int(raw.get("n_unnecessary_give_up")),
        "n_conflict_agents": _int(raw.get("n_conflict_agents"), None),
        "n_abandoned": _int(raw.get("n_abandoned")),
        "n_abandon_eligible": _int(raw.get("n_abandon_eligible"), None),
        "truncated": bool(raw.get("truncated_agents")),
        "model_served": raw.get("model_served") or "",
    }


def metric_counts(r: Dict[str, Any], metric: str) -> Optional[Tuple[int, int]]:
    """``(numerator, denominator)`` of ``metric`` in one episode, or ``None`` if not measurable."""
    if metric == "non_serializable":
        return r["non_serializable"], 1
    if metric in SUB_LABELS:
        return int(r["label"] == metric), 1
    if metric == "invariant_violation":
        return r["invariant_violation"], 1
    if metric in CHOICES:
        return sum(metric in cs for cs in r["choices"].values()), r["n_choice_agents"]
    if metric == "unnecessary_give_up":
        return None if r["n_conflict_agents"] is None else (r["n_unnecessary_give_up"], r["n_conflict_agents"])
    if metric == "abandoned":
        return None if r["n_abandon_eligible"] is None else (r["n_abandoned"], r["n_abandon_eligible"])
    raise KeyError(metric)


def failed_episode_ids(csv_path: str) -> set:
    """Episode ids in the ``failures.jsonl`` next to ``csv_path`` (provider failures)."""
    out = set()
    fpath = os.path.join(os.path.dirname(os.path.abspath(csv_path)), "failures.jsonl")
    if os.path.exists(fpath):
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.add(json.loads(line)["episode_id"])
                    except (ValueError, KeyError):
                        continue
    return out


def load(paths: Sequence[str], include_pilot: bool = False) -> Tuple[List[Dict[str, Any]], Dict[str, int], List[Dict[str, str]]]:
    """Read CSVs; return (kept rows, exclusion counts, input file digests)."""
    excl = OrderedDict((k, 0) for k in ("rows_read", "dry_run", "pilot_instance", "duplicate_episode_id",
                                         "provider_failure_missing", "provider_failure_recovered", "legacy_schema_rows"))
    rows: List[Dict[str, Any]] = []
    seen = set()
    inputs = []
    failed_ids = set()
    for path in paths:
        with open(path, "rb") as f:
            inputs.append({"path": path, "sha256": hashlib.sha256(f.read()).hexdigest()})
        with open(path, newline="") as f:
            for raw in csv.DictReader(f):
                excl["rows_read"] += 1
                r = normalize_row(raw)
                if r["dry_run"]:
                    excl["dry_run"] += 1
                    continue
                if r["instance"] == PILOT and not include_pilot:
                    excl["pilot_instance"] += 1
                    continue
                if r["episode_id"] in seen:
                    excl["duplicate_episode_id"] += 1
                    continue
                seen.add(r["episode_id"])
                r["source"] = path
                excl["legacy_schema_rows"] += r["legacy"]
                rows.append(r)
        failed_ids |= failed_episode_ids(path)
    kept_ids = {r["episode_id"] for r in rows}
    excl["provider_failure_recovered"] = len(failed_ids & kept_ids)
    excl["provider_failure_missing"] = len(failed_ids - kept_ids)
    return rows, dict(excl), inputs


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def in_scope(r: Dict[str, Any], scope: str) -> bool:
    return scope == "all" or r["category"] != "control"


def instance_key(r: Dict[str, Any]) -> Tuple[str, str]:
    return (r["task"], str(r["instance"]))


def cluster_rate(rows: Iterable[Dict[str, Any]], metric: str) -> Dict[str, Any]:
    """Instance-level rate of ``metric`` with a Wilson interval (see module docstring)."""
    per: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        c = metric_counts(r, metric)
        if c is None:
            continue
        acc = per[instance_key(r)]
        acc[0] += c[0]
        acc[1] += c[1]
    vals = [num / den for num, den in per.values() if den > 0]
    num = sum(v[0] for v in per.values())
    den = sum(v[1] for v in per.values())
    out = {"metric": metric, "numerator": num, "denominator": den, "n_instances": len(vals),
           "estimate": None, "ci_low": None, "ci_high": None}
    if vals:
        p = sum(vals) / len(vals)
        lo, hi = wilson(p, len(vals))
        out.update(estimate=p, ci_low=lo, ci_high=hi)
    return out


def cell_rates(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cells: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        cells[(r["model"], r["config"], r["aware"], r["n_agents"])].append(r)
    out = []
    for key in sorted(cells, key=lambda k: tuple(str(x) for x in k)):
        model, config, aware, n = key
        for scope in SCOPES:
            pool = [r for r in cells[key] if in_scope(r, scope)]
            if not pool:
                continue
            for metric in METRICS:
                rec = {"model": model, "config": config, "aware": aware, "n_agents": n, "scope": scope,
                       "unit": "episode" if metric in EPISODE_METRICS else "agent", "n_episodes": len(pool)}
                rec.update(cluster_rate(pool, metric))
                out.append(rec)
    return out


def paired_diffs(treat: Sequence[Dict[str, Any]], ctrl: Sequence[Dict[str, Any]], metric: str) -> Tuple[List[float], int, int]:
    """Per-instance differences over seeds paired exactly; returns (diffs, n_paired_episodes, n_unpaired_episodes)."""
    def index(rows):
        d: Dict[Tuple[Tuple[str, str], int], Dict[str, Any]] = {}
        for r in rows:
            d[(instance_key(r), r["seed"])] = r
        return d

    ti, ci = index(treat), index(ctrl)
    common = set(ti) & set(ci)
    unpaired = len(set(ti) ^ set(ci))
    acc: Dict[Tuple[str, str], List[int]] = defaultdict(lambda: [0, 0, 0, 0])
    paired = 0
    for k in common:
        a, b = metric_counts(ti[k], metric), metric_counts(ci[k], metric)
        if a is None or b is None:
            continue
        paired += 1
        v = acc[k[0]]
        v[0] += a[0]; v[1] += a[1]; v[2] += b[0]; v[3] += b[1]  # noqa: E702
    diffs = [v[0] / v[1] - v[2] / v[3] for _, v in sorted(acc.items()) if v[1] > 0 and v[3] > 0]
    return diffs, paired, unpaired


def comparisons(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pool = [r for r in rows if in_scope(r, "contended")]
    by: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for r in pool:
        by[(r["model"], r["config"], r["aware"], r["n_agents"])].append(r)
    models = sorted({k[0] for k in by})
    configs = sorted({k[1] for k in by})
    awares = sorted({k[2] for k in by})
    ns = sorted({k[3] for k in by})
    out: List[Dict[str, Any]] = []
    for metric in METRICS:
        for n in ns:
            for model in models:
                for config in configs:
                    t, c = by.get((model, config, 1, n)), by.get((model, config, 0, n))
                    if t and c:
                        out.append(_compare("aware", metric, model, n, {"config": config}, "aware_on", "aware_off", t, c))
                for aware in awares:
                    c = by.get((model, "none", aware, n))
                    for config in configs:
                        t = by.get((model, config, aware, n))
                        if config != "none" and t and c:
                            out.append(_compare("config", metric, model, n, {"aware": aware}, config, "none", t, c))
    families: Dict[Tuple[str, str, Any], List[int]] = defaultdict(list)
    for i, rec in enumerate(out):
        families[(rec["comparison"], rec["metric"], rec["n_agents"])].append(i)
    for fam, idx in families.items():
        adj = holm([out[i]["p_two_sided"] for i in idx])
        for i, a in zip(idx, adj):
            out[i]["family"] = f"{fam[0]}|{fam[1]}|n{fam[2]}"
            out[i]["family_size"] = sum(out[j]["p_two_sided"] is not None for j in idx)
            out[i]["p_holm"] = a
    return out


def _compare(kind, metric, model, n, fixed, treat_name, ctrl_name, t, c) -> Dict[str, Any]:
    diffs, paired, unpaired = paired_diffs(t, c, metric)
    key = f"{kind}|{metric}|{model}|{n}|{json.dumps(fixed, sort_keys=True)}|{treat_name}"
    test = sign_flip_test(diffs, key)
    rec = {"comparison": kind, "metric": metric, "model": model, "n_agents": n, **fixed,
           "treatment": treat_name, "control": ctrl_name, "n_instances": len(diffs),
           "n_paired_episodes": paired, "n_unpaired_episodes": unpaired}
    rec.update({"mean_diff": test["mean"], "p_two_sided": test["p_two_sided"], "p_greater": test["p_greater"],
                "p_less": test["p_less"], "method": test["method"]})
    return rec


# --------------------------------------------------------------------------
# Confirmatory tests (pre-registered; see the module docstring, "Confirmatory")
# --------------------------------------------------------------------------

# Requested model ids exactly as in run_full.sh (MODELS_ORDERED), in run order.
REGISTERED_MODELS: Tuple[str, ...] = (
    "openrouter:qwen/qwen3.6-27b-20260422",
    "claude-haiku-4-5-20251001",
    "openrouter:openai/gpt-5.5-20260423",
    "openrouter:google/gemini-4-argon-20261013",
    "claude-sonnet-5",
    "claude-fable-5",
)
N_BOOT = 10000
BOOT_SEED = 20261031
ALPHA = 0.05
EPS = 1e-12
CONTENDED_TEMPLATES = ("inventory_last_unit", "inventory_still_valid", "seat_same", "ticket_same",
                       "transfer_shared_source", "budget_write_skew", "joint_account_write_skew")
SINGLE_RECORD_TEMPLATES = ("inventory_last_unit", "inventory_still_valid", "seat_same", "ticket_same")
WRITE_SKEW_TEMPLATES = ("budget_write_skew", "joint_account_write_skew")
N2_INSTANCES, N2_SEEDS = (0, 1, 2, 3), (0, 1)         # phase 1
SCALE_INSTANCES, SCALE_SEEDS = (0, 1), (0,)            # phases 2-3 (and their n = 2 counterparts)
SCALE_NS = (2, 4, 8)
H5_TEMPLATE = "transfer_shared_source"
H5_CONFIGS = ("cas_available", "cas_required", "locks")
H5_REJECT_REASONS = ("version_conflict", "locked_by_other")
H3_OPTION = {"locks": "lock", "messages": "message"}
HYPOTHESES = ("H1", "H2", "H3", "H4a", "H4b", "H6")


def _safe_name(s: str) -> str:
    """Same as ``run4.safe_name`` (episode ids use it for the model)."""
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in s)


def parse_episode_id(eid: str) -> Optional[Tuple[str, str, int, str, str, int, int]]:
    """``(safe model, config, aware, task, instance, n, seed)`` from a run4 full-run episode id, or ``None``."""
    parts = eid.split("__")
    if len(parts) < 5 or "@i" not in parts[-3] or not parts[-2].startswith("n") or not parts[-1].startswith("s"):
        return None
    cfg = parts[-4]
    aware = int(cfg.endswith("+aware"))
    if aware:
        cfg = cfg[: -len("+aware")]
    task, inst = parts[-3].rsplit("@i", 1)
    try:
        return "__".join(parts[:-4]), cfg, aware, task, inst, int(parts[-2][1:]), int(parts[-1][1:])
    except ValueError:
        return None


def binom_sign_p(k: int, n: int) -> float:
    """Exact one-sided sign-test p-value P(X >= k), X ~ Binomial(n, 1/2); 1.0 when n = 0."""
    if n == 0:
        return 1.0
    return sum(math.comb(n, j) for j in range(k, n + 1)) / 2 ** n


def sign_test(values: Sequence[float], theta0: float, alternative: str) -> Dict[str, Any]:
    """Exact sign test of cluster values against ``theta0`` (ties with ``theta0`` dropped)."""
    above = sum(v > theta0 + EPS for v in values)
    below = sum(v < theta0 - EPS for v in values)
    k = above if alternative == "greater" else below
    return {"n_nonzero": above + below, "k": k, "p": binom_sign_p(k, above + below)}


def cluster_bootstrap(values: Sequence[float], theta0: float, alternative: str, key: str, n_boot: int = N_BOOT) -> Dict[str, Any]:
    """One-sided cluster bootstrap test of the mean of cluster values (see "Confirmatory" in the module docstring).

    ``alternative`` ``"greater"``: H0 theta <= theta0, p = (1 + #{theta* <= theta0}) / (B + 1);
    ``"less"``: H0 theta >= theta0, p = (1 + #{theta* >= theta0}) / (B + 1). Resamples are drawn
    with ``random.Random(f"{BOOT_SEED}|{key}")``. When every cluster value is equal the bootstrap
    distribution is degenerate (this includes every observed rate of 0 or 1) and the decision
    p-value is the exact sign test; the sign test is reported in every case.
    """
    m = len(values)
    if m == 0:
        return {"n_clusters": 0, "estimate": None, "ci_low": None, "ci_high": None, "p_bootstrap": None,
                "p_sign": None, "p": None, "method": None, "degenerate": None}
    est = sum(values) / m
    rng = random.Random(f"{BOOT_SEED}|{key}")
    stats = sorted(sum(rng.choices(values, k=m)) / m for _ in range(n_boot))
    if alternative == "greater":
        null_side = sum(t <= theta0 + EPS for t in stats)
    elif alternative == "less":
        null_side = sum(t >= theta0 - EPS for t in stats)
    else:
        raise ValueError(alternative)
    p_boot = (1 + null_side) / (n_boot + 1)
    sg = sign_test(values, theta0, alternative)
    degenerate = max(values) - min(values) <= EPS
    return {"n_clusters": m, "estimate": est, "ci_low": stats[int(math.floor(0.025 * n_boot))],
            "ci_high": stats[int(math.ceil(0.975 * n_boot)) - 1], "p_bootstrap": p_boot, "p_sign": sg["p"],
            "sign_k": sg["k"], "sign_n": sg["n_nonzero"], "p": sg["p"] if degenerate else p_boot,
            "method": "sign_test" if degenerate else "bootstrap", "degenerate": degenerate}


def _episode_value(r: Dict[str, Any], metric: str) -> Tuple[int, int]:
    c = metric_counts(r, metric)
    assert c is not None, metric
    return c


def _rate(eps: Sequence[Dict[str, Any]], metric_of) -> float:
    num = den = 0
    for r in eps:
        a, b = _episode_value(r, metric_of(r))
        num += a
        den += b
    return num / den


def _spec(h: str) -> Dict[str, Any]:
    """Registered design of one hypothesis: clusters, the episodes each needs, and the test."""
    n2 = lambda cfgs, awares: [(c, a, 2, s) for c in cfgs for a in awares for s in N2_SEEDS]  # noqa: E731
    if h == "H1":
        return {"templates": CONTENDED_TEMPLATES, "instances": N2_INSTANCES, "needs": n2(["none"], [0]),
                "theta0": 0.5, "alternative": "greater", "kind": "rate", "metric": "non_serializable", "cfg": "none",
                "statistic": "proportion of episodes non_serializable (config none, n = 2, aware off)"}
    if h == "H2":
        return {"templates": CONTENDED_TEMPLATES, "instances": N2_INSTANCES, "needs": n2(["locks"], [0]),
                "theta0": 0.25, "alternative": "less", "kind": "rate", "metric": "lock", "cfg": "locks",
                "statistic": "proportion of agents with a successful acquire_lock (config locks, n = 2, aware off)"}
    if h == "H3":
        return {"templates": CONTENDED_TEMPLATES, "instances": N2_INSTANCES, "needs": n2(["locks", "messages"], [0, 1]),
                "theta0": 0.0, "alternative": "greater", "kind": "h3",
                "statistic": "agent rate of the offered option (lock | locks, message | messages), aware on - off"}
    if h == "H4a":
        return {"templates": SINGLE_RECORD_TEMPLATES, "instances": N2_INSTANCES, "needs": n2(["none", "cas_available"], [0]),
                "theta0": 0.0, "alternative": "greater", "kind": "diff", "metric": "stale_overwrite",
                "treat": "none", "ctrl": "cas_available",
                "statistic": "primary-label stale_overwrite rate, none - cas_available (n = 2, aware off)"}
    if h == "H4b":
        return {"templates": WRITE_SKEW_TEMPLATES, "instances": N2_INSTANCES, "needs": n2(["none", "cas_available"], [0]),
                "kind": "h4b", "metric": "write_skew",
                "statistic": "(i) write_skew rate under cas_available > 0.50; (ii) drop none - cas_available < 0.25"}
    if h == "H6":
        return {"templates": CONTENDED_TEMPLATES, "instances": SCALE_INSTANCES,
                "needs": [("cas_available", 0, n, s) for n in SCALE_NS for s in SCALE_SEEDS],
                "theta0": 0.0, "alternative": "greater", "kind": "slope", "metric": "non_serializable",
                "statistic": "OLS slope of non_serializable (0/1) on log2(n), n = 2, 4, 8 (cas_available, aware off, seed 0)"}
    raise KeyError(h)


H4B_MARGIN = 0.25
H2_MIN_REJECT = 4


def _cluster_values(spec: Dict[str, Any], eps: Dict[Tuple[str, int, int, int], Dict[str, Any]]) -> Dict[str, float]:
    """Cluster-level value(s) for one complete cluster (``eps`` keyed by (config, aware, n, seed))."""
    kind = spec["kind"]
    sel = lambda cfg=None, aware=None, n=None: [r for (c, a, nn, _), r in eps.items()  # noqa: E731
                                               if (cfg is None or c == cfg) and (aware is None or a == aware) and (n is None or nn == n)]
    if kind == "rate":
        return {"v": _rate(sel(), lambda r: spec["metric"])}
    if kind == "diff":
        m = spec["metric"]
        return {"v": _rate(sel(spec["treat"]), lambda r: m) - _rate(sel(spec["ctrl"]), lambda r: m)}
    if kind == "h3":
        opt = lambda r: H3_OPTION[r["config"]]  # noqa: E731
        return {"v": _rate(sel(aware=1), opt) - _rate(sel(aware=0), opt)}
    if kind == "h4b":
        cas = _rate(sel("cas_available"), lambda r: "write_skew")
        return {"i": cas, "ii": _rate(sel("none"), lambda r: "write_skew") - cas}
    if kind == "slope":
        xs = [math.log2(n) for n in SCALE_NS]
        ys = [_rate(sel(n=n), lambda r: "non_serializable") for n in SCALE_NS]
        xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
        return {"v": sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys)) / sum((x - xbar) ** 2 for x in xs)}
    raise KeyError(kind)


def _test_model(h: str, spec: Dict[str, Any], model: str, index: Dict[Tuple[Any, ...], Dict[str, Any]],
                explained: set, n_boot: int) -> Dict[str, Any]:
    registered = [(t, str(i)) for t in spec["templates"] for i in spec["instances"]]
    values: List[Dict[str, float]] = []
    dropped, not_run = [], []
    safe = _safe_name(model)
    for task, inst in registered:
        eps, missing = {}, []
        for need in spec["needs"]:
            r = index.get((model, task, inst) + need)
            if r is None:
                missing.append(need)
            else:
                eps[need] = r
        if not missing:
            values.append(_cluster_values(spec, eps))
            continue
        cfg_aware_n_seed = [(safe, c, a, task, inst, n, s) for c, a, n, s in missing]
        (dropped if all(k in explained for k in cfg_aware_n_seed) else not_run).append(f"{task}@i{inst}")
    rec: Dict[str, Any] = {"hypothesis": h, "model": model, "n_registered_clusters": len(registered),
                           "n_complete_clusters": len(values), "dropped_clusters": dropped, "not_run_clusters": not_run}
    if not_run or not values:
        rec.update(status="not_tested", p=None, reject=None,
                   reason="registered episodes not run (e.g. budget cap)" if not_run else "no complete clusters")
        return rec
    rec["status"] = "tested"
    key = f"{h}|{model}"
    if spec["kind"] == "h4b":
        ti = cluster_bootstrap([v["i"] for v in values], 0.5, "greater", key + "|i", n_boot)
        tii = cluster_bootstrap([v["ii"] for v in values], H4B_MARGIN, "less", key + "|ii", n_boot)
        rec.update(component_i=ti, component_ii=tii, p=max(ti["p"], tii["p"]), estimate=None)
    else:
        t = cluster_bootstrap([v["v"] for v in values], spec["theta0"], spec["alternative"], key, n_boot)
        rec.update(t)
    return rec


def wilson_count(k: int, n: int) -> Dict[str, Any]:
    """``k / n`` with a 95% Wilson interval (``None`` when ``n`` = 0)."""
    if n == 0:
        return {"k": 0, "n": 0, "rate": None, "ci_low": None, "ci_high": None}
    lo, hi = wilson(k / n, n)
    return {"k": k, "n": n, "rate": k / n, "ci_low": lo, "ci_high": hi}


def h5_from_transcript(tr: Dict[str, Any]) -> List[Dict[str, Any]]:
    """H5-eligible agents of one transcript, each with ``partial`` (see "Confirmatory", H5).

    Eligible: the agent's intent writes two or more records, and at least one of its writes
    (``update_record``/``claim``) to a record its intent writes was rejected with
    ``version_conflict`` (409) or ``locked_by_other`` (423). ``partial``: the agent committed
    an action (it is in ``committed_agents``), ended, and did not fulfil its intent.
    """
    import instances4
    import tasks4

    t = tr["task"]
    inst = t.get("instance")
    task = (tasks4.CATALOG[t["factory"]](tr["n_agents"]) if inst in (None, PILOT)
            else instances4.build(t["factory"], int(inst), tr["n_agents"]))
    calls = tr["ledger"]["calls"]
    committed = set(tr["score"]["committed_agents"])
    out = []
    for agent, intent in task.intents.items():
        writes = set(intent.writes)
        if len(writes) < 2:
            continue
        if not any(c["agent_id"] == agent and c["tool"] in ("update_record", "claim") and c.get("reason") in H5_REJECT_REASONS
                   and c.get("record_id") in writes for c in calls):
            continue
        s = tr["score"]["agents"][agent]
        out.append({"episode_id": tr["episode_id"], "model": tr["model"], "agent": agent,
                    "partial": agent in committed and s["end_reason"] != "running" and not s["fulfilled"]})
    return out


def h5_agents(rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """H5-eligible agents from the transcripts next to each row's results.csv; also the number of missing transcripts."""
    out, missing = [], 0
    for r in rows:
        if r["task"] != H5_TEMPLATE or r["config"] not in H5_CONFIGS or r["n_agents"] != 2:
            continue
        path = os.path.join(os.path.dirname(os.path.abspath(r.get("source", "."))), "transcripts", r["episode_id"] + ".json")
        if not os.path.exists(path):
            missing += 1
            continue
        with open(path) as f:
            out.extend(h5_from_transcript(json.load(f)))
    return out, missing


def confirmatory(rows: Sequence[Dict[str, Any]], h5: Optional[Sequence[Dict[str, Any]]] = None,
                 failed_ids: Iterable[str] = (), models: Sequence[str] = REGISTERED_MODELS,
                 exclude_truncated: bool = False, n_boot: int = N_BOOT) -> Dict[str, Any]:
    """The pre-registered confirmatory tests H1, H2, H3, H4a, H4b, H6 and the H5 count.

    ``rows``: analysis records (:func:`load`). ``h5``: H5-eligible agents (:func:`h5_agents`), or
    ``None`` if transcripts are unavailable. ``failed_ids``: episode ids of unrecovered provider
    failures; a cluster whose missing episodes are all failures (or, with ``exclude_truncated``,
    excluded truncated episodes) is dropped and counted; a cluster missing any episode that was
    never run makes the hypothesis ``not_tested`` for that model (never a null result).
    """
    index: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    explained = set()
    for eid in failed_ids:
        p = parse_episode_id(eid)
        if p is not None:
            explained.add(p)
    n_trunc = 0
    for r in rows:
        key = (r["model"], r["task"], str(r["instance"]), r["config"], r["aware"], r["n_agents"], r["seed"])
        if exclude_truncated and r.get("truncated"):
            n_trunc += 1
            explained.add((_safe_name(r["model"]), r["config"], r["aware"], r["task"], str(r["instance"]), r["n_agents"], r["seed"]))
            continue
        index.setdefault(key, r)
    out: Dict[str, Any] = {"meta": {"n_boot": n_boot, "boot_seed": BOOT_SEED, "alpha": ALPHA, "models": list(models),
                                    "exclude_truncated": exclude_truncated, "truncated_episodes_excluded": n_trunc,
                                    "h4b_margin": H4B_MARGIN,
                                    "served_ids": {m: sorted({x for r in rows if r["model"] == m
                                                              for x in r.get("model_served", "").split("|") if x})
                                                   for m in models}},
                           "hypotheses": {}}
    for h in HYPOTHESES:
        spec = _spec(h)
        recs = [_test_model(h, spec, m, index, explained, n_boot) for m in models]
        adj = holm([r["p"] for r in recs])
        for r, a in zip(recs, adj):
            r["p_holm"] = a
            r["reject"] = None if a is None else a <= ALPHA
        tested = [r for r in recs if r["status"] == "tested"]
        rejecting = [r["model"] for r in recs if r["reject"]]
        k = len(rejecting)
        if h == "H1":
            verdict = "supported" if k == len(models) else "not supported"
            rule = "supported iff all registered models reject after Holm"
        elif h == "H2":
            verdict = "supported" if k >= H2_MIN_REJECT else "not supported"
            rule = f"supported iff at least {H2_MIN_REJECT} of {len(models)} models reject after Holm"
        elif h == "H3":
            verdict = "reported per model (no overall claim)"
            rule = "report which models reject after Holm; no claim about the others"
        else:
            verdict = f"supported for {k} of {len(models)} models"
            rule = "supported for each model that rejects after Holm"
        out["hypotheses"][h] = {"statistic": spec["statistic"], "family_size": len(tested), "decision_rule": rule,
                                "verdict": verdict, "rejecting_models": rejecting,
                                "not_tested_models": [r["model"] for r in recs if r["status"] == "not_tested"],
                                "tests": recs}
    if h5 is None:
        out["H5"] = {"status": "not available (no transcripts)"}
    else:
        per = {}
        for m in models:
            el = [a for a in h5 if a["model"] == m]
            per[m] = wilson_count(sum(a["partial"] for a in el), len(el))
            per[m]["episodes"] = sorted({a["episode_id"] for a in el if a["partial"]})
        with_one = [m for m in models if per[m]["k"] >= 1]
        out["H5"] = {"status": "descriptive", "per_model": per, "models_with_at_least_one": with_one,
                     "outcome_met_before_audit": len(with_one) >= 3,
                     "note": "pre-specified outcome: >= 1 such agent, confirmed by transcript audit, in >= 3 of 6 models; "
                             "counts here are before the manual audit"}
    return out


def confirmatory_markdown(c: Dict[str, Any], title: str = "CONFIRMATORY tests (pre-registered)") -> str:
    m = c["meta"]
    lines = [f"# {title}", "",
             f"Cluster bootstrap over task instances, B = {m['n_boot']}, seed {m['boot_seed']}; one-sided; exact sign test "
             f"when the bootstrap is degenerate; Holm within each hypothesis over tested models; alpha = {m['alpha']}. "
             f"Truncated episodes excluded: {m['exclude_truncated']} ({m['truncated_episodes_excluded']}).", ""]
    for h, rec in c["hypotheses"].items():
        lines += [f"## {h}: {rec['statistic']}", "", f"Decision rule: {rec['decision_rule']}. **Verdict: {rec['verdict']}.** "
                  f"Holm family size: {rec['family_size']}. Not tested: {', '.join(rec['not_tested_models']) or 'none'}.", "",
                  "| model | status | clusters (complete/registered) | dropped | estimate | 95% CI | p | method | p Holm | reject |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for t in rec["tests"]:
            if t["status"] != "tested":
                lines.append(f"| {t['model']} | not tested ({t['reason']}) | {t['n_complete_clusters']}/{t['n_registered_clusters']} | "
                             f"{len(t['dropped_clusters'])} | - | - | - | - | - | - |")
                continue
            if h == "H4b":
                ci, cii = t["component_i"], t["component_ii"]
                est = f"(i) {_f(ci['estimate'])}; (ii) {_f(cii['estimate'])}"
                ci_txt = f"(i) [{_f(ci['ci_low'])}, {_f(ci['ci_high'])}]; (ii) [{_f(cii['ci_low'])}, {_f(cii['ci_high'])}]"
                method = f"(i) {ci['method']}; (ii) {cii['method']}"
            else:
                est, ci_txt, method = _f(t["estimate"]), f"[{_f(t['ci_low'])}, {_f(t['ci_high'])}]", t["method"]
            lines.append(f"| {t['model']} | tested | {t['n_complete_clusters']}/{t['n_registered_clusters']} | {len(t['dropped_clusters'])} | "
                         f"{est} | {ci_txt} | {_f(t['p'], 4)} | {method} | {_f(t['p_holm'], 4)} | {'yes' if t['reject'] else 'no'} |")
        lines.append("")
    h5 = c["H5"]
    lines += ["## H5 (pre-specified descriptive): partial actions after a concurrency rejection", ""]
    if h5["status"] != "descriptive":
        lines.append(h5["status"])
    else:
        lines += ["| model | partial / eligible agents | rate | 95% Wilson CI |", "|---|---|---|---|"]
        for model, w in h5["per_model"].items():
            ci_txt = "-" if w["rate"] is None else f"[{w['ci_low']:.2f}, {w['ci_high']:.2f}]"
            lines.append(f"| {model} | {w['k']} / {w['n']} | {_f(w['rate'], 2)} | {ci_txt} |")
        lines += ["", f"Models with at least one: {len(h5['models_with_at_least_one'])} "
                  f"(outcome met before audit: {h5['outcome_met_before_audit']}). {h5['note']}."]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def _f(x: Optional[float], nd: int = 3) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def _rate_cell(r: Dict[str, Any]) -> str:
    if r["estimate"] is None:
        return "-"
    return f"{r['estimate']:.2f} [{r['ci_low']:.2f}, {r['ci_high']:.2f}]"


def markdown(numbers: Dict[str, Any]) -> str:
    lines = ["# Concurrency benchmark: EXPLORATORY descriptive tables and comparisons", "",
             "EXPLORATORY: these tables and permutation tests support no confirmatory claim; the pre-registered "
             "tests are in confirmatory.md / confirmatory.json.", "",
             "Generated by analyze4.py; every number is in numbers.json. Rates: mean of task-instance rates "
             "[Wilson 95% CI, n = instances; an approximation used for descriptive tables only].", "", "## Exclusions", "", "| reason | count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in numbers["exclusions"].items()]
    rates = numbers["rates"]
    groups = [("Integrity (episode level)", EPISODE_METRICS), ("Coordination choices (agent level)", CHOICES),
              ("Give-up and abandonment (agent level)", ("unnecessary_give_up", "abandoned"))]
    for scope in SCOPES:
        for title, metrics in groups:
            lines += ["", f"## {title}, scope = {scope}", "",
                      "| model | config | aware | n | instances | " + " | ".join(metrics) + " |",
                      "|" + "---|" * (5 + len(metrics))]
            cells: Dict[Tuple[Any, ...], Dict[str, Dict[str, Any]]] = OrderedDict()
            for r in rates:
                if r["scope"] == scope and r["metric"] in metrics:
                    cells.setdefault((r["model"], r["config"], r["aware"], r["n_agents"]), {})[r["metric"]] = r
            for (model, config, aware, n), ms in cells.items():
                n_inst = max(m["n_instances"] for m in ms.values())
                lines.append(f"| {model} | {config} | {'on' if aware else 'off'} | {n} | {n_inst} | "
                             + " | ".join(_rate_cell(ms[m]) if m in ms else "-" for m in metrics) + " |")
    for kind, title in (("aware", "Aware on vs off"), ("config", "Config vs none")):
        lines += ["", f"## EXPLORATORY paired comparisons: {title} (contended templates; Holm within family)", "",
                  "| family | model | condition | treatment - control | instances | mean diff | p (two-sided) | p Holm | method |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for c in numbers["comparisons"]:
            if c["comparison"] != kind:
                continue
            cond = f"config={c['config']}" if kind == "aware" else f"aware={'on' if c['aware'] else 'off'}"
            lines.append(f"| {c['family']} | {c['model']} | {cond} | {c['treatment']} - {c['control']} | {c['n_instances']} | "
                         f"{_f(c['mean_diff'])} | {_f(c['p_two_sided'], 4)} | {_f(c['p_holm'], 4)} | {c['method'] or '-'} |")
    return "\n".join(lines) + "\n"


def analyze(paths: Sequence[str], include_pilot: bool = False, n_boot: int = N_BOOT) -> Dict[str, Any]:
    """Exploratory numbers (``status`` EXPLORATORY) plus ``confirmatory`` (pre-registered tests and the
    truncation sensitivity rerun)."""
    rows, excl, inputs = load(paths, include_pilot)
    with open(os.path.abspath(__file__), "rb") as f:
        self_hash = hashlib.sha256(f.read()).hexdigest()
    return {
        "meta": {"analyze4_sha256": self_hash, "inputs": inputs, "n_rows_analyzed": len(rows),
                 "include_pilot": include_pilot, "z": Z95, "n_perm": N_PERM, "exact_max": EXACT_MAX, "perm_seed": PERM_SEED,
                 "ci": "Wilson on the mean of task-instance rates, n = instances",
                 "holm_family": "(comparison, metric, n_agents)"},
        "status": "EXPLORATORY (rates, Wilson intervals and permutation comparisons); see confirmatory",
        "exclusions": excl,
        "rates": cell_rates(rows),
        "comparisons": comparisons(rows),
        "confirmatory": _confirmatory_block(rows, paths, inputs, self_hash, n_boot),
    }


def _confirmatory_block(rows, paths, inputs, self_hash, n_boot) -> Dict[str, Any]:
    failed = set().union(*(failed_episode_ids(p) for p in paths)) if paths else set()
    h5, missing = h5_agents(rows)
    main_c = confirmatory(rows, h5 if rows else None, failed, n_boot=n_boot)
    sens_rows = [r for r in rows if not r.get("truncated")]
    sens_h5 = [a for a in h5 if a["episode_id"] in {r["episode_id"] for r in sens_rows}]
    sens = confirmatory(rows, sens_h5 if rows else None, failed, exclude_truncated=True, n_boot=n_boot)
    main_c["meta"].update(analyze4_sha256=self_hash, inputs=inputs, h5_missing_transcripts=missing)
    return {"registered": main_c, "sensitivity_exclude_truncated": sens}


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="+", help="results.csv files")
    p.add_argument("--out", default="analysis")
    p.add_argument("--include-pilot", action="store_true", help="keep pilot rows (exploratory only)")
    a = p.parse_args(argv)
    numbers = analyze(a.csv, a.include_pilot)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "numbers.json"), "w") as f:
        json.dump(numbers, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(a.out, "tables.md"), "w") as f:
        f.write(markdown(numbers))
    conf = numbers["confirmatory"]
    with open(os.path.join(a.out, "confirmatory.json"), "w") as f:
        json.dump(conf, f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(a.out, "confirmatory.md"), "w") as f:
        f.write(confirmatory_markdown(conf["registered"]))
        f.write("\n" + confirmatory_markdown(conf["sensitivity_exclude_truncated"],
                                             "Sensitivity: confirmatory tests excluding episodes with a truncated agent"))
    print(f"analyzed {numbers['meta']['n_rows_analyzed']} episodes; exclusions {numbers['exclusions']}; wrote {a.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
