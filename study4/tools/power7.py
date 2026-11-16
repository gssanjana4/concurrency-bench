#!/usr/bin/env python3
"""Study 4 power by simulation (descriptive planning aid). Failure rates per model under the Study 2 text (s2) and the
bundle (b) from Study 3 contended together episodes; Fable from assumptions (Study 2: 0 of 12 under locks).
Scenarios split the s2 -> bundle drop between instruction (I) and signals (S)."""
import json, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis7"))
import analyze7 as A, core7 as C

RATES = {"Qwen": (40/64, 0/64), "Haiku": (57/64, 7/64), "Sonnet": (24/64, 4/64), "Fable": (0.10, 0.0)}
FABLE_RATES = (0.10, 0.05, 0.02)
def cells(s2, b, sc):
    d = s2 - b
    if sc == "instr_only":  return {A.TWO: s2, A.INSTR: b, A.SIGNALS: s2, A.BUNDLE: b}
    if sc == "signals_only": return {A.TWO: s2, A.INSTR: s2, A.SIGNALS: b, A.BUNDLE: b}
    if sc == "additive_half": return {A.TWO: s2, A.INSTR: s2 - d/2, A.SIGNALS: s2 - d/2, A.BUNDLE: b}
    if sc == "either_suffices": return {A.TWO: s2, A.INSTR: b, A.SIGNALS: b, A.BUNDLE: b}
    if sc == "multiplicative":  # each part alone removes the same share of failures; together the product
        g = (s2 * b) ** 0.5
        return {A.TWO: s2, A.INSTR: g, A.SIGNALS: g, A.BUNDLE: b}
    if sc == "instr_75": return {A.TWO: s2, A.INSTR: s2 - .75*d, A.SIGNALS: s2 - .25*d, A.BUNDLE: b}
def one(sc, rng):
    """One simulated study under the registered rules, the Fable stage rule included (rejections per test)."""
    vals, fails = {}, {}
    for m, (s2, b) in RATES.items():
        if m == "Fable":
            s2 = FABLE_S2
        p = cells(s2, b, sc)
        v = {h: {} for h in A.HYPOTHESES}
        fails[m] = 0
        for f in A.FAMILIES:
            for i in range(A.INSTANCES):
                fs = {c: float(rng.random() < p[c]) for c in A.CONFIGS}
                fails[m] += int(fs[A.TWO])
                for h in A.HYPOTHESES: v[h][(f, i)] = A.cluster_value(h, fs)
        vals[m] = v
    run = [m for m in RATES if m != "Fable" or fails[m] >= A.FLOOR_FAILURES]  # Fable stage 2 only above the floor
    rej = {"Fable|stage2_run": "Fable" in run}
    for h in A.HYPOTHESES:
        per = {m: vals[m][h] for m in run}
        per["pooled"] = A.pooled_values(per)
        names = list(per)
        ps = []
        for n in names:
            v = list(per[n].values())
            if h != "H6":
                ps.append(C.signflip(v, "greater", "x")["p"])
            else:
                g, l_ = C.signflip(v, "greater", "x")["p"], C.signflip(v, "less", "x")["p"]
                ps.append(min(1.0, 2 * min(g, l_)))
        adj = C.holm(ps)
        for n, a in zip(names, adj): rej[f"{h}|{n}"] = a < 0.05
        for n in RATES:
            rej.setdefault(f"{h}|{n}", False)
    return rej
out = {}
for fr in FABLE_RATES:
    FABLE_S2 = fr
    for sc in ("instr_only", "signals_only", "additive_half", "multiplicative", "either_suffices", "instr_75"):
        rng = random.Random(f"power7|{sc}|{fr}"); R = 200; acc = {}
        for _ in range(R):
            for k, v in one(sc, rng).items(): acc[k] = acc.get(k, 0) + v
        key = f"fable{fr:.2f}|{sc}"
        out[key] = {k: round(v / R, 2) for k, v in sorted(acc.items())}
        print(key, " ".join(f"{k}={v}" for k, v in out[key].items()))
json.dump({"rates": RATES, "fable_s2_rates": FABLE_RATES, "R": 200, "power": out}, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis7", "power_study4.json"), "w"), indent=1)
