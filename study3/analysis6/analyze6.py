"""Confirmatory analysis of Study 3 (stdlib only, deterministic). Implements PREREGISTRATION_STUDY3.md.

    python3 analysis6/analyze6.py analyze --base results6/study3 --out analysis6/out_study3
    # dry-run rehearsal (fake models): add --allow-dry-run (reads <base>/<lane>/dry_run/transcripts)

Writes ``<out>/results.json`` (every number, sorted keys, no timestamps) and ``<out>/numbers.tex`` (one
``\\newcommand`` per reported value, prefix ``Siii``).

Scope (registration, "Analysis plan"): the confirmatory tests S3-H1 (replication, difference tests), S3-H2a and
S3-H2b (the Study 3 lock text against the Study 2 lock text), S3-H3 (reactive uptake of the late agent under the
staggered start: equivalence with the perceivable-signal informativeness gate, and difference), the calibration
under ``none``, the checks (leakage, exposure, isolation and lock safety, the stagger), the pre-specified
descriptive blocks D1 to D6 (no test) and the sensitivity analyses S1 to S9.

Inputs. The scored transcripts ``<base>/n2-*/transcripts/*.json``. Only scorer output is read (``src6/score6.score``
as stored by the harness; ``first_reply``, ``final_text`` and the per-completion ``turns`` from
``src6/model_agent6``), plus the call log for the descriptive mechanism counts and the stagger check. ``src6`` is
imported read-only (``sys.dont_write_bytecode``) only for the lock-safety gate.

The statistical core (sign-flip, bootstrap-t TOST sides, intervals, family-level p, Holm with the Monte Carlo
recompute) is copied unchanged from ``analysis5/analyze5.py`` (Study 2, frozen); only the RNG seed string differs.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import random
import re
import sys
from fractions import Fraction
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_SRC6 = os.path.join(ROOT, "src6")

QWEN = "openrouter:qwen/qwen3.6-27b-20260422"
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5"
MODELS = (QWEN, HAIKU, SONNET)
CONFIRMATORY = MODELS
SHORT = {QWEN: "Qwen", HAIKU: "Haiku", SONNET: "Sonnet"}
POOLED = "pooled"
RNG_MODEL = {QWEN: "qwen", HAIKU: "haiku", SONNET: "sonnet", POOLED: "pooled"}
CONFIGS = ("none", "cas_available", "locks_s2text", "locks", "all_available")
CFG_SHORT = {"none": "None", "cas_available": "Cas", "locks_s2text": "LocksTwo", "locks": "Locks", "all_available": "All"}
START_SHORT = {"together": "Tg", "staggered": "Stg"}
CONDITIONS = tuple((c, "together") for c in CONFIGS) + (("locks", "staggered"), ("all_available", "staggered"))
FAMILIES = ("inventory_last_unit", "inventory_still_valid", "seat_same", "ticket_same", "transfer_shared_source",
            "budget_write_skew", "joint_account_write_skew", "transfer_same_amount")
DISTINCT_FAMILIES = ("inventory_last_unit", "inventory_still_valid", "transfer_shared_source", "budget_write_skew",
                     "joint_account_write_skew")
MULTI_FAMILIES = ("transfer_shared_source", "budget_write_skew", "joint_account_write_skew", "transfer_same_amount")
TRANSFER_FAMILIES = ("transfer_shared_source", "transfer_same_amount")
INSTANCES = 8
SEEDS = (0,)
REGISTERED_CLUSTERS = len(FAMILIES) * INSTANCES  # 64 per model
H1_CONFIGS = ("cas_available", "locks_s2text", "locks", "all_available")
H3_CONFIGS = ("locks", "all_available")
LOCK_CONFIGS = ("locks_s2text", "locks", "all_available")
LATE_AGENT = "a1"

N_BOOT = 10_000
N_SIGNFLIP_MC = 100_000
MC_RECOMPUTE_FACTOR = 10
SIGNFLIP_MAX_DENOM = 10_000
SEED = "20261115"
ALPHA = 0.05
DELTA_CELL = 0.25
DELTA_POOLED = 0.15
MIN_UNIT_FRACTION = 0.75
EPS = 1e-12
VAR_EPS = 1e-12
T_TOL = 1e-9

AGENT_ERROR_ENDS = ("truncated", "provider_error", "error")
REFUSAL_ENDS = ("refusal", "content_filter")
REFUSAL_STOPS = ("content_filter", "refusal")
REQUIRED_HOST = {QWEN: "alibaba"}
STUDY3_AGENT_FIELDS = ("perceivable_signals", "first_perceivable_call", "protect_before_perceivable", "read_before_lock",
                       "lock_scope", "contention_signals", "protect_before_contention", "first_protective")

RNG_TEST = {"H1-diff": "H1diff", "H1cal-diff": "H1caldiff", "H2a": "H2a", "H2b": "H2b", "H3-eq": "H3eq",
            "H3-diff": "H3diff", "H3b": "H3b", "leakage": "check1", "exposure": "check2"}
OUTCOME_NOUN = {"H3": "reactive primitive uptake of the late agent"}

# Final-reply rules of the Study 2 post hoc counts (analysis5/descriptives5.py, SUCCESS_RE and NEGATION_RE), copied
# unchanged and now pre-specified for D1: "success reported" = SUCCESS_RE matches the agent's final text and
# NEGATION_RE does not.
SUCCESS_RE = re.compile(
    r"(task (?:is|has been|was) (?:now )?complete|completed successfully|(?:has been|have been|was|were|is) (?:completed|successful|successfully)"
    r"|successfully (?:sold|reduced|recorded|transferred|assigned|withdr\w+|added|moved|completed|updated|claimed|credited|debited|processed|booked|taken|given|decremented|set)"
    r"|sale (?:of [^.]{0,40})?(?:has been|was|is) (?:completed|recorded|successful|processed|done)"
    r"|transfer(?:red)?[^.]{0,80}(?:complete|success)|(?:withdrawal|spend|claim|assignment)[^.]{0,60}(?:complete|success|recorded)"
    r"|\bsold [0-9]+ from\b|sale recorded successfully"
    r"|\btransferred [0-9.]+ (?:from|out of)\b)", re.I)
NEGATION_RE = re.compile(
    r"\b(not|no|cannot|can't|could not|couldn't|unable|did not|didn't|declin\w*|abort\w*|skipp?\w*|insufficient|fail\w*|rejected|exceed\w*"
    r"|over the cap|below the floor|would (?:breach|violate|drop)|nothing|unchanged|no action|without (?:making|writing|changing)"
    r"|already (?:held|taken|assigned|claimed|has a holder|sold out|owned|booked|occupied|belongs)|is held by|is assigned to|holder is)\b", re.I)


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
    """``<SEED>|<test>|<model>|<config>`` (registration, Bootstrap); ``|sens<k>`` in sensitivity analysis k."""
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
# src6 (read-only, lazily imported): the lock-safety gate
# ---------------------------------------------------------------------------------------------------------------

_SRC6: Dict[str, Any] = {}


def src6_modules(src6_dir: Optional[str]) -> Dict[str, Any]:
    key = src6_dir or ""
    if key in _SRC6:
        return _SRC6[key]
    if not src6_dir or not os.path.isdir(src6_dir):
        _SRC6[key] = {"error": f"no src6 directory {src6_dir!r}"}
        return _SRC6[key]
    sys.dont_write_bytecode = True
    if src6_dir not in sys.path:
        sys.path.insert(0, src6_dir)
    try:
        import score6  # type: ignore
        from rescore6 import ledger_from_transcript  # type: ignore
        _SRC6[key] = {"score6": score6, "ledger_from_transcript": ledger_from_transcript}
    except Exception as e:  # pragma: no cover
        _SRC6[key] = {"error": f"import failed: {type(e).__name__}: {e}"}
    return _SRC6[key]


# ---------------------------------------------------------------------------------------------------------------
# Normalising one transcript
# ---------------------------------------------------------------------------------------------------------------


class ScorerVersionError(ValueError):
    """A transcript scored without the Study 3 fields."""


def success_reported(text: Any) -> bool:
    t = str(text or "")
    return bool(SUCCESS_RE.search(t)) and not NEGATION_RE.search(t)


def agent_view(s: Mapping[str, Any], raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Per-agent measures, read from score6's columns (never recomputed). ``at_risk`` (the S3-H3 q gate) = a
    perceivable signal and ``protect_before_perceivable`` not True; ``reacting`` = perceivable signal and
    ``protect_before_perceivable`` False. ``at_risk_s2`` / ``reacting_s2``: the same with Study 2's signal set
    (``contention_signals``, ``protect_before_contention``; sensitivity S8)."""
    missing = [f for f in STUDY3_AGENT_FIELDS if f not in s]
    if missing:
        raise ScorerVersionError(f"agent score lacks Study 3 fields {missing}: re-score with the frozen src6/score6.py")
    n_p = int(s["perceivable_signals"] or 0)
    if (n_p > 0) != (s["first_perceivable_call"] is not None):
        raise ScorerVersionError("perceivable_signals disagrees with first_perceivable_call")
    n_s2 = int(s["contention_signals"] or 0)
    pbp, pbc = s["protect_before_perceivable"], s["protect_before_contention"]
    codes = reply_codes(raw.get("first_reply"))
    turns = raw.get("turns") or []
    return {
        "lock": bool(s.get("lock")), "cas": bool(s.get("cas")), "prim": s.get("first_protective") is not None,
        "perceivable": n_p, "pbp": pbp, "at_risk": n_p > 0 and pbp is not True, "reacting": n_p > 0 and pbp is False,
        "exposed_s2": n_s2 > 0, "at_risk_s2": n_s2 > 0 and pbc is not True, "reacting_s2": n_s2 > 0 and pbc is False,
        "read_before_lock": s.get("read_before_lock"), "lock_scope": s.get("lock_scope"),
        "unread_basis": int(s.get("fenced_unread_basis") or 0) > 0,
        "missing_leg": bool(s.get("missing_leg")), "fulfilled": bool(s.get("fulfilled")),
        "committed_writes": int(s.get("committed_writes") or 0), "end": s.get("end_reason"),
        "first_reply": raw.get("first_reply"), "fr_lock": "lock" in codes,
        "success_reported": success_reported(raw.get("final_text")),
        "last_stop": turns[-1].get("stop_reason") if turns else None, "truncated": bool(raw.get("truncated")),
    }


def protocol_order(calls: Sequence[Mapping[str, Any]], aid: str) -> str:
    """D3 (Study 2 post hoc rule, now pre-specified): lock_first / read_then_lock / no_lock by the agent's first
    successful read and first well-formed acquire (granted or 423)."""
    own = [c for c in calls if c["agent_id"] == aid]
    fr = next((c["own_call"] for c in own if c["tool"] == "get_record" and c["status"] == 200), None)
    fl = next((c["own_call"] for c in own if c["tool"] == "acquire_lock" and c["status"] in (200, 423)), None)
    if fl is None:
        return "no_lock"
    return "lock_first" if fr is None or fl < fr else "read_then_lock"


def mechanisms(sc: Mapping[str, Any], calls: Sequence[Mapping[str, Any]], scopes: Mapping[str, str]) -> List[str]:
    """D2 (Study 2 post hoc rules, now pre-specified), for an fs-failed contended episode: ``read_then_lock`` (a stale
    overwrite that is a fenced write whose basis read precedes its token's grant), ``no_lock`` (a stale overwrite that
    is an unfenced write), ``fenced_other`` (another stale fenced write), ``own_only`` (write skew and some agent did
    not hold locks on every record its intent reads), ``missing_leg``."""
    stale, fsb = set(sc.get("stale_overwrite_seqs") or []), set(sc.get("fenced_stale_basis_seqs") or [])
    byeff = {c["effect_seq"]: c for c in calls if c.get("committed")}
    mech = set()
    for es in stale:
        c = byeff.get(es)
        if c is None:
            continue
        if c.get("fencing_token") is not None and es in fsb:
            mech.add("read_then_lock")
        elif c.get("fencing_token") is None:
            mech.add("no_lock")
        else:
            mech.add("fenced_other")
    flags = sc.get("flags") or {}
    if flags.get("write_skew") and any(v != "all" for v in scopes.values()):
        mech.add("own_only")
    if flags.get("missing_leg"):
        mech.add("missing_leg")
    return sorted(mech)


def normalize(tr: Mapping[str, Any], path: str, src6_dir: Optional[str], allow_dry_run: bool) -> Dict[str, Any]:
    t = tr.get("task") or {}
    factory = str(t.get("factory") or "")
    family = str(t.get("family") or factory.replace("_ctrl", ""))
    if family.endswith("_ctrl"):
        family = family[: -len("_ctrl")]
    arm = "control" if factory.endswith("_ctrl") or t.get("category") == "control" else "contended"
    sc = tr.get("score") or {}
    raw_agents = tr.get("agents") or {}
    dry = bool(tr.get("dry_run"))
    rec: Dict[str, Any] = {
        "id": tr.get("episode_id"), "path": path, "model": tr.get("model"), "config": tr.get("config"),
        "start": tr.get("start_mode"), "aware": int(bool(tr.get("concurrency_aware_prompt"))),
        "probe": bool(tr.get("probe")), "study": tr.get("study"), "dry_run": dry, "n_agents": tr.get("n_agents"),
        "family": family, "arm": arm, "instance": int(t.get("instance", -1)), "seed": int(tr.get("seed", 0) or 0),
    }
    agents = {a: agent_view(s, raw_agents.get(a) or {}) for a, s in sorted((sc.get("agents") or {}).items())}
    cap = sc.get("cap_truncated")
    rec.update(fs=int(bool(sc.get("fs_nonserializable"))), basis=int(bool(sc.get("dsg_basis_cycle"))),
               outcome=sc.get("outcome"), cap_truncated=bool(cap), cross_agent_edges=int(sc.get("cross_agent_edges") or 0),
               agents=agents)
    led = tr.get("ledger") or {}
    calls = led.get("calls") or []
    rec["order"] = {a: protocol_order(calls, a) for a in agents}
    rec["mechanisms"] = mechanisms(sc, calls, {a: v["lock_scope"] for a, v in agents.items()}) if rec["fs"] else []
    # the stagger check (C4): every non-lead agent's first call at or after a0's start + stagger_min
    starts = (led.get("flags") or {}).get("start_rounds") or {}
    if rec["start"] == "staggered" and starts:
        lead = sorted(starts)[0]
        smin = int((tr.get("schedule") or {}).get("stagger_min", 0))
        firsts = {a: min((c["step"] for c in calls if c["agent_id"] == a), default=None) for a in starts}
        rec["stagger_ok"] = all(firsts[a] is None or firsts[a] >= starts[lead] + smin for a in starts if a != lead)
    else:
        rec["stagger_ok"] = None
    rec["order_key"] = (str((tr.get("run_info") or {}).get("started_utc") or ""), os.path.basename(path))
    trig = []
    for a, av in agents.items():
        if av["end"] in AGENT_ERROR_ENDS or av["end"] in REFUSAL_ENDS or av["truncated"]:
            trig.append(f"{a}:{av['end'] if av['end'] in AGENT_ERROR_ENDS + REFUSAL_ENDS else 'truncated'}")
        if av["last_stop"] in REFUSAL_STOPS:
            trig.append(f"{a}:{av['last_stop']}")
    rec["exclusion_trigger"] = ";".join(sorted(set(trig))) or None
    rec["errored_agents"] = sorted({x.split(":")[0] for x in trig})
    turns = [tu for _, raw in sorted(raw_agents.items()) for tu in (raw.get("turns") or [])]
    hosts = sorted({host_norm(tu.get("served_host")) for tu in turns})
    rec["hosts"] = hosts
    rec["served"] = sorted({str(tu.get("model_served")) for tu in turns})
    need = REQUIRED_HOST.get(rec["model"])
    rec["host_bad"] = bool(need) and any(not h.startswith(need) and not (h == "fake" and dry and allow_dry_run)
                                         for h in hosts)
    rec["me_violations"] = None
    mods = src6_modules(src6_dir) if led else {"error": "no ledger"}
    fn = getattr(mods.get("score6"), "mutual_exclusion_violations", None)
    if fn is not None:
        try:
            ledger, _ = mods["ledger_from_transcript"](tr)
            rec["me_violations"] = list(fn(ledger))
        except Exception as e:  # pragma: no cover
            rec["me_violations_error"] = f"{type(e).__name__}: {e}"
    return rec


# ---------------------------------------------------------------------------------------------------------------
# Loading and exclusions
# ---------------------------------------------------------------------------------------------------------------


def discover(base: str, allow_dry_run: bool) -> List[str]:
    sub = os.path.join("dry_run", "transcripts") if allow_dry_run else "transcripts"
    return [os.path.join(d, sub) for d in sorted(glob.glob(os.path.join(base, "n2-*")))
            if os.path.isdir(os.path.join(d, sub))]


def read_transcripts(dirs: Sequence[str]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.json"))):
            with open(path) as f:
                yield path, json.load(f)


def pair_key(rec: Mapping[str, Any], arm: Optional[str] = None) -> Tuple[Any, ...]:
    return (rec["model"], rec["config"], rec["start"], rec["family"], rec["instance"], rec["seed"], arm or rec["arm"])


def other_arm(arm: str) -> str:
    return "control" if arm == "contended" else "contended"


def _cell(r: Mapping[str, Any]) -> str:
    return f"{SHORT.get(r['model'], r['model'])}|{r['config']}|{r['start']}"


def select(recs: Sequence[Dict[str, Any]], allow_dry_run: bool) -> Dict[str, Any]:
    """Never-data rules and the exclusion rule (registration, "Data inclusion and exclusion"). If an episode id has
    more than one transcript, the earliest (``run_info.started_utc``, then file name) is used. An episode is excluded
    with its matched partner (the other arm, same model, config, start, family, instance, schedule) if an agent ended
    ``truncated``, ``provider_error``, ``error``, ``refusal`` or ``content_filter``, or its last completion stopped
    ``content_filter`` or ``refusal``, or (Qwen) a written completion was not served by Alibaba."""
    log: Dict[str, Any] = {"never_data": {}, "excluded": [], "flags": {}}

    def bump(d: Dict[str, int], k: str, n: int = 1) -> None:
        d[k] = d.get(k, 0) + n

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in recs:
        why = None
        if r["study"] not in (3, "3"):
            why = "not_study3"
        elif r["dry_run"] and not allow_dry_run:
            why = "dry_run"
        elif (r["config"], r["start"]) not in CONDITIONS:
            why = f"unregistered_condition:{r['config']}@{r['start']}"
        elif r["model"] not in MODELS:
            why = "unregistered_model"
        elif r["n_agents"] != 2 or r["aware"] or r["probe"]:
            why = "unregistered_cell"
        elif r["family"] not in FAMILIES or not 0 <= r["instance"] < INSTANCES or r["seed"] not in SEEDS:
            why = "unregistered_unit"
        if why:
            bump(log["never_data"], why)
            continue
        groups.setdefault(r["id"], []).append(r)
    main: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    as_is: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    excluded: Dict[Tuple[Any, ...], str] = {}
    counts: Dict[str, int] = {}
    by_cell: Dict[str, int] = {}
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
            bump(by_cell, f"{_cell(chosen)}|{chosen['arm']}|{why}")
        else:
            main[pair_key(chosen)] = chosen
    for k, why in sorted(excluded.items(), key=lambda kv: str(kv[0])):
        pk = k[:-1] + (other_arm(k[-1]),)
        if pk in main:
            r = main.pop(pk)
            excluded[pk] = f"partner_of:{why}"
            bump(counts, "partner_excluded")
            bump(by_cell, f"{_cell(r)}|{r['arm']}|partner")
    log["excluded"] = [{"key": list(map(str, k)), "reason": v} for k, v in sorted(excluded.items(), key=lambda kv: str(kv[0]))]
    log["counts"] = dict(sorted(counts.items()))
    log["excluded_by_cell_and_arm"] = dict(sorted(by_cell.items()))
    log["flags"] = {"cap_truncated_episodes": sum(1 for r in main.values() if r["cap_truncated"])}
    return {"main": main, "as_is": as_is, "excluded": excluded, "log": log}


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
    """Reads ``<base>/openrouter_balance.jsonl`` (``analysis6/balance6.py``: one line before and one after the OpenRouter
    lane, each run) and every Study 3 ``spend.jsonl`` under ``base``. Per window: key usage change, Study 3 OpenRouter
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
            windows.append({"from_utc": t0, "to_utc": t1, "key_usage_change_usd": used, "study3_spend_usd": ours,
                            "others_spend_usd": others, "lane_exit": r.get("lane_exit"),
                            "stopped_by_external_cause": bool(r.get("lane_exit") == 4 and others is not None and others > 0.01)})
            before = None
    return {"status": "done", "windows": windows, "unclosed_window": before is not None}




# ---------------------------------------------------------------------------------------------------------------
# Cluster values per test
# ---------------------------------------------------------------------------------------------------------------


class Data:
    """Index of the selected episodes: (model, config, start, family, instance, seed, arm) -> record."""

    def __init__(self, sample: Mapping[Tuple[Any, ...], Dict[str, Any]]):
        self.ep: Dict[Tuple[Any, ...], Dict[str, Any]] = dict(sample)

    def clusters(self, model: str, config: str, start: str) -> List[Tuple[str, int]]:
        return sorted({(k[3], k[4]) for k in self.ep if k[:3] == (model, config, start)})

    def episodes(self, model: str, config: str, start: str, fam: str, inst: int, arm: str) -> List[Dict[str, Any]]:
        return [r for k, r in sorted(self.ep.items(), key=lambda kv: str(kv[0]))
                if k[:5] == (model, config, start, fam, inst) and k[6] == arm]

    def pairs(self, model: str, config: str, start: str, fam: str, inst: int) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        out = []
        for s in sorted({k[5] for k in self.ep if k[:5] == (model, config, start, fam, inst)}):
            c = self.ep.get((model, config, start, fam, inst, s, "contended"))
            k = self.ep.get((model, config, start, fam, inst, s, "control"))
            if c is not None and k is not None:
                out.append((c, k))
        return out


def agent_rate(eps: Sequence[Mapping[str, Any]], outcome: str, agents: Optional[Sequence[str]] = None) -> Optional[float]:
    vals = [bool(a[outcome]) for e in eps for aid, a in e["agents"].items() if agents is None or aid in agents]
    return sum(vals) / len(vals) if vals else None


def h3_outcome(config: str) -> str:
    """S3-H3 uptake: a lock attempt under ``locks``; any primitive (lock or CAS) under ``all_available``."""
    return "lock" if config == "locks" else "prim"


def h1_values(D: Data, model: str, config: str, metric: str = "fs") -> Dict[Tuple[Any, ...], float]:
    """S3-H1: per cluster, mean over its complete pairs (together start) of fs(contended) - fs(control)."""
    out = {}
    for fam, inst in D.clusters(model, config, "together"):
        d = [c[metric] - k[metric] for c, k in D.pairs(model, config, "together", fam, inst)]
        if d:
            out[(fam, inst)] = mean(d)
    return out


def h2a_values(D: Data, model: str) -> Dict[Tuple[Any, ...], float]:
    """S3-H2a: per cluster, fs(locks_s2text) - fs(locks), contended episodes, together start, matched by schedule."""
    out = {}
    for fam, inst in D.clusters(model, "locks", "together"):
        d = []
        for s in SEEDS:
            a = D.ep.get((model, "locks_s2text", "together", fam, inst, s, "contended"))
            b = D.ep.get((model, "locks", "together", fam, inst, s, "contended"))
            if a is not None and b is not None:
                d.append(a["fs"] - b["fs"])
        if d:
            out[(fam, inst)] = mean(d)
    return out


def _rbl_share(eps: Sequence[Mapping[str, Any]]) -> Optional[float]:
    vals = [bool(a["read_before_lock"]) for e in eps for a in e["agents"].values() if a["read_before_lock"] is not None]
    return sum(vals) / len(vals) if vals else None


def h2b_values(D: Data, model: str) -> Dict[Tuple[Any, ...], float]:
    """S3-H2b: per cluster, read-before-lock share among agents granted a lock that committed a write, over both arms
    of the together start, locks_s2text minus locks; a cluster needs one such agent in each config."""
    out = {}
    for fam, inst in D.clusters(model, "locks", "together"):
        a = _rbl_share([e for arm in ("contended", "control") for e in D.episodes(model, "locks_s2text", "together", fam, inst, arm)])
        b = _rbl_share([e for arm in ("contended", "control") for e in D.episodes(model, "locks", "together", fam, inst, arm)])
        if a is not None and b is not None:
            out[(fam, inst)] = a - b
    return out


def h3_values(D: Data, model: str, config: str, agents: Sequence[str] = (LATE_AGENT,),
              outcome: Optional[str] = None) -> Dict[Tuple[Any, ...], float]:
    """S3-H3: per cluster (staggered start), mean over complete pairs of [uptake rate contended - uptake rate control]
    over ``agents`` (registered: the late agent a1)."""
    out, o = {}, outcome or h3_outcome(config)
    for fam, inst in D.clusters(model, config, "staggered"):
        p = D.pairs(model, config, "staggered", fam, inst)
        rc = agent_rate([c for c, _ in p], o, agents)
        rk = agent_rate([k for _, k in p], o, agents)
        if rc is not None and rk is not None:
            out[(fam, inst)] = rc - rk
    return out


def q_values(D: Data, model: str, config: str, agents: Sequence[str] = (LATE_AGENT,),
             risk: str = "at_risk") -> Dict[Tuple[Any, ...], float]:
    """The S3-H3 informativeness gate: per cluster, the share of contended late agents at risk (a perceivable signal
    before any protection), over the complete pairs S3-H3 uses."""
    out = {}
    for fam, inst in D.clusters(model, config, "staggered"):
        r = agent_rate([c for c, _ in D.pairs(model, config, "staggered", fam, inst)], risk, agents)
        if r is not None:
            out[(fam, inst)] = r
    return out


def uctrl_values(D: Data, model: str, config: str, agents: Sequence[str] = (LATE_AGENT,)) -> Dict[Tuple[Any, ...], float]:
    """The S3-H3 room condition: per cluster, the control late agents' uptake rate over the complete pairs S3-H3 uses."""
    out, o = {}, h3_outcome(config)
    for fam, inst in D.clusters(model, config, "staggered"):
        r = agent_rate([k for _, k in D.pairs(model, config, "staggered", fam, inst)], o, agents)
        if r is not None:
            out[(fam, inst)] = r
    return out


def h2b_unconditional_values(D: Data, model: str) -> Dict[Tuple[Any, ...], float]:
    """Sensitivity S9: S3-H2b with every agent in the denominator (read_before_lock True = 1, otherwise 0)."""
    def share(eps: Sequence[Mapping[str, Any]]) -> Optional[float]:
        v = [a["read_before_lock"] is True for e in eps for a in e["agents"].values()]
        return sum(v) / len(v) if v else None
    out = {}
    for fam, inst in D.clusters(model, "locks", "together"):
        a = share([e for arm in ("contended", "control") for e in D.episodes(model, "locks_s2text", "together", fam, inst, arm)])
        b = share([e for arm in ("contended", "control") for e in D.episodes(model, "locks", "together", fam, inst, arm)])
        if a is not None and b is not None:
            out[(fam, inst)] = a - b
    return out


def intersect(per_model: Mapping[str, Mapping[Tuple[Any, ...], float]]) -> Dict[Tuple[Any, ...], float]:
    models = sorted(per_model)
    if not models:
        return {}
    keys = set(per_model[models[0]])
    for m in models[1:]:
        keys &= set(per_model[m])
    return {k: mean([per_model[m][k] for m in models]) for k in sorted(keys, key=str)}


# ---------------------------------------------------------------------------------------------------------------
# The confirmatory suite
# ---------------------------------------------------------------------------------------------------------------


def _entry(test: str, model: str, config: str, status: str, **kw: Any) -> Dict[str, Any]:
    d = {"id": f"{test}|{SHORT.get(model, model)}|{config}", "test": test, "model": model, "config": config,
         "status": status}
    d.update(kw)
    return d


MIN_CLUSTERS = int(math.ceil(REGISTERED_CLUSTERS * MIN_UNIT_FRACTION - 1e-9))  # 48 of 64


def suite(D: Data, n_boot: int, h1_metric: str = "fs", only: Optional[Sequence[str]] = None,
          sens: Optional[int] = None, h3_agents: Sequence[str] = (LATE_AGENT,), h2b_fn: Optional[Callable] = None) -> Dict[str, Any]:
    tests: List[Dict[str, Any]] = []
    want = lambda t: only is None or t in only  # noqa: E731

    def cell(test: str, model: str, config: str, vals: Dict[Tuple[Any, ...], float], kind: str,
             delta: Optional[float]) -> Dict[str, Any]:
        if len(vals) < MIN_CLUSTERS:
            return _entry(test, model, config, "not_tested", n_clusters=len(vals), min_units=MIN_CLUSTERS)
        r = run_test(test, model, config, vals, kind, delta, n_boot, sens=sens)
        return _entry(test, model, config, "tested", min_units=MIN_CLUSTERS, **r)

    def pooled(test: str, config: str, per_model: Dict[str, Dict[Tuple[Any, ...], float]], kind: str,
               delta: Optional[float]) -> Dict[str, Any]:
        models = [SHORT[m] for m in sorted(per_model)]
        if len(per_model) < 2:
            return _entry(test, POOLED, config, "not_tested", models=models, reason="fewer_than_2_models")
        vals = intersect(per_model)
        if len(vals) < MIN_CLUSTERS:
            return _entry(test, POOLED, config, "not_tested", models=models, n_clusters=len(vals), min_units=MIN_CLUSTERS)
        r = run_test(test, POOLED, config, vals, kind, delta, n_boot, sens=sens)
        return _entry(test, POOLED, config, "tested", models=models, min_units=MIN_CLUSTERS, **r)

    for name, cfgs in (("H1-diff", H1_CONFIGS), ("H1cal-diff", ("none",))):
        if not want("H1"):  # the calibration belongs to S3-H1
            continue
        for config in cfgs:
            tested = {}
            for model in MODELS:
                v = h1_values(D, model, config, h1_metric)
                e = cell(name, model, config, v, "greater", None)
                tests.append(e)
                if e["status"] == "tested":
                    tested[model] = v
            tests.append(pooled(name, config, tested, "greater", None))
    for name, fn in (("H2a", h2a_values), ("H2b", h2b_fn or h2b_values)):
        if not want(name):
            continue
        tested = {}
        for model in MODELS:
            v = fn(D, model)
            e = cell(name, model, "locks_s2text-locks", v, "greater", None)
            tests.append(e)
            if e["status"] == "tested":
                tested[model] = v
        tests.append(pooled(name, "locks_s2text-locks", tested, "greater", None))
    if want("H3"):
        for config in H3_CONFIGS:
            vals = {m: h3_values(D, m, config, h3_agents) for m in MODELS}
            qv = {m: q_values(D, m, config, h3_agents) for m in MODELS}
            uv = {m: uctrl_values(D, m, config, h3_agents) for m in MODELS}
            for kind, tname in (("tost", "H3-eq"), ("greater", "H3-diff")):
                tested = {}
                for model in MODELS:
                    e = cell(tname, model, config, vals[model], kind, DELTA_CELL if kind == "tost" else None)
                    e["q"] = mean(list(qv[model].values())) if qv[model] else None
                    e["u_ctrl"] = mean(list(uv[model].values())) if uv[model] else None
                    tests.append(e)
                    if e["status"] == "tested":
                        tested[model] = vals[model]
                pe = pooled(tname, config, tested, kind, DELTA_POOLED if kind == "tost" else None)
                keys = set(intersect(tested)) if tested else set()
                qs = [mean([qv[m][k] for k in keys if k in qv[m]]) for m in tested if any(k in qv[m] for k in keys)]
                pe["q"] = mean(qs) if qs else None
                us = [mean([uv[m][k] for k in keys if k in uv[m]]) for m in tested if any(k in uv[m] for k in keys)]
                pe["u_ctrl"] = mean(us) if us else None
                tests.append(pe)
    apply_holm(tests, n_boot)
    return {"tests": tests}


HOLM_FAMILIES = ("H1-diff", "H2a", "H2b", "H3-eq/stage1", "H3-eq/stage2", "H3-diff")


def holm_family(t: Mapping[str, Any]) -> Optional[str]:
    if t["status"] not in ("tested", "not_tested_gate_closed"):
        return None
    if t["test"] == "H3-eq":
        return "H3-eq/stage1" if t["model"] == POOLED else "H3-eq/stage2"
    if t["test"] in ("H1-diff", "H2a", "H2b", "H3-diff"):
        return t["test"]
    return None  # H1cal-diff: raw p at alpha (calibration)


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
    """Holm within each family; S3-H3-eq by serial gatekeeping: stage 2 (per-model cells) is tested only if both
    stage-1 (pooled) tests were tested and rejected."""
    stage1 = [t for t in tests if holm_family(t) == "H3-eq/stage1"]
    _holm_with_recompute(stage1, "H3-eq/stage1", n_boot)
    pooled_all = [t for t in tests if t["test"] == "H3-eq" and t["model"] == POOLED]
    gate_open = len(stage1) == len(H3_CONFIGS) and len(pooled_all) == len(H3_CONFIGS) and all(t["reject"] for t in stage1)
    stage2 = [t for t in tests if holm_family(t) == "H3-eq/stage2"]
    if gate_open:
        _holm_with_recompute(stage2, "H3-eq/stage2", n_boot)
    else:
        for t in stage2:
            t.update(status="not_tested_gate_closed", reject=None, p_adj=None, holm_family="H3-eq/stage2")
    for t in pooled_all + stage2:
        t["gate_open"] = gate_open
    for fam in ("H1-diff", "H2a", "H2b", "H3-diff"):
        _holm_with_recompute([t for t in tests if holm_family(t) == fam], fam, n_boot)
    for t in tests:
        if t["test"] == "H1cal-diff" and t["status"] == "tested":
            t["p_adj"], t["holm_level"] = None, ALPHA
            if _mc_near(t, ALPHA):
                _recompute(t, n_boot)
            t["reject"] = t["p"] < ALPHA
    for t in tests:
        if t.get("kind") == "tost" and t.get("_bs") is not None and t.get("holm_level"):
            t["ci_holm_t"] = t_interval(t["_bs"], t["holm_level"])


# ---------------------------------------------------------------------------------------------------------------
# Claims per cell (registration, "Reading per cell, and the claim allowed")
# ---------------------------------------------------------------------------------------------------------------


def _f(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def read_cells(tests: List[Dict[str, Any]], s5_tests: Optional[Sequence[Mapping[str, Any]]] = None,
               leakage: Optional[Mapping[str, Any]] = None) -> None:
    """S3-H3: ``reading`` and ``claim`` per (model, config) and pooled pair (eq, diff). eq_claim = the eq test rejected
    (Holm and gate), it rejects under sensitivity S5 too, and the cell is informative (q > delta). Readings:
    worse_within_delta, bounded, worse, uninformative, inconclusive. S3-H1, S3-H2a, S3-H2b: ``reading`` = the
    difference rejected or not; a non-rejection is never read as no effect."""
    by = {(t["test"], t["model"], t["config"]): t for t in tests}
    s5 = {t["id"]: t for t in (s5_tests or [])}
    for (test, model, config), eq in sorted(by.items(), key=lambda kv: str(kv[0])):
        if test != "H3-eq":
            continue
        diff = by.get(("H3-diff", model, config))
        if diff is None or eq["status"] not in ("tested", "not_tested_gate_closed") or diff["status"] != "tested":
            continue
        flags: List[str] = []
        eq_rej, diff_rej = bool(eq.get("reject")), bool(diff.get("reject"))
        if eq["status"] == "not_tested_gate_closed":
            flags.append("eq_not_tested_gate_closed")
        robust = True
        if eq_rej and s5_tests is not None:
            robust = bool(s5.get(eq["id"], {}).get("reject"))
            if not robust:
                flags.append("eq_not_robust_to_sensitivity_S5")
        q, d, u = eq.get("q"), eq.get("delta"), eq.get("u_ctrl")
        enough_risk = q is not None and q > d + EPS
        room = u is not None and 1 - u >= d - EPS  # a reaction of size delta is possible above the control uptake
        informative = enough_risk and room
        why = "; ".join(x for x in ("" if enough_risk else f"q = {_f(q)} <= delta",
                                    "" if room else f"control uptake {_f(u)} leaves less than delta of room") if x)
        if eq_rej and not enough_risk:
            flags.append("uninformative_low_q")
        if eq_rej and not room:
            flags.append("uninformative_ceiling")
        if eq_rej and informative:
            eq["implied_bound_reacting_share"] = d / q
        if leakage is not None and model != POOLED and leakage.get(SHORT.get(model, model), {}).get("leaks"):
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
        i90 = eq.get("ci90_t") or [None, None]
        i95 = diff.get("ci95") or [None, None]
        x = _f(eq.get("estimate"))
        noun = OUTCOME_NOUN["H3"]
        txt = {
            "bounded": f"Contention changed the {noun} by at most ±{_f(d)} (Δ = {x}, 90 % [{_f(i90[0])}, {_f(i90[1])}]; "
                       f"q = {_f(q)}, control uptake {_f(u)}, implied bound on the reacting share of at-risk late agents "
                       f"{_f(d / q if q else None)}).",
            "worse": f"Contention raised the {noun} (Δ = {x}, 95 % [{_f(i95[0])}, {_f(i95[1])}]).",
            "worse_within_delta": f"Contention raised the {noun}, by less than {_f(d)} (Δ = {x}, 90 % [{_f(i90[0])}, {_f(i90[1])}]).",
            "uninformative": f"Inconclusive: the equivalence is uninformative here ({why}) (Δ = {x}, 90 % [{_f(i90[0])}, {_f(i90[1])}]).",
            "inconclusive": f"Inconclusive (Δ = {x}, 90 % [{_f(i90[0])}, {_f(i90[1])}]). No direction is claimed.",
        }[reading]
        if "eq_not_robust_to_sensitivity_S5" in flags and reading in ("inconclusive", "worse"):
            txt += " The equivalence test rejected but did not hold under sensitivity S5, so no bound is claimed."
        for t in (eq, diff):
            t["reading"], t["flags"], t["claim"] = reading, flags, txt
    claims = {"H1-diff": "Contention added integrity failures under {c} (Δ = {x}, 95 % [{lo}, {hi}]).",
              "H1cal-diff": "Calibration: contention added integrity failures under none (Δ = {x}, 95 % [{lo}, {hi}]).",
              "H2a": "The Study 3 lock text lowered contended integrity failures against the Study 2 text by {x} (95 % [{lo}, {hi}]).",
              "H2b": "The Study 3 lock text lowered the read-before-lock share of lock users by {x} (95 % [{lo}, {hi}])."}
    for t in tests:
        if t["test"] in claims and t["status"] == "tested":
            lo, hi = t.get("ci95") or (None, None)
            t["reading"] = "rejects" if t.get("reject") else "does_not_reject"
            t["claim"] = (claims[t["test"]].format(c=t["config"], x=_f(t.get("estimate")), lo=_f(lo), hi=_f(hi))
                          if t.get("reject") else f"No claim (Δ = {_f(t.get('estimate'))}); not evidence of no effect.")


# ---------------------------------------------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------------------------------------------


def leakage_values(D: Data, model: str) -> Dict[Tuple[Any, ...], float]:
    """C1: units (family, instance, config, start) under the three lock configs with both a1 episodes; d = first-reply
    lock token of a1 contended minus a1 control (the first completion's input differs only by the group tag)."""
    out: Dict[Tuple[Any, ...], float] = {}
    for k, r in sorted(D.ep.items(), key=lambda kv: str(kv[0])):
        m, c, st, fam, inst, s, arm = k
        if m != model or arm != "contended" or c not in LOCK_CONFIGS:
            continue
        ctl = D.ep.get((m, c, st, fam, inst, s, "control"))
        if ctl and LATE_AGENT in r["agents"] and LATE_AGENT in ctl["agents"]:
            out[(fam, inst, c, st)] = float(r["agents"][LATE_AGENT]["fr_lock"]) - float(ctl["agents"][LATE_AGENT]["fr_lock"])
    return out


def checks(D: Data, sample: Mapping[Tuple[Any, ...], Dict[str, Any]], n_boot: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    leak = {}
    for model in MODELS:
        vals = leakage_values(D, model)
        if not vals:
            leak[SHORT[model]] = {"status": "not_run", "n_units": 0, "p": None, "leaks": False}
            continue
        r = run_test("leakage", model, "+".join(LOCK_CONFIGS), vals, "two_sided", None, n_boot)
        r = {k: v for k, v in r.items() if not k.startswith("_")}
        r.update(status="tested", n_units=len(vals), leaks=r["p"] < ALPHA)
        leak[SHORT[model]] = r
    out["leakage"] = leak
    expo: Dict[str, Any] = {}
    for model in MODELS:
        for config, start in CONDITIONS:
            eps = [r for k, r in D.ep.items() if k[:3] == (model, config, start) and k[6] == "contended"]
            if not eps:
                continue
            expo[f"{SHORT[model]}|{config}|{start}"] = {
                "perceivable_share": agent_rate(eps, "perceivable"), "study2_signal_share": agent_rate(eps, "exposed_s2"),
                "late_agent_at_risk_share": agent_rate(eps, "at_risk", (LATE_AGENT,)), "episodes": len(eps)}
    ctrl = [f"{e['id']}:{a}" for k, e in sorted(D.ep.items(), key=lambda kv: str(kv[0])) if k[6] == "control"
            for a, av in e["agents"].items() if av["perceivable"] or av["exposed_s2"]]
    out["exposure"] = {"cells": expo, "control_agents_exposed": len(ctrl), "examples": ctrl[:20], "ok": not ctrl,
                       "note": "a control agent with a signal is a scorer bug: fix, rescore all, report a deviation"}
    iso = [r["id"] for r in sample.values() if r["arm"] == "control" and r["cross_agent_edges"] != 0]
    me_na = sum(1 for r in sample.values() if r["me_violations"] is None)
    me_bad = [r["id"] for r in sample.values() if r["me_violations"]]
    out["isolation"] = {"control_episodes_with_cross_agent_edges": len(iso), "examples": sorted(iso)[:20], "ok": not iso}
    out["lock_safety"] = {"episodes_with_mutual_exclusion_violations": len(me_bad), "examples": sorted(me_bad)[:20],
                          "episodes_not_checked": me_na, "ok": not me_bad and me_na == 0}
    stg = [r for r in sample.values() if r["start"] == "staggered"]
    bad = [r["id"] for r in stg if r["stagger_ok"] is False]
    out["stagger"] = {"staggered_episodes": len(stg), "violations": len(bad), "examples": bad[:20], "ok": not bad}
    return out


# ---------------------------------------------------------------------------------------------------------------
# Pre-specified descriptive blocks (no test, no Holm)
# ---------------------------------------------------------------------------------------------------------------


def descriptives(D: Data, n_boot: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # D1 amounts: half-done transfers and success reports, distinct vs same amount (contended, together)
    d1: Dict[str, Any] = {}
    for model in MODELS:
        for config in ("cas_available", "all_available", "locks_s2text", "locks", "none"):
            for fam in FAMILIES:
                eps = [r for k, r in D.ep.items() if k[:4] == (model, config, "together", fam) and k[6] == "contended"]
                ags = [a for e in eps for a in e["agents"].values()]
                if not ags:
                    continue
                half = [a for a in ags if a["missing_leg"]]
                d1[f"{SHORT[model]}|{config}|{fam}"] = {
                    "agents": len(ags), "half_done": len(half),
                    "half_done_success_reported": sum(a["success_reported"] for a in half),
                    "no_write_success_reported": sum(1 for a in ags if a["committed_writes"] == 0 and a["success_reported"]),
                    "fs_episodes": sum(e["fs"] for e in eps), "episodes": len(eps)}
    out["D1_amounts"] = d1
    # D2 lock-failure mechanisms (fs-failed contended episodes, lock configs, both starts)
    d2: Dict[str, Any] = {}
    for model in MODELS:
        for config, start in CONDITIONS:
            if config not in LOCK_CONFIGS:
                continue
            eps = [r for k, r in D.ep.items() if k[:3] == (model, config, start) and k[6] == "contended" and r["fs"]]
            row = {"failed": len(eps)}
            for mname in ("read_then_lock", "no_lock", "own_only", "fenced_other", "missing_leg"):
                row[mname] = sum(mname in e["mechanisms"] for e in eps)
            three = [len({"read_then_lock", "no_lock", "own_only"} & set(e["mechanisms"])) for e in eps]
            row.update(exactly_one=three.count(1), more_than_one=sum(x > 1 for x in three), none_of_three=three.count(0))
            d2[f"{SHORT[model]}|{config}|{start}"] = row
    out["D2_lock_mechanisms"] = d2
    # D3 protocol order and lock scope per agent (lock configs, both arms, both starts)
    d3: Dict[str, Any] = {}
    for model in MODELS:
        for config, start in CONDITIONS:
            if config not in LOCK_CONFIGS:
                continue
            for arm in ("contended", "control"):
                eps = [r for k, r in D.ep.items() if k[:3] == (model, config, start) and k[6] == arm]
                codes = [e["order"][a] for e in eps for a in e["agents"]]
                multi = [e["agents"][a]["lock_scope"] for e in eps if e["family"] in MULTI_FAMILIES for a in e["agents"]]
                rbl = [a["read_before_lock"] for e in eps for a in e["agents"].values() if a["read_before_lock"] is not None]
                blind = [a["unread_basis"] for e in eps for a in e["agents"].values() if a["read_before_lock"] is not None]
                if codes:
                    d3[f"{SHORT[model]}|{config}|{start}|{arm}"] = {
                        "agents": len(codes), **{c: codes.count(c) / len(codes) for c in ("lock_first", "read_then_lock", "no_lock")},
                        "multi_agents": len(multi), **{f"scope_{s}": (multi.count(s) / len(multi) if multi else None)
                                                       for s in ("all", "own", "none")},
                        "read_before_lock_eligible": len(rbl), "read_before_lock_share": (sum(rbl) / len(rbl)) if rbl else None,
                        "fenced_unread_basis_share": (sum(blind) / len(blind)) if blind else None}
    out["D3_protocol"] = d3
    # D4 (H3b): among at-risk contended late agents (staggered), the share that reacted (protected after the signal)
    d4: Dict[str, Any] = {}
    for model in MODELS:
        for config in H3_CONFIGS:
            acc: Dict[Tuple[Any, ...], List[int]] = {}
            for fam, inst in D.clusters(model, config, "staggered"):
                for c, _ in D.pairs(model, config, "staggered", fam, inst):
                    a = c["agents"].get(LATE_AGENT)
                    if a and a["at_risk"]:
                        acc.setdefault((fam, inst), []).append(int(a["reacting"]))
            vals = {k: mean(v) for k, v in acc.items()}
            r = run_test("H3b", model, config, vals, "greater", None, n_boot, describe_only=True) if vals else {}
            d4[f"{SHORT[model]}|{config}"] = {"late_agents_at_risk": sum(len(v) for v in acc.values()),
                                              "reacting": sum(sum(v) for v in acc.values()), "n_clusters": len(vals),
                                              "estimate": r.get("estimate"), "ci95": r.get("ci95")}
    out["D4_reacting_share"] = d4
    # D4b: the conditional reaction. Among contended late agents at risk, uptake minus that of the paired control late
    # agent (same seed: the same start, first call round and first completion input, so the at-risk event precedes any
    # divergence between the arms). Cluster value = mean over its at-risk pairs; clusters without one are dropped.
    d4b: Dict[str, Any] = {}
    for model in MODELS:
        for config in H3_CONFIGS:
            o = h3_outcome(config)
            acc2: Dict[Tuple[Any, ...], List[float]] = {}
            for fam, inst in D.clusters(model, config, "staggered"):
                for c, k in D.pairs(model, config, "staggered", fam, inst):
                    a, b = c["agents"].get(LATE_AGENT), k["agents"].get(LATE_AGENT)
                    if a and b and a["at_risk"]:
                        acc2.setdefault((fam, inst), []).append(float(a[o]) - float(b[o]))
            vals = {kk: mean(v) for kk, v in acc2.items()}
            r = run_test("H3b", model, config + "|conditional", vals, "two_sided", None, n_boot, describe_only=True) if vals else {}
            d4b[f"{SHORT[model]}|{config}"] = {"pairs": sum(len(v) for v in acc2.values()), "n_clusters": len(vals),
                                               "estimate": r.get("estimate"), "ci95": r.get("ci95")}
    out["D4b_conditional_reaction"] = d4b
    # D6: reactive re-read. Among late agents granted a lock that committed a write (staggered), the read-before-lock
    # share, contended minus control, per cluster (clusters need an eligible late agent in both arms).
    d6: Dict[str, Any] = {}
    for model in MODELS:
        for config in H3_CONFIGS:
            vals = {}
            for fam, inst in D.clusters(model, config, "staggered"):
                p = D.pairs(model, config, "staggered", fam, inst)
                ca = [c["agents"][LATE_AGENT]["read_before_lock"] for c, _ in p if LATE_AGENT in c["agents"]]
                ka = [k["agents"][LATE_AGENT]["read_before_lock"] for _, k in p if LATE_AGENT in k["agents"]]
                ca, ka = [x for x in ca if x is not None], [x for x in ka if x is not None]
                if ca and ka:
                    vals[(fam, inst)] = sum(ca) / len(ca) - sum(ka) / len(ka)
            r = run_test("H3b", model, config + "|reread", vals, "two_sided", None, n_boot, describe_only=True) if vals else {}
            d6[f"{SHORT[model]}|{config}"] = {"n_clusters": len(vals), "estimate": r.get("estimate"), "ci95": r.get("ci95")}
    out["D6_reactive_reread"] = d6
    # D5 fs per family, condition and arm
    d5: Dict[str, Any] = {}
    for model in MODELS:
        for config, start in CONDITIONS:
            for fam in FAMILIES:
                for arm in ("contended", "control"):
                    eps = [r for k, r in D.ep.items() if k[:4] == (model, config, start, fam) and k[6] == arm]
                    if eps:
                        d5[f"{SHORT[model]}|{config}|{start}|{fam}|{arm}"] = {"episodes": len(eps), "fs": sum(e["fs"] for e in eps)}
    out["D5_fs_by_family"] = d5
    return out


# ---------------------------------------------------------------------------------------------------------------
# Sensitivity analyses (registration, S1 to S9)
# ---------------------------------------------------------------------------------------------------------------


def verdicts(tests: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {t["id"]: {"status": t["status"], "reject": t.get("reject"), "reading": t.get("reading")}
            for t in tests if t["status"] in ("tested", "not_tested_gate_closed")}


def changed(main: Sequence[Mapping[str, Any]], other: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    a, b = verdicts(main), verdicts(other)
    return [{"id": k, "main": a.get(k), "sensitivity": b.get(k)} for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


def drop_with_partners(sample: Mapping[Tuple[Any, ...], Dict[str, Any]], bad: Callable[[Dict[str, Any]], bool]) -> Tuple[Dict[Tuple[Any, ...], Dict[str, Any]], int]:
    drop = {k[:-1] for k, r in sample.items() if bad(r)}
    return {k: r for k, r in sample.items() if k[:-1] not in drop}, len(drop)


def against_equivalence_sample(sel: Mapping[str, Any]) -> Tuple[Dict[Tuple[Any, ...], Dict[str, Any]], int]:
    """S5: every excluded pair enters as written; in its contended episode fs = 1 and every errored agent counts as
    having used a primitive (lock and prim), against equivalence; the control enters as scored."""
    out = dict(sel["main"])
    n = 0
    for k, r in sel["as_is"].items():
        if k in out:
            continue
        r2 = dict(r)
        if r["arm"] == "contended":
            r2["fs"] = 1
            ag = {a: dict(v) for a, v in r["agents"].items()}
            for a in r["errored_agents"]:
                if a in ag:
                    ag[a].update(lock=True, prim=True)
            r2["agents"] = ag
        out[k] = r2
        n += 1
    return out, n


def holm_within_model(tests: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for model in MODELS:
        mem = [t for t in tests if t["model"] == model and t["status"] in ("tested", "not_tested_gate_closed")
               and t["test"] in ("H1-diff", "H2a", "H2b", "H3-eq", "H3-diff") and t.get("p") is not None]
        adj = holm([t["p"] for t in mem])
        out[SHORT[model]] = {t["id"]: {"p": t["p"], "p_adj": a, "reject": a is not None and a < ALPHA,
                                       "main_reject": t.get("reject"),
                                       "changed": (a is not None and a < ALPHA) != bool(t.get("reject"))}
                             for t, a in zip(mem, adj)}
    return out


def sensitivities(sel: Mapping[str, Any], main: Sequence[Mapping[str, Any]], n_boot: int,
                  s5: Sequence[Mapping[str, Any]], n5: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    s1, n1 = drop_with_partners(sel["main"], lambda r: r["cap_truncated"])
    t1 = suite(Data(s1), n_boot, sens=1)["tests"] if n1 else [dict(t) for t in main]
    read_cells(t1)
    out["S1_cap_truncated_excluded"] = {"pairs_dropped": n1, "changed_verdicts": changed(main, t1)}
    keep = dict(sel["as_is"])
    t2 = suite(Data(keep), n_boot, sens=2)["tests"] if len(keep) != len(sel["main"]) else [dict(t) for t in main]
    read_cells(t2)
    out["S2_exclusions_kept"] = {"episodes_added": len(keep) - len(sel["main"]), "changed_verdicts": changed(main, t2)}
    out["S3_holm_within_model"] = holm_within_model(main)
    out["S4_family_level"] = {t["id"]: t.get("p_family_level") for t in main if t["status"] in ("tested", "not_tested_gate_closed")}
    out["S5_against_equivalence"] = {"pairs_added": n5, "changed_verdicts": changed(main, s5), "tests": slim(s5)}
    t6 = suite(Data(sel["main"]), n_boot, h1_metric="basis", only=("H1",), sens=6)["tests"]
    out["S6_h1_dsg_basis_cycle"] = {"tests": slim(t6),
                                    "changed_verdicts": changed([t for t in main if t["test"].startswith("H1")], t6)}
    t7 = suite(Data(sel["main"]), n_boot, only=("H3",), sens=7, h3_agents=("a0", "a1"))["tests"]
    read_cells(t7)
    out["S7_h3_both_agents"] = {"tests": slim(t7), "changed_verdicts": changed([t for t in main if t["test"].startswith("H3")], t7)}
    t9 = suite(Data(sel["main"]), n_boot, only=("H2b",), sens=9, h2b_fn=h2b_unconditional_values)["tests"]
    read_cells(t9)
    out["S9_h2b_every_agent"] = {"tests": slim(t9), "changed_verdicts": changed([t for t in main if t["test"] == "H2b"], t9)}
    D = Data(sel["main"])
    out["S8_q_study2_signals"] = {f"{SHORT[m]}|{c}": (lambda v: mean(list(v.values())) if v else None)(
        q_values(D, m, c, risk="at_risk_s2")) for m in MODELS for c in H3_CONFIGS}
    return out


def slim(tests: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    keep = ("id", "status", "estimate", "ci95", "ci90_t", "p", "p_adj", "reject", "reading", "flags", "n_clusters", "q",
            "u_ctrl")
    return [{k: t[k] for k in keep if k in t} for t in tests]


# ---------------------------------------------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------------------------------------------


def load_sample(transcripts: Iterable[Tuple[str, Mapping[str, Any]]], src6_dir: Optional[str], allow_dry_run: bool,
                root: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
    recs, hashes = [], []
    for path, tr in transcripts:
        recs.append(normalize(tr, path, src6_dir, allow_dry_run))
        rel = os.path.relpath(path, root) if root else os.path.basename(path)
        hashes.append([rel, sha256_file(path) if os.path.exists(path) else hashlib.sha256(
            json.dumps(tr, sort_keys=True).encode()).hexdigest()])
    return recs, sorted(hashes)


def inputs_digest(hashes: Sequence[Sequence[str]]) -> str:
    return hashlib.sha256("\n".join(f"{a} {b}" for a, b in hashes).encode()).hexdigest()


def run_analysis(transcripts: Iterable[Tuple[str, Mapping[str, Any]]], allow_dry_run: bool, n_boot: int = N_BOOT,
                 src6_dir: Optional[str] = DEFAULT_SRC6, root: Optional[str] = None,
                 failures: Optional[Mapping[str, int]] = None, with_sensitivity: bool = True) -> Dict[str, Any]:
    recs, hashes = load_sample(transcripts, src6_dir, allow_dry_run, root=root)
    sel = select(recs, allow_dry_run)
    D = Data(sel["main"])
    main = suite(D, n_boot)["tests"]
    ck = checks(D, sel["main"], n_boot)
    s5_sample, n5 = against_equivalence_sample(sel)
    s5 = suite(Data(s5_sample), n_boot, only=("H3",), sens=5)["tests"] if n5 else [dict(t) for t in main if t["test"].startswith("H3")]
    read_cells(s5, leakage=ck["leakage"])
    read_cells(main, s5_tests=s5, leakage=ck["leakage"])
    res: Dict[str, Any] = {
        "registration": "PREREGISTRATION_STUDY3.md", "dry_run": allow_dry_run,
        "constants": {"B": n_boot, "seed": SEED, "alpha": ALPHA, "delta_cell": DELTA_CELL, "delta_pooled": DELTA_POOLED,
                      "min_clusters": MIN_CLUSTERS, "registered_clusters": REGISTERED_CLUSTERS, "late_agent": LATE_AGENT,
                      "signflip_mc_R": N_SIGNFLIP_MC},
        "inputs": {"n_files": len(hashes), "sha256_of_list": inputs_digest(hashes)},
        "selection": sel["log"], "provider_failures": dict(failures or {}), "budget": balance_report(root),
        "tests": main, "checks": ck, "descriptive": descriptives(D, n_boot),
    }
    if with_sensitivity:
        res["sensitivity"] = sensitivities(sel, main, n_boot, s5, n5)
    res["summary"] = {t["id"]: {"status": t["status"], "estimate": t.get("estimate"), "p": t.get("p"),
                                "p_adj": t.get("p_adj"), "reject": t.get("reject"), "reading": t.get("reading"),
                                "claim": t.get("claim"), "q": t.get("q"), "u_ctrl": t.get("u_ctrl")}
                      for t in main if t["status"] in ("tested", "not_tested_gate_closed")}
    return res


# ---------------------------------------------------------------------------------------------------------------
# numbers.tex
# ---------------------------------------------------------------------------------------------------------------

_DIGITS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
           "8": "eight", "9": "nine"}


def macro(*parts: str) -> str:
    s = "Siii" + "".join(p[:1].upper() + p[1:] for p in parts if p)
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



_TEST_TEX3 = {"H1-diff": "HoneDiff", "H1cal-diff": "HoneCalDiff", "H2a": "HtwoA", "H2b": "HtwoB", "H3-eq": "HthreeEq",
              "H3-diff": "HthreeDiff"}


def numbers_tex(res: Mapping[str, Any], self_hash: str) -> str:
    lines = ["% GENERATED by analysis6/analyze6.py -- do not edit.", f"% analyze6.py sha256 {self_hash}",
             f"% inputs: {res['inputs']['n_files']} transcripts, list sha256 {res['inputs']['sha256_of_list']}"]
    vals: Dict[str, str] = {"SiiiDryRunFlag": "1" if res["dry_run"] else "0",
                            "SiiiNBoot": f"{res['constants']['B']:,}".replace(",", "{,}"), "SiiiBootSeed": SEED,
                            "SiiiDeltaCell": fnum(DELTA_CELL), "SiiiDeltaPooled": fnum(DELTA_POOLED)}
    for t in res["tests"]:
        if t["test"] not in _TEST_TEX3:
            continue
        cfg = "TwoVsThree" if t["test"] in ("H2a", "H2b") else CFG_SHORT.get(t["config"], t["config"])
        base = (_TEST_TEX3[t["test"]], "Pooled" if t["model"] == POOLED else SHORT[t["model"]], cfg)
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
    vals["SiiiControlExposedAgents"] = str(ck["exposure"]["control_agents_exposed"])
    vals["SiiiIsolationViolations"] = str(ck["isolation"]["control_episodes_with_cross_agent_edges"])
    vals["SiiiMutexViolations"] = str(ck["lock_safety"]["episodes_with_mutual_exclusion_violations"])
    vals["SiiiStaggerViolations"] = str(ck["stagger"]["violations"])
    for k, v in res["selection"].get("counts", {}).items():
        vals[macro("Excl", *k.split("_"))] = str(v)
    sens = res.get("sensitivity") or {}
    for key, name in (("S1_cap_truncated_excluded", "CapTrunc"), ("S2_exclusions_kept", "ExclKept"),
                      ("S5_against_equivalence", "AgainstEq"), ("S6_h1_dsg_basis_cycle", "Basis"),
                      ("S7_h3_both_agents", "BothAgents")):
        if key in sens and "changed_verdicts" in sens[key]:
            vals[macro("Sens", name, "Changed")] = str(len(sens[key]["changed_verdicts"]))
    if "S3_holm_within_model" in sens:
        vals["SiiiSensHolmModelChanged"] = str(sum(v["changed"] for m in sens["S3_holm_within_model"].values() for v in m.values()))
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
    data["analyze6_sha256"] = self_hash
    jp, tp = os.path.join(out, "results.json"), os.path.join(out, "numbers.tex")
    with open(jp, "w") as f:
        json.dump(_jsonable(data), f, indent=1, sort_keys=True)
        f.write("\n")
    with open(tp, "w") as f:
        f.write(numbers_tex(res, self_hash))
    return jp, tp


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("analyze",))
    ap.add_argument("--base", required=True, help="results6/study3 (lane directories n2-*)")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--src6", default=DEFAULT_SRC6)
    ap.add_argument("--allow-dry-run", action="store_true", help="rehearsal on dry-run transcripts (never data)")
    ap.add_argument("--n-boot", type=int, default=N_BOOT, help="registered: 10000 (other values only for tests)")
    ap.add_argument("--no-sensitivity", action="store_true")
    a = ap.parse_args(argv)
    dirs = discover(a.base, a.allow_dry_run)
    if not dirs:
        raise SystemExit(f"no transcripts under {a.base}")
    res = run_analysis(read_transcripts(dirs), a.allow_dry_run, a.n_boot, a.src6, root=a.base,
                       failures=failure_counts(dirs), with_sensitivity=not a.no_sensitivity)
    jp, tp = write_outputs(res, a.out)
    n_t = sum(1 for t in res["tests"] if t["status"] == "tested")
    print(f"{'DRY RUN - ' if a.allow_dry_run else ''}{n_t} tests run; wrote {jp} and {tp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
