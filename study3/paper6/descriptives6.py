#!/usr/bin/env python3
"""descriptives6.py: the Study 3 numbers and tables of the paper that the registered analysis does not print as macros.

Reads only:
  analysis6/out_study3/results.json   (frozen analyze6.py output; its pre-specified descriptives D1 to D6, the checks,
                                       the tests and the sensitivity analyses)
  analysis6/out_study3/numbers.tex    (the registered macros; only its sha256 is recorded here)
  paper6/posthoc6.json                (exploratory transcript counts: reported waits, locked reads, served model,
                                       effective temperature; written by paper6/posthoc6.py)
  results6/study3/run_study3.log      (spend by provider, as the run script printed it)
Writes (into the paper's LaTeX folder, given as the only argument):
  study3_out/study3_registered_numbers.tex   verbatim copy of numbers.tex (\\Siii...; never edited)
  study3_out/study3_numbers.tex              descriptive macros (\\SiiiD...), no name shared with the registered file
  study3_out/tables/*.tex                    the Study 3 tables

Nothing here is a test. Shares are as computed by analyze6.py (cluster means where it says so, else agent or episode
shares); two decimals. Pooled = equal-weight mean over the three models. The corrected sensitivity counts recount the
registered sensitivity output by its reject flags (see the Study 3 deviations table): the frozen script's
changed-verdict lists also hold tests a sensitivity analysis did not rerun and readings it does not compute.

    python3 paper6/descriptives6.py ../latex     (run from the study3 folder)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
S3 = os.path.dirname(HERE)
MODELS = ("Qwen", "Haiku", "Sonnet")
NAME = {"Qwen": r"\ModelQwenName", "Haiku": r"\ModelHaikuName", "Sonnet": r"\ModelSonnetName", "pooled": "pooled"}
# condition keys: (config, start) -> macro part
CONDS = [("none", "together", "None"), ("cas_available", "together", "Cas"), ("locks_s2text", "together", "LocksTwo"),
         ("locks", "together", "Locks"), ("all_available", "together", "All"), ("locks", "staggered", "LocksStag"),
         ("all_available", "staggered", "AllStag")]
CFG_TT = {"none": r"\texttt{none}", "cas_available": r"\texttt{cas\_available}", "locks_s2text": r"\texttt{locks\_s2text}",
          "locks": r"\texttt{locks}", "all_available": r"\texttt{all\_available}"}
MULTI = ("transfer_shared_source", "transfer_same_amount", "budget_write_skew", "joint_account_write_skew")
FAMILIES = ("inventory_last_unit", "inventory_still_valid", "seat_same", "ticket_same", "transfer_shared_source",
            "transfer_same_amount", "budget_write_skew", "joint_account_write_skew")


def sha(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def f2(x) -> str:
    if x is None:
        return r"\textemdash{}"
    s = f"{x:.2f}"
    return "0.00" if s == "-0.00" else s


def cnt(n: int) -> str:
    return f"{n:,}".replace(",", "{,}")


def word(n: int) -> str:
    return ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")[n] if 0 <= n <= 9 else cnt(n)


def pfmt(p) -> str:
    if p is None:
        return r"\textemdash{}"
    return "$<$0.001" if p < 0.001 else f"{p:.3f}"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    latex = os.path.abspath(sys.argv[1])
    out_dir = os.path.join(latex, "study3_out")
    tab_dir = os.path.join(out_dir, "tables")
    os.makedirs(tab_dir, exist_ok=True)
    res_p = os.path.join(S3, "analysis6", "out_study3", "results.json")
    num_p = os.path.join(S3, "analysis6", "out_study3", "numbers.tex")
    ph_p = os.path.join(HERE, "posthoc6.json")
    R = json.load(open(res_p))
    PH = json.load(open(ph_p))
    D = R["descriptive"]
    T = {t["id"]: t for t in R["tests"]}
    shutil.copyfile(num_p, os.path.join(out_dir, "study3_registered_numbers.tex"))
    reserved = set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", open(num_p).read()))
    V: dict[str, str] = {}

    def put(name: str, val: str) -> None:
        name = "SiiiD" + name
        assert name not in reserved and name not in V, name
        V[name] = val

    # ---- counts and checks
    put("Files", cnt(R["inputs"]["n_files"]))
    put("PerModel", cnt(R["inputs"]["n_files"] // 3))
    put("StaggeredEpisodes", cnt(R["checks"]["stagger"]["staggered_episodes"]))
    put("Excluded", word(len(R["selection"]["excluded"])))
    put("ProviderFailures", word(sum(len(v) for v in R["provider_failures"].values()) if R["provider_failures"] else 0))
    put("CapTruncated", word(R["selection"]["flags"].get("cap_truncated_episodes", 0)))
    # ---- failure shares per model x condition x arm (D5 summed over families), and pooled
    fs = {}
    for m in MODELS:
        for cfg, start, key in CONDS:
            for arm, ak in (("contended", "Cont"), ("control", "Ctrl")):
                n = s = 0
                for fam in FAMILIES:
                    c = D["D5_fs_by_family"].get(f"{m}|{cfg}|{start}|{fam}|{arm}")
                    if c:
                        n += c["episodes"]
                        s += c["fs"]
                fs[(m, key, ak)] = s / n
                put(f"Fs{m}{key}{ak}", f2(s / n))
                if m == "Haiku":
                    put(f"FsEpisodes{key}{ak}", cnt(n))
    for cfg, start, key in CONDS:
        for ak in ("Cont", "Ctrl"):
            put(f"FsPooled{key}{ak}", f2(sum(fs[(m, key, ak)] for m in MODELS) / 3))
    # ---- task classes under cas_available (together, contended): write-skew failures and single-record failures
    SINGLE = ("inventory_last_unit", "inventory_still_valid", "seat_same", "ticket_same")
    WS = ("budget_write_skew", "joint_account_write_skew")
    single_f = single_n = 0
    for m in MODELS:
        wf = wn = 0
        for fam in FAMILIES:
            c = D["D5_fs_by_family"][f"{m}|cas_available|together|{fam}|contended"]
            if fam in WS:
                wf += c["fs"]
                wn += c["episodes"]
            if fam in SINGLE:
                single_f += c["fs"]
                single_n += c["episodes"]
        put(f"CasWsFailed{m}", cnt(wf))
        if m == "Haiku":
            put("CasWsN", cnt(wn))
    put("CasSingleFailedTotal", word(single_f))
    put("CasSingleN", cnt(single_n))
    # ---- D2 lock-failure mechanisms
    mech_fields = (("failed", "Failed"), ("read_then_lock", "ReadThenLock"), ("own_only", "OwnOnly"), ("no_lock", "NoLock"),
                   ("none_of_three", "Other"), ("more_than_one", "MoreThanOne"))
    for cfg, start, key in CONDS:
        if cfg not in ("locks", "locks_s2text", "all_available"):
            continue
        tot = {f: 0 for f, _ in mech_fields}
        for m in MODELS:
            x = D["D2_lock_mechanisms"].get(f"{m}|{cfg}|{start}", {})
            for f, fk in mech_fields:
                put(f"Mech{m}{key}{fk}", cnt(x.get(f, 0)))
                tot[f] += x.get(f, 0)
        for f, fk in mech_fields:
            put(f"MechTotal{key}{fk}", cnt(tot[f]))
    # ---- D1 amounts: half-done transfers and success reports, distinct (shared source) vs same amount
    for cfg, ck in (("cas_available", "Cas"), ("all_available", "All")):
        tot = {}
        for fam, fk in (("transfer_shared_source", "Distinct"), ("transfer_same_amount", "Same")):
            for f, ffk in (("half_done", "HalfDone"), ("half_done_success_reported", "Reported"), ("agents", "Agents")):
                s = 0
                for m in MODELS:
                    v = D["D1_amounts"][f"{m}|{cfg}|{fam}"][f]
                    put(f"Amt{m}{ck}{fk}{ffk}", cnt(v))
                    s += v
                put(f"AmtTotal{ck}{fk}{ffk}", cnt(s))
                tot[(fk, ffk)] = s
    phantom = sum(v["no_write_success_reported"] for v in D["D1_amounts"].values())
    phantom_agents = sum(v["agents"] for v in D["D1_amounts"].values())
    put("PhantomTotal", word(phantom))
    put("PhantomAgents", cnt(phantom_agents))
    # ---- D3 protocol order and lock scope (together and staggered, both arms)
    for cfg, start, key in CONDS:
        if cfg not in ("locks", "locks_s2text", "all_available"):
            continue
        for arm, ak in (("contended", "Cont"), ("control", "Ctrl")):
            for m in MODELS:
                x = D["D3_protocol"][f"{m}|{cfg}|{start}|{arm}"]
                put(f"Rbl{m}{key}{ak}", f2(x["read_before_lock_share"]))
                put(f"LockFirst{m}{key}{ak}", f2(x["lock_first"]))
                put(f"ReadThenLock{m}{key}{ak}", f2(x["read_then_lock"]))
                put(f"NoLock{m}{key}{ak}", f2(x["no_lock"]))
                put(f"ScopeAll{m}{key}{ak}", f2(x["scope_all"]))
                put(f"ScopeOwn{m}{key}{ak}", f2(x["scope_own"]))
    blind_equal = all(abs((x["fenced_unread_basis_share"] or 0) - (x["read_before_lock_share"] or 0)) < 1e-12
                      for x in D["D3_protocol"].values())
    put("BlindFencedNone", "yes" if blind_equal else "no")
    # ---- D4, D4b, D6 (staggered, late agent)
    for cfg, ck in (("locks", "Locks"), ("all_available", "All")):
        tr = ta = 0
        for m in MODELS:
            x = D["D4_reacting_share"][f"{m}|{cfg}"]
            put(f"React{m}{ck}AtRisk", cnt(x["late_agents_at_risk"]))
            put(f"React{m}{ck}Reacting", cnt(x["reacting"]))
            put(f"React{m}{ck}Est", f2(x["estimate"]))
            tr += x["reacting"]
            ta += x["late_agents_at_risk"]
            y = D["D4b_conditional_reaction"][f"{m}|{cfg}"]
            put(f"CondReact{m}{ck}Est", f2(y["estimate"]))
            put(f"CondReact{m}{ck}Lo", f2(y["ci95"][0]))
            put(f"CondReact{m}{ck}Hi", f2(y["ci95"][1]))
            z = D["D6_reactive_reread"][f"{m}|{cfg}"]
            put(f"Reread{m}{ck}Est", f2(z["estimate"]))
            put(f"Reread{m}{ck}Lo", f2(z["ci95"][0]))
            put(f"Reread{m}{ck}Hi", f2(z["ci95"][1]))
        put(f"ReactTotal{ck}AtRisk", cnt(ta))
        put(f"ReactTotal{ck}Reacting", cnt(tr))
    # ---- exposure (check C2) and the S3-H3 gate values
    for m in MODELS:
        for cfg, start, key in CONDS:
            x = R["checks"]["exposure"]["cells"][f"{m}|{cfg}|{start}"]
            put(f"Perc{m}{key}", f2(x["perceivable_share"]))
            if start == "staggered":
                put(f"LateRisk{m}{key}", f2(x["late_agent_at_risk_share"]))
    for mm in MODELS + ("pooled",):
        for cfg, ck in (("locks", "Locks"), ("all_available", "All")):
            t = T[f"H3-eq|{mm}|{cfg}"]
            put(f"Hthree{mm.capitalize()}{ck}Q", f2(t["q"]))
            put(f"Hthree{mm.capitalize()}{ck}U", f2(t["u_ctrl"]))
    # ---- corrected sensitivity counts (by reject flag; registered verdicts stand)
    sens = R["sensitivity"]
    main_rej = {t["id"]: t["reject"] for t in R["tests"]}
    main_read = {t["id"]: t["reading"] for t in R["tests"]}

    def real_changes(tests):
        out = []
        for t in tests:
            if t["id"] in main_rej and (t["reject"] != main_rej[t["id"]] or (t.get("reading") and t["reading"] != main_read[t["id"]])):
                out.append(t["id"])
        return out
    s5 = real_changes(sens["S5_against_equivalence"]["tests"])
    s6 = real_changes(sens["S6_h1_dsg_basis_cycle"]["tests"])
    s7 = real_changes(sens["S7_h3_both_agents"]["tests"])
    s9 = real_changes(sens["S9_h2b_every_agent"]["tests"])
    s3 = [t for mm in sens["S3_holm_within_model"].values() for t, v in mm.items() if v["changed"]]
    put("SensFiveReal", word(len(s5)))
    put("SensSixReal", word(len(s6)))
    put("SensSevenReal", word(len(s7)))
    put("SensNineReal", word(len(s9)))
    put("SensThreeReal", word(len(s3)))
    put("SensFivePairsAdded", word(sens["S5_against_equivalence"]["pairs_added"]))
    put("SensFiveListed", cnt(len(sens["S5_against_equivalence"]["changed_verdicts"])))
    put("SensSixListed", cnt(len(sens["S6_h1_dsg_basis_cycle"]["changed_verdicts"])))
    s4 = sens["S4_family_level"]
    put("SfourHtwoAPooled", pfmt(s4["H2a|pooled|locks_s2text-locks"]))
    put("SfourHtwoASonnet", pfmt(s4["H2a|Sonnet|locks_s2text-locks"]))
    put("SfourHonePooledLocks", pfmt(s4["H1-diff|pooled|locks"]))
    put("SfourHonePooledCas", pfmt(s4["H1-diff|pooled|cas_available"]))
    put("SsevenQwenAllReading", sens["S7_h3_both_agents"]["changed_verdicts"][0]["sensitivity"]["reading"] if s7 else "")
    s9t = {t["id"]: t for t in sens["S9_h2b_every_agent"]["tests"]}
    put("SnineHtwoBPooledEst", f2(s9t["H2b|pooled|locks_s2text-locks"]["estimate"]))
    # ---- the lock bundle at work (exploratory): agents shown a reported wait or a locked read
    lb = PH["lock_bundle"]
    for cfg, start, key in CONDS:
        if cfg not in ("locks", "all_available", "locks_s2text"):
            continue
        w = lr = ag = 0
        for m in MODELS:
            a = lb[f"{m}|{cfg}|{start}|contended|agents"]
            put(f"Waits{m}{key}", cnt(lb[f"{m}|{cfg}|{start}|contended|waits"]))
            put(f"LockedReads{m}{key}", cnt(lb[f"{m}|{cfg}|{start}|contended|locked_reads"]))
            w += lb[f"{m}|{cfg}|{start}|contended|waits"]
            lr += lb[f"{m}|{cfg}|{start}|contended|locked_reads"]
            ag += a
            assert lb[f"{m}|{cfg}|{start}|control|waits"] == 0 and lb[f"{m}|{cfg}|{start}|control|locked_reads"] == 0
        put(f"WaitsTotal{key}", cnt(w))
        put(f"LockedReadsTotal{key}", cnt(lr))
        put(f"AgentsTotal{key}", cnt(ag))
    temp = PH["temperature_effective"]
    put("TempNoneClaude", cnt(temp.get("Haiku|None", 0) + temp.get("Sonnet|None", 0)))
    put("TempNoneHaiku", cnt(temp.get("Haiku|None", 0)))
    put("CompletionsQwenAlibaba", cnt(PH["served"].get("Qwen|qwen/qwen3.6-27b @Alibaba", 0)))
    put("CompletionsTotal", cnt(sum(PH["served"].values())))
    # ---- the one printed value that depends on the Python version of the analysis (exactly 40/64 = 0.625)
    est = T["H1-diff|pooled|locks_s2text"]["estimate"]
    assert abs(est - 0.625) < 1e-12
    put("ExactHalf", "0.625")
    put("ExactHalfDown", "0.62")
    # ---- spend (run_study3.log: "spend by provider: {...}")
    log = open(os.path.join(S3, "results6", "study3", "run_study3.log")).read()
    sp = json.loads(re.search(r"spend by provider: (\{.*\})", log).group(1).replace("'", '"'))
    put("SpendAnthropic", f"{sp['anthropic']:.2f}")
    put("SpendOpenRouter", f"{sp['openrouter']:.2f}")
    put("SpendTotal", f"{sp['anthropic'] + sp['openrouter']:.2f}")
    # ---- write macros
    hdr = ("% GENERATED by study3/paper6/descriptives6.py -- do not edit. Descriptive Study 3 numbers (prefix \\SiiiD).\n"
           f"% inputs: results.json sha256 {sha(res_p)}; registered numbers.tex sha256 {sha(num_p)}; "
           f"posthoc6.json sha256 {sha(ph_p)}\n")
    with open(os.path.join(out_dir, "study3_numbers.tex"), "w") as fh:
        fh.write(hdr)
        for k in sorted(V):
            fh.write(f"\\newcommand{{\\{k}}}{{{V[k]}}}\n")
    write_tables(R, D, T, fs, tab_dir, PH)
    print(f"descriptives6: {len(V)} macros; tables in {tab_dir}")
    return 0


def reading_cell(t) -> str:
    rd = {"rejects": "rejects", "does_not_reject": "no claim", "inconclusive": "inconclusive", "uninformative": "uninformative"}
    return rd.get(t["reading"], t["reading"] or "")


def write_tables(R, D, T, fs, tab_dir, PH) -> None:
    # (1) main-text table: registered Delta per model and pooled, bold = rejects (after Holm; calibration at raw alpha)
    rows = [("H1cal-diff", "none", r"\texttt{none} (calibration)"), ("H1-diff", "cas_available", r"\texttt{cas\_available}"),
            ("H1-diff", "locks_s2text", r"\texttt{locks\_s2text}"), ("H1-diff", "locks", r"\texttt{locks}"),
            ("H1-diff", "all_available", r"\texttt{all\_available}")]
    L = [r"\begin{table}[t]", r"\centering\scriptsize", r"\begin{adjustbox}{max width=\columnwidth}",
         r"\begin{tabular}{@{}llcccc@{}}", r"\toprule",
         r" & & \ModelQwenName & \ModelHaikuName & \ModelSonnetName & pooled \\", r"\midrule"]
    first = True
    for test, cfg, lab in rows:
        cells = []
        for mm in ("Qwen", "Haiku", "Sonnet", "pooled"):
            t = T[f"{test}|{mm}|{cfg}"]
            v = f2(t["estimate"])
            cells.append(r"\textbf{" + v + "}" if t["reject"] else v)
        head = r"\SThreeHone" if first else ""
        first = False
        L.append(f"{head} & {lab} & " + " & ".join(cells) + r" \\")
    L.append(r"\midrule")
    for test, lab in (("H2a", r"failures, \texttt{locks\_s2text} $-$ \texttt{locks}"), ("H2b", r"read-before-lock share, same")):
        cells = []
        for mm in ("Qwen", "Haiku", "Sonnet", "pooled"):
            t = T[f"{test}|{mm}|locks_s2text-locks"]
            v = f2(t["estimate"])
            cells.append(r"\textbf{" + v + "}" if t["reject"] else v)
        name = r"\SThreeHtwoA" if test == "H2a" else r"\SThreeHtwoB"
        L.append(f"{name} & {lab} & " + " & ".join(cells) + r" \\")
    L.append(r"\midrule")
    for cfg, lab in (("locks", r"\texttt{locks}, staggered"), ("all_available", r"\texttt{all\_available}, staggered")):
        cells = []
        for mm in ("Qwen", "Haiku", "Sonnet", "pooled"):
            t = T[f"H3-diff|{mm}|{cfg}"]
            cells.append(f2(t["estimate"]))
        name = r"\SThreeHthree" if cfg == "locks" else ""
        L.append(f"{name} & {lab} & " + " & ".join(cells) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}",
          r"\caption{\SThree{} registered estimates. \SThreeHone: contended minus control failure rate (calibration under \texttt{none}); \SThreeHtwoA: contended failure rate under the \STwo{} lock text minus that under the \SThree{} lock bundle; \SThreeHtwoB: the same difference in the read-before-lock share of lock users; \SThreeHthree: the late agent's uptake, contended minus control. Bold: the registered test rejected after Holm (the calibration at raw $\alpha$). Every \SThreeHthree{} cell is uninformative or inconclusive under the registered gate. Intervals, $p$-values and readings: Appendix Tables~\ref{tab:s3-tests} and~\ref{tab:s3-h3}.}",
          r"\label{tab:s3-main}", r"\end{table}"]
    open(os.path.join(tab_dir, "s3_main.tex"), "w").write("\n".join(L) + "\n")

    # (2) appendix: every H1, calibration, H2a, H2b test
    L = [r"\begin{table*}[tp]", r"\centering\scriptsize", r"\begin{adjustbox}{max width=\textwidth}",
         r"\begin{tabular}{@{}lllcccl@{}}", r"\toprule",
         r"test & model & config & $\Delta$ [95\% CI] & $p$ & Holm $p$ & reading \\", r"\midrule"]
    order = [t for t in R["tests"] if t["test"] in ("H1cal-diff", "H1-diff", "H2a", "H2b")]
    key = {"H1cal-diff": 0, "H1-diff": 1, "H2a": 2, "H2b": 3}
    cfgo = {"none": 0, "cas_available": 1, "locks_s2text": 2, "locks": 3, "all_available": 4, "locks_s2text-locks": 5}
    mo = {"Qwen": 0, "Haiku": 1, "Sonnet": 2, "pooled": 3}
    order.sort(key=lambda t: (key[t["test"]], cfgo[t["id"].split("|")[2]], mo[t["id"].split("|")[1]]))
    tn = {"H1cal-diff": r"\SThreeHone{} cal.", "H1-diff": r"\SThreeHone", "H2a": r"\SThreeHtwoA", "H2b": r"\SThreeHtwoB"}
    prev = None
    for t in order:
        mm, cfg = t["id"].split("|")[1], t["id"].split("|")[2]
        if prev is not None and prev != (t["test"], cfg):
            L.append(r"\addlinespace[2pt]")
        prev = (t["test"], cfg)
        c = cfg if cfg != "locks_s2text-locks" else "locks_s2text $-$ locks"
        c = r"\texttt{" + c.replace("_", r"\_").replace(r"$-$", "") + "}" if cfg != "locks_s2text-locks" else r"\texttt{locks\_s2text} $-$ \texttt{locks}"
        padj = r"\textemdash{}" if t["test"] == "H1cal-diff" else pfmt(t["p_adj"])
        L.append(f"{tn[t['test']]} & {NAME[mm]} & {c} & {f2(t['estimate'])} [{f2(t['ci95'][0])}, {f2(t['ci95'][1])}] & {pfmt(t['p'])} & {padj} & {reading_cell(t)} " + r"\\")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}",
          r"\caption{\SThree{} registered tests of \SThreeHone, its calibration, \SThreeHtwoA{} and \SThreeHtwoB{} (one-sided exact sign-flip tests over the cluster values; Holm within each hypothesis family, none for the calibration; percentile cluster-bootstrap intervals). ``No claim'': the test did not reject, which is not evidence of no effect. \SThreeHtwoB{} uses the clusters with a lock user that committed a write under both lock texts. Source: the frozen analysis's \texttt{results.json}.}",
          r"\label{tab:s3-tests}", r"\end{table*}"]
    open(os.path.join(tab_dir, "s3_tests.tex"), "w").write("\n".join(L) + "\n")

    # (3) appendix: S3-H3
    L = [r"\begin{table*}[tp]", r"\centering\scriptsize", r"\begin{adjustbox}{max width=\textwidth}",
         r"\begin{tabular}{@{}llcccccl@{}}", r"\toprule",
         r"config & model & $\Delta$ [90\% bootstrap-$t$] & TOST Holm $p$ & diff.\ $p$ & $q$ & $u$ & reading \\", r"\midrule"]
    for cfg in ("locks", "all_available"):
        for mm in ("Qwen", "Haiku", "Sonnet", "pooled"):
            e = T[f"H3-eq|{mm}|{cfg}"]
            d = T[f"H3-diff|{mm}|{cfg}"]
            ci = e.get("ci90_t") or e["ci90"]
            L.append(f"{CFG_TT[cfg]} & {NAME[mm]} & {f2(e['estimate'])} [{f2(ci[0])}, {f2(ci[1])}] & {pfmt(e['p_adj'])} & {pfmt(d['p'])} & {f2(e['q'])} & {f2(e['u_ctrl'])} & {reading_cell(e)} " + r"\\")
        if cfg == "locks":
            L.append(r"\addlinespace[2pt]")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}",
          r"\caption{\SThreeHthree{} (staggered start, late agent): uptake under the contended minus the control template. $q$: the share of contended late agents at risk (a perceivable signal before any primitive); $u$: the control late agents' uptake. An equivalence counts only if $q>\delta$ and $1-u\geq\delta$ ($\delta=\SiiiDeltaCell$ per model, \SiiiDeltaPooled{} pooled); every cell fails one of the two, so every reading is uninformative, or inconclusive where neither test rejected. The leakage check rejected for \ModelHaikuName, whose row is therefore the total effect of the contended template.}",
          r"\label{tab:s3-h3}", r"\end{table*}"]
    open(os.path.join(tab_dir, "s3_h3.tex"), "w").write("\n".join(L) + "\n")

    # (4) appendix: failure shares per condition and arm
    L = [r"\begin{table*}[tp]", r"\centering\scriptsize", r"\begin{adjustbox}{max width=\textwidth}",
         r"\begin{tabular}{@{}lccccccc@{}}", r"\toprule",
         r" & \multicolumn{5}{c}{together} & \multicolumn{2}{c}{staggered} \\", r"\cmidrule(lr){2-6}\cmidrule(l){7-8}",
         r"model & \texttt{none} & \texttt{cas} & \texttt{s2text} & \texttt{locks} & \texttt{all} & \texttt{locks} & \texttt{all} \\", r"\midrule"]
    for mm in MODELS:
        cells = [f"{f2(fs[(mm, k, 'Cont')])} ({f2(fs[(mm, k, 'Ctrl')])})" for _, _, k in CONDS]
        L.append(f"{NAME[mm]} & " + " & ".join(cells) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}",
          r"\caption{\SThree{} committed-intent serializability failure share of contended episodes, control in parentheses, per model and condition (\SiiiDFsEpisodesNoneCont{} episodes per cell and arm; descriptive). \texttt{cas} = \texttt{cas\_available}, \texttt{s2text} = \texttt{locks\_s2text} (the \STwo{} lock text), \texttt{all} = \texttt{all\_available}.}",
          r"\label{tab:s3-fs}", r"\end{table*}"]
    open(os.path.join(tab_dir, "s3_fs.tex"), "w").write("\n".join(L) + "\n")

    # (5) appendix: lock-failure mechanisms (D2) and protocol order (D3), contended
    L = [r"\begin{table*}[tp]", r"\centering\scriptsize", r"\begin{adjustbox}{max width=\textwidth}",
         r"\begin{tabular}{@{}lllcccccccc@{}}", r"\toprule",
         r" & & & \multicolumn{5}{c}{failed contended episodes (D2)} & \multicolumn{3}{c}{contended agents (D3)} \\",
         r"\cmidrule(lr){4-8}\cmidrule(l){9-11}",
         r"model & config & start & failed & read then lock & guard not locked & no lock & other & lock first & read before lock & scope all \\", r"\midrule"]
    for mm in MODELS:
        for cfg, start, key in CONDS:
            if cfg not in ("locks_s2text", "locks", "all_available"):
                continue
            x = D["D2_lock_mechanisms"][f"{mm}|{cfg}|{start}"]
            y = D["D3_protocol"][f"{mm}|{cfg}|{start}|contended"]
            L.append(f"{NAME[mm]} & {CFG_TT[cfg]} & {start} & {x['failed']} & {x['read_then_lock']} & {x['own_only']} & {x['no_lock']} & {x['none_of_three'] + x['more_than_one']} & {f2(y['lock_first'])} & {f2(y['read_before_lock_share'])} & {f2(y['scope_all'])} " + r"\\")
        if mm != MODELS[-1]:
            L.append(r"\addlinespace[2pt]")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}",
          r"\caption{\SThree{} lock-failure mechanisms (D2, pre-specified, the \STwo{} post hoc rules) among the failed contended episodes, and protocol order (D3) among contended agents: the share that locked before any read, the read-before-lock share of lock users that committed a fenced write (the \SThreeHtwoB{} quantity, agent level), and the share of multi-record agents that locked every record their intent reads. ``Other'': none or more than one mechanism. \texttt{locks\_s2text} carries the \STwo{} lock text; \texttt{locks} and \texttt{all\_available} the \SThree{} bundle.}",
          r"\label{tab:s3-mech}", r"\end{table*}"]
    open(os.path.join(tab_dir, "s3_mech.tex"), "w").write("\n".join(L) + "\n")

    # (6) appendix: amounts (D1) and reactions (D4, D4b, D6)
    L = [r"\begin{table*}[tp]", r"\centering\scriptsize", r"\begin{adjustbox}{max width=\textwidth}",
         r"\begin{tabular}{@{}llcccc@{}}", r"\toprule",
         r" & & \multicolumn{2}{c}{distinct amounts} & \multicolumn{2}{c}{same amount} \\", r"\cmidrule(lr){3-4}\cmidrule(l){5-6}",
         r"model & config & half-done & reported success & half-done & reported success \\", r"\midrule"]
    for mm in MODELS:
        for cfg in ("cas_available", "all_available"):
            a = D["D1_amounts"][f"{mm}|{cfg}|transfer_shared_source"]
            b = D["D1_amounts"][f"{mm}|{cfg}|transfer_same_amount"]
            L.append(f"{NAME[mm]} & {CFG_TT[cfg]} & {a['half_done']} & {a['half_done_success_reported']} & {b['half_done']} & {b['half_done_success_reported']} " + r"\\")
    L += [r"\midrule", r"\multicolumn{6}{@{}l}{\emph{Late agents at risk (staggered): reacting share (D4), conditional reaction (D4b), reactive re-read (D6)}} \\",
          r"model & config & at risk & reacted & D4b [95\% CI] & D6 [95\% CI] \\", r"\midrule"]
    for mm in MODELS:
        for cfg in ("locks", "all_available"):
            x = D["D4_reacting_share"][f"{mm}|{cfg}"]
            y = D["D4b_conditional_reaction"][f"{mm}|{cfg}"]
            z = D["D6_reactive_reread"][f"{mm}|{cfg}"]
            L.append(f"{NAME[mm]} & {CFG_TT[cfg]} & {x['late_agents_at_risk']} & {x['reacting']} & {f2(y['estimate'])} [{f2(y['ci95'][0])}, {f2(y['ci95'][1])}] & {f2(z['estimate'])} [{f2(z['ci95'][0])}, {f2(z['ci95'][1])}] " + r"\\")
    L += [r"\bottomrule", r"\end{tabular}", r"\end{adjustbox}",
          r"\caption{\SThree{} pre-specified descriptives. Top (D1): contended agents with a half-done transfer and how many of them reported success, on the transfer family with distinct amounts (\texttt{transfer\_shared\_source}) and with the \STwo{} same-amount rule (\texttt{transfer\_same\_amount}); \SiiiDAmtHaikuCasDistinctAgents{} agents per cell. Bottom: late agents at risk under the staggered start, how many protected after their first perceivable signal (D4), uptake minus that of the paired control late agent (D4b), and the read-before-lock share of lock users, contended minus control (D6); cluster-bootstrap intervals, no test.}",
          r"\label{tab:s3-desc}", r"\end{table*}"]
    open(os.path.join(tab_dir, "s3_desc.tex"), "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
