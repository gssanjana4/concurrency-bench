"""Power and size simulations of the Study 2 registered decision tests (bootstrap-t TOST sides, sign-flip at theta0 = 0)
on the T3b generator (sim_tost.py, copied unchanged from the T3b review). Needs numpy and scipy; not part of the
analysis. Run from this directory: python3 power.py 1000; python3 procedure.py 1000; python3 boundary.py 4000;
python3 power_shift.py; python3 variants.py 1500."""
import sys
import numpy as np
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import sim_tost as S  # noqa: E402

rng = np.random.default_rng(20261104)
EPS = 1e-12


def boot_t_tost(V, delta, B=1000, chunk=100):
    """V (n, m) cluster values. Returns (p_lo, p_hi, p_tost, p_pct_tost) arrays (n,), bootstrap-t as registered."""
    n, m = V.shape
    out = np.empty((n, 4))
    for s in range(0, n, chunk):
        v = V[s:s + chunk]
        k = v.shape[0]
        mu = v.mean(1)
        se = v.std(1, ddof=1) / np.sqrt(m)
        idx = rng.integers(0, m, (B, m))
        bs = v[:, idx]  # (k, B, m)
        mb = bs.mean(2)
        sb = bs.std(2, ddof=1) / np.sqrt(m)
        diff = mb - mu[:, None]
        den = np.where(sb > EPS, sb, se[:, None])  # registered: a resample with SE* = 0 is studentized by the observed SE
        with np.errstate(divide="ignore", invalid="ignore"):
            tb = np.where(den > EPS, diff / np.where(den > EPS, den, 1), 0.0)
            t_hi = (mu - delta) / se  # H0 D >= +delta: p = (1 + #{t* <= t}) / (B + 1)
            t_lo = (mu + delta) / se  # H0 D <= -delta: p = (1 + #{t* >= t}) / (B + 1)
        p_hi = (1 + (tb <= t_hi[:, None]).sum(1)) / (B + 1)
        p_lo = (1 + (tb >= t_lo[:, None]).sum(1)) / (B + 1)
        # SE = 0: exact sign test against theta0
        z = se <= EPS
        if z.any():
            for j in np.where(z)[0]:
                p_hi[j] = S.sign_p(v[j], delta, "less")
                p_lo[j] = S.sign_p(v[j], -delta, "greater")
        # percentile count bootstrap (Study 1 procedure, reported only)
        pp_hi = (1 + (mb >= delta - EPS).sum(1)) / (B + 1)
        pp_lo = (1 + (mb <= -delta + EPS).sum(1)) / (B + 1)
        out[s:s + k, 0], out[s:s + k, 1] = p_lo, p_hi
        out[s:s + k, 2] = np.maximum(p_lo, p_hi)
        out[s:s + k, 3] = np.maximum(pp_lo, pp_hi)
    return out[:, 0], out[:, 1], out[:, 2], out[:, 3]


def signflip_greater(V, R=2000, chunk=200):
    n, m = V.shape
    out = np.empty(n)
    for s in range(0, n, chunk):
        v = V[s:s + chunk]
        sg = rng.choice([-1.0, 1.0], (R, m))
        perm = v @ sg.T / m  # (k, R)
        obs = v.mean(1)
        out[s:s + v.shape[0]] = (1 + (perm >= obs[:, None] - EPS).sum(1)) / (R + 1)
    return out


def gen(ns, k, mu_c, rho=0.3, r=0.3, n_models=1, rho_m=0.0, shift=0.0, m=28):
    """Cluster values (ns, n_models, m); contended = control prob + shift (per model scalar or list)."""
    shifts = np.broadcast_to(np.asarray(shift, float), (n_models,))
    if np.allclose(shifts, shifts[0]):
        if shifts[0] == 0:
            return S.gen_d(ns, m, k, mu_c, mu_c, rho, r, n_models, rho_m)
        return S.gen_d(ns, m, k, mu_c, None, rho, r, n_models, rho_m, fam_delta=[shifts[0]] * 7)
    # heterogeneous model shifts: generate with a common latent, apply per-model shift
    shared_c = S.rng.standard_normal((ns, 1, m)); shared_e = S.rng.standard_normal((ns, 1, m))
    own_c = S.rng.standard_normal((ns, n_models, m)); own_e = S.rng.standard_normal((ns, n_models, m))
    zc = np.sqrt(rho_m) * shared_c + np.sqrt(1 - rho_m) * own_c
    ze = np.sqrt(rho_m) * shared_e + np.sqrt(1 - rho_m) * own_e
    zt = r * zc + np.sqrt(1 - r * r) * ze
    pc = S.arm_probs(zc, mu_c, rho)
    pt = np.clip(S.arm_probs(zt, mu_c, rho) + shifts[None, :, None], 0, 1)
    return S.rng.binomial(k, pt) / k - S.rng.binomial(k, pc) / k
