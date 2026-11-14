"""Degenerate-resample convention of the bootstrap-t: V1 (T3b) t* = +-inf when SE* = 0; V2 SE* = 0 -> observed SE."""
import json, sys
import numpy as np
from simlib import gen, rng, S, EPS
NS = int(sys.argv[1]) if len(sys.argv) > 1 else 800
B = 1000

def tost(V, delta, conv):
    n, m = V.shape
    res = np.empty(n)
    for s in range(0, n, 100):
        v = V[s:s+100]; mu = v.mean(1); se = v.std(1, ddof=1)/np.sqrt(m)
        idx = rng.integers(0, m, (B, m)); bs = v[:, idx]; mb = bs.mean(2); sb = bs.std(2, ddof=1)/np.sqrt(m)
        diff = mb - mu[:, None]
        if conv == "V1":
            with np.errstate(divide="ignore", invalid="ignore"):
                tb = np.where(sb > EPS, diff/np.where(sb > EPS, sb, 1), np.where(np.abs(diff) <= EPS, 0, np.sign(diff)*np.inf))
        else:
            den = np.where(sb > EPS, sb, se[:, None])
            with np.errstate(divide="ignore", invalid="ignore"):
                tb = np.where(den > EPS, diff/np.where(den > EPS, den, 1), 0.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            th = (mu - delta)/se; tl = (mu + delta)/se
        ph = (1 + (tb <= th[:, None]).sum(1))/(B+1); pl = (1 + (tb >= tl[:, None]).sum(1))/(B+1)
        for j in np.where(se <= EPS)[0]:
            ph[j] = S.sign_p(v[j], delta, "less"); pl[j] = S.sign_p(v[j], -delta, "greater")
        res[s:s+len(v)] = np.maximum(ph, pl)
    return res

LV = {"a": 0.05, "a/3": 0.05/3, "a/9": 0.05/9}
out = {}
for conv in ("V1", "V2"):
    for mu in (0.0, 0.01, 0.03, 0.05, 0.10):
        V = gen(NS, 2, mu, r=0.3)[:, 0, :]
        p = tost(V, 0.20, conv)
        out[f"{conv}_power_cell_mu{mu}_d0.20"] = {k: round(float((p < l).mean()), 3) for k, l in LV.items()}
    for mu in (0.0, 0.02, 0.05, 0.10):
        V = gen(NS, 2, mu, r=0.3, shift=0.20)[:, 0, :]
        p = tost(V, 0.20, conv)
        out[f"{conv}_size_cell_ctrl{mu}_D+0.20"] = {k: round(float((p < l).mean()), 4) for k, l in LV.items()}
    for k, v in out.items():
        if k.startswith(conv): print(k, v, flush=True)
json.dump(out, open("variants_out.json", "w"), indent=1)
