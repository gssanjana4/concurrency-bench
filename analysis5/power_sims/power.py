import json, sys
import numpy as np
from simlib import gen, boot_t_tost
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 800
A = 0.05
out = {}
def rates(p, lv):
    return {k: round(float((p < v).mean()), 3) for k, v in lv.items()}
# H1 per model
lv = {"a": A, "a/3": A/3, "a/9": A/9}
for mu in (0.03, 0.05, 0.07, 0.10, 0.15):
    for r in (0.0, 0.3):
        V = gen(NS, 2, mu, r=r)[:, 0, :]
        se = float(V.mean(1).std())
        row = {"SE": round(se, 4)}
        for d in (0.20, 0.25, 0.30):
            row[f"d{d}"] = rates(boot_t_tost(V, d)[2], lv)
        out[f"H1_cell_mu{mu}_r{r}"] = row
        print(f"H1_cell_mu{mu}_r{r}", row, flush=True)
# H1 pooled over 3 models
lv = {"a": A, "a/2": A/2, "a/3": A/3}
for mu in (0.03, 0.05, 0.07, 0.10, 0.15):
    for rho_m in (0.3, 0.6):
        V = gen(NS, 2, mu, r=0.3, n_models=3, rho_m=rho_m).mean(1)
        row = {"SE": round(float(V.mean(1).std()), 4)}
        for d in (0.10, 0.125, 0.15, 0.175):
            row[f"d{d}"] = rates(boot_t_tost(V, d)[2], lv)
        out[f"H1_pooled_mu{mu}_rhom{rho_m}"] = row
        print(f"H1_pooled_mu{mu}_rhom{rho_m}", row, flush=True)
# H4 per model (4 agents, r = 0.5) and pooled
lv = {"a": A, "a/2": A/2, "a/6": A/6}
for mu in (0.10, 0.20, 0.30, 0.50):
    V = gen(NS, 4, mu, r=0.5)[:, 0, :]
    row = {"SE": round(float(V.mean(1).std()), 4)}
    for d in (0.20, 0.25, 0.30):
        row[f"d{d}"] = rates(boot_t_tost(V, d)[2], lv)
    out[f"H4_cell_mu{mu}"] = row
    print(f"H4_cell_mu{mu}", row, flush=True)
    for rho_m in (0.3, 0.6):
        V = gen(NS, 4, mu, r=0.5, n_models=3, rho_m=rho_m).mean(1)
        row = {"SE": round(float(V.mean(1).std()), 4)}
        for d in (0.10, 0.15, 0.20):
            row[f"d{d}"] = rates(boot_t_tost(V, d)[2], lv)
        out[f"H4_pooled3_mu{mu}_rhom{rho_m}"] = row
        print(f"H4_pooled3_mu{mu}_rhom{rho_m}", row, flush=True)
json.dump(out, open("power_out.json", "w"), indent=1)
