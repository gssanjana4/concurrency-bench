#!/usr/bin/env python3
"""descriptives7.py: the Study 4 numbers and tables of the paper that the registered analysis does not print as macros.

Reads only:
  <out>/results.json      (frozen analyze7.py output: tests, checks, D1 to D4, sensitivity analyses, stage rule)
  <out>/numbers.tex       (the registered macros; copied verbatim)
  <base>/floor_gate.json  (the Fable stage rule's record), <base>/run_study4.log (spend by provider)
Writes (into the paper's LaTeX folder):
  study4_out/study4_registered_numbers.tex   verbatim copy of numbers.tex (\\Siv...; never edited)
  study4_out/study4_numbers.tex              descriptive macros (\\SivD...), no name shared with the registered file
  study4_out/tables/*.tex                    the Study 4 tables

Nothing here is a test.

    python3 paper7/descriptives7.py --out analysis7/out_study4 --base results7/study4 --latex ../latex
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil

MODELS = ("Qwen", "Haiku", "Sonnet", "Fable")
NAME = {"Qwen": r"\ModelQwenName", "Haiku": r"\ModelHaikuName", "Sonnet": r"\ModelSonnetName",
        "Fable": r"\ModelFableName", "pooled": "pooled"}
CONFIGS = ("locks_s2text", "locks_instr", "locks_signals", "locks")
CFG_PART = {"locks_s2text": "Two", "locks_instr": "Instr", "locks_signals": "Signals", "locks": "Bundle"}
CFG_TT = {"locks_s2text": r"\STwo{} text", "locks_instr": "instruction", "locks_signals": "signals", "locks": "bundle"}
HYP = ("H1", "H2", "H3", "H4", "H5", "H6")
HYP_MACRO = {h: r"\SFour" + {"H1": "Hone", "H2": "Htwo", "H3": "Hthree", "H4": "Hfour", "H5": "Hfive", "H6": "Hsix"}[h] + "{}"
             for h in HYP}
WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def f2(x) -> str:
    if x is None:
        return r"\textemdash{}"
    s = f"{x:.2f}"
    return "0.00" if s == "-0.00" else s


def pf(p) -> str:
    return r"\textemdash{}" if p is None else ("$<$0.001" if p < 0.001 else f"{p:.3f}")


def cnt(n: int) -> str:
    return f"{n:,}".replace(",", "{,}")


def short(model_id: str) -> str:
    for k, v in (("qwen", "Qwen"), ("haiku", "Haiku"), ("sonnet", "Sonnet"), ("fable", "Fable")):
        if k in model_id:
            return v
    return "pooled"


def mname(*parts: str) -> str:
    s = "SivD" + "".join(p[:1].upper() + p[1:] for p in parts)
    s = "".join(WORDS[int(c)] if c.isdigit() else c for c in s)
    return re.sub(r"[^A-Za-z]", "", s)


def spend(base: str):
    log = os.path.join(base, "run_study4.log")
    if not os.path.exists(log):
        return {}
    m = None
    for ln in open(log):
        if "spend by provider:" in ln:
            m = ln
    if not m:
        return {}
    return {k: float(v) for k, v in re.findall(r"'(\w+)': ([0-9.]+)", m)}


def verdict(t) -> str:
    if t["status"] == "not_run_floor":
        return "not run (floor)"
    if t["status"] == "invalid":
        return "invalid"
    if t["status"] != "tested":
        return "not tested"
    return "reject" if t["reject"] else "no claim"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--latex", required=True)
    a = ap.parse_args()
    res = json.load(open(os.path.join(a.out, "results.json")))
    dst = os.path.join(a.latex, "study4_out")
    os.makedirs(os.path.join(dst, "tables"), exist_ok=True)
    shutil.copyfile(os.path.join(a.out, "numbers.tex"), os.path.join(dst, "study4_registered_numbers.tex"))
    M = {}
    tests = {(t["test"], short(t["model"])): t for t in res["tests"]}
    for (h, m), t in tests.items():
        M[mname(h, m, "Verdict")] = verdict(t)
        M[mname(h, m, "Est")] = f2(t.get("estimate"))
        if t.get("ci90"):
            M[mname(h, m, "Lb")] = f2(t["ci90"][0])
        if t.get("ci95"):
            M[mname(h, m, "Lo")], M[mname(h, m, "Hi")] = f2(t["ci95"][0]), f2(t["ci95"][1])
        M[mname(h, m, "P")] = pf(t.get("p"))
        M[mname(h, m, "Padj")] = pf(t.get("p_adj"))
        M[mname(h, m, "FamP")] = pf(t.get("p_family_level"))
        if m == "pooled":
            names = [NAME[x] + "{}" for x in (t.get("models_pooled") or [])]
            M[mname(h, "Pooled", "Models")] = (", ".join(names[:-1]) + " and " + names[-1]) if len(names) > 1 else "".join(names)
    for k, v in res["descriptive"]["fs"].items():
        m, c = k.split("|")
        M[mname("Fs", m, CFG_PART[c])] = f2(v["share"])
        M[mname("Failed", m, CFG_PART[c])] = str(v["failed"])
        M[mname("Episodes", m, CFG_PART[c])] = str(v["episodes"])
    for k, v in res["descriptive"]["mechanisms"].items():
        m, c = k.split("|")
        for kk in ("read_then_lock", "own_only", "no_lock", "other"):
            M[mname("Mech", m, CFG_PART[c], kk.replace("_", ""))] = str(v[kk])
    for k, v in res["descriptive"]["protocol"].items():
        m, c = k.split("|")
        for kk in ("lock_first", "read_then_lock", "no_lock", "scope_all", "read_before_lock_share"):
            M[mname("Proto", m, CFG_PART[c], kk.replace("_", ""))] = f2(v[kk])
    for k, v in res["checks"]["signal_counts"].items():
        m, c = k.split("|")
        M[mname("Waits", m, CFG_PART.get(c, c))] = str(v["waits"])
        M[mname("LockedReads", m, CFG_PART.get(c, c))] = str(v["locked_reads"])
    M[mname("Episodes")] = cnt(res["selection"]["main_episodes"])
    M[mname("Excluded")] = str(len(res["selection"]["excluded"]))
    M[mname("CapTruncated")] = str(res["selection"]["cap_truncated_episodes"])
    M[mname("LockViolations")] = str(res["checks"]["lock_safety"]["violations"])
    M[mname("FableStage")] = (res.get("fable_stage_rule") or {}).get("claude-fable-5", "not recorded").replace("_", " ")
    sens = res["sensitivity"]
    for key, nm in (("S1_exclusions_kept", "SensOne"), ("S4_basis_cycle", "SensFour"), ("S5_cap_truncated_excluded", "SensFive")):
        M[mname(nm, "Changed")] = str(len(sens[key]["changed"]))
    M[mname("SensThree", "Changed")] = str(sum(1 for v in sens["S3_holm_within_model"].values() if v["changed"]))
    sp = spend(a.base)
    for k, v in sp.items():
        M[mname("Spend", k)] = f"{v:.2f}"
    if sp:
        M[mname("Spend", "Total")] = f"{sum(sp.values()):.2f}"
    with open(os.path.join(dst, "study4_numbers.tex"), "w") as f:
        f.write("% GENERATED by paper7/descriptives7.py from results.json (sha256 "
                + hashlib.sha256(open(os.path.join(a.out, "results.json"), "rb").read()).hexdigest() + ")\n")
        for k in sorted(M):
            f.write(f"\\newcommand{{\\{k}}}{{{M[k]}}}\n")
    # tables
    L = [r"\begin{table*}[tp]", r"\centering\scriptsize",
         r"\begin{tabular}{@{}llrrrrrl@{}}", r"\toprule",
         r"hypothesis & model & estimate & bound & $p$ & Holm $p$ & clusters & reading \\", r"\midrule"]
    for h in HYP:
        for m in MODELS + ("pooled",):
            t = tests.get((h, m))
            if t is None:
                continue
            if t.get("kind") == "two_sided" and t.get("ci95"):
                b = f"[{f2(t['ci95'][0])}, {f2(t['ci95'][1])}]"
            else:
                b = f2(t["ci90"][0]) if t.get("ci90") else r"\textemdash{}"
            L.append(f"{HYP_MACRO[h] if m == MODELS[0] else ''} & {NAME[m]} & {f2(t.get('estimate'))} & {b} & {pf(t.get('p'))} & "
                     f"{pf(t.get('p_adj'))} & {t['n_clusters']} & {verdict(t)} \\\\")
        L.append(r"\addlinespace" if h != HYP[-1] else "")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\SFour{} confirmatory tests. Estimate: mean cluster value (failure-share difference, positive = fewer "
          r"failures with the part). Bound: one-sided 95\,\% lower bound (two-sided 95\,\% interval for the interaction), "
          r"percentile cluster bootstrap, unadjusted. $p$: exact sign-flip; Holm within each hypothesis.}",
          r"\label{tab:s4-tests}", r"\end{table*}"]
    open(os.path.join(dst, "tables", "s4_tests.tex"), "w").write("\n".join(x for x in L if x is not None) + "\n")
    L = [r"\begin{table}[tp]", r"\centering\scriptsize\setlength{\tabcolsep}{3pt}", r"\begin{tabular}{@{}l" + "r" * len(CONFIGS) + "@{}}", r"\toprule",
         "model & " + " & ".join(CFG_TT[c] for c in CONFIGS) + r" \\", r"\midrule"]
    for m in MODELS:
        row = []
        for c in CONFIGS:
            v = res["descriptive"]["fs"].get(f"{m}|{c}")
            row.append(r"\textemdash{}" if not v or not v["episodes"] else f"{v['failed']}/{v['episodes']}")
        label = NAME[m] + (r"{} (incomplete)" if m == "Qwen" else "")
        L.append(f"{label} & " + " & ".join(row) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\SFour{} contended integrity failures (failed / episodes) per model and configuration: the \STwo{} lock text (\texttt{locks\_s2text}), its instruction only (\texttt{locks\_instr}), its signals only (\texttt{locks\_signals}) and the \SThree{} bundle (\texttt{locks}). \ModelQwenName{} stopped after \SivQwenDone{} episodes and \ModelFableName{} after its first config (Appendix~\ref{app:s4}).}",
          r"\label{tab:s4-fs}", r"\end{table}"]
    open(os.path.join(dst, "tables", "s4_fs.tex"), "w").write("\n".join(L) + "\n")
    L = [r"\begin{table}[tp]", r"\centering\scriptsize\setlength{\tabcolsep}{3pt}", r"\begin{tabular}{@{}llrrrr@{}}", r"\toprule",
         r"model & config & read then lock & own only & no lock & other \\", r"\midrule"]
    for m in MODELS:
        for i, c in enumerate(CONFIGS):
            v = res["descriptive"]["mechanisms"].get(f"{m}|{c}")
            if not v:
                continue
            L.append(f"{NAME[m] if i == 0 else ''} & {CFG_TT[c]} & {v['read_then_lock']} & {v['own_only']} & {v['no_lock']} & {v['other']} \\\\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{\SFour{} lock-failure mechanisms of the failed episodes (an episode with none or more than one of "
          r"the three counts as other).}", r"\label{tab:s4-mech}", r"\end{table}"]
    open(os.path.join(dst, "tables", "s4_mech.tex"), "w").write("\n".join(L) + "\n")
    print(f"wrote {len(M)} macros and 3 tables into {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
