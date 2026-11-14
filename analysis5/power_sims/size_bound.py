import json, sys, numpy as np
import sim_tost as S
from bt import tost, gen_het
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
LV = {"a": 0.05, "a/2": 0.025, "a/3": 0.05/3, "a/6": 0.05/6, "a/9": 0.05/9}
out = {}
def rec(name, V, d):
    P = tost(V, d)
    out[name] = {"mean_D": round(float(V.mean()), 4), **{c: {a: round(float((P[c] < l).mean()), 4) for a, l in LV.items()} for c in P}}
    print(name, out[name], flush=True)
# 1. authors' homogeneous shift (reproduce), H1 cell
for mu in (0.0, 0.05):
    V = S.gen_d(NS, 28, 2, mu, None, 0.3, 0.3, fam_delta=[0.25]*7)[:, 0, :]
    rec(f"H1cell_homog_ctrl{mu}", V, 0.25)
# 2. heterogeneous effect, H1 cell, ICC of contended prob 0.3 / 0.6 / 0.9
for rho_e in (0.3, 0.6, 0.9):
    for mu in (0.0, 0.02, 0.05):
        V = gen_het(NS, 2, mu, 0.25, 0.3, 0.3, rho_e=rho_e)[:, 0, :]
        rec(f"H1cell_het_rhoE{rho_e}_ctrl{mu}", V, 0.25)
# 3. H1 pooled (3 models, rho_m 0.3), heterogeneous
for rho_e in (0.3, 0.6, 0.9):
    for mu in (0.0, 0.05):
        V = gen_het(NS, 2, mu, 0.15, 0.3, 0.3, n_models=3, rho_m=0.3, rho_e=rho_e).mean(1)
        rec(f"H1pooled_het_rhoE{rho_e}_ctrl{mu}", V, 0.15)
# 4. H4 cell (4 agents, r 0.5), heterogeneous
for rho_e in (0.3, 0.6, 0.9):
    for mu in (0.05, 0.2):
        V = gen_het(NS, 4, mu, 0.25, 0.3, 0.5, rho_e=rho_e)[:, 0, :]
        rec(f"H4cell_het_rhoE{rho_e}_ctrl{mu}", V, 0.25)
json.dump(out, open("size_bound_out.json", "w"), indent=1)
