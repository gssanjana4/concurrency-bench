"""Familywise error and power of the registered two-stage (gatekeeping) Holm procedure for H1-eq / H4-eq,
with bootstrap-t TOST sides, delta = 0.25 per (model, config) and 0.15 pooled. Also: sign-flip size at theta0 = 0."""
import json, sys
import numpy as np
from simlib import gen, boot_t_tost, signflip_greater, rng
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
A, DC, DP = 0.05, 0.25, 0.15

def holm_reject(P, alpha=A):
    """P (n, k) -> boolean (n, k) Holm rejections."""
    n, k = P.shape
    order = np.argsort(P, 1)
    Ps = np.take_along_axis(P, order, 1)
    lv = alpha / (k - np.arange(k))
    ok = np.cumprod(Ps < lv, 1).astype(bool)
    R = np.zeros_like(ok)
    np.put_along_axis(R, order, ok, 1)
    return R

def run(shifts, mu, k, rho_m=0.3, r=0.3):
    """shifts: list per config of per-model Delta. Returns rejection matrices."""
    cells, pooled = [], []
    for sh in shifts:
        V = gen(NS, k, mu, r=r, n_models=len(sh), rho_m=rho_m, shift=sh)  # (NS, models, 28)
        for j in range(len(sh)):
            cells.append(boot_t_tost(V[:, j, :], DC)[2])
        pooled.append(boot_t_tost(V.mean(1), DP)[2])
    Pp, Pc = np.stack(pooled, 1), np.stack(cells, 1)
    R1 = holm_reject(Pp)
    gate = R1.all(1)
    R2 = holm_reject(Pc) & gate[:, None]
    return R1, R2, gate

out = {}
def rec(name, shifts, mu, k, true_null_cells=(), true_null_pooled=()):
    R1, R2, gate = run(shifts, mu, k)
    err = np.zeros(NS, bool)
    for i in true_null_cells: err |= R2[:, i]
    for i in true_null_pooled: err |= R1[:, i]
    out[name] = {"FWER": round(float(err.mean()), 4), "P_gate_open": round(float(gate.mean()), 3),
                 "P_pooled_reject": [round(float(x), 3) for x in R1.mean(0)],
                 "P_cell_reject": [round(float(x), 3) for x in R2.mean(0)],
                 "mean_cells_rejected": round(float(R2.sum(1).mean()), 2)}
    print(name, out[name], flush=True)

z3 = [0.0, 0.0, 0.0]
for mu in (0.02, 0.05, 0.10):
    rec(f"H1_power_all0_mu{mu}", [z3, z3, z3], mu, 2)
for mu in (0.02, 0.05):
    rec(f"H1_size_one_cell_at_+0.25_mu{mu}", [[0.25, 0, 0], z3, z3], mu, 2, true_null_cells=[0])
    rec(f"H1_size_three_cells_at_+0.25_mu{mu}", [[0.25, 0, 0]] * 3, mu, 2, true_null_cells=[0, 3, 6])
    rec(f"H1_size_pooled_at_+0.15_mu{mu}", [[0.15] * 3, z3, z3], mu, 2, true_null_pooled=[0])
    rec(f"H1_size_pooled_and_cell_mu{mu}", [[0.25, 0.10, 0.10], z3, z3], mu, 2, true_null_cells=[0], true_null_pooled=[0])
z2 = [0.0, 0.0, 0.0]
for mu in (0.10, 0.20, 0.30):
    rec(f"H4_power_all0_mu{mu}", [z2, z2], mu, 4)
rec("H4_size_one_cell_at_+0.25_mu0.05", [[0.25, 0, 0], z2], 0.05, 4, true_null_cells=[0])
rec("H4_size_pooled_at_+0.15_mu0.05", [[0.15] * 3, z2], 0.05, 4, true_null_pooled=[0])
# sign-flip at theta0 = 0, sparse symmetric null, m = 28, size at alpha/12 and alpha
for pi in (0.1, 0.2, 0.4):
    V = rng.choice([-0.5, 0.0, 0.5], (4000, 28), p=[pi / 2, 1 - pi, pi / 2])
    p = signflip_greater(V, R=4000)
    out[f"signflip_size_sparse_pi{pi}"] = {"a": round(float((p < A).mean()), 4), "a/12": round(float((p < A / 12).mean()), 4)}
    print(f"signflip_size_sparse_pi{pi}", out[f"signflip_size_sparse_pi{pi}"], flush=True)
json.dump(out, open("procedure_out.json", "w"), indent=1)
