"""Size of one TOST at its boundary (Delta = +delta), registered bootstrap-t vs the Study 1 percentile bootstrap."""
import json, sys
import numpy as np
from simlib import gen, boot_t_tost
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
LV = {"a": 0.05, "a/2": 0.025, "a/3": 0.05 / 3, "a/6": 0.05 / 6, "a/9": 0.05 / 9}
out = {}
for lab, k, r, n_models, d in (("H1_cell", 2, 0.3, 1, 0.25), ("H1_pooled3", 2, 0.3, 3, 0.15),
                                ("H4_cell", 4, 0.5, 1, 0.25), ("H4_pooled3", 4, 0.5, 3, 0.15)):
    for mu in (0.0, 0.02, 0.05, 0.10, 0.20):
        V = gen(NS, k, mu, r=r, n_models=n_models, rho_m=0.3, shift=[d] * n_models)
        V = V.mean(1) if n_models > 1 else V[:, 0, :]
        _, _, pt, pp = boot_t_tost(V, d)
        out[f"{lab}_ctrl{mu}_D+{d}"] = {"mean_D": round(float(V.mean()), 4),
                                         "bootstrap_t": {a: round(float((pt < l).mean()), 4) for a, l in LV.items()},
                                         "percentile": {a: round(float((pp < l).mean()), 4) for a, l in LV.items()}}
        print(f"{lab}_ctrl{mu}_D+{d}", out[f"{lab}_ctrl{mu}_D+{d}"], flush=True)
json.dump(out, open("boundary_out.json", "w"), indent=1)
