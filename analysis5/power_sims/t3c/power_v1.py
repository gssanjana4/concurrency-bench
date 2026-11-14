"""Power at Delta = 0 of the per-cell TOST (delta 0.25) under V1 vs V2, H1 generator, rare rates."""
import json, numpy as np
import sim_tost as S
from bt import tost
LV = {"a": 0.05, "a/9": 0.05/9}; out = {}
for mu in (0.01, 0.02, 0.03, 0.05, 0.10):
    V = S.gen_d(2000, 28, 2, mu, mu, 0.3, 0.3)[:, 0, :]
    P = tost(V, 0.25)
    out[f"cell_mu{mu}"] = {c: {a: round(float((P[c] < l).mean()), 3) for a, l in LV.items()} for c in P}
    print(f"cell_mu{mu}", out[f"cell_mu{mu}"], flush=True)
json.dump(out, open("power_v1_out.json", "w"), indent=1)
