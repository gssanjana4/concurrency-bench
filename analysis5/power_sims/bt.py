"""T3c: bootstrap-t TOST with the two zero-spread conventions. V1: t* = +-inf (T3b); V2: observed SE (filed text)."""
import numpy as np
import sim_tost as S
from scipy import stats
rng = np.random.default_rng(20261105)
EPS = 1e-12

def sign_p(v, th, alt):
    return S.sign_p(v, th, alt)

def tost(V, delta, B=2000, chunk=50):
    """V (n, m). Returns dict conv -> TOST p array; also the upper-side p."""
    n, m = V.shape
    res = {"V1": np.empty(n), "V2": np.empty(n)}
    for s in range(0, n, chunk):
        v = V[s:s+chunk]; mu = v.mean(1); se = v.std(1, ddof=1) / np.sqrt(m)
        idx = rng.integers(0, m, (B, m)); bs = v[:, idx]
        mb = bs.mean(2); sb = bs.std(2, ddof=1) / np.sqrt(m)
        diff = mb - mu[:, None]
        zero = sb <= EPS
        with np.errstate(divide="ignore", invalid="ignore"):
            t1 = np.where(zero, np.where(np.abs(diff) <= EPS, 0.0, np.sign(diff) * np.inf), diff / np.where(zero, 1, sb))
            den = np.where(zero, se[:, None], sb)
            t2 = np.where(den > EPS, diff / np.where(den > EPS, den, 1), 0.0)
            th = (mu - delta) / se; tl = (mu + delta) / se
        for conv, tb in (("V1", t1), ("V2", t2)):
            ph = (1 + (tb <= th[:, None] + 1e-9).sum(1)) / (B + 1)
            pl = (1 + (tb >= tl[:, None] - 1e-9).sum(1)) / (B + 1)
            for j in np.where(se <= EPS)[0]:
                ph[j] = sign_p(v[j], delta, "less"); pl[j] = sign_p(v[j], -delta, "greater")
            res[conv][s:s+len(v)] = np.maximum(ph, pl)
    return res

def gen_het(ns, k, mu_c, delta, rho, r, n_models=1, rho_m=0.0, rho_e=None, m=28):
    """Heterogeneous effect: contended prob ~ Beta(mean mu_c + delta, ICC rho_e) via copula; control Beta(mu_c, rho).
    Mean cluster d = delta exactly (before clipping, none here)."""
    rho_e = rho if rho_e is None else rho_e
    shared_c = S.rng.standard_normal((ns, 1, m)); shared_e = S.rng.standard_normal((ns, 1, m))
    own_c = S.rng.standard_normal((ns, n_models, m)); own_e = S.rng.standard_normal((ns, n_models, m))
    zc = np.sqrt(rho_m) * shared_c + np.sqrt(1 - rho_m) * own_c
    ze = np.sqrt(rho_m) * shared_e + np.sqrt(1 - rho_m) * own_e
    zt = r * zc + np.sqrt(1 - r * r) * ze
    pc = S.arm_probs(zc, mu_c, rho)
    pt = S.arm_probs(zt, mu_c + delta, rho_e)
    return S.rng.binomial(k, pt) / k - S.rng.binomial(k, pc) / k
