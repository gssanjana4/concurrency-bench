"""TOST power when contention adds a true Delta > 0 (H4's expectation 0.05 to 0.15)."""
import json
import numpy as np
from simlib import gen, boot_t_tost
NS = 1500
out = {}
for lab, k, r, nm, d, lv in (("H4_cell", 4, 0.5, 1, 0.25, {"a": 0.05, "a/6": 0.05 / 6}),
                             ("H4_pooled3", 4, 0.5, 3, 0.15, {"a": 0.05, "a/2": 0.025}),
                             ("H1_cell", 2, 0.3, 1, 0.25, {"a": 0.05, "a/9": 0.05 / 9}),
                             ("H1_pooled3", 2, 0.3, 3, 0.15, {"a": 0.05, "a/3": 0.05 / 3})):
    for mu in ((0.10, 0.20) if lab.startswith("H4") else (0.05, 0.10)):
        for sh in (0.05, 0.10):
            V = gen(NS, k, mu, r=r, n_models=nm, rho_m=0.3, shift=[sh] * nm)
            V = V.mean(1) if nm > 1 else V[:, 0, :]
            p = boot_t_tost(V, d)[2]
            key = f"{lab}_ctrl{mu}_D{sh}_delta{d}"
            out[key] = {a: round(float((p < l).mean()), 3) for a, l in lv.items()}
            print(key, out[key], flush=True)
json.dump(out, open("power_shift_out.json", "w"), indent=1)
