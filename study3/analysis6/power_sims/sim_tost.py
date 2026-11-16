"""T3b: power and size of the Study 2 registered procedures (PREREGISTRATION_STUDY2.md, draft of 2026-11-03).

Registered decision rule (Statistical models): cluster percentile-count bootstrap, B resamples, p = (1 + #{theta* on
null side}) / (B + 1); exact one-sided sign test (ties dropped) when all cluster values are equal or all lie strictly
on the alternative side of theta0. TOST p = max of the two one-sided p at -delta and +delta.

Generator (per model): 28 clusters = 7 families x 4 instances; per arm-cluster a probability drawn from a Beta with
mean mu_arm and ICC rho (Gaussian copula with cross-arm correlation r; optional cross-model correlation rho_m of the
cluster latent for pooled tests); k binary units per arm-cluster (H1: 2 episodes; H4: 4 agents).
"""
import json
import sys

import numpy as np
from scipy import stats

EPS = 1e-12
rng = np.random.default_rng(20261103)


def beta_ab(mu, rho):
    s = 1.0 / rho - 1.0
    return mu * s, (1 - mu) * s


def arm_probs(z, mu, rho):
    if mu <= 0:
        return np.zeros_like(z)
    a, b = beta_ab(mu, rho)
    return stats.beta.ppf(stats.norm.cdf(z), a, b)


def gen_d(nsim, m, k, mu_c, mu_t, rho, r, n_models=1, rho_m=0.0, fam_delta=None):
    """Cluster values d (nsim, n_models, m). fam_delta: per-family additive shift of the contended probability
    (length 7, repeated over 4 instances), replacing mu_t - mu_c."""
    shared_c = rng.standard_normal((nsim, 1, m))
    shared_e = rng.standard_normal((nsim, 1, m))
    own_c = rng.standard_normal((nsim, n_models, m))
    own_e = rng.standard_normal((nsim, n_models, m))
    zc = np.sqrt(rho_m) * shared_c + np.sqrt(1 - rho_m) * own_c
    ze = np.sqrt(rho_m) * shared_e + np.sqrt(1 - rho_m) * own_e
    zt = r * zc + np.sqrt(1 - r * r) * ze
    pc = arm_probs(zc, mu_c, rho)
    if fam_delta is None:
        pt = arm_probs(zt, mu_t, rho)
    else:
        shift = np.repeat(np.asarray(fam_delta, float), m // len(fam_delta))
        pt = np.clip(arm_probs(zt, mu_c, rho) + shift, 0, 1)
    yc = rng.binomial(k, pc) / k
    yt = rng.binomial(k, pt) / k
    return yt - yc


def sign_p(v, th, alt):
    up = (v > th + EPS).sum()
    dn = (v < th - EPS).sum()
    kk, n = (up, up + dn) if alt == "greater" else (dn, up + dn)
    return 1.0 if n == 0 else float(stats.binom.sf(kk - 1, n, 0.5))


def boot_means(v, B):
    m = v.shape[-1]
    return v[..., rng.integers(0, m, (B, m))].mean(-1)


def reg_p_from_boot(v, st, th, alt, B, fallback="draft"):
    """Registered one-sided p. fallback: 'draft' (all equal, or all strictly on the alternative side),
    'study1' (all equal only), 'none'."""
    if fallback in ("draft", "study1") and np.ptp(v) <= EPS:
        return sign_p(v, th, alt)
    if fallback == "draft":
        if alt == "greater" and (v > th + EPS).all():
            return sign_p(v, th, alt)
        if alt == "less" and (v < th - EPS).all():
            return sign_p(v, th, alt)
    ns = (st <= th + EPS).sum() if alt == "greater" else (st >= th - EPS).sum()
    return (1 + ns) / (B + 1)


def t_p(v, th, alt):
    m = len(v)
    sd = v.std(ddof=1)
    if sd <= EPS:
        return 0.0 if ((v.mean() > th) if alt == "greater" else (v.mean() < th)) else 1.0
    t = (v.mean() - th) / (sd / np.sqrt(m))
    return float(stats.t.sf(t, m - 1)) if alt == "greater" else float(stats.t.cdf(t, m - 1))


def signflip_p(v, alt, R=4000):
    """MC sign-flip permutation test of H0 mean = 0 (symmetric), one-sided."""
    s = rng.choice([-1.0, 1.0], (R, len(v)))
    perm = (s * v).mean(1)
    obs = v.mean()
    if alt == "greater":
        return (1 + (perm >= obs - EPS).sum()) / (R + 1)
    return (1 + (perm <= obs + EPS).sum()) / (R + 1)


ALPHAS = {"a05": 0.05, "a05/3": 0.05 / 3, "a05/8": 0.05 / 8, "a05/12": 0.05 / 12}


def tost_rates(D, delta, B=2000, methods=("boot", "t")):
    """D: (nsim, m) cluster values (already pooled if pooled). Returns rejection rates of TOST per method/alpha."""
    out = {mth: {a: 0 for a in ALPHAS} for mth in methods}
    for v in D:
        st = boot_means(v, B) if "boot" in methods else None
        ps = {}
        if "boot" in methods:
            ps["boot"] = max(reg_p_from_boot(v, st, -delta, "greater", B), reg_p_from_boot(v, st, delta, "less", B))
        if "t" in methods:
            ps["t"] = max(t_p(v, -delta, "greater"), t_p(v, delta, "less"))
        for mth, p in ps.items():
            for a, lvl in ALPHAS.items():
                out[mth][a] += p < lvl
    n = len(D)
    return {mth: {a: round(c / n, 4) for a, c in d.items()} for mth, d in out.items()}


def se_of(D):
    return float(D.mean(-1).std())


def main():
    NS = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
    res = {}
    z80 = 1.2816
    # ---------- A. per-model TOST power at Delta = 0 (H1: k=2; H4: k=4) and required margins at each alpha
    for label, k, mus, rs in (("H1", 2, (0.05, 0.10, 0.15, 0.20), (0.0, 0.3)), ("H4", 4, (0.20, 0.50), (0.0, 0.5))):
        for mu in mus:
            for r in rs:
                D = gen_d(NS, 28, k, mu, mu, 0.3, r)[:, 0, :]
                se = se_of(D)
                req = {a: round((stats.norm.isf(lvl) + z80) * se, 3) for a, lvl in ALPHAS.items()}
                pw = tost_rates(D, 0.20)
                res[f"A_{label}_permodel_mu{mu}_r{r}"] = {"SE": round(se, 4), "required_margin_80pct": req,
                                                          "TOST_power_delta0.20": pw}
    # ---------- B. pooled over 3 models (equal-weight mean of model Delta), cross-model cluster correlation rho_m
    for label, k, mu, r in (("H1", 2, 0.10, 0.0), ("H1", 2, 0.10, 0.3), ("H1", 2, 0.15, 0.0), ("H4", 4, 0.20, 0.0), ("H4", 4, 0.20, 0.5)):
        for rho_m in (0.0, 0.3, 0.6):
            D = gen_d(NS, 28, k, mu, mu, 0.3, r, n_models=3, rho_m=rho_m).mean(1)  # (nsim, 28) pooled cluster values
            se = se_of(D)
            req = {a: round((stats.norm.isf(lvl) + z80) * se, 3) for a, lvl in ALPHAS.items()}
            res[f"B_{label}_pooled3_mu{mu}_r{r}_rhom{rho_m}"] = {"SE": round(se, 4), "required_margin_80pct": req,
                                                                 "TOST_power_delta0.10": tost_rates(D, 0.10)}
    # ---------- C. size of the upper TOST side at the boundary Delta = +delta, family-heterogeneous effects
    # control 0.02; contended shift by family; mean shift = 0.20 (per model)
    het = {"homog": [0.20] * 7, "2of7_hot": [0.60, 0.60, 0.04, 0.04, 0.04, 0.04, 0.04],
           "1of7_hot": [1.0, 0.0667, 0.0667, 0.0667, 0.0667, 0.0667, 0.0667]}
    for name, fd in het.items():
        fd = np.asarray(fd) * 0.20 / np.mean(fd)
        D = gen_d(NS, 28, 2, 0.02, None, 0.3, 0.3, fam_delta=fd)[:, 0, :]
        true = float(np.mean(D))
        rates = {mth: {a: 0 for a in ALPHAS} for mth in ("boot_upper", "t_upper")}
        for v in D:
            st = boot_means(v, 2000)
            pb = reg_p_from_boot(v, st, 0.20, "less", 2000)
            pt = t_p(v, 0.20, "less")
            for a, lvl in ALPHAS.items():
                rates["boot_upper"][a] += pb < lvl
                rates["t_upper"][a] += pt < lvl
        res[f"C_size_upperTOST_at_boundary_{name}"] = {"empirical_mean_Delta": round(true, 4),
                                                        **{m_: {a: round(c / NS, 4) for a, c in d.items()} for m_, d in rates.items()}}
    # ---------- D. sparse symmetric null at theta0 = 0 (H3 / H2d / H1-diff / H4-diff): cluster values in
    # {-0.5, 0, +0.5} with P(nonzero) = pi, symmetric. Size of registered rule vs sign test, sign-flip, t.
    for m, pi in ((28, 0.05), (28, 0.10), (28, 0.20), (28, 0.40), (42, 0.10)):
        cnt = {x: {a: 0 for a in ALPHAS} for x in ("registered", "sign", "signflip", "t")}
        for _ in range(NS):
            v = rng.choice([-0.5, 0.0, 0.5], m, p=[pi / 2, 1 - pi, pi / 2])
            st = boot_means(v, 2000)
            ps = {"registered": reg_p_from_boot(v, st, 0.0, "greater", 2000), "sign": sign_p(v, 0.0, "greater"),
                  "signflip": signflip_p(v, "greater"), "t": t_p(v, 0.0, "greater")}
            for x, p in ps.items():
                for a, lvl in ALPHAS.items():
                    cnt[x][a] += p < lvl
        res[f"D_size_sparse_null_m{m}_pi{pi}"] = {x: {a: round(c / NS, 4) for a, c in d.items()} for x, d in cnt.items()}
    # ---------- E. deterministic: k clusters at +0.5, the rest 0 (m = 28): registered p vs exact tests
    tab = {}
    for kk in range(1, 9):
        v = np.r_[np.full(kk, 0.5), np.zeros(28 - kk)]
        st = boot_means(v, 20000)
        tab[kk] = {"registered_boot": round(reg_p_from_boot(v, st, 0.0, "greater", 20000), 4),
                   "approx_(1-k/28)^28": round((1 - kk / 28) ** 28, 4),
                   "sign_ties_dropped": round(sign_p(v, 0.0, "greater"), 4),
                   "signflip_exact": round(0.5 ** kk, 4), "t": round(t_p(v, 0.0, "greater"), 4)}
    res["E_k_positive_rest_zero_m28"] = tab
    # all 28 strictly on the alternative side: draft fallback vs bootstrap
    res["E_all28_alt_side"] = {"sign_p": 0.5 ** 28, "bootstrap_min_p_B10000": 1 / 10001}
    json.dump(res, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
