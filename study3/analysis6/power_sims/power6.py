"""Study 3 power of the registered decision tests (PREREGISTRATION_STUDY3.md, "Sample size rationale"), on the Study 2
generator (simlib.py and sim_tost.py, copied unchanged from analysis5/power_sims): 64 clusters per model (8 families
x 8 instances), one schedule, so ONE episode per arm (or per config) per cluster; ICC 0.3 within an arm-cluster;
correlation r between the two members of a pair; cross-model cluster correlation rho_m for pooled tests (mean over
3 models). Needs numpy and scipy; not part of the analysis. python3 power6.py [nsim]  (writes power6_out.json)
"""
import json
import sys

import numpy as np

import simlib as L
import sim_tost as S


def gen8(ns, k, mu_c, rho=0.3, r=0.3, n_models=1, rho_m=0.0, shift=0.0, m=64):
    """simlib.gen with 8 families (simlib hard-codes Study 2's 7): contended = control prob + shift."""
    if shift == 0:
        return S.gen_d(ns, m, k, mu_c, mu_c, rho, r, n_models, rho_m)
    return S.gen_d(ns, m, k, mu_c, None, rho, r, n_models, rho_m, fam_delta=[shift] * 8)

NS = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
M = 64
ALPHA = 0.05
out = {"nsim": NS, "clusters": M, "rows": []}


def pooled(ns, k, mu, shift, r, rho_m):
    v = gen8(ns, k, mu, rho=0.3, r=r, n_models=3, rho_m=rho_m, shift=shift, m=M)
    return v.mean(1)


def single(ns, k, mu, shift, r):
    return gen8(ns, k, mu, rho=0.3, r=r, n_models=1, shift=shift, m=M)[:, 0, :]


def row(**kw):
    out["rows"].append(kw)
    print(json.dumps(kw), flush=True)


# S3-H1 (difference, sign-flip, one-sided; Holm over 16: first step alpha/16). Control rate 0.02 (Study 2: 0 to 0.07).
for d in (0.10, 0.15, 0.20, 0.30):
    p1 = L.signflip_greater(single(NS, 1, 0.02, d, 0.3))
    pp = L.signflip_greater(pooled(NS, 1, 0.02, d, 0.3, 0.3))
    row(test="H1-diff", delta_true=d, base=0.02, k=1, per_model_a16=float((p1 < ALPHA / 16).mean()),
        per_model_a=float((p1 < ALPHA).mean()), pooled_a16=float((pp < ALPHA / 16).mean()))

# S3-H2a (fs, locks_s2text - locks, contended, one episode per config-cluster, r = 0.3; Holm over 4: alpha/4 first)
for base in (0.35, 0.55, 0.80):
    for d in (0.10, 0.15, 0.20, 0.25, 0.30):
        if base - d < 0.02:
            continue
        p1 = L.signflip_greater(single(NS, 1, base - d, d, 0.3))
        pp = L.signflip_greater(pooled(NS, 1, base - d, d, 0.3, 0.3))
        row(test="H2a", base_s2text=base, delta_true=d, k=1, per_model_a4=float((p1 < ALPHA / 4).mean()),
            per_model_a=float((p1 < ALPHA).mean()), pooled_a4=float((pp < ALPHA / 4).mean()))

# S3-H2b (read-before-lock share among granted lockers that committed; up to 4 agents per config-cluster, both arms)
for base in (0.40, 0.75, 0.95):
    for d in (0.10, 0.15, 0.20, 0.30):
        p1 = L.signflip_greater(single(NS, 4, base - d, d, 0.5))
        pp = L.signflip_greater(pooled(NS, 4, base - d, d, 0.5, 0.3))
        row(test="H2b", base_s2text=base, delta_true=d, k=4, per_model_a4=float((p1 < ALPHA / 4).mean()),
            per_model_a=float((p1 < ALPHA).mean()), pooled_a4=float((pp < ALPHA / 4).mean()))

# S3-H3 (a1 uptake contended - control, staggered; one a1 per arm-cluster, r = 0.5). TOST at a true Delta of 0:
# per model delta 0.25 (stage 2: first step alpha/6, last alpha), pooled delta 0.15 (stage 1: alpha/2, last alpha)
for rate in (0.50, 0.70, 0.85, 0.95):
    v1 = single(NS, 1, rate, 0.0, 0.5)
    _, _, pt1, _ = L.boot_t_tost(v1, 0.25)
    vp = pooled(NS, 1, rate, 0.0, 0.5, 0.3)
    _, _, ptp, _ = L.boot_t_tost(vp, 0.15)
    row(test="H3-eq", uptake_rate=rate, delta_true=0.0, k=1, per_model_d025_a6=float((pt1 < ALPHA / 6).mean()),
        per_model_d025_a=float((pt1 < ALPHA).mean()), pooled_d015_a2=float((ptp < ALPHA / 2).mean()),
        pooled_d015_a=float((ptp < ALPHA).mean()))
# and with a true reactive effect
for rate, d in ((0.70, 0.05), (0.70, 0.10), (0.85, 0.05), (0.85, 0.10)):
    vp = pooled(NS, 1, rate, d, 0.5, 0.3)
    _, _, ptp, _ = L.boot_t_tost(vp, 0.15)
    dp = L.signflip_greater(vp)
    row(test="H3-pooled-shift", uptake_rate=rate, delta_true=d, pooled_eq_a2=float((ptp < ALPHA / 2).mean()),
        pooled_diff_a8=float((dp < ALPHA / 8).mean()))
# size of the TOST at its boundary: a true null with the REALIZED mean difference equal to delta. The generator adds
# the shift to the contended probability and clips at 1, so the shift is calibrated (bisection on 20,000 draws) until
# the expected cluster difference equals delta; the realized value is reported with each row.
def calibrated(kind, rate_ctrl, delta):
    lo, hi = delta, 1.0
    for _ in range(25):
        mid = (lo + hi) / 2
        v = single(20000, 1, rate_ctrl, mid, 0.5) if kind == "single" else pooled(20000, 1, rate_ctrl, mid, 0.5, 0.3)
        if v.mean() < delta:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


for rate_ctrl in (0.25, 0.45, 0.60):
    s1 = calibrated("single", rate_ctrl, 0.25)
    v1 = single(NS, 1, rate_ctrl, s1, 0.5)
    _, _, pt1, _ = L.boot_t_tost(v1, 0.25)
    sp = calibrated("pooled", rate_ctrl + 0.10, 0.15)
    vp = pooled(NS, 1, rate_ctrl + 0.10, sp, 0.5, 0.3)
    _, _, ptp, _ = L.boot_t_tost(vp, 0.15)
    row(test="H3-eq-size-at-boundary", control_rate=rate_ctrl, per_model_realized=float(v1.mean()),
        per_model_a=float((pt1 < ALPHA).mean()), per_model_a6=float((pt1 < ALPHA / 6).mean()),
        pooled_control_rate=rate_ctrl + 0.10, pooled_realized=float(vp.mean()), pooled_a=float((ptp < ALPHA).mean()),
        pooled_a2=float((ptp < ALPHA / 2).mean()))

with open("power6_out.json", "w") as f:
    json.dump(out, f, indent=1)
