"""Confirmatory analysis of Study 2 (stdlib only, deterministic). Implements paper-concurrency/PREREGISTRATION_STUDY2.md.

    # 1. before any episode result is opened: eligibility from the probe transcripts only
    python3 analysis5/analyze5.py eligibility --base results5/study2 --out analysis5/out
    # 2. after eligibility.json and its sha256 are posted
    python3 analysis5/analyze5.py analyze --base results5/study2 --eligibility analysis5/out/eligibility.json \
        --out analysis5/out
    # dry-run rehearsal (fake models): add --allow-dry-run (reads <base>/<lane>/dry_run/transcripts)

Writes ``<out>/results.json`` (every number, sorted keys, no timestamps) and ``<out>/numbers.tex`` (one
``\\newcommand`` per reported value). ``eligibility`` writes ``<out>/eligibility.json``.

Scope (registration, Statistical models): the confirmatory tests, the claim per cell, the checks, H4b, the budget
report and sensitivity analyses 1 to 9. The pre-specified descriptive tables, the cross-model regression and the
exploratory analyses are not here.

Inputs. The scored transcripts ``<base>/n2-*/transcripts/*.json`` (episodes) and ``<base>/probe-*/transcripts/*.json``
(first-reply probes). Only scorer output is read (``src5/score5.score`` as stored by the harness; ``first_reply`` and
the per-completion ``turns`` from ``src5/model_agent5``). ``src5`` is imported read-only (``sys.dont_write_bytecode``)
for the 24-call re-score (``score5.rescore_at_cap``) and for the lock-safety gate when the stored score lacks it.
The block a row belongs to (probe 0, core 1, extension 4) comes from ``src5/plan_study2.json``; extension and
unplanned rows enter no statistic.

``GAP n`` comments point to the entries of ``analysis5/PREREG_GAPS.md``; each is now closed by registered text.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import random
import sys
from fractions import Fraction
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_SRC5 = os.path.join(ROOT, "src5")
DEFAULT_PLAN = os.path.join(DEFAULT_SRC5, "plan_study2.json")

# ---------------------------------------------------------------------------------------------------------------
# Registered constants
# ---------------------------------------------------------------------------------------------------------------

QWEN = "openrouter:qwen/qwen3.6-27b-20260422"
HAIKU = "claude-haiku-4-5-20251001"
GPT = "openrouter:openai/gpt-5.5-20260423"
GEMINI = "openrouter:google/gemini-4-argon-20261013"
SONNET = "claude-sonnet-5"
FABLE = "claude-fable-5"
MODELS = (QWEN, HAIKU, GPT, GEMINI, SONNET, FABLE)
CONFIRMATORY = (QWEN, HAIKU, SONNET)
DESCRIPTIVE = (GPT, GEMINI, FABLE)
SHORT = {QWEN: "Qwen", HAIKU: "Haiku", GPT: "Gpt", GEMINI: "Gemini", SONNET: "Sonnet", FABLE: "Fable"}
POOLED = "pooled"
RNG_MODEL = {QWEN: "qwen", HAIKU: "haiku", GPT: "gpt", GEMINI: "gemini", SONNET: "sonnet", FABLE: "fable",
             POOLED: "pooled"}  # GAP 5

CONFIGS = ("none", "cas_available", "locks", "all_available")
CFG_SHORT = {"none": "None", "cas_available": "Cas", "locks": "Locks", "all_available": "All"}
FAMILIES = ("inventory_last_unit", "transfer_shared_source", "budget_write_skew", "seat_same",
            "joint_account_write_skew", "inventory_still_valid", "ticket_same")
H1_CONFIGS = ("cas_available", "locks", "all_available")
H4_CONFIGS = ("locks", "all_available")
H3_CONFIGS = ("locks", "all_available")
LEAK_CONFIGS = ("locks", "all_available")  # GAP 11: Check 1 uses only the configs that offer acquire_lock
CAP24_CONFIGS = ("locks", "all_available")

N_BOOT = 10_000
N_SIGNFLIP_MC = 100_000
MC_RECOMPUTE_FACTOR = 10  # N6: a p within 2 MC SE of its Holm level is recomputed with 10 x the draws
SIGNFLIP_MAX_DENOM = 10_000
SEED = "20261103"
ALPHA = 0.05
DELTA_CELL = 0.25  # per (model, config); see Sample size rationale
DELTA_POOLED = 0.15
ELIGIBILITY_MAX = 0.80
MIN_UNIT_FRACTION = 0.75  # GAP 10: 75 % of the registered units (clusters, or (family, instance) probe units)
EPS = 1e-12
VAR_EPS = 1e-12
T_TOL = 1e-9  # ties of t* with t count against rejection

AGENT_ERROR_ENDS = ("truncated", "provider_error", "error")  # score5.ERROR_ENDS
# Round 4: score5.REFUSAL_ENDS (the end_reason of an agent whose reply without a tool call stopped for a refusal or a
# safety filter) and the per-completion stop reasons behind them (model_agent5.REFUSAL_END keys)
REFUSAL_ENDS = ("refusal", "content_filter")
REFUSAL_STOPS = ("content_filter", "refusal")
# Round 3 per-agent scorer fields (score5._protection_timing); an agent score without them is pre-Round-3 output
ROUND3_AGENT_FIELDS = ("first_protective", "first_protective_call", "first_contention_call", "protect_before_contention",
                       "contention_signals", "first_lock_call", "lock_after_contention")
REQUIRED_HOST = {QWEN: "alibaba"}  # a written completion from another host: excluded with its partner
FLAGGED_HOST = {GPT: "openai"}  # kept and flagged (sensitivity 5)

# GAP 5: the <test> field of the RNG key
RNG_TEST = {"H1-eq": "H1eq", "H1-diff": "H1diff", "H1cal-eq": "H1caleq", "H1cal-diff": "H1caldiff", "H2a": "H2a",
            "H2b": "H2b", "H2c": "H2c", "H2d": "H2d", "H3": "H3", "H4-eq": "H4eq", "H4-diff": "H4diff", "H4b": "H4b",
            "leakage": "check1", "exposure": "check2"}
H2_CONTRASTS = {  # name: (config A, config B, outcome, source)
    "H2a": ("all_available", "locks", "lock", "episodes"),
    "H2b": ("all_available", "cas_available", "cas", "episodes"),
    "H2c": ("locks", "cas_available", "prim", "episodes"),
    "H2d": ("all_available", "locks", "fr_lock", "probes"),
}
OUTCOME_NOUN = {"H1": "integrity failures", "H1cal": "integrity failures", "H4": "primitive uptake"}


# ---------------------------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------------------------


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs)


def sd(xs: Sequence[float]) -> float:
    m = len(xs)
    if m < 2:
        return 0.0
    mu = mean(xs)
    v = sum((x - mu) ** 2 for x in xs) / (m - 1)
    return math.sqrt(v) if v > VAR_EPS else 0.0


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def reply_codes(code: Any) -> Tuple[str, ...]:
    """Tokens of a ``first_reply`` code (``read+lock`` -> ``('read', 'lock')``)."""
    if not code or not isinstance(code, str):
        return ()
    return tuple(c for c in code.split("+") if c)


def host_norm(h: Any) -> str:
    return str(h or "").lower().replace(" ", "")


def _ceil_frac(n: int, frac: float) -> int:
    return int(math.ceil(n * frac - 1e-9))


def rng_key(test: str, model: str, config: str, sens: Optional[int] = None) -> str:
    """``20261103|<test>|<model>|<config>`` (registration, Bootstrap); ``|sens<k>`` in sensitivity analysis k."""
    k = f"{SEED}|{RNG_TEST.get(test, test)}|{RNG_MODEL.get(model, model)}|{config}"
    return k + (f"|sens{sens}" if sens else "")


# ---------------------------------------------------------------------------------------------------------------
# Distributions (stdlib)
# ---------------------------------------------------------------------------------------------------------------


def _betacf(a: float, b: float, x: float) -> float:
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e300
        de = d * c
        h *= de
        if abs(de - 1.0) < 3e-14:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lbt) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbt) * _betacf(b, a, 1 - x) / b


def t_sf(t: float, df: int) -> float:
    """P(T > t), T ~ Student t with df degrees of freedom."""
    if math.isinf(t):
        return 0.0 if t > 0 else 1.0
    tail = 0.5 * betainc(df / 2.0, 0.5, df / (df + t * t))
    return tail if t > 0 else 1.0 - tail


def binom_tail(k: int, n: int) -> float:
    """P(X >= k), X ~ Binomial(n, 1/2); 1.0 when n = 0."""
    if n == 0:
        return 1.0
    return sum(math.comb(n, j) for j in range(k, n + 1)) / 2 ** n


# ---------------------------------------------------------------------------------------------------------------
# Decision tests
# ---------------------------------------------------------------------------------------------------------------


def sign_test(values: Sequence[float], theta0: float, alt: str) -> Dict[str, Any]:
    """Exact one-sided sign test against theta0, ties dropped (reported; the decision only when SE = 0)."""
    above = sum(v > theta0 + EPS for v in values)
    below = sum(v < theta0 - EPS for v in values)
    k = above if alt == "greater" else below
    return {"k": k, "n": above + below, "p": binom_tail(k, above + below)}


def _as_integers(values: Sequence[float], max_den: int = SIGNFLIP_MAX_DENOM) -> Optional[List[int]]:
    """The cluster values as integers over their common denominator, or None if it exceeds ``max_den``."""
    fr = []
    for v in values:
        f = Fraction(v).limit_denominator(max_den)
        if abs(float(f) - v) > 1e-9:
            return None
        fr.append(f)
    den = 1
    for f in fr:
        den = den * f.denominator // math.gcd(den, f.denominator)
        if den > max_den:
            return None
    return [int(f * den) for f in fr]


def signflip(values: Sequence[float], alt: str, key: str, n_mc: int = N_SIGNFLIP_MC) -> Dict[str, Any]:
    """Sign-flip permutation test of H0 theta = 0 on cluster values (registration, Decision tests).

    One-sided p: the share of the 2^m sign assignments whose sum is at or above (``greater``) or at or below
    (``less``) the observed sum. Exact (counted over all 2^m assignments by dynamic programming over the values as
    integers on their common denominator). Monte Carlo only if that denominator exceeds 10,000: R draws of
    ``random.Random(key + '|signflip').getrandbits(m)``, bit j flipping the j-th value; p = (1 + #{S* >= S})/(R + 1).
    """
    m = len(values)
    if m == 0:
        return {"p": None, "method": "none"}
    ints = _as_integers(values)
    if ints is not None:
        counts: Dict[int, int] = {0: 1}
        zeros = 0
        for a in ints:
            if a == 0:
                zeros += 1
                continue
            nxt: Dict[int, int] = {}
            for s, c in counts.items():
                nxt[s + a] = nxt.get(s + a, 0) + c
                nxt[s - a] = nxt.get(s - a, 0) + c
            counts = nxt
        obs = sum(ints)
        tot = 2 ** (m - zeros)
        hit = sum(c for s, c in counts.items() if (s >= obs if alt == "greater" else s <= obs))
        return {"p": hit / tot, "method": "exact", "n": m}
    rng = random.Random(key + "|signflip")
    x = list(values)
    total = sum(x)
    tables = []
    for start in range(0, m, 8):
        chunk = x[start:start + 8]
        tab = [0.0] * 256
        for byte in range(256):
            tab[byte] = sum(v for j, v in enumerate(chunk) if (byte >> j) & 1)
        tables.append(tab)
    hit = 0
    for _ in range(n_mc):
        bits = rng.getrandbits(m)
        flipped = 0.0
        for tab in tables:
            flipped += tab[bits & 255]
            bits >>= 8
        s = total - 2.0 * flipped
        hit += (s >= total - 1e-9) if alt == "greater" else (s <= total + 1e-9)
    return {"p": (1 + hit) / (n_mc + 1), "method": "monte_carlo", "R": n_mc, "n": m}


def boot(values: Mapping[Any, float], key: str, n_boot: int = N_BOOT) -> Dict[str, Any]:
    """Cluster bootstrap of the mean of cluster values (registration, Bootstrap).

    Clusters in sorted key order; resample b uses draws b*m .. (b+1)*m - 1 of ``random.Random(key).choices(range(m),
    k=m*B)``. Returns the resample means (percentile intervals, Study 1 p) and the studentized resamples
    t*_b = (mean*_b - mean) / SE*_b, with SE* = sd(m - 1)/sqrt(m) and SE*_b = 0 replaced by the observed SE.
    """
    keys = sorted(values, key=str)
    x = [float(values[k]) for k in keys]
    m = len(x)
    est = mean(x)
    se = sd(x) / math.sqrt(m) if m > 1 else 0.0
    x2 = [v * v for v in x]
    rng = random.Random(key)
    draws = rng.choices(range(m), k=m * n_boot)
    means, ts = [], []
    for b in range(n_boot):
        sl = draws[b * m:(b + 1) * m]
        s = sum(map(x.__getitem__, sl))
        mb = s / m
        if m > 1:
            var = (sum(map(x2.__getitem__, sl)) - s * s / m) / (m - 1)
            seb = math.sqrt(var / m) if var > VAR_EPS else 0.0
        else:
            seb = 0.0
        if seb <= EPS:
            seb = se
        means.append(mb)
        ts.append((mb - est) / seb if seb > EPS else 0.0)
    means.sort()
    ts.sort()
    return {"keys": keys, "x": x, "m": m, "estimate": est, "se": se, "means": means, "ts": ts, "B": n_boot}


def _pct(stats: Sequence[float], lo: float, hi: float) -> List[float]:
    b = len(stats)
    return [stats[int(math.floor(lo * b))], stats[int(math.ceil(hi * b)) - 1]]  # GAP 5


def t_interval(bs: Mapping[str, Any], level_a: float) -> List[float]:
    """Bootstrap-t interval at 1 - 2a: [est - q*_{1-a} SE, est - q*_a SE]."""
    if bs["se"] <= EPS:
        return [bs["estimate"], bs["estimate"]]
    q_lo, q_hi = _pct(bs["ts"], level_a, 1 - level_a)
    return [bs["estimate"] - q_hi * bs["se"], bs["estimate"] - q_lo * bs["se"]]


def _count_le(sorted_xs: Sequence[float], v: float) -> int:
    lo, hi = 0, len(sorted_xs)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_xs[mid] <= v:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _count_lt(sorted_xs: Sequence[float], v: float) -> int:
    lo, hi = 0, len(sorted_xs)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_xs[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    return lo


def tost_side(bs: Mapping[str, Any], theta0: float, alt: str) -> Dict[str, Any]:
    """One TOST side (registration, Decision tests). ``alt='less'``: H0 theta >= theta0 (theta0 = +delta),
    p = (1 + #{t* <= t})/(B + 1); ``alt='greater'``: H0 theta <= theta0 (theta0 = -delta), p = (1 + #{t* >= t})/(B + 1).
    If SE = 0 (all cluster values equal) the decision p is the exact one-sided sign test against theta0."""
    B, est, se = bs["B"], bs["estimate"], bs["se"]
    means, ts = bs["means"], bs["ts"]
    sg = sign_test(bs["x"], theta0, alt)
    if alt == "less":
        p_pct = (1 + B - _count_lt(means, theta0 - EPS)) / (B + 1)
    else:
        p_pct = (1 + _count_le(means, theta0 + EPS)) / (B + 1)
    if se <= EPS:
        return {"theta0": theta0, "alternative": alt, "method": "sign_test_se0", "p": sg["p"], "p_percentile": p_pct,
                "p_sign": sg["p"], "t": None}
    t = (est - theta0) / se
    if alt == "less":
        p = (1 + _count_le(ts, t + T_TOL)) / (B + 1)
    else:
        p = (1 + (B - _count_le(ts, t - T_TOL))) / (B + 1)
    return {"theta0": theta0, "alternative": alt, "method": "bootstrap_t", "p": p, "p_percentile": p_pct,
            "p_sign": sg["p"], "t": t}


def family_level(values: Mapping[Tuple[Any, ...], float], kind: str, delta: Optional[float]) -> Optional[float]:
    """Sensitivity 7 (template level, GAP 21): the family means of the cluster values (key starts with family).
    TOST: a t-test (df = families - 1) at -delta and +delta, the larger p. theta0 = 0: the exact sign-flip test over
    all 2^f assignments (two-sided: twice the smaller side, capped at 1)."""
    fams: Dict[Any, List[float]] = {}
    for k in sorted(values, key=str):
        fams.setdefault(k[0], []).append(values[k])
    x = [mean(v) for _, v in sorted(fams.items(), key=lambda kv: str(kv[0]))]
    f = len(x)
    if f < 2:
        return None
    if kind == "tost":
        s = sd(x)
        if s <= EPS:
            return 0.0 if abs(mean(x)) < delta else 1.0  # type: ignore[operator]
        se = s / math.sqrt(f)
        p_hi = 1 - t_sf((mean(x) - delta) / se, f - 1)  # type: ignore[operator]
        p_lo = t_sf((mean(x) + delta) / se, f - 1)  # type: ignore[operator]
        return max(p_hi, p_lo)
    ints = _as_integers(x, 10 ** 9)
    vals = x if ints is None else ints
    obs = sum(vals)
    ge = le = 0
    for mask in range(1 << f):
        s = sum(-v if (mask >> j) & 1 else v for j, v in enumerate(vals))
        ge += s >= obs - (0 if ints is not None else 1e-9)
        le += s <= obs + (0 if ints is not None else 1e-9)
    pg, pl = ge / (1 << f), le / (1 << f)
    if kind == "greater":
        return pg
    return min(1.0, 2 * min(pg, pl))


def run_test(test: str, model: str, config: str, values: Mapping[Tuple[Any, ...], float], kind: str,
             delta: Optional[float] = None, n_boot: int = N_BOOT, describe_only: bool = False,
             sens: Optional[int] = None, key_suffix: str = "") -> Dict[str, Any]:
    """``kind``: ``greater`` (H0 theta <= 0, sign-flip), ``two_sided`` (H0 theta = 0, sign-flip), ``tost``
    (H0 |theta| >= delta, bootstrap-t sides). ``values``: cluster -> cluster value (for pooled tests, the pooled
    cluster values)."""
    key = rng_key(test, model, config, sens) + key_suffix
    out: Dict[str, Any] = {"kind": kind, "delta": delta, "n_clusters": len(values), "rng_key": key}
    if not values:
        out.update(estimate=None, p=None)
        return out
    bs = boot(values, key, n_boot)
    out.update(estimate=bs["estimate"], se=bs["se"], ci95=_pct(bs["means"], 0.025, 0.975),
               ci90=_pct(bs["means"], 0.05, 0.95), B=n_boot)
    if kind == "tost":
        out["ci90_t"] = t_interval(bs, 0.05)
        out["_bs"] = bs  # Holm-consistent interval and N6 recompute; stripped before output
    if describe_only:
        out["p"] = None
        return out
    x = bs["x"]
    if kind == "tost":
        lo, hi = tost_side(bs, -delta, "greater"), tost_side(bs, delta, "less")  # type: ignore[operator]
        out.update(sides=[lo, hi], p=max(lo["p"], hi["p"]), p_percentile=max(lo["p_percentile"], hi["p_percentile"]),
                   p_sign=max(lo["p_sign"], hi["p_sign"]),
                   mc=any(s["method"] == "bootstrap_t" for s in (lo, hi)))
    else:
        g = signflip(x, "greater", key)
        sg_g = sign_test(x, 0.0, "greater")
        pp_g = (1 + _count_le(bs["means"], EPS)) / (n_boot + 1)
        if kind == "greater":
            out.update(p=g["p"], method=g["method"], p_sign=sg_g["p"], p_percentile=pp_g, mc=g["method"] == "monte_carlo")
        else:
            l_ = signflip(x, "less", key)
            sg_l = sign_test(x, 0.0, "less")
            pp_l = (1 + n_boot - _count_lt(bs["means"], -EPS)) / (n_boot + 1)
            out.update(p=min(1.0, 2 * min(g["p"], l_["p"])), method=g["method"],
                       p_sign=min(1.0, 2 * min(sg_g["p"], sg_l["p"])), p_percentile=min(1.0, 2 * min(pp_g, pp_l)),
                       mc=g["method"] == "monte_carlo")
    out["p_family_level"] = family_level(values, kind, delta)
    out["_values"] = dict(values)
    return out


# ---------------------------------------------------------------------------------------------------------------
# src5 (read-only, lazily imported)
# ---------------------------------------------------------------------------------------------------------------

_SRC5: Dict[str, Any] = {}


def src5_modules(src5_dir: Optional[str]) -> Dict[str, Any]:
    """``{'score5', 'instances5', 'ledger_from_transcript'}`` or ``{'error': ...}``. Never writes into src5."""
    key = src5_dir or ""
    if key in _SRC5:
        return _SRC5[key]
    if not src5_dir or not os.path.isdir(src5_dir):
        _SRC5[key] = {"error": f"no src5 directory {src5_dir!r}"}
        return _SRC5[key]
    sys.dont_write_bytecode = True
    if src5_dir not in sys.path:
        sys.path.insert(0, src5_dir)
    out: Dict[str, Any] = {}
    try:
        import instances5  # type: ignore
        import score5  # type: ignore
        out["instances5"], out["score5"] = instances5, score5
    except Exception as e:  # pragma: no cover - depends on the other agent's edits
        _SRC5[key] = {"error": f"import failed: {type(e).__name__}: {e}"}
        return _SRC5[key]
    try:
        from rescore5 import ledger_from_transcript  # type: ignore
        out["ledger_from_transcript"] = ledger_from_transcript
    except Exception:
        out["ledger_from_transcript"] = _ledger_from_transcript_fallback
    _SRC5[key] = out
    return out


def _ledger_from_transcript_fallback(tr: Mapping[str, Any]):
    from records5 import AgentEnd, CallRecord, Ledger, WriteEffect, coerce_value, kind_of  # type: ignore
    val = lambda rid, v: coerce_value(kind_of(rid), v)  # noqa: E731
    led = Ledger()
    led.effects = [WriteEffect(**{**e, "old_value": val(e["record_id"], e["old_value"]),
                                  "new_value": val(e["record_id"], e["new_value"])}) for e in tr["ledger"]["effects"]]
    led.calls = [CallRecord(**c) for c in tr["ledger"]["calls"]]
    led.agent_ends = [AgentEnd(**{**e, "locks_held": tuple(e.get("locks_held") or ())}) for e in tr["ledger"]["agent_ends"]]
    led.flags = dict(tr["ledger"]["flags"])
    snap = {rid: (val(rid, d["value"]), int(d["version"])) for rid, d in tr["final_store"].items()}
    return led, snap


# ---------------------------------------------------------------------------------------------------------------
# Normalising one transcript
# ---------------------------------------------------------------------------------------------------------------


class ScorerVersionError(ValueError):
    """A transcript scored by a pre-Round-3 ``score5`` (no peer-caused contention fields)."""


def agent_view(s: Mapping[str, Any], raw: Mapping[str, Any]) -> Dict[str, Any]:
    """The per-agent measures the tests use, from one ``score.agents`` entry (``s``) and ``agents.<id>`` (``raw``).

    Timing measures are score5's own columns (``score5._protection_timing`` over ``score5.peer_signal_calls``), never
    recomputed here: ``exposed`` = ``contention_signals`` > 0; ``at_risk`` (H4b's denominator, the q gate) = exposed
    and ``protect_before_contention`` not True; ``reacting`` (H4b's numerator) = ``protect_before_contention`` is
    False. score5 counts a lock or CAS call whose own response is the first signal as protection before contention
    (``<=``), so such an agent is not at risk. ``lock_after_contention`` is score5's reactive-locking flag."""
    missing = [f for f in ROUND3_AGENT_FIELDS if f not in s]
    if missing:
        raise ScorerVersionError(f"agent score lacks Round 3 fields {missing}: re-score with the frozen src5/score5.py")
    turns = raw.get("turns") or []
    fp_call, fc_call = s["first_protective_call"], s["first_contention_call"]
    pbc = s["protect_before_contention"]
    n_sig = int(s["contention_signals"] or 0)
    if (n_sig > 0) != (fc_call is not None):
        raise ScorerVersionError(f"contention_signals={n_sig} disagrees with first_contention_call={fc_call}")
    codes = reply_codes(raw.get("first_reply"))
    return {
        "lock": bool(s.get("lock")),
        "cas": bool(s.get("cas")),
        "prim": s.get("first_protective") is not None,
        "fp": s.get("first_protective"),
        "fp_call": fp_call,
        "fc_call": fc_call,
        "exposed": n_sig > 0,
        "pbc": pbc,
        "at_risk": n_sig > 0 and pbc is not True,  # H4b's denominator (S1 gate)
        "reacting": n_sig > 0 and pbc is False,    # H4b's numerator
        "lock_after": s["lock_after_contention"] is True,
        "end": s.get("end_reason"),
        "fulfilled": bool(s.get("fulfilled")),
        "first_reply": raw.get("first_reply"),
        "fr_lock": "lock" in codes,
        "fr_prim": bool({"lock", "cas"} & set(codes)),
        "last_stop": turns[-1].get("stop_reason") if turns else None,
        "truncated": bool(raw.get("truncated")),
    }


def episode_measures(sc: Mapping[str, Any], raw_agents: Mapping[str, Any]) -> Dict[str, Any]:
    """Episode measures from a score dict (stored, or re-scored at the 24-call cap)."""
    agents = {a: agent_view(s, raw_agents.get(a) or {}) for a, s in sorted((sc.get("agents") or {}).items())}
    outcome = sc.get("outcome")
    # GAP 3: one definition, score5's: failed and some agent ended turn_cap (field ``cap_truncated``)
    cap = sc.get("cap_truncated")
    if cap is None:
        cap = outcome == "failed" and any(a["end"] == "turn_cap" for a in agents.values())
    inter = sc.get("interleaving") or {}
    return {
        "fs": int(bool(sc.get("fs_nonserializable"))),
        "basis": int(bool(sc.get("dsg_basis_cycle"))),
        "outcome": outcome,
        "cap_truncated": bool(cap),
        "reads_overlap": inter.get("reads_overlap"),
        "cross_agent_edges": int(sc.get("cross_agent_edges") or 0),
        "agents": agents,
    }


def normalize(tr: Mapping[str, Any], path: str, src5_dir: Optional[str], allow_dry_run: bool,
              want_cap24: bool = True) -> Dict[str, Any]:
    t = tr.get("task") or {}
    factory = str(t.get("factory") or "")
    family = str(t.get("family") or factory.replace("_ctrl", ""))
    if family.endswith("_ctrl"):
        family = family[: -len("_ctrl")]
    arm = "control" if factory.endswith("_ctrl") or t.get("category") == "control" else "contended"
    sc = tr.get("score") or {}
    raw_agents = tr.get("agents") or {}
    model = tr.get("model")
    dry = bool(tr.get("dry_run"))
    rec: Dict[str, Any] = {
        "id": tr.get("episode_id"), "path": path, "model": model, "config": tr.get("config"),
        "aware": int(bool(tr.get("concurrency_aware_prompt"))), "probe": bool(tr.get("probe")),
        "study": tr.get("study"), "dry_run": dry, "n_agents": tr.get("n_agents"), "family": family, "arm": arm,
        "instance": int(t.get("instance", -1)), "seed": int(tr.get("seed", 0) or 0),
    }
    rec.update(episode_measures(sc, raw_agents))
    run_info = tr.get("run_info") or {}
    rec["order_key"] = (str(run_info.get("started_utc") or ""), os.path.basename(path))
    trig = []
    for a, av in rec["agents"].items():
        if av["end"] in AGENT_ERROR_ENDS or av["end"] in REFUSAL_ENDS or av["truncated"]:
            trig.append(f"{a}:{av['end'] if av['end'] in AGENT_ERROR_ENDS + REFUSAL_ENDS else 'truncated'}")
    for a, raw in sorted(raw_agents.items()):
        turns = raw.get("turns") or []
        if turns and turns[-1].get("stop_reason") in REFUSAL_STOPS:
            trig.append(f"{a}:{turns[-1].get('stop_reason')}")
    rec["exclusion_trigger"] = ";".join(sorted(set(trig))) or None
    rec["errored_agents"] = sorted({x.split(":")[0] for x in trig})
    turns = [tu for _, raw in sorted(raw_agents.items()) for tu in (raw.get("turns") or [])]
    hosts = sorted({host_norm(tu.get("served_host")) for tu in turns})
    rec["hosts"] = hosts
    rec["served"] = sorted({str(tu.get("model_served")) for tu in turns})

    def bad(prefix: str) -> bool:
        return any(not h.startswith(prefix) and not (h == "fake" and dry and allow_dry_run) for h in hosts)

    rec["host_bad"] = model in REQUIRED_HOST and bad(REQUIRED_HOST[model])
    rec["host_flag"] = model in FLAGGED_HOST and bad(FLAGGED_HOST[model])
    if "mutual_exclusion_violations" in sc:
        rec["me_violations"] = list(sc.get("mutual_exclusion_violations") or [])
    else:
        rec["me_violations"] = None
        mods = src5_modules(src5_dir) if tr.get("ledger") else {"error": "no ledger"}
        fn = getattr(mods.get("score5"), "mutual_exclusion_violations", None)
        if fn is not None:
            try:
                led, _ = mods["ledger_from_transcript"](tr)
                rec["me_violations"] = list(fn(led))
            except Exception as e:  # pragma: no cover
                rec["me_violations_error"] = f"{type(e).__name__}: {e}"
    rec["cap24"] = None
    if want_cap24 and not rec["probe"] and rec["config"] in CAP24_CONFIGS:
        rec["cap24"] = cap24_rescore(tr, src5_dir)
    return rec


def cap24_rescore(tr: Mapping[str, Any], src5_dir: Optional[str]) -> Dict[str, Any]:
    """Sensitivity 1: ``score5.rescore_at_cap`` at 24 calls. Status unchanged | rescored | indeterminate, or
    not_available (no ledger, or src5 missing). GAP 2: indeterminate episodes are dropped with their partners."""
    if not tr.get("ledger") or not tr.get("final_store"):
        return {"status": "not_available", "reason": "no ledger"}
    mods = src5_modules(src5_dir)
    fn = getattr(mods.get("score5"), "rescore_at_cap", None)
    if fn is None:
        return {"status": "not_available", "reason": mods.get("error") or "score5.rescore_at_cap missing"}
    try:
        task = mods["instances5"].build(tr["task"]["factory"], int(tr["task"]["instance"]), int(tr["n_agents"]))
        led, snap = mods["ledger_from_transcript"](tr)
        r = fn(task, led, snap, 24, config_name=tr["config"])
    except Exception as e:  # pragma: no cover
        return {"status": "not_available", "reason": f"{type(e).__name__}: {e}"}
    out: Dict[str, Any] = {"status": str(r.status), "reason": getattr(r, "reason", "")}
    if r.score is not None:
        out.update(episode_measures(r.score.to_dict(), tr.get("agents") or {}))
    return out


# ---------------------------------------------------------------------------------------------------------------
# Loading, block membership and exclusions
# ---------------------------------------------------------------------------------------------------------------


def discover(base: str, allow_dry_run: bool, probes_only: bool = False) -> List[str]:
    """Transcript directories of the registered lanes under ``base`` (rehearsal, validity, preflight never)."""
    sub = os.path.join("dry_run", "transcripts") if allow_dry_run else "transcripts"
    pats = ["probe-*"] if probes_only else ["n2-*", "probe-*"]
    out = []
    for p in pats:
        for d in sorted(glob.glob(os.path.join(base, p))):
            t = os.path.join(d, sub)
            if os.path.isdir(t):
                out.append(t)
    return out


def read_transcripts(dirs: Sequence[str]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.json"))):
            with open(path) as f:
                yield path, json.load(f)


def block_priority(rec: Mapping[str, Any], plan: Mapping[str, Any]) -> Optional[int]:
    """Lowest priority of a plan block that contains the row (0 probe, 1 core, 4 extension), or None."""
    best = None
    for b in plan.get("blocks", []):
        if b.get("model") != rec["model"] or (b.get("mode") == "probe") != rec["probe"]:
            continue
        if rec["config"] not in b.get("configs", []) or bool(rec["aware"]) not in [bool(x) for x in b.get("aware", [])]:
            continue
        if rec["family"] not in b.get("families", []) or not 0 <= rec["instance"] < int(b.get("instances", 0)):
            continue
        if not 0 <= rec["seed"] < int(b.get("schedules", 1)):
            continue
        if int(b.get("n", 2)) != rec["n_agents"]:
            continue
        best = int(b["priority"]) if best is None else min(best, int(b["priority"]))
    return best


def registered_units(plan: Mapping[str, Any], model: str, mode: str, config: str, aware: bool) -> Optional[Dict[str, int]]:
    """Families x instances (x schedules) of the core (mode episodes, priority 1) or probe block for a cell."""
    for b in plan.get("blocks", []):
        if b.get("model") != model or b.get("mode") != mode or config not in b.get("configs", []):
            continue
        if bool(aware) not in [bool(x) for x in b.get("aware", [])]:
            continue
        if (mode == "probe" and int(b["priority"]) != 0) or (mode == "episodes" and int(b["priority"]) != 1):
            continue
        return {"families": len(b["families"]), "instances": int(b["instances"]), "schedules": int(b.get("schedules", 1)),
                "clusters": len(b["families"]) * int(b["instances"])}
    return None


def pair_key(rec: Mapping[str, Any], arm: Optional[str] = None) -> Tuple[Any, ...]:
    return (rec["model"], rec["config"], rec["aware"], rec["family"], rec["instance"], rec["seed"], rec["probe"],
            arm or rec["arm"])


def other_arm(arm: str) -> str:
    return "control" if arm == "contended" else "contended"


def _cell(r: Mapping[str, Any]) -> str:
    return f"{SHORT.get(r['model'], r['model'])}|{r['config']}|aware{r['aware']}|{'probe' if r['probe'] else 'episode'}"


def select(recs: Sequence[Dict[str, Any]], plan: Mapping[str, Any], allow_dry_run: bool) -> Dict[str, Any]:
    """Never-data rules, block membership and the exclusion rule (registration, Data exclusion; GAP 1).

    The harness never re-runs a written episode. If an episode id has more than one transcript, the earliest
    (``run_info.started_utc``, then file name) is used and the others are counted. An episode or probe is excluded,
    with its pair partner, if an agent ended ``truncated``, ``provider_error``, ``error``, ``refusal`` or
    ``content_filter`` (score5.ERROR_ENDS, score5.REFUSAL_ENDS), or its last completion stopped ``content_filter`` or
    ``refusal`` (probes, and agents that refused with a tool call as their last completion), or (Qwen) a written completion was not served by Alibaba. The partner of
    an episode is the other arm with the same model, config, aware level, family, instance and schedule; of a probe,
    the other-arm probe of the same model, config, aware level, family and instance.

    Returns ``{'main', 'as_is', 'excluded_pairs', 'log'}``. ``as_is`` keeps every scored episode (sensitivity 3).
    """
    log: Dict[str, Any] = {"never_data": {}, "block": {}, "excluded": [], "flags": {}}

    def bump(d: Dict[str, int], k: str, n: int = 1) -> None:
        d[k] = d.get(k, 0) + n

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in recs:
        why = None
        if r["study"] not in (2, "2"):
            why = "not_study2"
        elif r["dry_run"] and not allow_dry_run:
            why = "dry_run"
        elif r["config"] not in CONFIGS:
            why = f"unregistered_config:{r['config']}"
        elif r["model"] not in MODELS:
            why = "unregistered_model"
        elif r["n_agents"] != 2:
            why = "n_agents"
        if why:
            bump(log["never_data"], why)
            continue
        pr = block_priority(r, plan)
        r["priority"] = pr
        bump(log["block"], "unplanned" if pr is None else f"priority_{pr}")
        if pr not in (0, 1):
            continue
        groups.setdefault(r["id"], []).append(r)

    main: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    as_is: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    excluded: Dict[Tuple[Any, ...], str] = {}
    counts: Dict[str, int] = {}
    by_arm: Dict[str, int] = {}
    for eid in sorted(groups):
        tries = sorted(groups[eid], key=lambda r: r["order_key"])
        chosen = tries[0]
        if len(tries) > 1:
            bump(counts, "duplicate_transcripts_ignored", len(tries) - 1)
        as_is[pair_key(chosen)] = chosen
        why = "wrong_host" if chosen["host_bad"] else ("agent_error_or_refusal" if chosen["exclusion_trigger"] else None)
        if why:
            excluded[pair_key(chosen)] = why
            bump(counts, why)
            bump(by_arm, f"{_cell(chosen)}|{chosen['arm']}|{why}")
        else:
            main[pair_key(chosen)] = chosen
    pairs = set()
    for k, why in sorted(excluded.items(), key=lambda kv: str(kv[0])):
        pk = k[:-1] + (other_arm(k[-1]),)
        pairs.add(k[:-1])
        if pk in main:
            r = main.pop(pk)
            excluded[pk] = f"partner_of:{why}"
            bump(counts, "partner_excluded")
            bump(by_arm, f"{_cell(r)}|{r['arm']}|partner")
    log["excluded"] = [{"key": list(map(str, k)), "reason": v} for k, v in sorted(excluded.items(), key=lambda kv: str(kv[0]))]
    log["counts"] = dict(sorted(counts.items()))
    log["excluded_by_cell_and_arm"] = dict(sorted(by_arm.items()))
    log["flags"] = {
        "gpt_non_openai_host_episodes": sum(1 for r in main.values() if r["host_flag"]),
        "cap_truncated_episodes": sum(1 for r in main.values() if not r["probe"] and r["cap_truncated"]),
    }
    return {"main": main, "as_is": as_is, "excluded_pairs": sorted(pairs, key=str), "log": log}


def failure_counts(dirs: Sequence[str]) -> Dict[str, int]:
    """Provider failures (``failures.jsonl`` next to each transcript directory) per episode cell."""
    out: Dict[str, int] = {}
    for d in dirs:
        p = os.path.join(os.path.dirname(d), "failures.jsonl")
        if not os.path.exists(p):
            continue
        with open(p) as f:
            for line in f:
                try:
                    eid = json.loads(line).get("episode_id", "?")
                except ValueError:
                    eid = "?"
                parts = str(eid).split("__")
                k = "|".join(parts[:2]) if len(parts) >= 2 else "unparsed"
                out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------------------------------------------
# Budget: spend on the shared OpenRouter key by other projects (registration, Stopping rule)
# ---------------------------------------------------------------------------------------------------------------


def balance_report(base: Optional[str]) -> Dict[str, Any]:
    """Reads ``<base>/openrouter_balance.jsonl`` (``analysis5/balance5.py``: one line before and one after the OpenRouter
    lane, each run) and every Study 2 ``spend.jsonl`` under ``base``. Per window: key usage change, Study 2 OpenRouter
    spend in the window, and the rest (spend by others). A window whose lane exited 4 (credit or key limit) with
    others' spend above $0.01 is a stop by an external cause."""
    if not base:
        return {"status": "no_base"}
    p = os.path.join(base, "openrouter_balance.jsonl")
    if not os.path.exists(p):
        return {"status": "no_balance_log"}
    rows = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    spend = []
    for sp in sorted(glob.glob(os.path.join(base, "**", "spend.jsonl"), recursive=True)):
        with open(sp) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("provider_family") == "openrouter":
                    spend.append((str(e.get("at_utc") or ""), float(e.get("cost_usd") or 0.0)))
    windows = []
    before = None
    for r in rows:
        if r.get("phase") == "before":
            before = r
        elif r.get("phase") == "after" and before is not None:
            t0, t1 = str(before.get("at_utc")), str(r.get("at_utc"))
            used = None if before.get("usage_usd") is None or r.get("usage_usd") is None else \
                float(r["usage_usd"]) - float(before["usage_usd"])
            ours = sum(c for t, c in spend if t0 <= t <= t1)
            others = None if used is None else used - ours
            windows.append({"from_utc": t0, "to_utc": t1, "key_usage_change_usd": used, "study2_spend_usd": ours,
                            "others_spend_usd": others, "lane_exit": r.get("lane_exit"),
                            "stopped_by_external_cause": bool(r.get("lane_exit") == 4 and others is not None and others > 0.01)})
            before = None
    return {"status": "done", "windows": windows, "unclosed_window": before is not None}


# ---------------------------------------------------------------------------------------------------------------
# Cluster values per test
# ---------------------------------------------------------------------------------------------------------------


class Data:
    """Index of the selected episodes and probes."""

    def __init__(self, sample: Mapping[Tuple[Any, ...], Dict[str, Any]]):
        self.ep: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        self.pr: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for k, r in sample.items():
            if r["probe"]:
                self.pr[(r["model"], r["config"], r["aware"], r["family"], r["instance"], r["arm"])] = r
            else:
                self.ep[(r["model"], r["config"], r["aware"], r["family"], r["instance"], r["seed"], r["arm"])] = r

    def clusters(self, model: str, config: str, aware: int = 0) -> List[Tuple[str, int]]:
        return sorted({(k[3], k[4]) for k in self.ep if k[0] == model and k[1] == config and k[2] == aware})

    def seeds(self, model: str, config: str, aware: int, fam: str, inst: int) -> List[int]:
        return sorted({k[5] for k in self.ep if k[:5] == (model, config, aware, fam, inst)})

    def pairs(self, model: str, config: str, fam: str, inst: int, aware: int = 0) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        out = []
        for s in self.seeds(model, config, aware, fam, inst):
            c = self.ep.get((model, config, aware, fam, inst, s, "contended"))
            k = self.ep.get((model, config, aware, fam, inst, s, "control"))
            if c is not None and k is not None:
                out.append((c, k))
        return out


def agent_rate(eps: Sequence[Mapping[str, Any]], outcome: str) -> Optional[float]:
    vals = [bool(a[outcome]) for e in eps for a in e["agents"].values()]
    return sum(vals) / len(vals) if vals else None


def h4_outcome(config: str) -> str:
    return "lock" if config == "locks" else "prim"


def h1_values(D: Data, model: str, config: str, metric: str = "fs") -> Dict[Tuple[Any, ...], float]:
    out = {}
    for fam, inst in D.clusters(model, config):
        d = [c[metric] - k[metric] for c, k in D.pairs(model, config, fam, inst)]
        if d:
            out[(fam, inst)] = mean(d)
    return out


def h4_values(D: Data, model: str, config: str) -> Dict[Tuple[Any, ...], float]:
    out, o = {}, h4_outcome(config)
    for fam, inst in D.clusters(model, config):
        p = D.pairs(model, config, fam, inst)
        if p:
            rc, rk = agent_rate([c for c, _ in p], o), agent_rate([k for _, k in p], o)
            if rc is not None and rk is not None:
                out[(fam, inst)] = rc - rk
    return out


def q_values(D: Data, model: str, config: str) -> Dict[Tuple[Any, ...], float]:
    """S1 informativeness gate: per H4 cluster, the share of contended agents exposed and not protected before their
    first signal (H4b's denominator), over the complete pairs H4 uses."""
    out = {}
    for fam, inst in D.clusters(model, config):
        r = agent_rate([c for c, _ in D.pairs(model, config, fam, inst)], "at_risk")
        if r is not None:
            out[(fam, inst)] = r
    return out


def exposure_values(D: Data, model: str, config: str, aware: int = 0,
                    family: Optional[str] = None) -> Dict[Tuple[Any, ...], float]:
    """Check 2: share of contended agents exposed (score5 ``contention_signals`` > 0, i.e. ``first_contention_call``
    not None), per cluster, over every kept contended episode."""
    out = {}
    for fam, inst in D.clusters(model, config, aware):
        if family is not None and fam != family:
            continue
        eps = [D.ep[(model, config, aware, fam, inst, s, "contended")] for s in D.seeds(model, config, aware, fam, inst)
               if (model, config, aware, fam, inst, s, "contended") in D.ep]
        r = agent_rate(eps, "exposed")
        if r is not None:
            out[(fam, inst)] = r
    return out


def h2_values(D: Data, model: str, contrast: str) -> Dict[Tuple[Any, ...], float]:
    """GAP 15 / F1. Episodes: a unit is (family, instance, schedule, arm) with both configs; unit value = the
    difference of the per-episode agent shares; cluster value = mean over its units. Probes (H2d): a0, aware off,
    paired by (family, instance)."""
    ca, cb, o, src = H2_CONTRASTS[contrast]
    out: Dict[Tuple[Any, ...], float] = {}
    if src == "probes":
        units = sorted({(k[3], k[4]) for k in D.pr if k[0] == model and k[2] == 0 and k[5] == "contended"})
        for fam, inst in units:
            a = D.pr.get((model, ca, 0, fam, inst, "contended"))
            b = D.pr.get((model, cb, 0, fam, inst, "contended"))
            if a and b and "a0" in a["agents"] and "a0" in b["agents"]:
                out[(fam, inst)] = float(a["agents"]["a0"][o]) - float(b["agents"]["a0"][o])
        return out
    acc: Dict[Tuple[Any, ...], List[float]] = {}
    for k, ea in sorted(D.ep.items(), key=lambda kv: str(kv[0])):
        if k[0] != model or k[1] != ca or k[2] != 0:
            continue
        eb = D.ep.get((model, cb) + k[2:])
        if eb is None:
            continue
        ra, rb = agent_rate([ea], o), agent_rate([eb], o)
        if ra is not None and rb is not None:
            acc.setdefault((k[3], k[4]), []).append(ra - rb)
    return {c: mean(v) for c, v in sorted(acc.items())}


def h3_values(D: Data, model: str) -> Tuple[Dict[Tuple[Any, ...], float], Dict[str, Dict[Tuple[Any, ...], float]]]:
    """Per (family, instance): mean over locks and all_available of [lock_on - lock_off] (a0, first reply). A unit
    needs on/off pairs in both configs (GAP 16). Also the per-config values (reported, no test)."""
    units = sorted({(k[3], k[4]) for k in D.pr if k[0] == model and k[5] == "contended"})
    per_cfg: Dict[str, Dict[Tuple[Any, ...], float]] = {c: {} for c in H3_CONFIGS}
    for fam, inst in units:
        for c in H3_CONFIGS:
            on = D.pr.get((model, c, 1, fam, inst, "contended"))
            off = D.pr.get((model, c, 0, fam, inst, "contended"))
            if on and off and "a0" in on["agents"] and "a0" in off["agents"]:
                per_cfg[c][(fam, inst)] = float(on["agents"]["a0"]["fr_lock"]) - float(off["agents"]["a0"]["fr_lock"])
    both = {u: mean([per_cfg[c][u] for c in H3_CONFIGS]) for u in units if all(u in per_cfg[c] for c in H3_CONFIGS)}
    return both, per_cfg


def leakage_values(D: Data, model: str) -> Dict[Tuple[Any, ...], float]:
    """Check 1 (F7, GAP 11): one unit per (config, aware, family, instance) under locks and all_available with both
    a1 probes; d = first-reply lock (a1 contended) - first-reply lock (a1 control). Key starts with family."""
    out: Dict[Tuple[Any, ...], float] = {}
    for (m, c, aw, fam, inst, arm), r in sorted(D.pr.items(), key=lambda kv: str(kv[0])):
        if m != model or arm != "contended" or c not in LEAK_CONFIGS:
            continue
        k = D.pr.get((m, c, aw, fam, inst, "control"))
        if k and "a1" in r["agents"] and "a1" in k["agents"]:
            out[(fam, inst, c, aw)] = float(r["agents"]["a1"]["fr_lock"]) - float(k["agents"]["a1"]["fr_lock"])
    return out


def h4b_values(D: Data, model: str, config: str) -> Tuple[Dict[Tuple[Any, ...], float], int, int, int]:
    """GAP 13. At risk: exposed contended agents (``contention_signals`` > 0) with ``protect_before_contention`` not
    True. Reacting: ``protect_before_contention`` is False (score5: first protective call, lock or CAS, after the first
    signal; under locks too). Cluster value = the reacting share; clusters with no agent at risk are dropped. Also
    returned: at-risk agents with ``lock_after_contention`` True (reported, no interval)."""
    acc: Dict[Tuple[Any, ...], List[int]] = {}
    n_den = n_num = n_lock_after = 0
    for k, e in sorted(D.ep.items(), key=lambda kv: str(kv[0])):
        if k[0] != model or k[1] != config or k[2] != 0 or k[6] != "contended":
            continue
        for a in e["agents"].values():
            if not a["at_risk"]:
                continue
            hit = int(a["reacting"])
            acc.setdefault((k[3], k[4]), []).append(hit)
            n_den += 1
            n_num += hit
            n_lock_after += int(a["lock_after"])
    return {c: mean(v) for c, v in sorted(acc.items())}, n_num, n_den, n_lock_after


def intersect(per_model: Mapping[str, Mapping[Tuple[Any, ...], float]]) -> Dict[Tuple[Any, ...], float]:
    """F2 / GAP 6: pooled cluster values over the clusters that enter for every pooled model; the value is the mean
    over the models (the equal-weight pooled estimand restricted to those clusters)."""
    models = sorted(per_model)
    if not models:
        return {}
    keys = set(per_model[models[0]])
    for m in models[1:]:
        keys &= set(per_model[m])
    return {k: mean([per_model[m][k] for m in models]) for k in sorted(keys, key=str)}


# ---------------------------------------------------------------------------------------------------------------
# Eligibility (from probes only; applies to H4)
# ---------------------------------------------------------------------------------------------------------------


def eligibility(sample: Mapping[Tuple[Any, ...], Dict[str, Any]], plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Per (model, config): share of aware-off contended probe agents (a0 and a1) whose first reply contains a
    ``lock`` or ``cas`` token (GAP 14 / F8). Probes excluded under Data exclusion leave the denominator; ``no_call``,
    ``message``, ``read``, ``blind_write`` and ``other`` count as no primitive. Computed only if at least 75 % of the
    registered aware-off contended probes remain. Eligible for H4 iff the share is below 0.80."""
    cells: Dict[str, Dict[str, Any]] = {}
    for model in MODELS:
        for config in CONFIGS:
            reg = registered_units(plan, model, "probe", config, False)
            eps = [r for r in sample.values() if r["probe"] and r["model"] == model and r["config"] == config
                   and r["aware"] == 0 and r["arm"] == "contended"]
            agents = [a for r in eps for _, a in sorted(r["agents"].items())]
            k = sum(a["fr_prim"] for a in agents)
            n_reg = reg["clusters"] if reg else 0
            enough = n_reg > 0 and len(eps) >= _ceil_frac(n_reg, MIN_UNIT_FRACTION)
            rate = k / len(agents) if agents else None
            cells[f"{model}|{config}"] = {
                "model": model, "config": config, "registered_probes": n_reg, "probes": len(eps), "agents": len(agents),
                "k_lock_or_cas": k, "rate": rate, "computed": bool(enough and rate is not None),
                "eligible": bool(enough and rate is not None and rate < ELIGIBILITY_MAX)}
    return {"rule": "H4 only: share of aware-off contended probe agents (a0, a1) whose first_reply contains lock or cas "
                    "< 0.80; computed only with >= 75% of registered probes", "threshold": ELIGIBILITY_MAX, "cells": cells}


def is_eligible(elig: Mapping[str, Any], model: str, config: str) -> Tuple[bool, str]:
    c = elig.get("cells", {}).get(f"{model}|{config}")
    if c is None or not c.get("computed"):
        return False, "eligibility_not_computed"
    return (True, "eligible") if c.get("eligible") else (False, "not_eligible")


# ---------------------------------------------------------------------------------------------------------------
# The confirmatory suite
# ---------------------------------------------------------------------------------------------------------------


def _entry(test: str, model: str, config: str, status: str, **kw: Any) -> Dict[str, Any]:
    d = {"id": f"{test}|{SHORT.get(model, model)}|{config}", "test": test, "model": model, "config": config,
         "status": status}
    d.update(kw)
    return d


def _min_units(plan: Mapping[str, Any], model: str, mode: str, config: str, aware: bool = False) -> Optional[int]:
    reg = registered_units(plan, model, mode, config, aware)
    return None if reg is None else _ceil_frac(reg["clusters"], MIN_UNIT_FRACTION)


def suite(D: Data, plan: Mapping[str, Any], elig: Mapping[str, Any], n_boot: int, h1_metric: str = "fs",
          only: Optional[Sequence[str]] = None, sens: Optional[int] = None) -> Dict[str, Any]:
    """Every confirmatory test, the H1 calibration and the descriptive-model statistics, with the registered
    Holm/gatekeeping (``apply_holm``). Claims are attached by ``read_cells``."""
    tests: List[Dict[str, Any]] = []
    want = lambda t: only is None or t in only  # noqa: E731

    def cell_test(test: str, model: str, config: str, vals: Dict[Tuple[Any, ...], float], kind: str,
                  delta: Optional[float], mode: str, cfgs: Sequence[str] = (), describe: bool = False,
                  gate: Tuple[bool, str] = (True, "")) -> Dict[str, Any]:
        if not gate[0]:
            return _entry(test, model, config, gate[1], n_clusters=len(vals))
        need = [_min_units(plan, model, mode, c) for c in (cfgs or [config])]
        need_n = max((n for n in need if n is not None), default=None)
        if describe:
            r = run_test(test, model, config, vals, kind, delta, n_boot, describe_only=True, sens=sens)
            return _entry(test, model, config, "descriptive", **r)
        if need_n is None or len(vals) < need_n:
            return _entry(test, model, config, "not_tested", n_clusters=len(vals), min_units=need_n)
        r = run_test(test, model, config, vals, kind, delta, n_boot, sens=sens)
        return _entry(test, model, config, "tested", min_units=need_n, **r)

    def pooled_test(test: str, config: str, per_model: Dict[str, Dict[Tuple[Any, ...], float]], kind: str,
                    delta: Optional[float], mode: str = "episodes") -> Dict[str, Any]:
        models = [SHORT[m] for m in sorted(per_model)]
        if len(per_model) < 2:
            return _entry(test, POOLED, config, "not_tested", models=models, reason="fewer_than_2_models")
        vals = intersect(per_model)
        need_n = max(n for n in (_min_units(plan, m, mode, config) for m in per_model) if n is not None)
        if len(vals) < need_n:
            return _entry(test, POOLED, config, "not_tested", models=models, n_clusters=len(vals), min_units=need_n)
        r = run_test(test, POOLED, config, vals, kind, delta, n_boot, sens=sens)
        return _entry(test, POOLED, config, "tested", models=models, min_units=need_n, **r)

    # H1 (and the calibration under none: every confirmatory model, no eligibility rule)
    for name, cfgs in (("H1", H1_CONFIGS), ("H1cal", ("none",))):
        if not want(name):
            continue
        for config in cfgs:
            vals_by_model = {m: h1_values(D, m, config, h1_metric) for m in CONFIRMATORY}
            for kind, delta, tname in (("tost", DELTA_CELL, f"{name}-eq"), ("greater", None, f"{name}-diff")):
                tested: Dict[str, Dict[Tuple[Any, ...], float]] = {}
                for model in CONFIRMATORY:
                    e = cell_test(tname, model, config, vals_by_model[model], kind, delta, "episodes")
                    tests.append(e)
                    if e["status"] == "tested":
                        tested[model] = vals_by_model[model]
                tests.append(pooled_test(tname, config, tested, kind, DELTA_POOLED if kind == "tost" else None))
                for model in DESCRIPTIVE:
                    tests.append(cell_test(tname, model, config, h1_values(D, model, config, h1_metric), kind, delta,
                                           "episodes", describe=True))
    # H2
    if want("H2"):
        for contrast, (ca, cb, _, src) in H2_CONTRASTS.items():
            for model in MODELS:
                vals = h2_values(D, model, contrast)
                mode = "probe" if src == "probes" else "episodes"
                tests.append(cell_test(contrast, model, f"{ca}-{cb}", vals, "two_sided", None, mode, cfgs=(ca, cb),
                                       describe=model in DESCRIPTIVE))
    # H3
    if want("H3"):
        for model in MODELS:
            vals, per_cfg = h3_values(D, model)
            e = cell_test("H3", model, "locks+all_available", vals, "greater", None, "probe", cfgs=H3_CONFIGS,
                          describe=model in DESCRIPTIVE)
            e["per_config"] = {c: {"n_units": len(v), "estimate": mean(list(v.values())) if v else None}
                               for c, v in per_cfg.items()}
            tests.append(e)
    # H4 (eligible confirmatory models only)
    if want("H4"):
        for config in H4_CONFIGS:
            vals_by_model = {m: h4_values(D, m, config) for m in MODELS}
            q_by_model = {m: q_values(D, m, config) for m in MODELS}
            for kind, delta, tname in (("tost", DELTA_CELL, "H4-eq"), ("greater", None, "H4-diff")):
                tested = {}
                for model in CONFIRMATORY:
                    e = cell_test(tname, model, config, vals_by_model[model], kind, delta, "episodes",
                                  gate=is_eligible(elig, model, config))
                    qv = q_by_model[model]
                    e["q"] = mean(list(qv.values())) if qv else None
                    tests.append(e)
                    if e["status"] == "tested":
                        tested[model] = vals_by_model[model]
                pe = pooled_test(tname, config, tested, kind, DELTA_POOLED if kind == "tost" else None)
                keys = set(intersect(tested)) if tested else set()
                qs = [mean([q_by_model[m][k] for k in keys if k in q_by_model[m]]) for m in tested
                      if any(k in q_by_model[m] for k in keys)]
                pe["q"] = mean(qs) if qs else None
                tests.append(pe)
                for model in DESCRIPTIVE:
                    e = cell_test(tname, model, config, vals_by_model[model], kind, delta, "episodes", describe=True)
                    qv = q_by_model[model]
                    e["q"] = mean(list(qv.values())) if qv else None
                    tests.append(e)
    apply_holm(tests, n_boot)
    return {"tests": tests}


# Holm families (registration, Holm families and gatekeeping)
STAGES = {"H1-eq": ("H1-eq/stage1", "H1-eq/stage2", len(H1_CONFIGS)), "H4-eq": ("H4-eq/stage1", "H4-eq/stage2", len(H4_CONFIGS))}
HOLM_FAMILIES = ("H1-eq/stage1", "H1-eq/stage2", "H1-diff", "H2", "H3", "H4-eq/stage1", "H4-eq/stage2", "H4-diff")


def holm_family(t: Mapping[str, Any]) -> Optional[str]:
    if t["status"] not in ("tested", "not_tested_gate_closed"):
        return None
    if t["test"] in ("H2a", "H2b", "H2c", "H2d"):
        return "H2"
    if t["test"] in STAGES:
        s1, s2, _ = STAGES[t["test"]]
        return s1 if t["model"] == POOLED else s2
    if t["test"] in ("H1-diff", "H3", "H4-diff"):
        return t["test"]
    return None  # H1cal-*: raw p at alpha (calibration)


def holm(pvalues: Sequence[Optional[float]]) -> List[Optional[float]]:
    """Holm step-down adjusted p-values (``None`` skipped)."""
    idx = sorted((i for i, p in enumerate(pvalues) if p is not None), key=lambda i: (pvalues[i], i))
    m = len(idx)
    out: List[Optional[float]] = [None] * len(pvalues)
    running = 0.0
    for rank, i in enumerate(idx):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))  # type: ignore[operator]
        out[i] = running
    return out


def _holm_pass(members: List[Dict[str, Any]], fam: str) -> None:
    adj = holm([t["p"] for t in members])
    order = sorted(range(len(members)), key=lambda i: (members[i]["p"], i))
    k = len(members)
    for rank, i in enumerate(order):
        members[i]["holm_level"] = ALPHA / (k - rank)
    for t, a in zip(members, adj):
        t["holm_family"], t["p_adj"], t["holm_family_size"] = fam, a, k
        t["reject"] = a is not None and a < ALPHA


def _mc_near(t: Mapping[str, Any], level: float) -> bool:
    if not t.get("mc") or t.get("p") is None:
        return False
    draws = t.get("B") if t["kind"] == "tost" else N_SIGNFLIP_MC
    return abs(t["p"] - level) < 2 * math.sqrt(level * (1 - level) / draws)


def _recompute(t: Dict[str, Any], n_boot: int) -> None:
    """N6: the p of a Monte Carlo test within 2 MC standard errors of its level, recomputed with 10 x the draws under
    the key plus ``|mc2``; the recomputed value governs."""
    vals = t.get("_values") or {}
    sens = None
    key = t["rng_key"]
    if "|sens" in key:
        sens = int(key.split("|sens")[1].split("|")[0])
    if t["kind"] == "tost":
        r = run_test(t["test"], t["model"], t["config"], vals, "tost", t["delta"], n_boot * MC_RECOMPUTE_FACTOR,
                     sens=sens, key_suffix="|mc2")
    else:
        r = run_test(t["test"], t["model"], t["config"], vals, t["kind"], None, n_boot, sens=sens, key_suffix="|mc2")
        # sign-flip MC: 10 x R
        g = signflip(list(r["_values"].values()), "greater", r["rng_key"], N_SIGNFLIP_MC * MC_RECOMPUTE_FACTOR)
        if t["kind"] == "greater":
            r["p"] = g["p"]
        else:
            l_ = signflip(list(r["_values"].values()), "less", r["rng_key"], N_SIGNFLIP_MC * MC_RECOMPUTE_FACTOR)
            r["p"] = min(1.0, 2 * min(g["p"], l_["p"]))
    t["p_first_pass"] = t["p"]
    t["p"] = r["p"]
    t["recomputed_mc2"] = True
    if t["kind"] == "tost":
        t["sides"], t["_bs"], t["B_recomputed"] = r["sides"], r["_bs"], r["B"]


def _holm_with_recompute(members: List[Dict[str, Any]], fam: str, n_boot: int) -> None:
    if not members:
        return
    _holm_pass(members, fam)
    near = [t for t in members if _mc_near(t, t["holm_level"])]
    if near:
        for t in near:
            _recompute(t, n_boot)
        _holm_pass(members, fam)


def apply_holm(tests: List[Dict[str, Any]], n_boot: int = N_BOOT) -> None:
    """Holm within each family; H1-eq and H4-eq by serial gatekeeping: stage 2 (per-(model, config) cells) is
    tested only if every stage-1 (pooled) test of that hypothesis was tested and rejected."""
    for name, (s1, s2, n_cfg) in STAGES.items():
        stage1 = [t for t in tests if holm_family(t) == s1]
        _holm_with_recompute(stage1, s1, n_boot)
        pooled_all = [t for t in tests if t["test"] == name and t["model"] == POOLED]
        gate_open = len(stage1) == n_cfg and len(pooled_all) == n_cfg and all(t["reject"] for t in stage1)
        stage2 = [t for t in tests if holm_family(t) == s2]
        if gate_open:
            _holm_with_recompute(stage2, s2, n_boot)
        else:
            for t in stage2:
                t.update(status="not_tested_gate_closed", reject=None, p_adj=None, holm_family=s2)
        for t in pooled_all + stage2:
            t["gate_open"] = gate_open
    for fam in ("H1-diff", "H2", "H3", "H4-diff"):
        _holm_with_recompute([t for t in tests if holm_family(t) == fam], fam, n_boot)
    for t in tests:
        if t["test"].startswith("H1cal") and t["status"] == "tested":
            t["p_adj"], t["holm_level"] = None, ALPHA
            if _mc_near(t, ALPHA):
                _recompute(t, n_boot)
            t["reject"] = t["p"] < ALPHA  # raw p, no Holm
    for t in tests:  # N4: the Holm-consistent bootstrap-t interval at 1 - 2 x (the level the test was compared at)
        if t.get("kind") == "tost" and t.get("_bs") is not None and t.get("holm_level"):
            t["ci_holm_t"] = t_interval(t["_bs"], t["holm_level"])


# ---------------------------------------------------------------------------------------------------------------
# Claims per cell (registration, Reading per cell, and the claim allowed)
# ---------------------------------------------------------------------------------------------------------------


def _f(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def claim_text(base: str, reading: str, eq: Mapping[str, Any], diff: Mapping[str, Any], why: str = "") -> str:
    noun = OUTCOME_NOUN[base]
    d = eq.get("delta")
    i90 = eq.get("ci90_t") or [None, None]
    i95 = diff.get("ci95") or [None, None]
    x = _f(eq.get("estimate"))
    if reading == "bounded":
        return f"Contention did not add {noun} beyond ±{_f(d)} (Δ = {x}, 90 % [{_f(i90[0])}, {_f(i90[1])}])."
    if reading == "worse":
        return f"Contention added {noun} (Δ = {x}, 95 % [{_f(i95[0])}, {_f(i95[1])}])."
    if reading == "worse_within_delta":
        return f"Contention added {noun}, by less than {_f(d)} (Δ = {x}, 90 % [{_f(i90[0])}, {_f(i90[1])}])."
    if reading == "uninformative":
        return f"Inconclusive: equivalence is uninformative here ({why}) (Δ = {x}, 90 % [{_f(i90[0])}, {_f(i90[1])}])."
    return f"Inconclusive (Δ = {x}, 90 % [{_f(i90[0])}, {_f(i90[1])}]). No direction is claimed."


def read_cells(tests: List[Dict[str, Any]], s9_tests: Optional[Sequence[Mapping[str, Any]]] = None,
               leakage: Optional[Mapping[str, Any]] = None) -> None:
    """Attach ``reading``, ``flags`` and ``claim`` to every H1, H1cal and H4 (model, config) and pooled pair.

    eq_claim = the eq test rejected (Holm and gate) and, for H1/H4, also rejects under sensitivity 9, and the cell is
    informative (H1: the model's calibration H1-diff under none rejected; H4: q > delta). Readings: worse_within_delta
    (eq_claim and diff), bounded (eq_claim), worse (diff), uninformative (eq rejected and robust, not informative),
    inconclusive."""
    by = {(t["test"], t["model"], t["config"]): t for t in tests}
    s9 = {t["id"]: t for t in (s9_tests or [])}
    cal = {t["model"]: t for t in tests if t["test"] == "H1cal-diff" and t["status"] == "tested"}
    for (test, model, config), eq in sorted(by.items(), key=lambda kv: str(kv[0])):
        if not test.endswith("-eq"):
            continue
        base = test[:-3]
        diff = by.get((base + "-diff", model, config))
        if diff is None or eq["status"] not in ("tested", "not_tested_gate_closed") or diff["status"] != "tested":
            continue
        flags: List[str] = []
        eq_rej = bool(eq.get("reject"))
        diff_rej = bool(diff.get("reject"))
        if eq["status"] == "not_tested_gate_closed":
            flags.append("eq_not_tested_gate_closed")
        robust = True
        if base in ("H1", "H4") and eq_rej and s9_tests is not None:
            robust = bool(s9.get(eq["id"], {}).get("reject"))
            if not robust:
                flags.append("eq_not_robust_to_sensitivity_9")
        informative, why = True, ""
        if base == "H1" and eq_rej:
            c = cal.get(model)
            if c is None or not c.get("reject"):
                informative, why = False, "calibration under none did not reject"
                flags.append("uninformative_calibration")
        if base == "H4" and eq_rej:
            q, d = eq.get("q"), eq.get("delta")
            if q is None or q <= d + EPS:
                informative, why = False, f"q = {_f(q)} <= delta"
                flags.append("uninformative_low_q")
            else:
                eq["implied_bound_reacting_share"] = d / q
        if base == "H4" and leakage is not None and model != POOLED and leakage.get(SHORT.get(model, model), {}).get("leaks"):
            flags.append("leakage_total_effect_of_template")
        eq_claim = eq_rej and robust and informative
        if eq_claim and diff_rej:
            reading = "worse_within_delta"
        elif eq_claim:
            reading = "bounded"
        elif diff_rej:
            reading = "worse"
        elif eq_rej and robust and not informative:
            reading = "uninformative"
        else:
            reading = "inconclusive"
        txt = claim_text(base, reading, eq, diff, why)
        if "eq_not_robust_to_sensitivity_9" in flags and reading in ("inconclusive", "worse"):
            txt += " The equivalence test rejected but did not hold under sensitivity 9, so no bound is claimed."
        for t in (eq, diff):
            t["reading"], t["flags"], t["claim"] = reading, flags, txt
    for t in tests:
        if t["test"] == "H3" and t["status"] == "tested":
            t["claim"] = (f"The notice raised first-reply lock use by {_f(t.get('estimate'))}." if t.get("reject")
                          else "No claim.")


# ---------------------------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------------------------


def checks(D: Data, sample: Mapping[Tuple[Any, ...], Dict[str, Any]], n_boot: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # 1. Leakage (sign-flip on (config, aware, family, instance) units, two-sided, per model, alpha 0.05, no Holm)
    leak = {}
    for model in MODELS:
        vals = leakage_values(D, model)
        if not vals:
            leak[SHORT[model]] = {"status": "not_run", "n_units": 0, "p": None, "leaks": False}
            continue
        r = run_test("leakage", model, "+".join(LEAK_CONFIGS), vals, "two_sided", None, n_boot)
        r = {k: v for k, v in r.items() if not k.startswith("_")}
        r.update(status="tested", n_units=len(vals), leaks=r["p"] < ALPHA)
        leak[SHORT[model]] = r
    out["leakage"] = leak
    # 2. Exposure (manipulation check), per model x config x family (aware off; Gemini aware on as its own cells)
    expo: Dict[str, Any] = {}
    ctrl_exposed = []
    for model in MODELS:
        for config in CONFIGS:
            for aware in (0, 1):
                if not D.clusters(model, config, aware):
                    continue
                key = f"{SHORT[model]}|{config}|aware{aware}"
                all_vals = exposure_values(D, model, config, aware=aware)
                cell: Dict[str, Any] = {"estimate": mean(list(all_vals.values())) if all_vals else None,
                                        "n_clusters": len(all_vals), "families": {}}
                for fam in FAMILIES:
                    v = exposure_values(D, model, config, aware=aware, family=fam)
                    if not v:
                        continue
                    cfg_label = f"{config}|{fam}" + ("|aware" if aware else "")
                    r = run_test("exposure", model, cfg_label, v, "two_sided", None, n_boot, describe_only=True)
                    cell["families"][fam] = {"estimate": r["estimate"], "ci95": r["ci95"], "n_clusters": r["n_clusters"]}
                expo[key] = cell
    for k, e in sorted(D.ep.items(), key=lambda kv: str(kv[0])):
        if k[6] == "control":
            for a, av in e["agents"].items():
                if av["exposed"]:
                    ctrl_exposed.append(f"{e['id']}:{a}")
    out["exposure"] = {"cells": expo, "control_agents_exposed": len(ctrl_exposed),
                       "control_exposed_examples": ctrl_exposed[:20], "ok": not ctrl_exposed,
                       "note": "a control agent coded as exposed is a scorer bug: fix, rescore all, report a deviation"}
    # 3. Isolation and lock safety
    iso = [r["id"] for r in sample.values() if not r["probe"] and r["arm"] == "control" and r["cross_agent_edges"] != 0]
    me_na = sum(1 for r in sample.values() if not r["probe"] and r["me_violations"] is None)
    me_bad = [r["id"] for r in sample.values() if not r["probe"] and r["me_violations"]]
    out["isolation"] = {"control_episodes_with_cross_agent_edges": len(iso), "examples": sorted(iso)[:20], "ok": not iso}
    out["lock_safety"] = {"episodes_with_mutual_exclusion_violations": len(me_bad), "examples": sorted(me_bad)[:20],
                          "episodes_not_checked": me_na, "ok": not me_bad and me_na == 0}
    return out


def reads_overlap_table(D: Data) -> Dict[str, Any]:
    """S2: per model x config x arm, the share of H1 complete-pair episodes with ``interleaving.reads_overlap`` True."""
    out = {}
    for model in MODELS:
        for config in CONFIGS:
            for arm_i, arm in ((0, "contended"), (1, "control")):
                vals = [p[arm_i]["reads_overlap"] for fam, inst in D.clusters(model, config)
                        for p in D.pairs(model, config, fam, inst) if p[arm_i]["reads_overlap"] is not None]
                if vals:
                    out[f"{SHORT[model]}|{config}|{arm}"] = {"share": sum(map(bool, vals)) / len(vals), "n": len(vals)}
    return out


def h4b(D: Data, n_boot: int) -> Dict[str, Any]:
    out = {}
    for model in MODELS:
        for config in H4_CONFIGS:
            vals, k, n, n_la = h4b_values(D, model, config)
            r = run_test("H4b", model, config, vals, "greater", None, n_boot, describe_only=True) if vals else {}
            out[f"{SHORT[model]}|{config}"] = {"agents_at_risk": n, "agents_reacting": k,
                                               "agents_at_risk_lock_after_contention": n_la, "n_clusters": len(vals),
                                               "estimate": r.get("estimate"), "ci95": r.get("ci95")}
    return out


# ---------------------------------------------------------------------------------------------------------------
# Sensitivity analyses
# ---------------------------------------------------------------------------------------------------------------


def verdicts(tests: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {t["id"]: {"status": t["status"], "reject": t.get("reject"), "reading": t.get("reading")}
            for t in tests if t["status"] in ("tested", "not_tested_gate_closed")}


def changed(main: Sequence[Mapping[str, Any]], other: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    a, b = verdicts(main), verdicts(other)
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            out.append({"id": k, "main": a.get(k), "sensitivity": b.get(k)})
    return out


def drop_with_partners(sample: Mapping[Tuple[Any, ...], Dict[str, Any]], bad: Callable[[Dict[str, Any]], bool]) -> Tuple[Dict[Tuple[Any, ...], Dict[str, Any]], int]:
    drop = {k for k, r in sample.items() if bad(r)}
    drop |= {k[:-1] + (other_arm(k[-1]),) for k in list(drop)}
    return {k: r for k, r in sample.items() if k not in drop}, len([k for k in drop if k in sample])


def cap24_sample(sample: Mapping[Tuple[Any, ...], Dict[str, Any]]) -> Tuple[Optional[Dict[Tuple[Any, ...], Dict[str, Any]]], Dict[str, Any]]:
    """Sensitivity 1: lock-config episodes replaced by their 24-call re-score; ``indeterminate`` (and
    ``not_available``) episodes dropped with their partners (GAP 2), counted per arm."""
    status: Dict[str, int] = {}
    out: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for k, r in sample.items():
        c = r.get("cap24")
        if c is None:
            out[k] = r
            continue
        sk = f"{c['status']}|{_cell(r)}|{r['arm']}"
        status[sk] = status.get(sk, 0) + 1
        if c["status"] == "unchanged":
            out[k] = r
        elif c["status"] == "rescored":
            nr = dict(r)
            nr.update({f: c[f] for f in ("fs", "basis", "outcome", "cap_truncated", "reads_overlap", "agents")})
            out[k] = nr
    seen = {s.split("|")[0] for s in status}
    if seen and seen <= {"not_available"}:
        return None, dict(sorted(status.items()))
    missing = {k for k, r in sample.items() if r.get("cap24") is not None and k not in out}
    out = {k: r for k, r in out.items() if k[:-1] + (other_arm(k[-1]),) not in missing}
    status["dropped_with_partners"] = len(set(sample) - set(out))
    return out, dict(sorted(status.items()))


def majority_version_sample(sample: Mapping[Tuple[Any, ...], Dict[str, Any]]) -> Tuple[Dict[Tuple[Any, ...], Dict[str, Any]], Dict[str, Any]]:
    """Sensitivity 4 (GAP 18): for a model with more than one ``model_served`` value, keep the rows served only by
    its majority value (majority by rows); count pairs whose two episodes differ."""
    info: Dict[str, Any] = {}
    out = dict(sample)
    for model in MODELS:
        rows = [r for r in sample.values() if r["model"] == model]
        ids: Dict[str, int] = {}
        for r in rows:
            for s in r["served"]:
                ids[s] = ids.get(s, 0) + 1
        mixed_pairs = sum(1 for k, r in sample.items() if r["model"] == model and k[-1] == "contended"
                          and (k[:-1] + ("control",)) in sample and sample[k[:-1] + ("control",)]["served"] != r["served"])
        info[SHORT[model]] = {"served_ids": dict(sorted(ids.items())), "pairs_with_different_served_ids": mixed_pairs}
        if len(ids) > 1:
            maj = sorted(ids.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            info[SHORT[model]]["majority"] = maj
            for k, r in list(out.items()):
                if r["model"] == model and r["served"] != [maj]:
                    del out[k]
    return out, info


def against_equivalence_sample(sel: Mapping[str, Any]) -> Tuple[Dict[Tuple[Any, ...], Dict[str, Any]], int]:
    """Sensitivity 9 (S3): every episode pair excluded under Data exclusion enters as written, scored against
    equivalence: the contended episode gets fs = 1 (and basis = 1), and its errored agents count as having used a
    primitive (lock and first_protective); the control enters as scored. Probes enter as written."""
    out = dict(sel["main"])
    n = 0
    for pk in sel["excluded_pairs"]:
        c, k = sel["as_is"].get(pk + ("contended",)), sel["as_is"].get(pk + ("control",))
        if c is None or k is None:
            continue
        if not c["probe"]:
            c = dict(c, fs=1, basis=1)
            c["agents"] = {a: (dict(v, lock=True, prim=True) if a in c["errored_agents"] else v)
                           for a, v in c["agents"].items()}
        out[pk + ("contended",)], out[pk + ("control",)] = c, k
        n += 1
    return out, n


def holm_within_model(tests: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Sensitivity 6: Holm across all per-(model, config) tests of H1-eq, H1-diff, H2, H3, H4-eq and H4-diff within
    each confirmatory model, without gatekeeping. Pooled tests are not within a model and are left out (GAP 20)."""
    out = {}
    for model in CONFIRMATORY:
        members = [t for t in tests if t["model"] == model and holm_family(t) is not None and t.get("p") is not None]
        adj = holm([t["p"] for t in members])
        out[SHORT[model]] = {t["id"]: {"p": t["p"], "p_adj": a, "reject": a is not None and a < ALPHA,
                                       "main_reject": bool(t.get("reject")),
                                       "changed": (a is not None and a < ALPHA) != bool(t.get("reject"))}
                             for t, a in zip(members, adj)}
    return out


EPISODE_TESTS = ("H1", "H1cal", "H2", "H4")  # H3 uses probes only: no episode sensitivity changes it


def _episode_ids(tests: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [x for x in tests if x["test"] != "H3"]


def sensitivities(sel: Mapping[str, Any], main_tests: Sequence[Mapping[str, Any]], plan: Mapping[str, Any],
                  elig: Mapping[str, Any], n_boot: int, s9_tests: Sequence[Mapping[str, Any]], n9: int) -> Dict[str, Any]:
    main = sel["main"]
    out: Dict[str, Any] = {}
    s1, st = cap24_sample(main)
    if s1 is None:
        out["s1_cap24"] = {"status": "not_available", "rescore_status": st}
    else:
        t = suite(Data(s1), plan, elig, n_boot, only=EPISODE_TESTS, sens=1)["tests"]
        read_cells(t)
        out["s1_cap24"] = {"status": "done", "rescore_status": st, "changed_verdicts": changed(_episode_ids(main_tests), t),
                           "tests": slim(t)}
    s2, n2 = drop_with_partners(main, lambda r: (not r["probe"]) and r["cap_truncated"])
    t = suite(Data(s2), plan, elig, n_boot, only=EPISODE_TESTS, sens=2)["tests"]
    read_cells(t)
    out["s2_cap_truncated_excluded"] = {"dropped": n2, "changed_verdicts": changed(_episode_ids(main_tests), t), "tests": slim(t)}
    t = suite(Data(sel["as_is"]), plan, elig, n_boot, sens=3)["tests"]
    read_cells(t)
    out["s3_exclusions_kept"] = {"rows": len(sel["as_is"]), "changed_verdicts": changed(main_tests, t), "tests": slim(t)}
    s4, info = majority_version_sample(main)
    if len(s4) == len(main):
        out["s4_majority_version"] = {"status": "no_model_changed_served_id", "served": info, "changed_verdicts": []}
    else:
        t = suite(Data(s4), plan, elig, n_boot, sens=4)["tests"]
        read_cells(t)
        out["s4_majority_version"] = {"status": "done", "served": info, "changed_verdicts": changed(main_tests, t), "tests": slim(t)}
    s5 = {k: r for k, r in main.items() if not (r["model"] == GPT and r["host_flag"])}
    if len(s5) == len(main):
        out["s5_gpt_openai_only"] = {"status": "no_non_openai_gpt_episodes"}
    else:
        out["s5_gpt_openai_only"] = {"status": "done", "descriptive": slim([
            x for x in suite(Data(s5), plan, elig, n_boot, only=EPISODE_TESTS, sens=5)["tests"] if x["model"] == GPT])}
    out["s6_holm_within_model"] = holm_within_model(main_tests)
    out["s7_template_level"] = {t["id"]: t.get("p_family_level") for t in main_tests if t["status"] == "tested"}
    t = suite(Data(main), plan, elig, n_boot, h1_metric="basis", only=("H1", "H1cal"), sens=8)["tests"]
    read_cells(t)
    out["s8_h1_dsg_basis_cycle"] = {"changed_verdicts": changed([x for x in main_tests if x["test"].startswith("H1")],
                                                                [x for x in t if x["test"].startswith("H1")]), "tests": slim(t)}
    out["s9_against_equivalence"] = {"pairs_scored_against": n9, "changed_verdicts": changed(_episode_ids(main_tests), s9_tests),
                                     "tests": slim(s9_tests)}
    return out


def slim(tests: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    keep = ("id", "status", "estimate", "ci95", "ci90_t", "p", "p_adj", "reject", "reading", "flags", "n_clusters", "q")
    return [{k: t[k] for k in keep if k in t} for t in tests]


# ---------------------------------------------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------------------------------------------


def load_sample(transcripts: Iterable[Tuple[str, Mapping[str, Any]]], src5_dir: Optional[str], allow_dry_run: bool,
                probes_only: bool = False, root: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
    recs, hashes = [], []
    for path, tr in transcripts:
        if probes_only and not tr.get("probe"):
            raise SystemExit(f"eligibility reads probes only; {path} is an episode")
        recs.append(normalize(tr, path, src5_dir, allow_dry_run, want_cap24=not probes_only))
        rel = os.path.relpath(path, root) if root else os.path.basename(path)
        hashes.append([rel, sha256_file(path) if os.path.exists(path) else hashlib.sha256(
            json.dumps(tr, sort_keys=True).encode()).hexdigest()])
    return recs, sorted(hashes)


def inputs_digest(hashes: Sequence[Sequence[str]]) -> str:
    return hashlib.sha256("\n".join(f"{a} {b}" for a, b in hashes).encode()).hexdigest()


def run_eligibility(transcripts: Iterable[Tuple[str, Mapping[str, Any]]], plan: Mapping[str, Any], allow_dry_run: bool,
                    root: Optional[str] = None) -> Dict[str, Any]:
    recs, hashes = load_sample(transcripts, None, allow_dry_run, probes_only=True, root=root)
    sel = select(recs, plan, allow_dry_run)
    e = eligibility(sel["main"], plan)
    e.update(inputs={"n_files": len(hashes), "sha256_of_list": inputs_digest(hashes)}, selection=sel["log"],
             dry_run=allow_dry_run)
    return e


def run_analysis(transcripts: Iterable[Tuple[str, Mapping[str, Any]]], plan: Mapping[str, Any],
                 elig: Optional[Mapping[str, Any]], allow_dry_run: bool, n_boot: int = N_BOOT,
                 src5_dir: Optional[str] = DEFAULT_SRC5, root: Optional[str] = None,
                 failures: Optional[Mapping[str, int]] = None, with_sensitivity: bool = True) -> Dict[str, Any]:
    recs, hashes = load_sample(transcripts, src5_dir, allow_dry_run, root=root)
    sel = select(recs, plan, allow_dry_run)
    elig_source = "file"
    if elig is None:
        elig = eligibility({k: r for k, r in sel["main"].items() if r["probe"]}, plan)
        elig_source = "computed_inline"
    D = Data(sel["main"])
    main = suite(D, plan, elig, n_boot)["tests"]
    ck = checks(D, sel["main"], n_boot)
    s9_sample, n9 = against_equivalence_sample(sel)
    s9 = suite(Data(s9_sample), plan, elig, n_boot, only=EPISODE_TESTS, sens=9)["tests"] if n9 else \
        [dict(t) for t in main if t["test"] != "H3"]
    read_cells(s9, leakage=ck["leakage"])
    read_cells(main, s9_tests=s9, leakage=ck["leakage"])
    res: Dict[str, Any] = {
        "registration": "paper-concurrency/PREREGISTRATION_STUDY2.md",
        "dry_run": allow_dry_run,
        "constants": {"B": n_boot, "seed": SEED, "alpha": ALPHA, "delta_cell": DELTA_CELL, "delta_pooled": DELTA_POOLED,
                      "eligibility_max": ELIGIBILITY_MAX, "min_unit_fraction": MIN_UNIT_FRACTION,
                      "signflip_mc_R": N_SIGNFLIP_MC},
        "inputs": {"n_files": len(hashes), "sha256_of_list": inputs_digest(hashes)},
        "selection": sel["log"],
        "provider_failures": dict(failures or {}),
        "budget": balance_report(root),
        "eligibility": {"source": elig_source, "cells": elig.get("cells", {})},
        "tests": main,
        "checks": ck,
        "reads_overlap": reads_overlap_table(D),
        "h4b": h4b(D, n_boot),
    }
    if with_sensitivity:
        res["sensitivity"] = sensitivities(sel, main, plan, elig, n_boot, s9, n9)
    res["summary"] = summary(res)
    return res


def summary(res: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for t in res["tests"]:
        if t["status"] in ("tested", "not_tested_gate_closed"):
            out[t["id"]] = {"status": t["status"], "estimate": t.get("estimate"), "p": t.get("p"), "p_adj": t.get("p_adj"),
                            "reject": t.get("reject"), "reading": t.get("reading"), "claim": t.get("claim")}
    return out


# ---------------------------------------------------------------------------------------------------------------
# numbers.tex
# ---------------------------------------------------------------------------------------------------------------

_DIGITS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
           "8": "eight", "9": "nine"}
_TEST_TEX = {"H1-eq": "HoneEq", "H1-diff": "HoneDiff", "H1cal-eq": "HoneCalEq", "H1cal-diff": "HoneCalDiff",
             "H2a": "HtwoA", "H2b": "HtwoB", "H2c": "HtwoC", "H2d": "HtwoD", "H3": "Hthree", "H4-eq": "HfourEq",
             "H4-diff": "HfourDiff"}


def macro(*parts: str) -> str:
    s = "Sii" + "".join(p[:1].upper() + p[1:] for p in parts if p)
    s = "".join(_DIGITS.get(c, c) for c in s)
    return "".join(c for c in s if c.isalpha())


def fnum(x: Optional[float], nd: int = 2) -> str:
    if x is None:
        return r"\textemdash{}"
    return f"{x:.{nd}f}".replace("-", "$-$") if x < 0 else f"{x:.{nd}f}"


def fp(p: Optional[float]) -> str:
    if p is None:
        return r"\textemdash{}"
    return "$<$0.001" if p < 0.001 else f"{p:.3f}"


def numbers_tex(res: Mapping[str, Any], self_hash: str) -> str:
    lines = ["% GENERATED by analysis5/analyze5.py -- do not edit.",
             f"% analyze5.py sha256 {self_hash}",
             f"% inputs: {res['inputs']['n_files']} transcripts, list sha256 {res['inputs']['sha256_of_list']}"]
    vals: Dict[str, str] = {"SiiDryRunFlag": "1" if res["dry_run"] else "0", "SiiNBoot": f"{res['constants']['B']:,}".replace(",", "{,}"),
                            "SiiBootSeed": SEED, "SiiDeltaCell": fnum(DELTA_CELL), "SiiDeltaPooled": fnum(DELTA_POOLED)}
    for c in res["eligibility"]["cells"].values():
        if c["model"] in MODELS:
            vals[macro("Elig", SHORT[c["model"]], CFG_SHORT[c["config"]], "Rate")] = fnum(c["rate"])
            vals[macro("Elig", SHORT[c["model"]], CFG_SHORT[c["config"]])] = ("yes" if c["eligible"] else "no") if c["computed"] else "not computed"
    for t in res["tests"]:
        if t["test"] not in _TEST_TEX:
            continue
        cfg = "".join(CFG_SHORT.get(x, "") for x in t["config"].replace("+", "-").split("-")) if t["test"] in ("H2a", "H2b", "H2c", "H2d", "H3") else CFG_SHORT.get(t["config"], t["config"])
        base = (_TEST_TEX[t["test"]], "Pooled" if t["model"] == POOLED else SHORT[t["model"]], cfg)
        vals[macro(*base, "Status")] = t["status"].replace("_", " ")
        if t.get("estimate") is not None:
            vals[macro(*base, "Est")] = fnum(t["estimate"])
            lo, hi = t.get("ci95") or (None, None)
            vals[macro(*base, "Lo")], vals[macro(*base, "Hi")] = fnum(lo), fnum(hi)
            if t.get("ci90_t"):
                vals[macro(*base, "LoNinety")], vals[macro(*base, "HiNinety")] = fnum(t["ci90_t"][0]), fnum(t["ci90_t"][1])
            vals[macro(*base, "N")] = str(t.get("n_clusters"))
        if t["status"] in ("tested", "not_tested_gate_closed") and t.get("p") is not None:
            vals[macro(*base, "P")] = fp(t.get("p"))
        if t["status"] == "tested":
            vals[macro(*base, "Padj")] = fp(t.get("p_adj"))
            vals[macro(*base, "Reject")] = "yes" if t.get("reject") else "no"
        if t.get("reading"):
            vals[macro(*base, "Reading")] = t["reading"].replace("_", " ")
        if t.get("q") is not None:
            vals[macro(*base, "Q")] = fnum(t["q"])
    for m, r in res["checks"]["leakage"].items():
        vals[macro("Leak", m, "Est")] = fnum(r.get("estimate"))
        vals[macro("Leak", m, "P")] = fp(r.get("p"))
    ck = res["checks"]
    vals["SiiControlExposedAgents"] = str(ck["exposure"]["control_agents_exposed"])
    vals["SiiIsolationViolations"] = str(ck["isolation"]["control_episodes_with_cross_agent_edges"])
    vals["SiiMutexViolations"] = str(ck["lock_safety"]["episodes_with_mutual_exclusion_violations"])
    for k, v in res["selection"].get("counts", {}).items():
        vals[macro("Excl", *k.split("_"))] = str(v)
    sens = res.get("sensitivity") or {}
    for key, name in (("s1_cap24", "CapTwentyFour"), ("s2_cap_truncated_excluded", "CapTrunc"), ("s3_exclusions_kept", "ExclKept"),
                      ("s4_majority_version", "Version"), ("s8_h1_dsg_basis_cycle", "Basis"),
                      ("s9_against_equivalence", "AgainstEq")):
        if key in sens and "changed_verdicts" in sens[key]:
            vals[macro("Sens", name, "Changed")] = str(len(sens[key]["changed_verdicts"]))
    if "s6_holm_within_model" in sens:
        vals["SiiSensHolmModelChanged"] = str(sum(v["changed"] for m in sens["s6_holm_within_model"].values() for v in m.values()))
    for k in sorted(vals):
        lines.append(r"\newcommand{\%s}{%s}" % (k, vals[k]))
    return "\n".join(lines) + "\n"


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {(k if isinstance(k, str) else "|".join(map(str, k)) if isinstance(k, tuple) else str(k)): _jsonable(v)
                for k, v in x.items() if not (isinstance(k, str) and k.startswith("_"))}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def write_outputs(res: Mapping[str, Any], out: str) -> Tuple[str, str]:
    os.makedirs(out, exist_ok=True)
    self_hash = sha256_file(os.path.abspath(__file__))
    data = dict(res)
    data["analyze5_sha256"] = self_hash
    jp, tp = os.path.join(out, "results.json"), os.path.join(out, "numbers.tex")
    with open(jp, "w") as f:
        json.dump(_jsonable(data), f, indent=1, sort_keys=True)
        f.write("\n")
    with open(tp, "w") as f:
        f.write(numbers_tex(res, self_hash))
    return jp, tp


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("eligibility", "analyze"))
    ap.add_argument("--base", required=True, help="results5/study2 (lane directories n2-*, probe-*)")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--plan", default=DEFAULT_PLAN)
    ap.add_argument("--src5", default=DEFAULT_SRC5)
    ap.add_argument("--eligibility", help="posted eligibility.json (analyze); computed inline if omitted")
    ap.add_argument("--eligibility-sha256", help="refuse unless --eligibility has this sha256")
    ap.add_argument("--allow-dry-run", action="store_true", help="rehearsal on dry-run transcripts (never data)")
    ap.add_argument("--n-boot", type=int, default=N_BOOT, help="registered: 10000 (other values only for tests)")
    ap.add_argument("--no-sensitivity", action="store_true")
    a = ap.parse_args(argv)
    with open(a.plan) as f:
        plan = json.load(f)
    if a.command == "eligibility":
        dirs = discover(a.base, a.allow_dry_run, probes_only=True)
        if not dirs:
            raise SystemExit(f"no probe transcripts under {a.base}")
        e = run_eligibility(read_transcripts(dirs), plan, a.allow_dry_run, root=a.base)
        os.makedirs(a.out, exist_ok=True)
        p = os.path.join(a.out, "eligibility.json")
        with open(p, "w") as f:
            json.dump(_jsonable(e), f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"eligibility: {p} sha256 {sha256_file(p)}")
        return 0
    elig = None
    if a.eligibility:
        if a.eligibility_sha256 and sha256_file(a.eligibility) != a.eligibility_sha256:
            raise SystemExit("eligibility.json differs from the posted sha256")
        with open(a.eligibility) as f:
            elig = json.load(f)
    dirs = discover(a.base, a.allow_dry_run)
    if not dirs:
        raise SystemExit(f"no transcripts under {a.base}")
    res = run_analysis(read_transcripts(dirs), plan, elig, a.allow_dry_run, a.n_boot, a.src5, root=a.base,
                       failures=failure_counts(dirs), with_sensitivity=not a.no_sensitivity)
    jp, tp = write_outputs(res, a.out)
    n_t = sum(1 for t in res["tests"] if t["status"] == "tested")
    print(f"{'DRY RUN - ' if a.allow_dry_run else ''}{n_t} tests run; wrote {jp} and {tp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
