#!/usr/bin/env python3
"""Generate every number in the concurrency paper from the frozen analysis.

    python3 make_numbers4.py --analysis DIR [--check]

Reads (read-only):
  DIR/provenance.json      written by run_analysis.py (inputs, dry-run flag)
  DIR/numbers.json         analyze4.py, EXPLORATORY rates + permutation comparisons
  DIR/confirmatory.json    analyze4.py, pre-registered tests (+ truncation sensitivity)
  the analysed CSVs        through analyze4.load() (same row filtering as analyze4)
  src4/*.py, run_full.sh   design constants (imported or regex-parsed; nothing written)
  ../PREREGISTRATION.md    pilot/budget facts, each checked by exact substring match

Writes (inside latex/ only):
  numbers.tex              one \\newcommand per value; \\PipelineDryRun flag
  numbers_report.txt       provenance, warnings, every macro and its value
  tables/*.tex             tables that reference numbers.tex macros (no literal results)
  build/figdata.json       data for figures/make_figs.py (same values as the macros)
  facts/*.md               rendered from facts/src/*.md ({{Macro}} -> `\\Macro` = value)

Refuses to run if the src4 FREEZE hashes do not verify or the analysis was produced
by a different analyze4.py than the frozen one.

Macro naming (letters only):
  confirmatory   \\H<one|two|three|fourA|fourB|six><Model><Field>, \\H<..>Verdict, ...
                 Field: Est (Rate for H1/H2), CI, CILo, CIHi, P, PHolm, Method, Reject,
                 Verdict, Clusters, RegClusters, Status; H4b: EstI/EstII, CII/CIII, PI/PII
  H5             \\Hfive<Model><K|N|Rate|CI>, \\HfiveNModelsWithOne, \\HfiveOutcomeMet
  sensitivity    \\Sens<H...><Model><Est|PHolm|Verdict>, \\Sens<H...>Verdict
  cell rates     \\X<Metric><Config><Model><Off|On><Two|Four|Eight><Est|CI|Num|Den|Inst>
                 (contended scope; EXPLORATORY)
  comparisons    \\CmpCfg<Metric><Config><Model><Off|On><N><Diff|P|PHolm|Inst>,
                 \\CmpAware<Metric><Config><Model><N><...>  (EXPLORATORY)
  H6 per n       \\HsixNonser<Model><Two|Four|Eight>
  design         \\Des...;  pilot/budget (from the prereg) \\Pilot..., \\Plan...
  observed       \\Excl..., \\Obs..., \\Cost..., \\Served<Model>, \\Model<Key>Name
  exploratory E  \\Expl...  from DIR/exploratory_posthoc.json (explore4.py; EXPLORATORY, saved data only)
  post hoc       \\Rb...    from DIR/rollback_sensitivity.json (rollback_sensitivity.py; POST HOC, not confirmatory)
  H5 audit       \\HfiveAudit...  from the same file (counts of audit/H5_AUDIT.csv; "--" for dry runs)
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys
from collections import OrderedDict, defaultdict
from decimal import ROUND_HALF_UP, Decimal

from pipeline_common import HERE, PAPER, SRC4, require_freeze, sha256_file

sys.dont_write_bytecode = True
sys.path.insert(0, SRC4)
import analyze4 as A  # noqa: E402  (frozen; imported read-only for constants and load())

PREREG = os.path.join(PAPER, "PREREGISTRATION.md")
TABLES = os.path.join(HERE, "tables")
BUILD = os.path.join(HERE, "build")
FACTS_SRC = os.path.join(HERE, "facts", "src")
FACTS_OUT = os.path.join(HERE, "facts")

# ------------------------------------------------------------------ naming
MODEL_KEYS = [  # (substring of requested id, macro key, display name), paper order = registered order
    ("qwen", "Qwen", "Qwen3.6-27B"),
    ("haiku", "Haiku", "Haiku 4.5"),
    ("gpt-5.5", "GPT", "GPT-5.5"),
    ("gemini", "Gemini", "Gemini 4 Argon"),
    ("sonnet", "Sonnet", "Sonnet 5"),
    ("fable", "Fable", "Fable 5"),
]
CONFIG_KEYS = OrderedDict([("none", "None"), ("reread_only", "Reread"), ("cas_available", "CasAvail"),
                           ("cas_required", "CasReq"), ("locks", "Locks"), ("messages", "Messages")])
METRIC_KEYS = OrderedDict([("non_serializable", "Nonser"), ("stale_overwrite", "Stale"), ("partial_action", "Partial"),
                           ("write_skew", "Skew"), ("invariant_violation", "Inv"), ("reread", "Reread"), ("cas", "Cas"),
                           ("lock", "Lock"), ("message", "Msg"), ("none", "NoCoord"),
                           ("unnecessary_give_up", "Giveup"), ("abandoned", "Abandon")])
H_KEYS = OrderedDict([("H1", "Hone"), ("H2", "Htwo"), ("H3", "Hthree"), ("H4a", "HfourA"), ("H4b", "HfourB"), ("H6", "Hsix")])
NUMWORD = {0: "Zero", 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight",
           16: "Sixteen", 32: "ThirtyTwo"}
AWARE = {0: "Off", 1: "On"}
_LETTERS = re.compile(r"^[A-Za-z]+$")


def model_key(mid):
    m = mid.lower()
    for sub, key, _ in MODEL_KEYS:
        if sub in m:
            return key
    return "M" + "".join(w.capitalize() for w in re.split(r"[^a-z]+", m) if w)


def model_name(mid):
    m = mid.lower()
    for sub, _, name in MODEL_KEYS:
        if sub in m:
            return name
    return mid


def config_key(c):
    return CONFIG_KEYS.get(c) or "".join(w.capitalize() for w in re.split(r"[^a-z]+", c) if w)


def nword(n):
    if n in NUMWORD:
        return NUMWORD[n]
    raise KeyError(f"no word for {n}")


# ------------------------------------------------------------------ formatting
def f2(x, nd=2):
    if x is None:
        return None
    q = Decimal(1).scaleb(-nd)
    s = str(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))
    if s.startswith("-"):
        s = "$-$" + s[1:] if Decimal(s) != 0 else s[1:]
    return s


def fci(lo, hi):
    if lo is None or hi is None:
        return None
    return f"[{f2(lo)}, {f2(hi)}]"


def fp(p):
    if p is None:
        return None
    if p < 0.001:
        return "$<$0.001"
    return f2(p, 3)


def thou(n):
    """Integer with a LaTeX thousands separator ({,})."""
    return f"{int(n):,}".replace(",", "{,}")


def tex_text(s):
    rep = {"\\": r"\textbackslash{}", "$": r"\$", "%": r"\%", "#": r"\#", "&": r"\&", "_": r"\_",
           "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\^{}"}
    return "".join(rep.get(c, c) for c in str(s))


def tex_tt(s):
    rep = {"_": r"\_\allowbreak{}", "-": r"-\allowbreak{}", ".": r".\allowbreak{}", ":": r":\allowbreak{}",
           "/": r"/\allowbreak{}", "#": r"\#", "%": r"\%", "&": r"\&", "~": r"\textasciitilde{}", "$": r"\$"}
    return r"\texttt{%s}" % "".join(rep.get(c, c) for c in str(s))


def plain(v):
    v = v.replace("$<$", "<").replace("$-$", "-").replace(r"\allowbreak{}", "")
    v = re.sub(r"\\texttt\{(.*)\}", r"\1", v)
    v = re.sub(r"\\PENDING\{([^}]*)\}", r"[PENDING: \1]", v)
    for a, b in ((r"\_", "_"), (r"\%", "%"), (r"\&", "&"), (r"\#", "#"), (r"\$", "$")):
        v = v.replace(a, b)
    return v


# ------------------------------------------------------------------ state
NUMS = OrderedDict()   # macro -> LaTeX value
GROUP = {}             # macro -> group name (report)
REPORT = []            # notes
WARN = []              # problems that need attention


def put(name, value, group):
    if not _LETTERS.match(name):
        raise ValueError(f"macro name {name!r} is not letters-only")
    if name in NUMS and NUMS[name] != value:
        raise ValueError(f"macro {name} defined twice with different values")
    NUMS[name] = "--" if value is None else str(value)
    GROUP[name] = group


def pending(name, why, group):
    put(name, r"\PENDING{%s}" % tex_text(why), group)
    WARN.append(f"PENDING {name}: {why}")


# ------------------------------------------------------------------ design constants
def regex1(path, pattern, cast=str):
    with open(path) as f:
        m = re.search(pattern, f.read(), re.M)
    if not m:
        raise SystemExit(f"could not find /{pattern}/ in {path}")
    return cast(m.group(1))


def design_constants():
    g = "design"
    put("DesNModels", len(A.REGISTERED_MODELS), g)
    put("DesNTemplates", len(A.CONTENDED_TEMPLATES) + 1, g)  # + budget_control (checked below)
    put("DesNContendedTemplates", len(A.CONTENDED_TEMPLATES), g)
    put("DesNSingleRecordTemplates", len(A.SINGLE_RECORD_TEMPLATES), g)
    put("DesNWriteSkewTemplates", len(A.WRITE_SKEW_TEMPLATES), g)
    put("DesNInstances", len(A.N2_INSTANCES), g)
    put("DesNScaleInstances", len(A.SCALE_INSTANCES), g)
    put("DesNSeedsPhaseOne", len(A.N2_SEEDS), g)
    put("DesNBoot", thou(A.N_BOOT), g)
    put("DesBootSeed", A.BOOT_SEED, g)
    put("DesAlpha", f2(A.ALPHA), g)
    put("DesCILevel", round(100 * math.erf(A.Z95 / math.sqrt(2))), g)
    put("DesHfourBMargin", f2(A.H4B_MARGIN), g)
    put("DesHtwoMinReject", A.H2_MIN_REJECT, g)
    put("DesHoneThreshold", f2(A._spec("H1")["theta0"]), g)
    put("DesHtwoThreshold", f2(A._spec("H2")["theta0"]), g)
    put("DesHsixSeed", ", ".join(str(x) for x in A.SCALE_SEEDS), g)
    put("DesScaleNs", ", ".join(str(n) for n in A.SCALE_NS), g)
    for n in A.SCALE_NS:
        put(f"DesN{nword(n)}", n, g)
    for h, key in H_KEYS.items():
        s = A._spec(h)
        put(f"Des{key}Clusters", len(s["templates"]) * len(s["instances"]), g)
    # run4 / model loop / world defaults
    run4 = os.path.join(SRC4, "run4.py")
    put("DesGap", regex1(run4, r'"--gap", type=int, default=(\d+)'), g)
    put("DesJitter", regex1(run4, r'"--jitter", type=int, default=(\d+)'), g)
    put("DesStallRounds", regex1(run4, r'"--stall-rounds", type=int, default=(\d+)'), g)
    put("DesMaxRounds", thou(regex1(run4, r'"--max-rounds", type=int, default=(\d+)')), g)
    ma = os.path.join(SRC4, "model_agent4.py")
    tc = int(regex1(ma, r"^DEFAULT_TURN_CAP = (\d+)"))
    put("DesTurnCap", tc, g)
    put("DesCompletionCap", tc + 1, g)
    put("DesMaxTokens", thou(regex1(ma, r"^DEFAULT_MAX_TOKENS = (\d+)")), g)
    put("DesTemperature", regex1(ma, r"^TEMPERATURE = ([\d.]+)").rstrip("0").rstrip(".") or "0", g)
    import world4
    wc = world4.WorldConfig()
    put("DesMaxLease", wc.max_lease_steps, g)
    put("DesLockExpiry", "on" if wc.lock_expiry else "off", g)
    put("DesAwareSentence", tex_text(world4.CONCURRENCY_NOTICE), g)
    put("DesMaxMessageChars", thou(world4.MAX_MESSAGE_CHARS), g)
    # run_full.sh grid
    rf = os.path.join(SRC4, "run_full.sh")
    txt = open(rf).read()
    max_usd = int(regex1(rf, r"^MAX_USD=(\d+)"))
    put("DesMaxUSD", max_usd, g)
    tasks = regex1(rf, r'^TASKS="([^"]+)"').split(",")
    if len(tasks) != len(A.CONTENDED_TEMPLATES) + 1 or set(A.CONTENDED_TEMPLATES) - set(tasks):
        WARN.append("run_full.sh TASKS disagree with analyze4 CONTENDED_TEMPLATES + control")
    arr = lambda name: dict(re.findall(r"\[(\d)\]=\"?([^\]\"\s)]+)\"?", re.search(rf"declare -A {name}=\(([^)]*)\)", txt).group(1)))  # noqa: E731
    agents, configs, inst, seeds = arr("P_AGENTS"), arr("P_CONFIGS"), arr("P_INST"), arr("P_SEEDS")
    total = 0
    phases = {}
    for ph in sorted(agents):
        n_cfg = len(configs[ph].split(","))
        per_model = n_cfg * 2 * len(tasks) * int(inst[ph]) * len(seeds[ph].split(","))
        phases[int(ph)] = {"n_agents": int(agents[ph]), "configs": configs[ph].split(","), "per_model": per_model}
        w = nword(int(ph))
        put(f"DesPhase{w}NAgents", agents[ph], g)
        put(f"DesPhase{w}NConfigs", n_cfg, g)
        put(f"DesPhase{w}NInstances", inst[ph], g)
        put(f"DesPhase{w}NSeeds", len(seeds[ph].split(",")), g)
        put(f"DesPhase{w}EpisodesPerModel", per_model, g)
        put(f"DesPhase{w}Episodes", thou(per_model * len(A.REGISTERED_MODELS)), g)
        total += per_model
    put("DesEpisodesPerModel", total, g)
    put("DesEpisodesTotal", thou(total * len(A.REGISTERED_MODELS)), g)
    for mid in A.REGISTERED_MODELS:
        k = model_key(mid)
        put(f"Model{k}Name", tex_text(model_name(mid)), "models")
        put(f"Model{k}Id", tex_tt(mid), "models")
    return phases


PREREG_FACTS = [  # (macro, value, exact substring of PREREGISTRATION.md that must contain it)
    ("PilotEpisodes", "192", "the pilot: 192 episodes"),
    ("PilotSpendUSD", "1.60", "the pilot spent $1.60"),
    ("PilotNoneNonserLow", "13", "13–14 of 14 contended episodes per model per config were non-serializable"),
    ("PilotNoneNonserHigh", "14", "13–14 of 14 contended episodes"),
    ("PilotNoneNonserDen", "14", "13–14 of 14 contended"),
    ("PilotLockLow", "2", "about 2–3 of 28 episodes contained any lock use"),
    ("PilotLockHigh", "3", "about 2–3 of 28 episodes"),
    ("PilotLockDen", "28", "2–3 of 28 episodes"),
    ("PilotMsgK", "1", "The message channel was used in 1 of 28"),
    ("PilotMsgDen", "28", "used in 1 of 28"),
    ("PilotInstancesPerTemplate", "one", "one instance per template"),
    ("PlanPhaseOneUSD", "146.61", "$146.61 for phase 1"),
    ("PlanPhaseTwoUSD", "40.32", "$40.32 for phase 2"),
    ("PlanPhaseThreeUSD", "88.70", "$88.70 for phase 3"),
    ("PlanTotalUSD", "275.63", "$275.63 in total"),
    ("BudgetTotalUSD", "350", "The total budget is $350"),
    ("MutantsKilled", "97", "97 of 99 mutants were killed"),
    ("MutantsTotal", "99", "97 of 99 mutants"),
    ("HfourBExampleP", "0.01", "about 0.01 at margin 0.25"),
    ("HfourBExamplePTight", "0.27", "about 0.27 at 0.10"),
    ("HfourBTightMargin", "0.10", "about 0.27 at 0.10"),
]


def prereg_facts():
    txt = open(PREREG).read()
    for name, val, needle in PREREG_FACTS:
        if needle in txt and val in needle:
            put(name, val, "prereg")
        else:
            pending(name, "not found in PREREGISTRATION.md", "prereg")


# ------------------------------------------------------------------ confirmatory
def conf_macros(c, prefix, models):
    g = "confirmatory" if not prefix else "sensitivity"
    for h, hk in H_KEYS.items():
        rec = c["hypotheses"][h]
        base = prefix + hk
        put(f"{base}Verdict", tex_text(rec["verdict"]), g)
        put(f"{base}FamilySize", rec["family_size"], g)
        put(f"{base}NReject", len(rec["rejecting_models"]), g)
        put(f"{base}NNotTested", len(rec["not_tested_models"]), g)
        if rec["family_size"] == 0:
            WARN.append(f"{prefix or ''}{h}: no model tested; analyze4 verdict string is '{rec['verdict']}' "
                        "(rule-based; printed verbatim, see \\%sNNotTested)" % base)
        for t in rec["tests"]:
            mk = model_key(t["model"])
            b = f"{base}{mk}"
            tested = t["status"] == "tested"
            put(f"{b}Status", "tested" if tested else "not tested", g)
            put(f"{b}Clusters", t["n_complete_clusters"], g)
            put(f"{b}RegClusters", t["n_registered_clusters"], g)
            put(f"{b}DroppedClusters", len(t["dropped_clusters"]), g)
            put(f"{b}PHolm", fp(t.get("p_holm")), g)
            put(f"{b}P", fp(t.get("p")), g)
            put(f"{b}Reject", "n/t" if not tested else ("yes" if t["reject"] else "no"), g)
            put(f"{b}Verdict", "not tested" if not tested else ("rejected" if t["reject"] else "not rejected"), g)
            if h == "H4b":
                for part, suf in (("component_i", "I"), ("component_ii", "II")):
                    ct = t.get(part) or {}
                    put(f"{b}Est{suf}", f2(ct.get("estimate")), g)
                    put(f"{b}CI{suf}", fci(ct.get("ci_low"), ct.get("ci_high")), g)
                    put(f"{b}P{suf}", fp(ct.get("p")), g)
                    put(f"{b}Method{suf}", (ct.get("method") or "--").replace("_", " "), g)
            else:
                put(f"{b}Est", f2(t.get("estimate")), g)
                if h in ("H1", "H2"):
                    put(f"{b}Rate", f2(t.get("estimate")), g)
                put(f"{b}CI", fci(t.get("ci_low"), t.get("ci_high")), g)
                put(f"{b}CILo", f2(t.get("ci_low")), g)
                put(f"{b}CIHi", f2(t.get("ci_high")), g)
                put(f"{b}Method", (t.get("method") or "--").replace("_", " "), g)
    h5 = c.get("H5", {})
    base = prefix + "Hfive"
    if h5.get("status") != "descriptive":
        for mid in models:
            for f in ("K", "N", "Rate", "CI"):
                pending(f"{base}{model_key(mid)}{f}", "H5 not available (no transcripts)", g)
        return
    for mid, w in h5["per_model"].items():
        b = f"{base}{model_key(mid)}"
        put(f"{b}K", w["k"], g)
        put(f"{b}N", w["n"], g)
        put(f"{b}Rate", f2(w["rate"]), g)
        put(f"{b}CI", fci(w["ci_low"], w["ci_high"]), g)
    put(f"{base}NModelsWithOne", len(h5["models_with_at_least_one"]), g)
    put(f"{base}OutcomeMet", "yes" if h5["outcome_met_before_audit"] else "no", g)


# ------------------------------------------------------------------ exploratory
def rate_index(numbers):
    idx = {}
    for r in numbers["rates"]:
        idx[(r["model"], r["config"], r["aware"], r["n_agents"], r["scope"], r["metric"])] = r
    return idx


def cell_macros(numbers):
    g = "exploratory-rates"
    for r in numbers["rates"]:
        if r["scope"] != "contended" or r["metric"] not in METRIC_KEYS:
            continue
        b = (f"X{METRIC_KEYS[r['metric']]}{config_key(r['config'])}{model_key(r['model'])}"
             f"{AWARE[r['aware']]}{nword(r['n_agents'])}")
        put(b + "Est", f2(r["estimate"]), g)
        put(b + "CI", fci(r["ci_low"], r["ci_high"]), g)
        put(b + "Num", r["numerator"], g)
        put(b + "Den", r["denominator"], g)
        put(b + "Inst", r["n_instances"], g)


def cmp_macros(numbers):
    g = "exploratory-comparisons"
    for c in numbers["comparisons"]:
        if c["metric"] not in METRIC_KEYS:
            continue
        m = METRIC_KEYS[c["metric"]]
        if c["comparison"] == "config":
            b = f"CmpCfg{m}{config_key(c['treatment'])}{model_key(c['model'])}{AWARE[c['aware']]}{nword(c['n_agents'])}"
        else:
            b = f"CmpAware{m}{config_key(c['config'])}{model_key(c['model'])}{nword(c['n_agents'])}"
        put(b + "Diff", f2(c["mean_diff"]), g)
        put(b + "P", fp(c["p_two_sided"]), g)
        put(b + "PHolm", fp(c.get("p_holm")), g)
        put(b + "Inst", c["n_instances"], g)


# ------------------------------------------------------------------ from rows (analyze4.load)
def h6_per_n(rows, conf, models):
    """Mean non_serializable per n over complete H6 clusters (figure c); cross-checked against analyze4's slope."""
    out = {}
    idx = {}
    for r in rows:
        idx.setdefault((r["model"], r["task"], str(r["instance"]), r["config"], r["aware"], r["n_agents"], r["seed"]), r)
    for mid in models:
        ys = {n: [] for n in A.SCALE_NS}
        n_cl = 0
        for t in A.CONTENDED_TEMPLATES:
            for i in A.SCALE_INSTANCES:
                eps = {n: idx.get((mid, t, str(i), "cas_available", 0, n, 0)) for n in A.SCALE_NS}
                if all(eps.values()):
                    n_cl += 1
                    for n, r in eps.items():
                        ys[n].append(r["non_serializable"])
        mk = model_key(mid)
        rates = {n: (sum(v) / len(v) if v else None) for n, v in ys.items()}
        out[mid] = {"rates": rates, "n_clusters": n_cl}
        for n, v in rates.items():
            put(f"HsixNonser{mk}{nword(n)}", f2(v), "H6-per-n")
        put(f"HsixClustersObs{mk}", n_cl, "H6-per-n")
        t = next(x for x in conf["hypotheses"]["H6"]["tests"] if x["model"] == mid)
        if t["status"] == "tested" and n_cl == t["n_complete_clusters"] and None not in rates.values():
            xs = [math.log2(n) for n in A.SCALE_NS]
            yv = [rates[n] for n in A.SCALE_NS]
            xb, yb = sum(xs) / len(xs), sum(yv) / len(yv)
            slope = sum((x - xb) * (y - yb) for x, y in zip(xs, yv)) / sum((x - xb) ** 2 for x in xs)
            if abs(slope - t["estimate"]) > 1e-9:
                WARN.append(f"H6 cross-check FAILED for {mid}: slope from per-n means {slope} != analyze4 {t['estimate']}")
            else:
                REPORT.append(f"H6 cross-check ok for {mid}: slope {slope:.4f} (per-n means agree with analyze4)")
    return out


def observed_macros(rows, numbers, conf, phases, models):
    g = "observed"
    ex = numbers["exclusions"]
    for k, v in ex.items():
        put("Excl" + "".join(w.capitalize() for w in k.split("_")), v, g)
    put("ObsNAnalyzed", thou(numbers["meta"]["n_rows_analyzed"]), g)
    by_n = defaultdict(int)
    by_model_n = defaultdict(int)
    cost = defaultdict(float)
    trunc = 0
    for r in rows:
        by_n[r["n_agents"]] += 1
        by_model_n[(r["model"], r["n_agents"])] += 1
        trunc += bool(r["truncated"])
    for ph, info in phases.items():
        w = nword(ph)
        put(f"ObsPhase{w}Episodes", thou(by_n.get(info["n_agents"], 0)), g)
        for mid in models:
            got = by_model_n.get((mid, info["n_agents"]), 0)
            put(f"ObsPhase{w}{model_key(mid)}Episodes", got, g)
            if got != info["per_model"]:
                WARN.append(f"phase {ph} {mid}: {got} episodes analysed, {info['per_model']} registered")
    put("ObsTruncatedEpisodes", trunc, g)
    sens = conf["sensitivity_exclude_truncated"]["meta"]["truncated_episodes_excluded"]
    put("SensTruncatedExcluded", sens, g)
    meta = conf["registered"]["meta"]
    put("HfiveMissingTranscripts", meta.get("h5_missing_transcripts", 0), g)
    for mid in models:
        ids = meta["served_ids"].get(mid, [])
        put(f"Served{model_key(mid)}", ", ".join(tex_tt(x) for x in ids) if ids else "--", g)
        if any(x.startswith("fake/") for x in ids):
            REPORT.append(f"served ids for {mid} are fake/* (dry-run provider)")
    return cost


def cost_macros(paths, models):
    """Total cost per model from the analysed CSVs' cost_usd column (rows kept by analyze4.load)."""
    import csv
    g = "cost"
    rows, _, _ = A.load(paths)
    keep = {r["episode_id"] for r in rows}
    tot = defaultdict(float)
    for p in paths:
        with open(p, newline="") as f:
            for raw in csv.DictReader(f):
                if raw["episode_id"] in keep:
                    try:
                        tot[raw["model"]] += float(raw.get("cost_usd") or 0)
                    except ValueError:
                        pass
    for mid in models:
        put(f"Cost{model_key(mid)}USD", f2(tot.get(mid, 0.0)), g)
    put("CostTotalUSD", f2(sum(tot.values())), g)


def raw_csv_macros(paths, models):
    """EXPLORATORY episode counts that analyze4 does not aggregate (prereg "Exploratory analyses"):
    lock leaks, stalls, graph_cycle vs non_serializable agreement, control-template outcomes.
    Read directly from the CSV columns, restricted to rows analyze4.load keeps. Not confirmatory."""
    import csv
    g = "exploratory-raw-csv"
    rows, _, _ = A.load(paths)
    keep = {r["episode_id"] for r in rows}
    leak, stall, agree, ctl = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for p in paths:
        with open(p, newline="") as f:
            for raw in csv.DictReader(f):
                if raw["episode_id"] not in keep:
                    continue
                m, c, a, n = raw["model"], raw["config"], int(raw["aware_prompt"]), int(raw["n_agents"])
                if raw["category"] == "control":
                    v = ctl[(m, c, a, n)]
                    v[0] += int(raw["non_serializable"]); v[1] += 1  # noqa: E702
                    continue
                if c == "locks":
                    v = leak[(m, a, n)]
                    v[0] += int(int(raw["n_lock_leak"] or 0) > 0); v[1] += 1  # noqa: E702
                v = stall[(m, a, n)]
                v[0] += int(raw["stall"] or 0); v[1] += 1  # noqa: E702
                v = agree[m]
                v[0] += int(int(raw["graph_cycle"] or 0) == int(raw["non_serializable"])); v[1] += 1  # noqa: E702
    for (m, a, n), (k, d) in leak.items():
        b = f"RawLockLeak{model_key(m)}{AWARE[a]}{nword(n)}"
        put(b + "K", k, g); put(b + "N", d, g)  # noqa: E702
    for (m, a, n), (k, d) in stall.items():
        b = f"RawStall{model_key(m)}{AWARE[a]}{nword(n)}"
        put(b + "K", k, g); put(b + "N", d, g)  # noqa: E702
    for m, (k, d) in agree.items():
        put(f"RawGraphAgree{model_key(m)}K", k, g); put(f"RawGraphAgree{model_key(m)}N", d, g)  # noqa: E702
    for (m, c, a, n), (k, d) in ctl.items():
        b = f"RawCtlNonser{config_key(c)}{model_key(m)}{AWARE[a]}{nword(n)}"
        put(b + "K", k, g); put(b + "N", d, g)  # noqa: E702
    REPORT.append("Raw* macros (lock leak, stall, graph agreement, control non-serializable) are episode counts computed "
                  "by make_numbers4 from CSV columns, not by analyze4; EXPLORATORY.")


# ------------------------------------------------------------------ exploratory analyses (explore4.py output)
EX_NAME = "exploratory_posthoc.json"
TEMPLATE_KEYS = OrderedDict([("inventory_last_unit", "InvLast"), ("inventory_still_valid", "InvValid"), ("seat_same", "Seat"),
                             ("ticket_same", "Ticket"), ("transfer_shared_source", "Transfer"), ("budget_write_skew", "Budget"),
                             ("joint_account_write_skew", "Joint")])
E4_KEYS = OrderedDict([("reread_retry", "Reread"), ("stale_retry", "Stale"), ("version_from_error", "VerErr"), ("bypass", "Bypass"),
                       ("other_record", "Other"), ("giveup_valid", "GiveupValid"), ("giveup_invalid", "GiveupInvalid"),
                       ("cut_off", "Cutoff"), ("already_fulfilled", "Done")])
E4_SHORT = OrderedDict([("reread_retry", "re-read+retry"), ("stale_retry", "stale retry"), ("version_from_error", "version from error"),
                        ("bypass", "bypass"), ("other_record", "other record"), ("giveup_valid", "give up (valid)"),
                        ("giveup_invalid", "give up (invalid)"), ("cut_off", "cut off"), ("already_fulfilled", "done")])
H_PART = {("H4b", "i"): "HfourBI", ("H4b", "ii"): "HfourBII"}


def load_explore(analysis, prov):
    path = os.path.join(analysis, EX_NAME)
    if not os.path.exists(path):
        raise SystemExit(f"{path} missing: run explore4.py --analysis {analysis} first")
    ex = json.load(open(path))
    want = sorted((x["path"], x["sha256"]) for x in ex["inputs"])
    have = sorted((os.path.abspath(p), sha256_file(p)) for p in prov["analyzed_paths"])
    if want != have:
        raise SystemExit(f"REFUSING: {path} was computed from different inputs than {analysis}/provenance.json; rerun explore4.py")
    if bool(ex["dry_run"]) != bool(prov["dry_run"]):
        raise SystemExit("REFUSING: exploratory output and provenance disagree on dry_run")
    return ex


def put_rate(b, rec, g):
    put(b + "Est", f2(rec["est"]), g)
    put(b + "CI", fci(rec["lo"], rec["hi"]), g)
    put(b + "Num", rec["num"], g)
    put(b + "Den", rec["den"], g)


def explore_macros(ex):
    """Expl... macros (all EXPLORATORY; registered vs post hoc is stated in facts and table captions)."""
    g = "exploratory-E"
    for r in ex["E1"]["rows"]:
        sc = "" if r["scope"] == "contended" else "Sv"
        for met, key in (("fulfil", "Fulfil"), ("complete", "Complete"), ("giveup", "Giveup"), ("clean", "Clean")):
            put_rate(f"Expl{sc}{key}{config_key(r['config'])}{model_key(r['model'])}{AWARE[r['aware']]}", r[met], g)
        if not r["identity_ok"]:
            WARN.append(f"E1: n_fulfilled + n_abandoned != n_abandon_eligible in some episode ({r['model']}, {r['config']})")
    for r in ex["E3"]["rows"]:
        k = model_key(r["model"])
        put_rate(f"ExplCasCtl{k}", r["cas_ctl"], g)
        put_rate(f"ExplCasCont{k}", r["cas_cont"], g)
        u = r["cas_uncont"]
        put(f"ExplCasUncont{k}K", u["k"], g); put(f"ExplCasUncont{k}N", u["n"], g)  # noqa: E702
        put(f"ExplCasUncont{k}Rate", f2(u["rate"]), g)
    for r in ex["E4"]["rows"]:
        b = f"{config_key(r['config'])}{model_key(r['model'])}{AWARE[r['aware']]}"
        put(f"ExplPostN{b}", r["n_eligible"], g)
        for code, ck in E4_KEYS.items():
            put_rate(f"ExplPost{ck}{b}", r["codes"][code], g)
    for r in ex["E5"]["rows"]:
        b = f"{config_key(r['config'])}{model_key(r['model'])}"
        for met, key in (("promote", "Promote"), ("verify", "Verify"), ("compensate", "Compensate"), ("skew_ws", "SkewWs")):
            put_rate(f"ExplWs{key}{b}", r[met], g)
    for r in ex["E6"]["tpl"]:
        put_rate(f"ExplTpl{TEMPLATE_KEYS[r['template']]}{config_key(r['config'])}{model_key(r['model'])}", r["nonser"], g)
    for r in ex["E6"]["loto"]:
        hk = H_PART.get((r["hypothesis"], r["part"]), H_KEYS[r["hypothesis"]])
        b = f"ExplLoto{hk}{model_key(r['model'])}"
        put(b + "Full", f2(r["full"]), g)
        put(b + "Min", f2(r["min"]), g)
        put(b + "Max", f2(r["max"]), g)
        put(b + "MinTpl", tex_tt(r["min_tpl"]) if r["min_tpl"] else "--", g)
        put(b + "MaxTpl", tex_tt(r["max_tpl"]) if r["max_tpl"] else "--", g)
        if r["matches_analyze4"] is False:
            WARN.append(f"E6 cross-check FAILED: {r['hypothesis']} {r['part']} {r['model']} full estimate != analyze4")
    for r in ex["E7"]["rows"]:
        b = f"ExplLock{model_key(r['model'])}{AWARE[r['aware']]}"
        for f in ("n_lockers", "cover", "release", "leak", "stall_episodes", "episodes"):
            put(b + "".join(w.capitalize() for w in f.split("_")), r[f], g)
    for r in ex["E8"]["rows"]:
        b = f"{config_key(r['config'])}{model_key(r['model'])}"
        put_rate(f"ExplTurnCap{b}", r["turncap"], g)
        put(f"ExplCompletions{b}", f2(r["completions_per_agent"], 1), g)
    for r in ex["E8"]["trunc"]:
        k = model_key(r["model"])
        put(f"ExplTrunc{k}K", r["k"], g); put(f"ExplTrunc{k}N", r["n"], g)  # noqa: E702
    for r in ex["E10"]["rows"]:
        k = model_key(r["model"])
        put_rate(f"ExplCtlFulfil{k}", r["ctl_fulfil"], g)
        put(f"ExplInvalidPerAgent{k}", f2(r["invalid_per_agent"]), g)
    put("ExplMissingTranscripts", ex["missing_transcripts"], g)
    REPORT.append("Expl* macros come from explore4.py (exploratory_posthoc.json): EXPLORATORY, computed from saved CSVs and "
                  "transcripts only; registered vs post hoc per block is in its 'label'.")


def explore_tables(models, dry):
    mk = [model_key(m) for m in models]
    cfgs = list(CONFIG_KEYS)
    tt = lambda s: r"\texttt{%s}" % tex_text(s)  # noqa: E731
    # E1 goodput
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{ll" + "c" * len(cfgs) + "}", r"\toprule",
         "Model & metric & " + " & ".join(tt(c) for c in cfgs) + r" \\", r"\midrule"]
    for k in mk:
        for key, lab in (("Fulfil", "fulfilled (own view)"), ("StoreFulfil", "fulfilled, effect in store"),
                         ("Giveup", "unnecessary give-up"), ("Clean", "clean episode"),
                         ("SvFulfil", r"fulfilled, \texttt{inventory\_still\_valid}"), ("SvGiveup", r"give-up, \texttt{inventory\_still\_valid}")):
            pre = "" if key == "StoreFulfil" else "Expl"
            L.append((M(f"Model{k}Name") if key == "Fulfil" else "") + f" & {lab} & " +
                     " & ".join(M(f"{pre}{key}{CONFIG_KEYS[c]}{k}OffEst") for c in cfgs) + r" \\")
        L.append(r"\midrule" if k != mk[-1] else "")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{EXPLORATORY integrity vs.\ goodput (E1), contended templates, $n=\DesNTwo$, aware off; mean of task-instance "
          r"rates. Fulfilled (own view): agents that fulfilled their intent as judged from the state they acted on / agents whose "
          r"intent was still valid when they ended or that fulfilled it (post hoc); a stale write that computed the right value "
          r"from a stale read counts. Fulfilled, effect in store: the same, and no later stale write by another agent removed "
          r"the agent's last write (post hoc). Unnecessary give-up: / agents that saw a concurrency rejection (registered). Clean: episodes "
          r"serializable with no abandoned agent (post hoc). Intervals and counts are in the artifact (\texttt{numbers.tex}).}",
          r"\label{tab:goodput}", r"\end{table*}", ""]
    write_table("goodput.tex", "\n".join(L), dry)
    # E4 post-rejection
    codes = list(E4_KEYS)
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{llc" + "c" * len(codes) + "}", r"\toprule",
         "Model & config & $N$ & " + " & ".join(E4_SHORT[c] for c in codes) + r" \\", r"\midrule"]
    for k in mk:
        for c in ("cas_available", "cas_required", "locks"):
            b = f"{CONFIG_KEYS[c]}{k}Off"
            L.append((M(f"Model{k}Name") if c == "cas_available" else "") + f" & {tt(c)} & " + M(f"ExplPostN{b}") + " & " +
                     " & ".join(M(f"ExplPost{E4_KEYS[x]}{b}Est") for x in codes) + r" \\")
        L.append(r"\midrule" if k != mk[-1] else "")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{EXPLORATORY, post hoc (E4): first response after an agent's first concurrency rejection (409 "
          r"\texttt{version\_conflict} or \texttt{claim\_conflict}, 423 \texttt{locked\_by\_other}) on a record its intent writes; "
          r"contended templates, $n=\DesNTwo$, aware off. $N$: eligible agents. Shares (mean of task-instance shares) sum to one "
          r"per row. Codes are defined in \texttt{latex/explore4.py}.}", r"\label{tab:post-rejection}", r"\end{table*}", ""]
    write_table("post_rejection.tex", "\n".join(L), dry)
    # E5 write-skew preventability
    skc = [c for c in cfgs]
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{l" + "c" * len(skc) + "|ccc}", r"\toprule",
         r" & \multicolumn{%d}{c|}{\texttt{write\_skew} rate, write-skew templates} & \multicolumn{3}{c}{\texttt{cas\_available}} \\" % len(skc),
         "Model & " + " & ".join(tt(c) for c in skc) + r" & promote & verify & compensate \\", r"\midrule"]
    for k in mk:
        L.append(M(f"Model{k}Name") + " & " + " & ".join(M(f"ExplWsSkewWs{CONFIG_KEYS[c]}{k}Est") for c in skc) + " & " +
                 " & ".join(M(f"ExplWs{x}CasAvail{k}Est") for x in ("Promote", "Verify", "Compensate")) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{EXPLORATORY, post hoc (E5): write skew on the \DesNWriteSkewTemplates{} write-skew templates by config, and "
          r"agent behaviours that would prevent it with the offered tools under \texttt{cas\_available}: promote (a conditional "
          r"write to a record outside the agent's write set), verify (a read of the other records after the agent's own commit), "
          r"compensate (a later write restoring the agent's record). $n=\DesNTwo$, aware off.}", r"\label{tab:ws-prevent}",
          r"\end{table*}", ""]
    write_table("ws_prevent.tex", "\n".join(L), dry)
    # E6 leave-one-template-out
    hrows = [("H1", "Hone"), ("H2", "Htwo"), ("H3", "Hthree"), ("H4a", "HfourA"), ("H4b (i)", "HfourBI"), ("H4b (ii)", "HfourBII"), ("H6", "Hsix")]
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{l" + "c" * len(mk) + "}", r"\toprule",
         "Hypothesis & " + " & ".join(M(f"Model{k}Name") for k in mk) + r" \\", r"\midrule"]
    for lab, hk in hrows:
        L.append(f"{lab} & " + " & ".join(M(f"ExplLoto{hk}{k}Full") for k in mk) + r" \\")
        L.append(" & " + " & ".join(r"{\tiny[" + M(f"ExplLoto{hk}{k}Min") + ", " + M(f"ExplLoto{hk}{k}Max") + "]}" for k in mk) + r" \\[2pt]")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{EXPLORATORY, post hoc (E6): confirmatory point estimates (first line; equal to Table~\ref{tab:verdicts}) and "
          r"their range when each template is left out in turn (second line). Estimates only; no tests.}", r"\label{tab:loto}", r"\end{table*}", ""]
    write_table("loto.tex", "\n".join(L), dry)
    # diagnostics: E3, E7, E8, E10, truncation
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{lccc|ccc|cc|cc}", r"\toprule",
         r" & \multicolumn{3}{c|}{E3 \texttt{cas} use, \texttt{cas\_available}} & \multicolumn{3}{c|}{E7 lockers, \texttt{locks}} & "
         r"\multicolumn{2}{c|}{E8} & \multicolumn{2}{c}{E10} \\",
         r"Model & control & contended & no peer write since read & cover & release & leak & turn cap & truncated & control fulfilled & invalid / agent \\",
         r"\midrule"]
    for k in mk:
        L.append(M(f"Model{k}Name") + " & " + M(f"ExplCasCtl{k}Est") + " & " + M(f"ExplCasCont{k}Est") + " & " +
                 M(f"ExplCasUncont{k}K") + "/" + M(f"ExplCasUncont{k}N") + " & " +
                 " & ".join(M(f"ExplLock{k}Off{x}") + "/" + M(f"ExplLock{k}OffNLockers") for x in ("Cover", "Release", "Leak")) + " & " +
                 M(f"ExplTurnCapLocks{k}Est") + " & " + M(f"ExplTrunc{k}K") + "/" + M(f"ExplTrunc{k}N") + " & " +
                 M(f"ExplCtlFulfil{k}Est") + " & " + M(f"ExplInvalidPerAgent{k}") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{EXPLORATORY diagnostics, aware off, $n=\DesNTwo$. E3 (post hoc): share of agents using \texttt{cas} on the "
          r"control template vs.\ contended templates, and committed writes carrying \texttt{expected\_version} among writes with no "
          r"other agent's write since the writer's read. E7: agents with a lock that held locks on all their write records at their "
          r"first write / released every lock (post hoc) / leaked a lock (registered). E8 (counted per cell in the prereg): "
          r"agents ending at the turn cap under \texttt{locks} (all configs: Table~\ref{tab:turncap}); "
          r"episodes with a truncated agent, all phases. E10: control-template fulfilment (post hoc); invalid tool calls per agent.}",
          r"\label{tab:diagnostics}", r"\end{table*}", ""]
    write_table("diagnostics.tex", "\n".join(L), dry)


# ------------------------------------------------------------------ figure data
def figdata(numbers, h6, models, dry, ex=None):
    idx = rate_index(numbers)
    get = lambda m, c, a, n, met: idx.get((m, c, a, n, "contended", met))  # noqa: E731
    fd = {"dry_run": dry, "models": [{"id": m, "key": model_key(m), "name": model_name(m)} for m in models],
          "configs": list(CONFIG_KEYS), "a": {}, "b": {"0": {}, "1": {}}, "c": {}, "d": {}, "choices": list(A.CHOICES),
          "labels": list(A.SUB_LABELS), "scale_ns": list(A.SCALE_NS)}
    for m in models:
        fd["a"][m] = {}
        fd["d"][m] = {}
        for c in CONFIG_KEYS:
            r = get(m, c, 0, 2, "non_serializable")
            fd["a"][m][c] = None if r is None else [r["estimate"], r["ci_low"], r["ci_high"]]
            fd["d"][m][c] = {lab: (get(m, c, 0, 2, lab) or {}).get("estimate") for lab in A.SUB_LABELS}
        for a in (0, 1):
            fd["b"][str(a)][m] = {c: {ch: (get(m, c, a, 2, ch) or {}).get("estimate") for ch in A.CHOICES} for c in CONFIG_KEYS}
        fd["c"][m] = {str(n): v for n, v in h6[m]["rates"].items()}
    if ex is not None:
        e1 = {(r["model"], r["config"]): r for r in ex["E1"]["rows"] if r["scope"] == "contended" and r["aware"] == 0}
        st = {(r["model"], r["config"]): r for r in REVIEW["pr"]["store_goodput"]["rows"] if r["aware"] == 0} if REVIEW else {}
        fd["e1"] = {m: {c: ({"fulfil": e1[(m, c)]["fulfil"]["est"], "giveup": e1[(m, c)]["giveup"]["est"],
                             "store_fulfil": (st.get((m, c)) or {}).get("store_fulfil", {}).get("est")} if (m, c) in e1 else None)
                        for c in CONFIG_KEYS} for m in models}
        fd["templates"] = list(TEMPLATE_KEYS)
        fd["tpl"] = {m: {t: {c: None for c in CONFIG_KEYS} for t in TEMPLATE_KEYS} for m in models}
        for r in ex["E6"]["tpl"]:
            if r["model"] in fd["tpl"]:
                fd["tpl"][r["model"]][r["template"]][r["config"]] = r["nonser"]["est"]
    return fd


# ------------------------------------------------------------------ tables
def M(name):
    """Reference to a macro (must exist in NUMS)."""
    if name not in NUMS:
        WARN.append(f"table references undefined macro \\{name}")
        return r"\PENDING{%s}" % name
    return "\\" + name


def write_table(name, body, dry):
    os.makedirs(TABLES, exist_ok=True)
    head = (f"% GENERATED by make_numbers4.py -- do not edit. Input: {'DRY RUN (fake model)' if dry else 'real data'}.\n"
            "% Every value is a numbers.tex macro.\n")
    width = r"\textwidth" if r"\begin{table*}" in body else r"\columnwidth"
    body = re.sub(r"(\\begin\{tabular\})", lambda m: r"\begin{adjustbox}{max width=%s}" % width + "\n" + m.group(1), body)
    body = body.replace(r"\end{tabular}", r"\end{tabular}" + "\n" + r"\end{adjustbox}")
    with open(os.path.join(TABLES, name), "w") as f:
        f.write(head + body)


def tables(models, dry):
    mk = [model_key(m) for m in models]
    cfgs = list(CONFIG_KEYS)
    tt = lambda s: r"\texttt{%s}" % tex_text(s)  # noqa: E731
    # 1. main results
    L = [r"\begin{table*}[t]", r"\centering\small\DryTag\par", r"\begin{tabular}{l" + "c" * len(cfgs) + "}", r"\toprule",
         "Model & " + " & ".join(tt(c) for c in cfgs) + r" \\", r"\midrule"]
    for k in mk:
        L.append(M(f"Model{k}Name") + " & " + " & ".join(M(f"XNonser{CONFIG_KEYS[c]}{k}OffTwoEst") for c in cfgs) + r" \\")
        L.append(" & " + " & ".join(r"{\scriptsize " + M(f"XNonser{CONFIG_KEYS[c]}{k}OffTwoCI") + "}" for c in cfgs) + r" \\[2pt]")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Non-serializable episode rate by model and coordination config (contended templates, $n=\DesNTwo$ agents, "
          r"aware prompt off). Mean of task-instance rates with \DesCILevel\% Wilson interval over instances (EXPLORATORY descriptive; "
          r"confirmatory tests in Table~\ref{tab:verdicts}).}", r"\label{tab:main-results}", r"\end{table*}", ""]
    write_table("main_results.tex", "\n".join(L), dry)

    # 2. coordination choice (offered option per config)
    offered = [("reread_only", "reread"), ("cas_available", "cas"), ("cas_required", "cas"), ("locks", "lock"), ("messages", "message")]
    hdr = " & ".join(r"\shortstack{%s\\{\scriptsize %s}}" % (tt(ch), tt(c)) for c, ch in offered)
    L = [r"\begin{table*}[t]", r"\centering\small\DryTag\par", r"\begin{tabular}{l" + "c" * len(offered) + "|" + "c" * len(offered) + "}",
         r"\toprule", r" & \multicolumn{%d}{c|}{aware off} & \multicolumn{%d}{c}{aware on} \\" % (len(offered), len(offered)),
         "Model & " + hdr + " & " + hdr + r" \\", r"\midrule"]
    for k in mk:
        cells = [M(f"X{METRIC_KEYS[ch]}{CONFIG_KEYS[c]}{k}{aw}TwoEst") for aw in ("Off", "On") for c, ch in offered]
        L.append(M(f"Model{k}Name") + " & " + " & ".join(cells) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Share of agents that made the coordination choice each config offers (column: choice, config), "
          r"contended templates, $n=\DesNTwo$. Choices are counted from successful calls only and overlap. EXPLORATORY "
          r"descriptive; the registered lock and prompt tests are H2 and H3.}", r"\label{tab:coordination}", r"\end{table*}", ""]
    write_table("coordination.tex", "\n".join(L), dry)

    # 3. verdicts: per-model estimate [95% CI], bold if rejected after Holm; H5 k/N row. p-values: Table conf-full.
    rows_v = [("H1", "Hone", "Est", "CI"), ("H2", "Htwo", "Est", "CI"), ("H3", "Hthree", "Est", "CI"),
              ("H4a", "HfourA", "Est", "CI"), ("H4b (i)", "HfourB", "EstI", "CII"), ("H4b (ii)", "HfourB", "EstII", "CIII"),
              ("H6", "Hsix", "Est", "CI")]
    L = [r"\begin{table*}[t]", r"\centering\small\DryTag\par", r"\begin{tabular}{l" + "c" * len(mk) + "cc}", r"\toprule",
         "Hypothesis & " + " & ".join(M(f"Model{k}Name") for k in mk) + r" & rejected & exact bound$^\dagger$ \\", r"\midrule"]
    for lab, hk, est, ci in rows_v:
        ek = {"H4b (i)": "HfourBI", "H4b (ii)": "HfourBII"}.get(lab, hk)
        rej = "" if lab == "H4b (ii)" else M(f"{hk}NReject") + "/" + M(f"{hk}FamilySize")
        L.append(f"{lab} & " + " & ".join(r"\VerdictCell{%s}{%s}" % (M(f"{hk}{k}Reject"), M(f"{hk}{k}{est}")) for k in mk)
                 + f" & {rej} & " + r"{\scriptsize " + M(f"Exact{ek}Col") + r"} \\")
        L.append(" & " + " & ".join(r"\VerdictCell{%s}{{\scriptsize %s%s}}" % (M(f"{hk}{k}Reject"), M(f"{hk}{k}{ci}"),
                                                                                M(f"Exact{ek}{k}Mark")) for k in mk)
                 + r" & & \\[2pt]")
    L.append(r"\midrule")
    L.append("H5 (descr.) & " + " & ".join(M(f"Hfive{k}K") + "/" + M(f"Hfive{k}N") for k in mk) +
             r" & " + M("HfiveNModelsWithOne") + r" $\geq$1 & \\")
    nt_note = ("; n/t = not tested" if any(NUMS.get(f"{hk}{k}Reject") == "n/t" for _, hk, _, _ in rows_v for k in mk) else "")
    L.append("H5 audited & " + " & ".join(M(f"HfiveAudit{k}Confirmed") for k in mk) +
             r" & " + M("HfiveAuditNModelsConfirmed") + r" $\geq$1 & \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Confirmatory tests. Cells: estimate of the registered statistic and \DesCILevel\% percentile cluster-bootstrap "
          r"interval; bold = rejected after Holm across tested models ($\alpha=\DesAlpha$)" + nt_note + r". Statistics: H1 "
          r"non-serializable rate under \texttt{none} (H$_0$: $\leq$\DesHoneThreshold); H2 lock rate under \texttt{locks} "
          r"(H$_0$: $\geq$\DesHtwoThreshold); H3 offered-option rate, aware on minus off; H4a \texttt{stale\_overwrite} rate, "
          r"\texttt{none} minus \texttt{cas\_available}; H4b (i) \texttt{write\_skew} rate under \texttt{cas\_available} "
          r"(H$_0$: $\leq$\DesHoneThreshold), (ii) its drop from \texttt{none} (H$_0$: $\geq$\DesHfourBMargin); H6 slope on "
          r"$\log_2 n$. Rejected: models rejecting / tested. H5 rows: partial / eligible agents (descriptive, before the transcript "
          r"audit) and agents the transcript audit confirmed (Supplement Table~\ref{tab:h5-audit}). $^\dagger$All cluster values equal: "
          r"zero-width interval by construction, decision by exact sign test; last column (post hoc): exact one-sided 95\% "
          r"Clopper--Pearson lower bound on the share of clusters at that value ($k$ of $k$), treating clusters as independent "
          r"although they come from \DesNContendedTemplates{} templates. $p$-values: Supplement Table~\ref{tab:conf-full}.}",
          r"\label{tab:verdicts}", r"\end{table*}", ""]
    write_table("verdicts.tex", "\n".join(L), dry)

    # 4. confirmatory full
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{llcccccccc}", r"\toprule",
         r"H & Model & clusters & estimate & \DesCILevel\% CI & $p$ & method & $p_{\mathrm{Holm}}$ & $p_{\mathrm{sign}}$ & "
         r"$p_{\mathrm{sign,Holm}}$ \\", r"\midrule"]
    for h, hk in H_KEYS.items():
        for k in mk:
            b = f"{hk}{k}"
            cl = M(f"{b}Clusters") + "/" + M(f"{b}RegClusters")
            if h == "H4b":
                est = "(i) " + M(f"{b}EstI") + r"; (ii) " + M(f"{b}EstII")
                ci = "(i) " + M(f"{b}CII") + r"; (ii) " + M(f"{b}CIII")
                p = "(i) " + M(f"{b}PI") + r"; (ii) " + M(f"{b}PII")
                meth = M(f"{b}MethodI") + "; " + M(f"{b}MethodII")
            else:
                est, ci, p, meth = M(f"{b}Est"), M(f"{b}CI"), M(f"{b}P"), M(f"{b}Method")
            L.append(f"{h} & " + M(f"Model{k}Name") + f" & {cl} & {est} & {ci} & {p} & {meth} & " + M(f"{b}PHolm") + " & "
                     + M(f"RevSign{hk}{k}P") + " & " + M(f"RevSign{hk}{k}PHolm") + r" \\")
        L.append(r"\midrule" if h != "H6" else "")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Confirmatory tests in full: complete/registered clusters, estimate (mean of cluster values), \DesCILevel\% percentile "
          r"bootstrap interval, one-sided $p$ (bootstrap, or exact sign test when degenerate), Holm-adjusted $p$, and the "
          r"registered exact one-sided sign test on the cluster values ($p_{\mathrm{sign}}$, ties dropped), which the registration "
          r"requires for every test, with its Holm adjustment across models (post hoc). H4b: "
          r"(i) write-skew rate under \texttt{cas\_available} vs.\ \DesHoneThreshold; (ii) drop from \texttt{none} vs.\ margin "
          r"\DesHfourBMargin; per-model $p=\max(p_i,p_{ii})$, likewise for the sign test.}", r"\label{tab:conf-full}", r"\end{table*}", ""]
    write_table("confirmatory_full.tex", "\n".join(L), dry)

    # 5. sensitivity
    L = [r"\begin{table}[t]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{l" + "c" * len(mk) + "}", r"\toprule",
         "H & " + " & ".join(M(f"Model{k}Name") for k in mk) + r" \\", r"\midrule"]
    for h, hk in H_KEYS.items():
        L.append(f"{h} & " + " & ".join(r"\VerdictCell{%s}{%s}" % (M(f"Sens{hk}{k}Reject"), M(f"Sens{hk}{k}PHolm")) for k in mk) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Sensitivity: confirmatory tests with episodes that had a truncated agent treated as missing "
          r"(\SensTruncatedExcluded{} episodes excluded). Cells as in Table~\ref{tab:verdicts}.}", r"\label{tab:sensitivity}",
          r"\end{table}", ""]
    write_table("sensitivity.tex", "\n".join(L), dry)

    # 6. H5
    L = [r"\begin{table}[t]", r"\centering\small\DryTag\par", r"\begin{tabular}{lcc}", r"\toprule",
         r"Model & partial / eligible & rate [\DesCILevel\% Wilson] \\", r"\midrule"]
    for k in mk:
        L.append(M(f"Model{k}Name") + " & " + M(f"Hfive{k}K") + "/" + M(f"Hfive{k}N") + " & " + M(f"Hfive{k}Rate") + " " + M(f"Hfive{k}CI") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{H5 (pre-specified descriptive): agents in \texttt{transfer\_shared\_source} with a concurrency-rejected "
          r"write on a record their intent writes that committed an action, ended and did not fulfil the intent. Counts before "
          r"the transcript audit, which an AI agent performed (Table~\ref{tab:h5-audit}).}", r"\label{tab:h5}", r"\end{table}", ""]
    write_table("h5.tex", "\n".join(L), dry)

    # 7. full rates n=2 (aware off / on)
    mets = ["non_serializable", "stale_overwrite", "partial_action", "write_skew", "invariant_violation", "unnecessary_give_up", "abandoned"]
    for aw in ("Off", "On"):
        L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{ll" + "c" * len(mets) + "}", r"\toprule",
             "Model & config & " + " & ".join(tt(m) for m in mets) + r" \\", r"\midrule"]
        for k in mk:
            for c in cfgs:
                L.append(M(f"Model{k}Name") + " & " + tt(c) + " & " +
                         " & ".join(M(f"X{METRIC_KEYS[m]}{CONFIG_KEYS[c]}{k}{aw}TwoEst") for m in mets) + r" \\")
            L.append(r"\midrule" if k != mk[-1] else "")
        L += [r"\bottomrule", r"\end{tabular}",
              r"\caption{All integrity and give-up rates, contended templates, $n=\DesNTwo$, aware prompt %s (EXPLORATORY; mean of "
              r"task-instance rates). Intervals and counts are in \texttt{numbers.tex}.}" % aw.lower(),
              r"\label{tab:rates-n2-%s}" % aw.lower(), r"\end{table*}", ""]
        write_table(f"rates_full_n2_{aw.lower()}.tex", "\n".join(L), dry)

    # 8. full choices n=2
    chs = list(A.CHOICES)
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{ll" + "c" * len(chs) + "|" + "c" * len(chs) + "}",
         r"\toprule", r" & & \multicolumn{%d}{c|}{aware off} & \multicolumn{%d}{c}{aware on} \\" % (len(chs), len(chs)),
         "Model & config & " + " & ".join(tt(c) for c in chs) + " & " + " & ".join(tt(c) for c in chs) + r" \\", r"\midrule"]
    for k in mk:
        for c in cfgs:
            L.append(M(f"Model{k}Name") + " & " + tt(c) + " & " + " & ".join(
                M(f"X{METRIC_KEYS[ch]}{CONFIG_KEYS[c]}{k}{aw}TwoEst") for aw in ("Off", "On") for ch in chs) + r" \\")
        L.append(r"\midrule" if k != mk[-1] else "")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{All coordination choices (share of agents; choices overlap), contended templates, $n=\DesNTwo$ (EXPLORATORY).}",
          r"\label{tab:choices-full}", r"\end{table*}", ""]
    write_table("choices_full_n2.tex", "\n".join(L), dry)

    # 9. scaling full (n = 4, 8)
    mets2 = ["non_serializable", "stale_overwrite", "partial_action", "write_skew", "cas", "lock"]
    scale_cfgs = [c for c in cfgs if c in ("none", "cas_available", "locks")]
    for n in [x for x in A.SCALE_NS if x != 2]:
        L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{lll" + "c" * len(mets2) + "}", r"\toprule",
             "Model & config & aware & " + " & ".join(tt(m) for m in mets2) + r" \\", r"\midrule"]
        for k in mk:
            for c in scale_cfgs:
                for aw in ("Off", "On"):
                    L.append(M(f"Model{k}Name") + " & " + tt(c) + f" & {aw.lower()} & " + " & ".join(
                        M(f"X{METRIC_KEYS[m]}{CONFIG_KEYS[c]}{k}{aw}{nword(n)}Est") for m in mets2) + r" \\")
            L.append(r"\midrule" if k != mk[-1] else "")
        L += [r"\bottomrule", r"\end{tabular}",
              r"\caption{Rates at $n=\DesN%s$ agents, contended templates (EXPLORATORY; H6 uses only \texttt{cas\_available}, aware off).}" % nword(n),
              r"\label{tab:scale-%d}" % n, r"\end{table*}", ""]
        write_table(f"scaling_n{n}.tex", "\n".join(L), dry)

    # 10. exclusions / episodes / cost
    L = [r"\begin{table}[t]", r"\centering\small\DryTag\par", r"\begin{tabular}{lc}", r"\toprule", r"Item & count \\", r"\midrule"]
    for k in [x for x in NUMS if x.startswith("Excl")]:
        L.append(tex_text(re.sub(r"([A-Z])", r" \1", k[4:]).strip().lower()) + " & " + M(k) + r" \\")
    L.append(r"episodes analysed & " + M("ObsNAnalyzed") + r" \\")
    L.append(r"episodes with a truncated agent & " + M("ObsTruncatedEpisodes") + r" \\")
    L.append(r"H5 transcripts missing & " + M("HfiveMissingTranscripts") + r" \\")
    L += [r"\midrule", r"\multicolumn{2}{l}{API cost (USD)} \\"]
    for k in mk:
        L.append(M(f"Model{k}Name") + " & " + M(f"Cost{k}USD") + r" \\")
    L.append(r"total & " + M("CostTotalUSD") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\caption{Rows read, exclusions (analyze4), and API cost per model.}",
          r"\label{tab:exclusions}", r"\end{table}", ""]
    write_table("exclusions.tex", "\n".join(L), dry)

    # 11. served ids
    L = [r"\begin{table}[t]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{p{0.34\columnwidth}p{0.36\columnwidth}p{0.2\columnwidth}}", r"\toprule",
         r"Requested id & Served id(s) & first / last episode (UTC) \\", r"\midrule"]
    for k in mk:
        L.append(M(f"Model{k}Id") + " & " + M(f"Served{k}") + " & " + M(f"RunFirst{k}") + r" / " + M(f"RunLast{k}") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\caption{Requested and served model ids (\texttt{model\_served}) and the "
          r"start dates of each model's first and last analysed episode. The \ModelGeminiName{} batch requests named the "
          r"undated Google model code \texttt{gemini-4-argon}; the registered dated OpenRouter id was never requested for "
          r"confirmatory episodes.}",
          r"\label{tab:served}", r"\end{table}", ""]
    write_table("served_ids.tex", "\n".join(L), dry)


RB_NAME = "rollback_sensitivity.json"


def rollback_audit_macros(analysis, models, dry):
    """POST HOC rollback sensitivity (rollback_sensitivity.py) and the H5 transcript audit (audit/H5_AUDIT.csv).

    \\Rb...: registered vs rescored estimates when rollback-only partial_action episodes count as serializable
    (not pre-registered, not confirmatory). \\HfiveAudit...: the pre-specified H5 transcript audit (performed by an
    AI agent that had not built the harness; audit/H5_AUDIT.md); counts are read from the audit CSV via rollback_sensitivity.py. Both are "--" when
    the file is missing or the inputs are a dry run. Writes tables/rollback_sensitivity.tex and tables/h5_audit.tex.
    """
    g = "posthoc-rollback-sensitivity"
    path = os.path.join(analysis, RB_NAME)
    rb = json.load(open(path)) if os.path.exists(path) else None
    if rb is not None:
        prov = json.load(open(os.path.join(analysis, "provenance.json")))
        have = sorted((os.path.abspath(p), sha256_file(p)) for p in prov["analyzed_paths"])
        if sorted((x["path"], x["sha256"]) for x in rb.get("inputs", [])) != have:
            raise SystemExit(f"REFUSING: {path} was computed from different inputs; rerun rollback_sensitivity.py")
    else:
        WARN.append(f"{path} missing: rollback sensitivity macros set to --")
    dash = "--"
    tests = lambda which, h: {t["model"]: t for t in rb[which][h]["tests"]} if rb else {}  # noqa: E731
    for h, key in (("H1", "Hone"), ("H6", "Hsix")):
        reg, res = tests("registered", h), tests("rescored", h)
        put(f"Rb{key}Verdict", res and rb["rescored"][h]["verdict"] or dash, g)
        for mid in models:
            k = model_key(mid)
            r = res.get(mid)
            put(f"Rb{key}{k}Est", f2(r["estimate"]) if r else dash, g)
            put(f"Rb{key}{k}CI", fci(r["ci_low"], r["ci_high"]) if r else dash, g)
            put(f"Rb{key}{k}PHolm", fp(r["p_holm"]) if r else dash, g)
            put(f"Rb{key}{k}Reject", ("yes" if r["reject"] else "no") if r else dash, g)
    res = tests("rescored", "H4b")
    put("RbHfourBVerdict", res and rb["rescored"]["H4b"]["verdict"] or dash, g)
    for mid in models:
        k = model_key(mid)
        r = res.get(mid)
        put(f"RbHfourB{k}EstI", f2(r["component_i"]["estimate"]) if r else dash, g)
        put(f"RbHfourB{k}EstII", f2(r["component_ii"]["estimate"]) if r else dash, g)
        c = (rb or {}).get("contended_partial_action_by_model", {}).get(mid, {})
        put(f"RbPartial{k}N", c.get("partial_action", 0) if rb else dash, g)
        put(f"RbPartial{k}K", c.get("rollback_only", 0) if rb else dash, g)
    tot = (rb or {}).get("contended_partial_action_by_model", {})
    put("RbPartialTotalN", sum(c.get("partial_action", 0) for c in tot.values()) if rb else dash, g)
    put("RbPartialTotalK", sum(c.get("rollback_only", 0) for c in tot.values()) if rb else dash, g)
    put("RbNRelabelled", rb["n_relabelled"] if rb else dash, g)
    if rb:
        REPORT.append("Rb* macros: POST HOC rollback sensitivity (rollback_sensitivity.py); not pre-registered, not confirmatory")

    # H5 transcript audit (pre-specified; performed by an AI agent, audit/H5_AUDIT.md). Not shown for dry runs.
    ga = "h5-audit"
    au = None if (dry or not rb) else rb.get("h5_audit")
    fields = (("Numerator", "numerator"), ("Confirmed", "confirmed"), ("Returned", "confirmed_returned"),
              ("TurnCap", "confirmed_turn_cap"), ("Rollback", "rollback"), ("OtherNot", "other_not_confirmed"),
              ("SameTurn", "same_turn"))
    n_conf = n_ret = 0
    for mid in models:
        k = model_key(mid)
        c = (au or {}).get("per_model", {}).get(mid, {})
        for name, fld in fields:
            put(f"HfiveAudit{k}{name}", c.get(fld, 0) if au else dash, ga)
        n_conf += c.get("confirmed", 0) > 0
        n_ret += c.get("confirmed_returned", 0) > 0
        if au and str(c.get("numerator", 0)) != str(NUMS.get(f"Hfive{k}K")):
            WARN.append(f"H5 audit numerator for {mid} ({c.get('numerator', 0)}) != analyze4 count ({NUMS.get(f'Hfive{k}K')})")
    put("HfiveAuditNModelsConfirmed", n_conf if au else dash, ga)
    put("HfiveAuditNModelsReturned", n_ret if au else dash, ga)
    put("HfiveAuditTotalConfirmed", sum(c.get("confirmed", 0) for c in au["per_model"].values()) if au else dash, ga)
    put("HfiveAuditTotalRollback", sum(c.get("rollback", 0) for c in au["per_model"].values()) if au else dash, ga)
    put("HfiveAuditTotalSameTurn", sum(c.get("same_turn", 0) for c in au["per_model"].values()) if au else dash, ga)
    put("HfiveAuditTotalNumerator", sum(c.get("numerator", 0) for c in au["per_model"].values()) if au else dash, ga)
    put("HfiveAuditOutcomeMet", ("yes" if n_conf >= 3 else "no") if au else dash, ga)
    ll = (rb or {}).get("h5_locks_lease") if not dry else None
    put("HfiveAuditLockCases", ll["cases"] if ll else dash, ga)
    put("HfiveAuditLockLeaseExpired", ll["own_lease_expired"] if ll else dash, ga)

    # tables
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{lcccccc}", r"\toprule",
         r"Model & \texttt{partial\_action} & rollback-only & H1 registered & H1 rescored & H6 registered & H6 rescored \\",
         r"\midrule"]
    for mid in models:
        k = model_key(mid)
        L.append(M(f"Model{k}Name") + " & " + M(f"RbPartial{k}N") + " & " + M(f"RbPartial{k}K") + " & " + M(f"Hone{k}Rate")
                 + " & " + M(f"RbHone{k}Est") + " " + M(f"RbHone{k}CI") + " & " + M(f"Hsix{k}Est") + " & "
                 + M(f"RbHsix{k}Est") + " " + M(f"RbHsix{k}CI") + r" \\")
    L += [r"\midrule", r"all & " + M("RbPartialTotalN") + " & " + M("RbPartialTotalK") + r" & & & & \\",
          r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC sensitivity, not pre-registered and not confirmatory. Contended \texttt{partial\_action} episodes, "
          r"those that are rollback-only (no invariant violation, a committed agent whose writes net to zero, and a final store "
          r"that a serial execution of the other agents reproduces), and the H1 rate and H6 slope with these episodes "
          r"counted as serializable (95\% bootstrap interval). H4a and H4b cannot change by construction.}",
          r"\label{tab:rollback}", r"\end{table*}", ""]
    write_table("rollback_sensitivity.tex", "\n".join(L), dry)

    L = [r"\begin{table}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{lcccccc}", r"\toprule",
         r"Model & counted & confirmed & returned & turn cap & rolled back & both legs, one reply$^{*}$ \\", r"\midrule"]
    for mid in models:
        k = model_key(mid)
        L.append(M(f"Model{k}Name") + " & " + M(f"Hfive{k}K") + "/" + M(f"Hfive{k}N") + " & " + M(f"HfiveAudit{k}Confirmed")
                 + " & " + M(f"HfiveAudit{k}Returned") + " & " + M(f"HfiveAudit{k}TurnCap") + " & " + M(f"HfiveAudit{k}Rollback")
                 + " & " + M(f"SameReply{k}AllK") + "/" + M(f"SameReply{k}AllN") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{H5 transcript audit (pre-specified). Counted: the automated count over eligible agents. Confirmed: the transcript "
          r"shows a half-done transfer at the end, split into agents that returned on their own and agents stopped by the turn cap. "
          r"Rolled back: counted agents that restored the credited record, so the final store holds no half-done transfer. "
          r"An AI agent performed the audit from the transcripts (\texttt{audit/H5\_AUDIT.md}). $^{*}$POST HOC: agents in "
          r"\texttt{transfer\_shared\_source} ($n=\DesNTwo$, every config, both aware levels) that wrote at all, and among them "
          r"those whose model sent the debit and the credit in one reply.}",
          r"\label{tab:h5-audit}", r"\end{table}", ""]
    write_table("h5_audit.tex", "\n".join(L), dry)


# ------------------------------------------------------------------ post hoc review analyses (posthoc_review.py, reference_policies.py)
PR_NAME = "posthoc_review.json"
RP_NAME = "reference_policies.json"
POLICY_KEYS = OrderedDict([("naive", "Naive"), ("rereader", "Rereader"), ("careful_cas", "CarefulCas"),
                           ("give_up_on_conflict", "GiveUp"), ("lock_user", "LockUser"), ("lock_leaker", "LockLeaker"),
                           ("messenger", "Messenger")])
POLICY_SHORT = {"naive": "naive writer", "rereader": "re-reader", "careful_cas": "conditional writer",
                "give_up_on_conflict": "conditional writer, gives up", "lock_user": "lock user", "lock_leaker": "lock leaker",
                "messenger": "messenger"}
SCOPE_KEYS = {"all": "", "single_record": "Single", "transfer": "Tr", "write_skew": "Ws"}
TB_PARTS = [("H1", "v", "Hone"), ("H2", "v", "Htwo"), ("H3", "v", "Hthree"), ("H4a", "v", "HfourA"), ("H4b", "i", "HfourBI"),
            ("H4b", "ii", "HfourBII"), ("H6", "v", "Hsix")]
SQL_TEMPLATE_KEYS = {"counter": "Counter", "handle": "Handle", "withdraw": "Withdraw", "order": "Order"}
NUM_EN = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
REVIEW = {}


def review_macros(analysis, models, dry):
    """POST HOC analyses added after the 2026-11-02 reviews (all from saved data or scripted agents; no model calls)."""
    g = "posthoc-review"
    pr_path, rp_path = os.path.join(analysis, PR_NAME), os.path.join(analysis, RP_NAME)
    for p, script in ((pr_path, "posthoc_review.py"), (rp_path, "reference_policies.py")):
        if not os.path.exists(p):
            raise SystemExit(f"{p} missing: run {script} --analysis {analysis} first")
    pr, rp = json.load(open(pr_path)), json.load(open(rp_path))
    prov = json.load(open(os.path.join(analysis, "provenance.json")))
    have = sorted((os.path.abspath(p), sha256_file(p)) for p in prov["analyzed_paths"])
    if sorted((x["path"], x["sha256"]) for x in pr["inputs"]) != have or bool(pr["dry_run"]) != bool(prov["dry_run"]):
        raise SystemExit(f"REFUSING: {pr_path} was computed from different inputs; rerun posthoc_review.py")
    REVIEW.update(pr=pr, rp=rp)
    # reference policies
    for r in rp["rows"]:
        b = f"Ref{POLICY_KEYS[r['policy']]}{config_key(r['config'])}{SCOPE_KEYS[r['scope']]}"
        put(b + "N", r["episodes"], g)
        for f, k in (("non_serializable", "Nonser"), ("stale_overwrite", "Stale"), ("partial_action", "Partial"),
                     ("write_skew", "Skew"), ("fulfilled", "Fulfil"), ("agents", "Agents")):
            put(b + k, r[f], g)
    put("RefNEpisodes", thou(sum(r["episodes"] for r in rp["rows"] if r["scope"] == "all")), g)
    put("RefNPolicies", len(rp["policies"]), g)
    none_rows = [r for r in rp["rows"] if r["config"] == "none" and r["scope"] == "all"]
    put("RefNoneNPolicies", len(none_rows), g)
    put("RefNoneMinNonser", min(r["non_serializable"] for r in none_rows), g)
    put("RefNoneN", none_rows[0]["episodes"], g)
    # template-level bootstrap
    tb = pr["template_boot"]["hypotheses"]
    for h, part, hk in TB_PARTS:
        rec = tb[h]
        put(f"Tpl{hk}NTemplates", rec["tests"][0]["n_templates"], g)
        put(f"TplMinP{hk}", fp(0.5 ** rec["tests"][0]["n_templates"]), g)
        for t in rec["tests"]:
            k = model_key(t["model"])
            c = t["parts"][part]
            put(f"Tpl{hk}{k}Est", f2(c["estimate"]), g)
            put(f"Tpl{hk}{k}P", fp(c["p"]), g)
            put(f"Tpl{hk}{k}Method", c["method"].replace("_", " "), g)
            put(f"Tpl{hk}{k}ICC", f2(c["icc"]) if c["icc"] is not None else "--", g)
            put(f"Tpl{hk}{k}NOff", c["n_templates_off_null"], g)
            if not c["equals_registered_estimate"]:
                WARN.append(f"template bootstrap {h}/{part} {t['model']}: estimate differs from the registered one")
    for h, rec in tb.items():
        hk = H_KEYS[h]
        put(f"Tpl{hk}NReject", rec["n_reject"], g)
        put(f"Tpl{hk}NRejectReg", rec["n_reject_registered"], g)
        put(f"Tpl{hk}Lost", ", ".join(tex_text(model_name(m)) for m in rec["lost"]) or "none", g)
        for t in rec["tests"]:
            k = model_key(t["model"])
            put(f"Tpl{hk}{k}PHolm", fp(t["p_holm"]), g)
            put(f"Tpl{hk}{k}Reject", "yes" if t["reject"] else "no", g)
            if h == "H3":
                for tpl, v in t["parts"]["v"]["template_means"].items():
                    put(f"TplHthree{k}{TEMPLATE_KEYS[tpl]}", f2(v), g)
            if h == "H6":
                put(f"TplHsixVarying{k}", t["h6_clusters_varying_with_n"], g)
    put("TplHsixNModelsNoChange", sum(t["h6_clusters_varying_with_n"] == 0 for t in tb["H6"]["tests"]), g)
    # exact bounds for degenerate cells
    ex = defaultdict(dict)
    for r in pr["exact_bounds"]["rows"]:
        hk = H_PART.get((r["hypothesis"], r["part"]), H_KEYS[r["hypothesis"]])
        ex[hk][model_key(r["model"])] = r
    for hk in [x[2] for x in TB_PARTS]:
        ks = set()
        for mid in models:
            k = model_key(mid)
            r = ex[hk].get(k)
            put(f"Exact{hk}{k}Mark", r"$^\dagger$" if r else "", g)
            if r:
                put(f"Exact{hk}{k}Bound", ffloor(r["bound"]), g)
                ks.add((r["k"], ffloor(r["bound"])))
        put(f"Exact{hk}Col", "; ".join(r"$\geq$%s (%d/%d)" % (b, k, k) for k, b in sorted(ks)) if ks else "--", g)
    # control-template choice use
    for r in pr["control_use"]["rows"]:
        k, aw = model_key(r["model"]), AWARE[r["aware"]]
        for f, key in (("lock_ctl", "LockCtl"), ("lock_cont", "LockCont"), ("msg_ctl", "MsgCtl"), ("msg_cont", "MsgCont"),
                       ("cas_ctl", "CasCtl"), ("cas_cont", "CasCont"), ("cas_cont_update", "CasContUpd")):
            put_rate(f"Use{key}{k}{aw}", r[f], g)
    # store-based goodput
    for r in pr["store_goodput"]["rows"]:
        b = f"{config_key(r['config'])}{model_key(r['model'])}{AWARE[r['aware']]}"
        put_rate(f"StoreFulfil{b}", r["store_fulfil"], g)
        put(f"StoreLost{b}", r["fulfilled_but_lost"], g)
    # lock-lease split
    for r in pr["lease_split"]["rows"]:
        b = f"Lease{model_key(r['model'])}{AWARE[r['aware']]}"
        for f in ("lockers", "expired", "held", "other", "no_lock"):
            put(b + "".join(w.capitalize() for w in f.split("_")), r["agents"].get(f, 0), g)
        for grp, key in (("expired", "Exp"), ("not_expired", "NotExp")):
            e = r["episodes"].get(grp, {"non_serializable": 0, "n": 0})
            put(f"{b}{key}Nonser", e["non_serializable"], g)
            put(f"{b}{key}N", e["n"], g)
        put(b + "Median", r["lease_steps"]["median"] if r["lease_steps"]["median"] is not None else "--", g)
    # same-reply legs
    for r in pr["same_reply"]["rows"]:
        b = f"SameReply{model_key(r['model'])}{'All' if r['scope'] == 'all' else 'Hfive'}"
        put(b + "K", r["k"], g)
        put(b + "N", r["n"], g)
        put(b + "Rate", f2(r["k"] / r["n"]) if r["n"] else "--", g)
    # serving facts
    sv = pr["serving"]
    put("QwenNHosts", len(sv["qwen_hosts_episodes"]), g)
    put("QwenMixedEpisodes", sv["qwen_mixed_host_episodes"], g)
    put("QwenEpisodes", sv["qwen_episodes"], g)
    hosts = dict.fromkeys(("Alibaba", "Chutes", "DeepInfra", "Phala", "Reka", "SiliconFlow", "Venice"), 0)
    hosts.update(sv["qwen_hosts_episodes"])  # known hosts default to 0 (e.g. dry runs), others are added
    for h, n in hosts.items():
        put(f"QwenHost{''.join(ch for ch in h.title() if ch.isalpha())}Episodes", n, g)
    for mid in models:
        d = sv["run_dates"].get(mid)
        put(f"RunFirst{model_key(mid)}", d["first"][:10] if d else "--", g)
        put(f"RunLast{model_key(mid)}", d["last"][:10] if d else "--", g)
    # SQL slice design counts (exploratory; recomputed from results_sql/results.csv)
    sq = pr["sql"]
    gs = "exploratory-sql"
    if sq:
        put("SqlNEpisodes", sq["n_episodes"], gs)
        put("SqlNAgents", sq["n_agents"], gs)
        put("SqlNModels", NUM_EN.get(len(sq["models"]), len(sq["models"])), gs)
        put("SqlNTemplates", NUM_EN.get(len(sq["templates"]), len(sq["templates"])), gs)
        put("SqlNVariants", NUM_EN.get(len(sq["variants"]), len(sq["variants"])), gs)
        put("SqlNReps", NUM_EN.get(len(sq["reps"]), len(sq["reps"])), gs)
        put("SqlNPerCell", len(sq["variants"]) * len(sq["reps"]), gs)
        put("SqlNs", ", ".join(str(n) for n in sq["ns"]), gs)
        put("SqlCostUSD", f2(sq["cost_usd"]), gs)
        for c in sq["cells"]:
            b = f"SqlViol{model_key(c['model'])}{SQL_TEMPLATE_KEYS[c['template']]}{nword(c['n'])}"
            put(b + "K", c["violations"], gs)
            put(b + "N", c["episodes"], gs)
    else:
        WARN.append("SQL slice results.csv missing: Sql* macros undefined")
    REPORT.append("Ref*, Tpl*, Exact*, Use*, StoreFulfil*, Lease*, SameReply*, RunFirst/RunLast, Qwen*: POST HOC review analyses "
                  "(posthoc_review.py, reference_policies.py); not pre-registered, not confirmatory.")


def review_tables(models, dry):
    mk = [model_key(m) for m in models]
    tt = lambda s: r"\texttt{%s}" % tex_text(s)  # noqa: E731
    # control-template choice use (main text, next to H2)
    L = [r"\begin{table}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{@{}lcc|cc|cc@{}}", r"\toprule",
         r" & \multicolumn{2}{c|}{lock, \texttt{locks}} & \multicolumn{2}{c|}{message, \texttt{messages}} & "
         r"\multicolumn{2}{c}{\texttt{cas}, \texttt{cas\_available}} \\",
         r"Model & control & contended & control & contended & control & contended$^{*}$ \\", r"\midrule"]
    for k in mk:
        L.append(M(f"Model{k}Name") + " & " + " & ".join(M(f"Use{x}{k}OffEst") for x in
                 ("LockCtl", "LockCont", "MsgCtl", "MsgCont", "CasCtl", "CasContUpd")) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{EXPLORATORY, post hoc: agents making the offered choice on the control template and on the "
          r"contended templates ($n=\DesNTwo$, aware off). The control template is the budget write-skew template with a cap "
          r"that fits every spend: agents still read each other's spend records, and an agent cannot tell from what it sees "
          r"whether the cap will bind. $^{*}$Templates written with \texttt{update\_record}.}", r"\label{tab:control-use}", r"\end{table}", ""]
    write_table("control_use.tex", "\n".join(L), dry)
    # reference policies (appendix)
    rp = REVIEW["rp"]
    L = [r"\begin{table}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{@{}llccccc@{}}", r"\toprule",
         r"Policy & config & non-ser. & stale & partial & skew & fulfilled \\", r"\midrule"]
    last = None
    for r in [x for x in rp["rows"] if x["scope"] == "all"]:
        b = f"Ref{POLICY_KEYS[r['policy']]}{config_key(r['config'])}"
        name = tex_text(POLICY_SHORT[r["policy"]]) if r["policy"] != last else ""
        if last is not None and r["policy"] != last:
            L.append(r"\midrule")
        last = r["policy"]
        L.append(f"{name} & {tt(r['config'])} & " + M(b + "Nonser") + "/" + M(b + "N") + " & " + M(b + "Stale") + " & " +
                 M(b + "Partial") + " & " + M(b + "Skew") + " & " + M(b + "Fulfil") + "/" + M(b + "Agents") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC reference floor and ceiling: the frozen scripted agents (\texttt{agents4.py}; no model calls) "
          r"under the registered schedule (read-to-write gap \DesGap, no start jitter, turn cap \DesTurnCap) on the "
          r"\DesNContendedTemplates{} contended templates $\times$ \DesNInstances{} instances $\times$ both phase-one seeds, "
          r"$n=\DesNTwo$, aware off, every agent running the same policy under every config whose tools it needs. "
          r"Episodes non-serializable / run, episodes by primary label, and fulfilled / agents.}",
          r"\label{tab:reference}", r"\end{table}", ""]
    write_table("reference_policies.tex", "\n".join(L), dry)
    # template-level bootstrap (appendix, next to tab:sensitivity)
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{ll" + "c" * len(mk) + "c}", r"\toprule",
         r"H & & " + " & ".join(M(f"Model{k}Name") for k in mk) + r" & rejected (registered) \\", r"\midrule"]
    for lab, hk, hkey in (("H1", "Hone", "Hone"), ("H2", "Htwo", "Htwo"), ("H3", "Hthree", "Hthree"), ("H4a", "HfourA", "HfourA"),
                          ("H4b (i)", "HfourBI", "HfourB"), ("H4b (ii)", "HfourBII", "HfourB"), ("H6", "Hsix", "Hsix")):
        rej = (M(f"Tpl{hkey}NReject") + "/" + M(f"{hkey}FamilySize") +
               " (" + M(f"Tpl{hkey}NRejectReg") + ")") if lab != "H4b (ii)" else ""
        if lab == "H4b (i)":
            pcells = [r"\VerdictCell{%s}{%s}" % (M(f"TplHfourB{k}Reject"), M(f"TplHfourB{k}PHolm")) for k in mk]
            L.append(r"H4b & $p_{\mathrm{Holm}}$ & " + " & ".join(pcells) + f" & {rej}" + r" \\")
        if lab not in ("H4b (i)", "H4b (ii)"):
            pcells = [r"\VerdictCell{%s}{%s}" % (M(f"Tpl{hkey}{k}Reject"), M(f"Tpl{hkey}{k}PHolm")) for k in mk]
            L.append(f"{lab} & " + r"$p_{\mathrm{Holm}}$ & " + " & ".join(pcells) + f" & {rej}" + r" \\")
        if lab != "H4b (ii)":
            sf = [r"\VerdictCell{%s}{%s}" % (M(f"Tpl{hkey}{k}RejectSignflip"), M(f"Tpl{hkey}{k}PSignflipHolm")) for k in mk]
            L.append(r" & sign-flip $p_{\mathrm{Holm}}$ & " + " & ".join(sf) + " & " + M(f"Tpl{hkey}NRejectSignflip") + "/" +
                     M(f"{hkey}FamilySize") + r" \\")
            sg = [r"\VerdictCell{%s}{%s}" % (M(f"Tpl{hkey}{k}RejectSign"), M(f"Tpl{hkey}{k}PSignHolm")) for k in mk]
            L.append(r" & sign $p_{\mathrm{Holm}}$ & " + " & ".join(sg) + " & " + M(f"Tpl{hkey}NRejectSign") + "/" +
                     M(f"{hkey}FamilySize") + r" \\")
        L.append((lab if lab.startswith("H4b") else "") + r" & ICC & " + " & ".join(M(f"Tpl{hk}{k}ICC") for k in mk) + r" & \\[2pt]")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC sensitivity, not pre-registered: the registered tests with templates instead of task instances "
          r"as the unit. First row: the frozen bootstrap on template means (exact sign test when all means are equal); then the "
          r"exact sign-flip test and the exact sign test on template means; Holm across models in each row; bold = rejected. "
          r"H4b: the larger $p$ of its two parts. The estimates equal the registered ones. ICC: intra-template correlation of the "
          r"instance cluster values (one-way ANOVA; -- when all values are equal). The sign-test fallback cannot reject with "
          r"\TplHfourANTemplates{} (H4a) or \TplHfourBINTemplates{} (H4b) templates (smallest one-sided $p$ \TplMinPHfourA{} and "
          r"\TplMinPHfourBI), but the percentile bootstrap can return $p=1/(B+1)$ from as few as two clusters whose values all "
          r"lie on the alternative side (\ModelGeminiName{} H4b (ii): $p$ \TplHfourBIIGeminiP{} from two template means), so the "
          r"bootstrap row is not a valid test at this number of templates. The registered unit is the instance, and the "
          r"registered verdicts (Table~\ref{tab:verdicts}) stand.}", r"\label{tab:template-boot}",
          r"\end{table*}", ""]
    write_table("template_boot.tex", "\n".join(L), dry)
    # per-template H3 differences (appendix)
    tk = list(TEMPLATE_KEYS)
    L = [r"\begin{table}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{@{}l" + "c" * len(mk) + r"@{}}", r"\toprule",
         "Template & " + " & ".join(M(f"Model{k}Name") for k in mk) + r" \\", r"\midrule"]
    for t in tk:
        L.append(tt(t) + " & " + " & ".join(M(f"TplHthree{k}{TEMPLATE_KEYS[t]}") for k in mk) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC: H3 statistic (offered-option rate, aware on minus off, \texttt{locks} and \texttt{messages} "
          r"pooled) per template, mean over its \DesNInstances{} instance clusters.}", r"\label{tab:h3-templates}", r"\end{table}", ""]
    write_table("h3_templates.tex", "\n".join(L), dry)
    # lease split (appendix)
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{lccccccc}", r"\toprule",
         r" & & \multicolumn{3}{c}{lockers at their first write} & \multicolumn{2}{c}{non-serializable episodes} & \\",
         r"Model & lockers & own lease expired & lock held & other & some lease expired & none expired & median lease \\",
         r"\midrule"]
    for k in mk:
        b = f"Lease{k}Off"
        L.append(M(f"Model{k}Name") + " & " + M(b + "Lockers") + " & " + M(b + "Expired") + " & " + M(b + "Held") + " & " +
                 M(b + "Other") + " & " + M(b + "ExpNonser") + "/" + M(b + "ExpN") + " & " + M(b + "NotExpNonser") + "/" +
                 M(b + "NotExpN") + " & " + M(b + "Median") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC lease-expiry split under \texttt{locks} (contended templates, $n=\DesNTwo$, aware off). "
          r"Lockers: agents with a granted lock. At an agent's first write attempt on each record it must write: its own "
          r"lease on that record had expired (expired), it still held it on every such record (held), or neither (other: "
          r"released, never locked that record). Episodes are split by whether any agent's own lease had expired before "
          r"its write. Median lease: requested \texttt{lease\_steps} of granted locks (scheduler rounds).}",
          r"\label{tab:lease-split}", r"\end{table*}", ""]
    write_table("lease_split.tex", "\n".join(L), dry)


# ------------------------------------------------------------------ POST HOC analyses after the four hard reviews (review/T1-T4, 2026-11-03)
POSTHOC_BLOCKS = (  # every post hoc analysis block printed in the paper (count stated in Section 4, reporting rule 4)
    "rollback rescoring", "scripted reference policies", "template-level resampling (bootstrap, sign, sign-flip)",
    "exact bounds", "control-template choice use", "store-based fulfilment", "lease-expiry split", "same-reply legs",
    "serving facts", "SQL slice", "first response after a rejection", "write-skew prevention", "leave-one-template-out",
    "diagnostics", "H3 per template", "sign-test Holm adjustment", "H6 detectable effect", "409 version leak",
    "partial-action mechanisms", "transient write-skew violations", "first-reply locks and the control template",
    "schedule overlap and seed invariance", "turn-cap endings", "Qwen lock use by host", "Gemini settings as logged",
    "scripted promoter")


def ffloor(x, nd=2):
    """Round DOWN (lower bounds must not be rounded up)."""
    if x is None:
        return None
    q = Decimal(1).scaleb(-nd)
    return str(Decimal(repr(float(x))).quantize(q, rounding="ROUND_FLOOR"))


def alpha_key(s):
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z]+", s) if w)


def review2_macros(models, dry, numbers):
    g = "posthoc-review2"
    pr, rp = REVIEW["pr"], REVIEW["rp"]
    r2 = pr.get("review2")
    if not r2 or "seed_invariance" not in rp:
        raise SystemExit("posthoc_review.json / reference_policies.json predate the review2 analyses: rerun posthoc_review.py "
                         "and reference_policies.py")
    # counts for the reporting rule
    put("RevNExplTests", thou(sum(c.get("p_two_sided") is not None for c in numbers["comparisons"])), g)
    put("RevNExplFamilies", len({c.get("family") for c in numbers["comparisons"]}), g)
    put("RevNPosthocBlocks", len(POSTHOC_BLOCKS), g)
    # registered sign test for every test, and its (post hoc) Holm adjustment
    for h, rec in r2["sign_tests"]["hypotheses"].items():
        hk = H_KEYS[h]
        put(f"RevSign{hk}NReject", rec["n_reject_sign"], g)
        for t in rec["tests"]:
            k = model_key(t["model"])
            put(f"RevSign{hk}{k}P", fp(t["p_sign"]), g)
            put(f"RevSign{hk}{k}PHolm", fp(t.get("p_sign_holm")), g)
            put(f"RevSign{hk}{k}Reject", "yes" if t.get("reject_sign") else "no", g)
            put(f"RevSign{hk}{k}K", "/".join(f"{a}/{b}" for a, b in zip(t["k"], t["n"])), g)
    # exact template-level tests
    for h, rec in pr["template_boot"]["hypotheses"].items():
        hk = H_KEYS[h]
        put(f"Tpl{hk}NRejectSign", rec["n_reject_sign"], g)
        put(f"Tpl{hk}NRejectSignflip", rec["n_reject_signflip"], g)
        for t in rec["tests"]:
            k = model_key(t["model"])
            for meth, key in (("sign", "Sign"), ("signflip", "Signflip")):
                put(f"Tpl{hk}{k}P{key}Holm", fp(t[f"p_{meth}_holm"]), g)
                put(f"Tpl{hk}{k}Reject{key}", "yes" if t[f"reject_{meth}"] else "no", g)
    ntpl = pr["template_boot"]["hypotheses"]["H1"]["tests"][0]["n_templates"]
    put("ExactTplBound", ffloor(0.05 ** (1.0 / ntpl)), g)
    # H6 detectable effect
    h6 = r2["h6_detectable"]
    put("RevHsixKAlpha", h6["k_alpha"], g)
    put("RevHsixKHolm", h6["k_alpha_first_holm"], g)
    put("RevHsixM", h6["m"], g)
    put("RevHsixRiseAlpha", f2(h6["k_alpha"] / h6["m"]), g)
    put("RevHsixRiseHolm", f2(h6["k_alpha_first_holm"] / h6["m"]), g)
    put("RevHsixMaxEst", f2(h6["max_estimate"]), g)
    put("RevHsixNPositive", NUM_EN.get(h6["n_positive_estimates"], h6["n_positive_estimates"]), g)
    # graph_cycle vs non_serializable
    for scope, key in (("all", "All"), ("single_record", "Single"), ("write_skew_n2", "Ws"), ("control", "Ctl")):
        t = r2["graph_agreement"][scope]
        for f, kk in (("ns1_gc1", "NsCyc"), ("ns1_gc0", "NsAcyc"), ("ns0_gc1", "SerCyc"), ("ns0_gc0", "SerAcyc"), ("n", "N")):
            put(f"RevGraph{key}{kk}", thou(t[f]), g)
        put(f"RevGraph{key}Disagree", thou(t["ns1_gc0"] + t["ns0_gc1"]), g)
    # stale overwrites
    st = r2["stale"]
    for c, v in st["episodes_with_stale_by_config"].items():
        put(f"RevStale{config_key(c)}K", thou(v["k"]), g)
        put(f"RevStale{config_key(c)}N", thou(v["n"]), g)
    put("RevHiddenLost", st["hidden_lost_updates"], g)
    cl = r2["cas_leak"]
    src = cl["committed_cas_by_version_source"]
    put("RevCasCommitted", thou(sum(v for k, v in src.items() if k in ("read", "own_write", "error_body", "unseen"))), g)
    put("RevCasErrBody", src.get("error_body", 0), g)
    put("RevCasErrBodyStale", src.get("error_body_stale", 0), g)
    put("RevCasStaleEpisodes", cl["stale_overwrite_label_episodes"], g)
    # partial_action mechanisms
    ps = r2["partial_split"]
    put("RevPartialN", ps["n"], g)
    for f, kk in (("missing_leg", "MissingLeg"), ("compensated", "Compensated"), ("guard_violation", "Guard"),
                  ("none_of_these", "Other"), ("compensated_only", "CompensatedOnly")):
        put(f"RevPartial{kk}", ps["flags"].get(f, 0), g)
    put("RevStaleWithPartial", ps["stale_overwrite_with_partial_commit"], g)
    # H4b: violated at any point vs at the end
    for r in r2["ws_transient"]["rows"]:
        k = model_key(r["model"])
        for f, kk in (("episodes", "N"), ("ever_violated", "Ever"), ("final_violated", "Final"), ("write_skew_label", "Label"),
                      ("graph_cycle", "Cycle")):
            put(f"RevWs{kk}{k}", r.get(f, 0), g)
    # control template and first-reply locks
    for r in r2["control"]["rows"]:
        k = model_key(r["model"])
        put(f"RevCtlCycle{k}K", r["control_graph_cycle"], g)
        put(f"RevCtlCycle{k}N", r["control_episodes"], g)
        put(f"RevLockCtl{k}", f2(r["lock_control"]["est"]), g)
        put(f"RevLockBudgetWs{k}", f2(r["lock_budget_ws"]["est"]), g)
        put(f"RevFirstLock{k}K", r["first_reply_lock"], g)
        put(f"RevFirstLock{k}N", r["first_reply_agents"], g)
    # schedule
    sc = r2["schedule"]
    put("RevSchedReadsFirstK", thou(sc["reads_before_first_commit"]), g)
    put("RevSchedReadsFirstN", thou(sc["episodes"]), g)
    fm = sc["first_mover"]
    put("RevSchedSeedZeroAzero", thou(fm.get("s0|a0", 0)), g)
    put("RevSchedSeedOneAone", thou(fm.get("s1|a1", 0)), g)
    put("RevSchedPerSeed", thou(sum(v for kk, v in fm.items() if kk.startswith("s0|"))), g)
    si = rp["seed_invariance"]
    put("RevSeedCells", len(si), g)
    put("RevSeedCellsAllSame", sum(x["same"] == x["instances"] for x in si), g)
    put("RevSeedInstances", si[0]["instances"] if si else "--", g)
    # scripted promoter
    for r in rp["promoter"]["rows"]:
        b = f"RevProm{'First' if r['order'] == 'promote_first' else 'Own'}{nword(r['n'])}{TEMPLATE_KEYS[r['template']]}"
        for f, kk in (("episodes", "N"), ("non_serializable", "Nonser"), ("write_skew", "Skew"), ("fulfilled", "Fulfil"),
                      ("agents", "Agents"), ("turn_cap", "Cap")):
            put(b + kk, r.get(f, 0), g)
    # turn cap
    tc = r2["turn_cap"]
    for m, v in tc["per_model"].items():
        k = model_key(m)
        put(f"RevCap{k}K", v["k"], g)
        put(f"RevCap{k}N", thou(v["n"]), g)
        put(f"RevCap{k}Rate", f2(v["k"] / v["n"]), g)
    for c in tc["cells"]:
        put(f"RevCapCell{model_key(c['model'])}{config_key(c['config'])}{nword(c['n'])}", f2(c["k"] / c["agents"]) if c["agents"] else "--", g)
    for m, v in tc["h6_n8_cas"].items():
        put(f"RevCapHsix{model_key(m)}K", v["capped"], g)
        put(f"RevCapHsix{model_key(m)}N", v["agents"], g)
    for r in tc["n8_multi_record"]:
        b = f"RevCapEight{model_key(r['model'])}{config_key(r['config'])}"
        put(b + "K", r["capped"], g)
        put(b + "N", r["agents"], g)
        put(b + "NoCommit", r["capped_no_commit"], g)
    # Qwen hosts, Gemini settings
    hosts = {h: {"k": 0, "n": 0} for h in ("Alibaba", "Chutes", "DeepInfra", "Phala", "Reka", "SiliconFlow", "Venice")}
    hosts.update(r2["qwen_hosts_locks"]["hosts"])  # known hosts default to 0 (e.g. dry runs)
    for h, v in hosts.items():
        b = f"RevQwenLock{alpha_key(h)}"
        put(b + "K", v["k"], g)
        put(b + "N", v["n"], g)
        put(b + "Rate", f2(v["k"] / v["n"]) if v["n"] else "--", g)
    gm = r2["gemini"]
    put("RevGeminiAgents", thou(gm["agents"]), g)
    put("RevGeminiZeroReason", thou(gm["first_completion_zero_reasoning"]), g)
    put("RevGeminiTempZero", thou(gm["temperature_sent_zero"]), g)
    # unfrozen orchestration code
    orc = r2.get("orchestrators") or {"rows": [], "recorded_at": None}
    put("RevOrchRecordedAt", (orc.get("recorded_at") or "--").replace("T", " ").replace("Z", " UTC"), g)
    put("RevOrchMissing", sum(r["local"] == "missing" for r in orc["rows"]), g)
    put("RevOrchDiffers", sum(r["local"] == "differs" for r in orc["rows"]), g)
    REVIEW["orch"] = orc["rows"]
    for r in orc["rows"]:
        b = f"RevOrch{alpha_key(r['file'])}"
        put(b + "Hash", (r.get("recorded_sha256") or r.get("local_sha256") or "")[:16], g)
        put(b + "Status", {"same": "same", "differs": "differs", "missing": "missing", "not recorded": "not recorded"}[r["local"]], g)
    REPORT.append("Rev*, Tpl*Sign*, ExactTplBound: POST HOC analyses added after the T1-T4 reviews (posthoc_review.py review2 "
                  "block, reference_policies.py seed invariance and promoter); not pre-registered, not confirmatory.")


def review2_tables(models, dry):
    mk = [model_key(m) for m in models]
    tt = lambda s: r"\texttt{%s}" % tex_text(s)  # noqa: E731
    hdr = " & ".join(M(f"Model{k}Name") for k in mk)
    # per-model behaviour diagnostics
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{l" + "c" * len(mk) + "}", r"\toprule",
         "Quantity & " + hdr + r" \\", r"\midrule",
         r"lock requested in first reply (\texttt{locks}, aware off) & " + " & ".join(M(f"RevFirstLock{k}K") + "/" + M(f"RevFirstLock{k}N") for k in mk) + r" \\",
         r"lock share, \texttt{budget\_control} & " + " & ".join(M(f"RevLockCtl{k}") for k in mk) + r" \\",
         r"lock share, \texttt{budget\_write\_skew} & " + " & ".join(M(f"RevLockBudgetWs{k}") for k in mk) + r" \\",
         r"control episodes with a graph cycle & " + " & ".join(M(f"RevCtlCycle{k}K") + "/" + M(f"RevCtlCycle{k}N") for k in mk) + r" \\",
         r"\midrule",
         r"write-skew episodes, \texttt{cas\_available} & " + " & ".join(M(f"RevWsN{k}") for k in mk) + r" \\",
         r"\quad constraint violated at some point & " + " & ".join(M(f"RevWsEver{k}") for k in mk) + r" \\",
         r"\quad violated at the end & " + " & ".join(M(f"RevWsFinal{k}") for k in mk) + r" \\",
         r"\quad \texttt{write\_skew} label (H4b (i)) & " + " & ".join(M(f"RevWsLabel{k}") for k in mk) + r" \\",
         r"\quad graph cycle & " + " & ".join(M(f"RevWsCycle{k}") for k in mk) + r" \\",
         r"\midrule",
         r"agents ending at the turn cap (all phases) & " + " & ".join(M(f"RevCap{k}K") + "/" + M(f"RevCap{k}N") for k in mk) + r" \\",
         r"\quad H6 cells at $n=\DesNEight$ & " + " & ".join(M(f"RevCapHsix{k}K") + "/" + M(f"RevCapHsix{k}N") for k in mk) + r" \\",
         r"\quad $n=\DesNEight$, \texttt{locks}, write-skew and control & " + " & ".join(M(f"RevCapEight{k}LocksK") + "/" + M(f"RevCapEight{k}LocksN") for k in mk) + r" \\",
         r"\qquad of these, never committed & " + " & ".join(M(f"RevCapEight{k}LocksNoCommit") for k in mk) + r" \\",
         r"\quad $n=\DesNEight$, \texttt{cas\_available}, write-skew and control & " + " & ".join(M(f"RevCapEight{k}CasAvailK") + "/" + M(f"RevCapEight{k}CasAvailN") for k in mk) + r" \\",
         r"\qquad of these, never committed & " + " & ".join(M(f"RevCapEight{k}CasAvailNoCommit") for k in mk) + r" \\",
         r"\bottomrule", r"\end{tabular}",
         r"\caption{POST HOC diagnostics added after the 2026-11-03 reviews (saved transcripts; no model calls). First reply: "
         r"agents whose first model reply contained \texttt{acquire\_lock}, before any record value was returned (all "
         r"\DesNTemplates{} templates, $n=\DesNTwo$). Lock shares: aware off, $n=\DesNTwo$, mean of instance rates; the "
         r"control template is the budget template with a cap that fits every spend. Write-skew rows: \DesNWriteSkewTemplates{} "
         r"templates, $n=\DesNTwo$, aware off; ``at some point'' replays the ledger after every committed write. Turn-cap "
         r"rows: aware off except the first.}",
         r"\label{tab:review-diag}", r"\end{table*}", ""]
    write_table("review_diag.tex", "\n".join(L), dry)
    # turn-cap endings by config and n
    cols = [(c, 2) for c in CONFIG_KEYS] + [(c, n) for n in (4, 8) for c in ("none", "cas_available", "locks")]
    L = [r"\begin{table*}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{l" + "c" * len(cols) + "}", r"\toprule",
         r" & \multicolumn{6}{c}{$n=\DesNTwo$} & \multicolumn{3}{c}{$n=\DesNFour$} & \multicolumn{3}{c}{$n=\DesNEight$} \\",
         "Model & " + " & ".join(tt(c) for c, _ in cols) + r" \\", r"\midrule"]
    for k in mk:
        L.append(M(f"Model{k}Name") + " & " + " & ".join(M(f"RevCapCell{k}{CONFIG_KEYS[c]}{nword(n)}") for c, n in cols) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC: share of agents that ended at the turn cap of \DesTurnCap{} executed calls, by config and $n$ "
          r"(all templates, both aware levels).}", r"\label{tab:turncap}", r"\end{table*}", ""]
    write_table("turncap.tex", "\n".join(L), dry)
    # graph agreement
    L = [r"\begin{table}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{@{}lccccc@{}}", r"\toprule",
         r"Scope & \multicolumn{2}{c}{non-serializable} & \multicolumn{2}{c}{serializable} & disagree \\",
         r" & cycle & no cycle & cycle & no cycle & \\", r"\midrule"]
    for key, lab in (("All", "all episodes"), ("Single", "single-record templates"), ("Ws", r"write-skew templates, $n=\DesNTwo$"),
                     ("Ctl", "control template")):
        L.append(lab + " & " + " & ".join(M(f"RevGraph{key}{x}") for x in ("NsCyc", "NsAcyc", "SerCyc", "SerAcyc", "Disagree")) +
                 r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Registered exploratory item, reported after the reviews: \texttt{graph\_cycle} against \texttt{non\_serializable}, "
          r"episodes per cell (all phases, configs and aware levels).}", r"\label{tab:graph-agree}", r"\end{table}", ""]
    write_table("graph_agree.tex", "\n".join(L), dry)
    # scripted promoter
    L = [r"\begin{table}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{@{}lllcccc@{}}", r"\toprule",
         r"Order & $n$ & template & non-ser. & \texttt{write\_skew} & fulfilled & turn cap \\", r"\midrule"]
    for o, lab in (("First", "promote first"), ("Own", "own write first")):
        for n in (2, 8):
            for t in ("budget_write_skew", "joint_account_write_skew"):
                b = f"RevProm{o}{nword(n)}{TEMPLATE_KEYS[t]}"
                L.append(f"{lab} & {M('DesN' + nword(n))} & {tt(t)} & " + M(b + "Nonser") + "/" + M(b + "N") + " & " + M(b + "Skew") +
                         " & " + M(b + "Fulfil") + "/" + M(b + "Agents") + " & " + M(b + "Cap") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{POST HOC scripted promoter under \texttt{cas\_available} and the registered schedule (written after the reviews, "
          r"not frozen code). It reads its intent's records and writes back each record it reads but does not change under the "
          r"read version, before (promote first; restart after a rejection) or after (own write first; stop after a rejection) "
          r"its own write. Episodes non-serializable / run, \texttt{write\_skew} episodes, fulfilled / agents, agents ending at "
          r"the turn cap.}", r"\label{tab:promoter}", r"\end{table}", ""]
    write_table("promoter.tex", "\n".join(L), dry)
    # unfrozen orchestration code
    L = [r"\begin{table}[p]", r"\centering\scriptsize\DryTag\par", r"\begin{tabular}{@{}llc@{}}", r"\toprule",
         r"File (\texttt{src4\_batch/}) & sha256 (first 16 hex) & local copy \\", r"\midrule"]
    for r in REVIEW.get("orch", []):
        b = f"RevOrch{alpha_key(r['file'])}"
        L.append(tt(r["file"]) + " & " + r"\texttt{" + M(b + "Hash") + "} & " + M(b + "Status") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}",
          r"\caption{Orchestration and batch code outside the freeze, with the sha256 recorded at the last run start "
          r"(\RevOrchRecordedAt) by \texttt{switch\_facts.py}, and whether the copy in the artifact matches it. "
          r"\texttt{prices\_batch.json} was not recorded; its hash is the local copy's.}", r"\label{tab:orchestrators}",
          r"\end{table}", ""]
    write_table("orchestrators.tex", "\n".join(L), dry)


def static_tables(dry):
    """Configs, tools, templates and fixed settings, generated from the frozen code."""
    import world4
    import tasks4
    import instances4
    tt = lambda s: r"\texttt{%s}" % tex_text(s)  # noqa: E731
    yn = lambda b: "yes" if b else "no"  # noqa: E731
    base = set(world4.CoordinationConfig.from_names("none").available_tools())
    L = [r"\begin{table}[t]", r"\centering\scriptsize", r"\begin{tabular}{@{}lcccp{0.30\columnwidth}@{}}", r"\toprule",
         r"Config & versions & cond.\ write & \texttt{claim} T\&S & added tools \\", r"\midrule"]
    for p in world4.PRESET_NAMES:
        c = world4.CoordinationConfig.from_names(p)
        extra = [t for t in c.available_tools() if t not in base]
        L.append(f"{tt(p)} & {yn(c.expose_versions)} & {c.conditional_writes} & {yn(c.claim_is_conditional)} & "
                 + (", ".join(tex_tt(t) for t in extra) or "--") + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\caption{\SOne{} coordination configs (generated from the frozen harness). "
          r"Every config offers " + ", ".join(tex_tt(t) for t in sorted(base)) + r"; T\&S = test-and-set.}",
          r"\label{tab:configs}", r"\end{table}", ""]
    write_table("configs.tex", "\n".join(L), dry)

    full = world4.CoordinationConfig.from_names("cas_available+locks+messages")
    L = [r"\begin{table*}[t]", r"\centering\scriptsize", r"\begin{tabular}{lp{0.35\textwidth}p{0.42\textwidth}}", r"\toprule",
         r"Tool & parameters & description (\texttt{cas\_available+locks+messages}) \\", r"\midrule"]
    for s in world4.tool_schemas(full):
        props = s["input_schema"].get("properties", {})
        req = set(s["input_schema"].get("required", []))
        params = ", ".join(tt(k) + ("" if k in req else "?") for k in props) or "--"
        L.append(f"{tt(s['name'])} & {params} & {tex_text(s['description'])}" + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\caption{\SOne{} tool schemas (generated from the frozen harness); ? = optional. "
          r"Under \texttt{cas\_required}, \texttt{expected\_version} is required; under configs without versions, "
          r"\texttt{get\_record} returns the value only.}", r"\label{tab:tools}", r"\end{table*}", ""]
    write_table("tools.tex", "\n".join(L), dry)

    L = [r"\begin{table*}[t]", r"\centering\scriptsize", r"\begin{tabular}{llp{0.5\textwidth}p{0.2\textwidth}}", r"\toprule",
         r"Template & category & example intent (instance 0, agent \texttt{a0}, $n=\DesNTwo$) & invariants \\", r"\midrule"]
    names = list(A.CONTENDED_TEMPLATES) + ["budget_control"]
    for t in names:
        task = instances4.build(t, 0, 2)
        intent = task.intents[task.agent_ids[0]].describe()
        invs = ", ".join(tt(re.sub(r"\[.*\]", "", i.name)) for i in task.invariants)
        L.append(f"{tt(t)} & {tex_text(task.category)} & {tex_text(intent)} & {invs}" + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\caption{Task templates of \SOne{} (one intent per template; parameters vary "
          r"by instance, wording paraphrase $=$ instance mod 2).}", r"\label{tab:templates}", r"\end{table*}", ""]
    write_table("templates.tex", "\n".join(L), dry)

    rows = [("read-to-write gap (rounds)", "DesGap"), ("start jitter", "DesJitter"), ("turn cap (executed calls / agent)", "DesTurnCap"),
            ("completion cap / agent", "DesCompletionCap"), ("temperature requested", "DesTemperature"), ("max tokens / completion", "DesMaxTokens"),
            ("lock expiry", "DesLockExpiry"), ("max lease (rounds)", "DesMaxLease"), ("stall rounds", "DesStallRounds"),
            ("max rounds", "DesMaxRounds"), ("bootstrap resamples", "DesNBoot"), ("bootstrap seed", "DesBootSeed"),
            ("cost cap (USD)", "DesMaxUSD")]
    L = [r"\begin{table}[t]", r"\centering\small", r"\begin{tabular}{lc}", r"\toprule", r"Setting & value \\", r"\midrule"]
    L += [f"{tex_text(a)} & {M(b)}" + r" \\" for a, b in rows]
    L += [r"\bottomrule", r"\end{tabular}", r"\caption{\SOne{} fixed settings (from the frozen harness and run scripts).}", r"\label{tab:settings}", r"\end{table}", ""]
    write_table("fixed_settings.tex", "\n".join(L), dry)

    # deviations: author-maintained CSV. The rows are long, so the table is split into page-sized table* floats by
    # an estimate of each row's height at \scriptsize (a single float taller than the page is clipped, which happened
    # with 11 rows: "Float too large for page by 602pt" and rows 7-11 missing from the PDF). The estimate is
    # conservative (about 20% high), so a 600pt budget keeps each part well inside the 705pt text height.
    import csv
    import math
    dev = os.path.join(HERE, "deviations.csv")
    keys = ("deviation", "reason", "before_after", "effect", "registered_result")
    widths = (0.2, 0.18, 0.1, 0.18, 0.18)  # fractions of \textwidth (455pt in acl.sty)
    recs = []
    if os.path.exists(dev):
        with open(dev, newline="") as f:
            recs = list(csv.DictReader(f))
    n = len(recs)

    def est_height(r):  # points: about 3.3pt per character and 8pt per line at \scriptsize, plus one line per cell
        return 2 + 8 * max(math.ceil(len(r.get(k, "")) / max(1, int(w * 455 / 3.3))) + 1 for k, w in zip(keys, widths))

    chunks, cur, tot = [], [], 0
    for r in recs:
        hgt = est_height(r)
        if cur and tot + hgt > 600:
            chunks.append(cur)
            cur, tot = [], 0
        cur.append(r)
        tot += hgt
    chunks.append(cur)
    L = []
    for i, ch in enumerate(chunks):
        L += [r"\begin{table*}[p]" if len(chunks) > 1 else r"\begin{table*}[t]", r"\centering\scriptsize",
              r"\begin{tabular}{" + "".join(r"p{%g\textwidth}" % w for w in widths) + "}",
              r"\toprule", r"Deviation & reason & before/after data & effect & registered-plan result \\", r"\midrule"]
        for r in ch:
            L.append(" & ".join(tex_text(r.get(k, "")) for k in keys) + r" \\")
        if n == 0:
            L.append(r"\multicolumn{5}{l}{None recorded in \texttt{deviations.csv}.} \\")
        cont = "" if len(chunks) == 1 else ", part %d of %d" % (i + 1, len(chunks))
        L += [r"\bottomrule", r"\end{tabular}",
              r"\caption{Deviations from the pre-registration (from \texttt{latex/deviations.csv}%s).}" % cont]
        if i == 0:
            L.append(r"\label{tab:deviations}")
        L += [r"\end{table*}", ""]
    write_table("deviations.tex", "\n".join(L), dry)
    put("ObsNDeviations", n, "observed")

    # EXPLORATORY SQL slice (Appendix app:sql): copied verbatim from src_sql/analyze_sql.py's output, which is a
    # separate, post hoc, unregistered study with real model runs. Its values are literal, not numbers.tex macros.
    sql = os.path.join(os.environ.get("RESULTS_SQL", os.path.join(os.path.dirname(PAPER), "results_sql")),
                       "analysis", "tables_appendix.tex")
    head = (f"% GENERATED by make_numbers4.py -- do not edit. Input: {'DRY RUN (fake model)' if dry else 'real data'} "
            "for the main study; this file is the EXPLORATORY SQL slice.\n"
            f"% Copied verbatim from {os.path.relpath(sql, os.path.dirname(PAPER))} (src_sql/analyze_sql.py, real model runs); "
            "values are literal, not numbers.tex macros: the one documented exception to the macro rule (Appendix app:sql).\n")
    if os.path.exists(sql):
        body = open(sql).read()
        put("ObsSqlSliceTables", 1, "exploratory-sql")
        REPORT.append(f"SQL slice tables copied from {sql}")
    else:
        body = r"\paragraph{}\textit{SQL slice tables not found (results\_sql/analysis/tables\_appendix.tex).}" + "\n"
        put("ObsSqlSliceTables", 0, "exploratory-sql")
        WARN.append(f"SQL slice tables missing: {sql}")
    with open(os.path.join(TABLES, "sql_slice.tex"), "w") as f:
        f.write(head + body)


# ------------------------------------------------------------------ facts rendering
def render_facts(dry):
    os.makedirs(FACTS_OUT, exist_ok=True)
    for src in sorted(glob.glob(os.path.join(FACTS_SRC, "*.md"))):
        txt = open(src).read()

        def sub(m):
            k = m.group(1)
            if k not in NUMS:
                WARN.append(f"facts/{os.path.basename(src)}: unknown macro {{{{{k}}}}}")
                return f"`\\{k}` = **UNDEFINED**"
            return f"`\\{k}` = {plain(NUMS[k])}"
        out = re.sub(r"\{\{([A-Za-z]+)\}\}", sub, txt)
        banner = ("<!-- GENERATED from facts/src by make_numbers4.py; edit facts/src, not this file. -->\n" +
                  ("> **DRY RUN DATA: every value below comes from the fake model. Cite the macro names, never these values.**\n\n"
                   if dry else "> Values from the real run. Cite the macro names in main.tex, not the values.\n\n"))
        with open(os.path.join(FACTS_OUT, os.path.basename(src)), "w") as f:
            f.write(banner + out)


# ------------------------------------------------------------------ lint of main.tex (and supplement.tex)
GEN_PREFIX = re.compile(r"^(H(one|two|three|fourA|fourB|five|six)|Rb[A-Z]|Sens|X[A-Z]|Cmp|Des|Pilot|Plan|Budget|Mutants|Excl|Expl|Obs|Cost|Served|Model[A-Z]|Raw[A-Z]|DataStatus|PipelineDryRun|Ref[A-Z]|Tpl[A-Z]|Exact[A-Z]|Use[A-Z]|Store[A-Z]|Lease[A-Z]|SameReply|RunFirst|RunLast|Qwen[A-Z]|SqlN[A-Z]|SqlViol|SqlCost|Rev[A-Z])")


def lint_main(path, nums):
    """Return (undefined generated macros, literal digits in the body) for main.tex."""
    txt = open(path).read()
    txt = re.sub(r"(?<!\\)%.*", "", txt)
    body = txt.split(r"\begin{document}", 1)[-1]
    used = set(re.findall(r"\\([A-Za-z]+)", body))
    undefined = sorted(u for u in used if GEN_PREFIX.match(u) and u not in nums)
    b = body
    for pat in (r"\\(SuppSecs|SuppTabs|SuppTabsAnd)\{[^}]*\}\{[^}]*\}", r"\\(SuppSec|SuppTab|SuppFig|PaperRef|externaldocument)(\[[^\]]*\])?\{[^}]*\}(\[[^\]]*\])?",
                r"\\(cite[tp]?|citealp|nocite|label|ref|pageref|eqref|input|include|includegraphics|bibliography|bibliographystyle|"
                r"setcounter|addtocounter|vspace|hspace|newpage|appendix)\*?(\[[^\]]*\])*\{[^}]*\}",
                r"\[[^\]]*(width|height|scale|angle)[^\]]*\]", r"\b[Hh]\d[ab]?\b", r"\{[0-9.]*\\(columnwidth|textwidth|linewidth)\}",
                r"[0-9.]+\\(columnwidth|textwidth|linewidth)", r"\\begin\{[a-z*]+\}(\[[^\]]*\])?(\{[^}]*\})?"):
        b = re.sub(pat, " ", b)
    digits = []
    for i, line in enumerate(b.splitlines(), 1):
        if re.search(r"\d", line):
            digits.append(line.strip())
    return undefined, digits


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis", required=True, help="output dir of run_analysis.py")
    ap.add_argument("--check", action="store_true", help="lint main.tex (undefined macros, literal digits); exit 1 on problems")
    a = ap.parse_args(argv)
    freeze = require_freeze()
    prov_p = os.path.join(a.analysis, "provenance.json")
    if not os.path.exists(prov_p):
        raise SystemExit(f"{prov_p} missing: run run_analysis.py first")
    prov = json.load(open(prov_p))
    numbers = json.load(open(os.path.join(a.analysis, "numbers.json")))
    conf = json.load(open(os.path.join(a.analysis, "confirmatory.json")))
    if numbers["meta"]["analyze4_sha256"] != freeze["analyze4.py"] or conf["registered"]["meta"]["analyze4_sha256"] != freeze["analyze4.py"]:
        raise SystemExit("REFUSING: analysis was produced by an analyze4.py whose hash differs from FREEZE.md")
    dry = bool(prov["dry_run"])
    models = list(A.REGISTERED_MODELS)

    put("PipelineDryRun", 1 if dry else 0, "meta")
    put("DataStatus", "DRY RUN (fake model)" if dry else "real data", "meta")
    phases = design_constants()
    prereg_facts()
    conf_macros(conf["registered"], "", models)
    conf_macros(conf["sensitivity_exclude_truncated"], "Sens", models)
    cell_macros(numbers)
    cmp_macros(numbers)
    rows, _, _ = A.load(prov["analyzed_paths"])
    h6 = h6_per_n(rows, conf["registered"], models)
    observed_macros(rows, numbers, conf, phases, models)
    cost_macros(prov["analyzed_paths"], models)
    raw_csv_macros(prov["analyzed_paths"], models)
    ex = load_explore(a.analysis, prov)
    explore_macros(ex)
    review_macros(a.analysis, models, dry)
    review2_macros(models, dry, numbers)
    rollback_audit_macros(a.analysis, models, dry)
    static_tables(dry)
    tables(models, dry)
    explore_tables(models, dry)
    review_tables(models, dry)
    review2_tables(models, dry)

    os.makedirs(BUILD, exist_ok=True)
    with open(os.path.join(BUILD, "figdata.json"), "w") as f:
        json.dump(figdata(numbers, h6, models, dry, ex), f, indent=1)

    # numbers.tex
    out = ["% GENERATED by make_numbers4.py -- do not edit.",
           f"% Input: {'DRY RUN (fake model) -- NOT REAL RESULTS' if dry else 'real data'}",
           f"% analyze4.py sha256 {freeze['analyze4.py']} (FREEZE verified)"]
    out += [f"%   input {x['path']} sha256 {x['sha256']}" for x in prov["inputs"]]
    out.append(r"\providecommand{\PENDING}[1]{\textcolor{red}{\fbox{\tiny PENDING: #1}}}")
    last = None
    for k, v in NUMS.items():
        if GROUP[k] != last:
            out.append(f"% ---- {GROUP[k]}")
            last = GROUP[k]
        out.append(r"\newcommand{\%s}{%s}" % (k, v))
    with open(os.path.join(HERE, "numbers.tex"), "w") as f:
        f.write("\n".join(out) + "\n")

    render_facts(dry)

    rep = [("DRY RUN DATA (fake model) -- NOT REAL RESULTS" if dry else "REAL DATA"),
           f"analysis dir: {os.path.abspath(a.analysis)}",
           f"analyze4.py sha256 {freeze['analyze4.py']} (FREEZE verified for {len(freeze)} files)"]
    rep += [f"input: {x['path']}  sha256 {x['sha256']}" for x in prov["inputs"]]
    if prov.get("staged_dry_run_flag_cleared"):
        rep.append("NOTE: dry-run CSVs were staged with dry_run=0 so analyze4 would analyse them (run_analysis.py).")
    rep.append(f"macros: {len(NUMS)}")
    rep += ["", "== warnings =="] + (WARN or ["none"]) + ["", "== notes =="] + REPORT + ["", "== macros =="]
    last = None
    for k, v in NUMS.items():
        if GROUP[k] != last:
            rep.append(f"-- {GROUP[k]}")
            last = GROUP[k]
        rep.append(f"\\{k} = {plain(v)}")
    with open(os.path.join(HERE, "numbers_report.txt"), "w") as f:
        f.write("\n".join(rep) + "\n")
    print(f"numbers.tex: {len(NUMS)} macros; dry_run={dry}; warnings={len(WARN)}")
    for w in WARN:
        print("  WARN", w)

    if a.check:
        # the paper (main.tex) and, since the 2026-11-10 split (CUT_LOG.md), the supplement's own body (supplement.tex);
        # the section files they input are linted by study2_lint.py
        bad = False
        for fn in ("main.tex", "supplement.tex"):
            if not os.path.exists(os.path.join(HERE, fn)):
                continue
            undefined, digits = lint_main(os.path.join(HERE, fn), NUMS)
            for u in undefined:
                print(f"  LINT {fn}: undefined macro \\{u}")
            for d in digits:
                print(f"  LINT {fn}: literal digit: {d[:100]}")
            bad = bad or bool(undefined or digits)
        if bad:
            return 1
        print("lint: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
