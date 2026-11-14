"""Two-stage H1-eq procedure FWER, one model at the per-cell boundary (Delta = +0.25, heterogeneous, ICC rho_e)
in k configs, the other two models at Delta = 0. V1 (+-inf) vs V2 (observed SE, as filed)."""
import json, sys, numpy as np
from bt import tost, gen_het
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
A, DC, DP = 0.05, 0.25, 0.15
def holm(P):
    n, k = P.shape; o = np.argsort(P, 1); Ps = np.take_along_axis(P, o, 1)
    ok = np.cumprod(Ps < A / (k - np.arange(k)), 1).astype(bool); R = np.zeros_like(ok); np.put_along_axis(R, o, ok, 1); return R
out = {}
for rho_e in (0.6, 0.9):
  for mu in (0.0, 0.02, 0.05):
    for nbad in (1, 3):
        cellP = {"V1": [], "V2": []}; poolP = {"V1": [], "V2": []}; null_idx = []
        for c in range(3):
            Vs = []
            for j in range(3):
                bad = (j == 0 and c < nbad)
                Vs.append(gen_het(NS, 2, mu, DC if bad else 0.0, 0.3, 0.3, rho_e=rho_e if bad else 0.3)[:, 0, :])
                if bad: null_idx.append(3 * c + j)
                P = tost(Vs[-1], DC)
                for v in P: cellP[v].append(P[v])
            Pp = tost(np.mean(Vs, 0), DP)
            for v in Pp: poolP[v].append(Pp[v])
        res = {}
        for v in ("V1", "V2"):
            R1 = holm(np.stack(poolP[v], 1)); gate = R1.all(1)
            R2 = holm(np.stack(cellP[v], 1)) & gate[:, None]
            err = R2[:, null_idx].any(1)
            res[v] = {"FWER": round(float(err.mean()), 4), "gate": round(float(gate.mean()), 3),
                      "null_cell_reject": [round(float(R2[:, i].mean()), 4) for i in null_idx]}
        name = f"rhoE{rho_e}_ctrl{mu}_nbad{nbad}"; out[name] = res; print(name, res, flush=True)
json.dump(out, open("procedure2_out.json", "w"), indent=1)
