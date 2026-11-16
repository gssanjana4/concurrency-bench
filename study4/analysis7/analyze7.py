#!/usr/bin/env python3
"""Study 4 registered analysis (src7): every confirmatory test, check, descriptive and sensitivity analysis of
PREREGISTRATION_STUDY4.md, from the transcripts alone.

    python3 analysis7/analyze7.py analyze --base results7/study4 --out analysis7/out_study4
    python3 analysis7/analyze7.py analyze --base results7/study4_dry --out analysis7/out --allow-dry-run

The statistical core (exact sign-flip tests on cluster values, percentile cluster bootstrap, Holm with the Monte Carlo
recompute, the family-level test) and the transcript reader (``normalize``: scores, protocol order, lock scope,
lock-failure mechanisms, exclusion triggers, the lock-safety gate through src7/score7.py) are Study 3's
(``core7.py``, a copy of the frozen Study 3 ``analyze6.py`` with the Study 4 grid constants). This file adds the
Study 4 selection, hypotheses, checks, descriptives, sensitivity analyses and outputs.

Design. Four models (Qwen3.6-27B, Claude Haiku 4.5, Claude Sonnet 5, Claude Fable 5); contended episodes only, n = 2,
together start; four lock configurations, a 2 x 2 of the Study 3 bundle's instruction (I) and its two signals (S):
``locks_s2text`` (neither), ``locks_instr`` (I), ``locks_signals`` (S), ``locks`` (both, the Study 3 bundle). The
cluster is a family and instance (8 x 16 = 128 per model); the four configs of a cluster share one schedule.

Confirmatory (one-sided exact sign-flip on cluster values, alpha 0.05, Holm over the four models and the pooled test
within each hypothesis; the pooled test is the equal-weight mean over the models whose own test runs, on the clusters present for all of them):
  S4-H1  replication:  d = fs(locks_s2text) - fs(locks)                                    H0 mean(d) <= 0
  S4-H2  instruction:  d = [fs(locks_s2text) + fs(locks_signals)]/2 - [fs(locks_instr) + fs(locks)]/2
  S4-H3  signals:      d = [fs(locks_s2text) + fs(locks_instr)]/2 - [fs(locks_signals) + fs(locks)]/2
Secondary (own Holm families): S4-H4 fs(locks_s2text) - fs(locks_instr); S4-H5 fs(locks_s2text) - fs(locks_signals);
S4-H6 (two-sided) the interaction [fs(locks_s2text) - fs(locks_instr)] - [fs(locks_signals) - fs(locks)].
A test runs only if at least 96 of its 128 clusters (75 %) enter; a cluster enters a test only with every config the
test needs. The pooled test uses the models whose own test runs. Claims are fixed by the plan ("Claims").
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import core7 as C  # noqa: E402

MODELS = C.MODELS
SHORT = C.SHORT
POOLED = C.POOLED
CONFIGS = C.CONFIGS
TWO, INSTR, SIGNALS, BUNDLE = CONFIGS
FAMILIES = C.FAMILIES
MULTI_FAMILIES = C.MULTI_FAMILIES
INSTANCES = 16
SEEDS = (0,)
REGISTERED_CLUSTERS = len(FAMILIES) * INSTANCES  # 128 per model
MIN_CLUSTERS = int(math.ceil(REGISTERED_CLUSTERS * 0.75 - 1e-9))  # 96
ALPHA = 0.05
FLOOR_FAILURES = 5  # fewer failed episodes than this under locks_s2text: the model's tests are at the floor
N_BOOT = C.N_BOOT
PRIMARY = ("H1", "H2", "H3")
SECONDARY = ("H4", "H5", "H6")
HYPOTHESES = PRIMARY + SECONDARY
NEEDS = {"H1": (TWO, BUNDLE), "H2": CONFIGS, "H3": CONFIGS, "H4": (TWO, INSTR), "H5": (TWO, SIGNALS), "H6": CONFIGS}
KIND = {"H6": "two_sided"}  # all others one-sided ("greater")
NAMES = {h: f"S4-{h}" for h in HYPOTHESES}
CLAIMS = {"H1": "The Study 3 lock bundle lowered contended integrity failures against the Study 2 lock text",
          "H2": "The bundle's instruction lowered contended integrity failures (averaged over the two signal levels)",
          "H3": "The bundle's two signals lowered contended integrity failures (averaged over the two instruction levels)",
          "H4": "The instruction alone (without the signals) lowered contended integrity failures against the Study 2 lock text",
          "H5": "The signals alone (without the instruction) lowered contended integrity failures against the Study 2 lock text"}


def cluster_value(h: str, fs: Mapping[str, float]) -> float:
    if h == "H1":
        return fs[TWO] - fs[BUNDLE]
    if h == "H2":
        return (fs[TWO] + fs[SIGNALS]) / 2 - (fs[INSTR] + fs[BUNDLE]) / 2
    if h == "H3":
        return (fs[TWO] + fs[INSTR]) / 2 - (fs[SIGNALS] + fs[BUNDLE]) / 2
    if h == "H4":
        return fs[TWO] - fs[INSTR]
    if h == "H5":
        return fs[TWO] - fs[SIGNALS]
    if h == "H6":  # interaction: the instruction's effect without the signals minus with them
        return (fs[TWO] - fs[INSTR]) - (fs[SIGNALS] - fs[BUNDLE])
    raise ValueError(h)


# ---------------------------------------------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------------------------------------------

def select(recs: Sequence[Dict[str, Any]], allow_dry_run: bool) -> Dict[str, Any]:
    """Never-data rules and exclusions (plan, "Data inclusion and exclusion"). Contended episodes only. If an episode id
    has more than one transcript, the earliest is used. An episode is excluded (alone: the cluster then lacks that config
    and leaves every test that needs it) if an agent ended truncated, provider_error, error, refusal or content_filter,
    or its last completion stopped content_filter or refusal, or (Qwen) a completion was not served by Alibaba."""
    log: Dict[str, Any] = {"never_data": {}, "counts": {}, "excluded": []}

    def bump(d: Dict[str, int], k: str, n: int = 1) -> None:
        d[k] = d.get(k, 0) + n
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in recs:
        why = None
        if r["study"] not in (4, "4"):
            why = "not_study4"
        elif r["dry_run"] and not allow_dry_run:
            why = "dry_run"
        elif r["config"] not in CONFIGS or r["start"] != "together":
            why = f"unregistered_condition:{r['config']}@{r['start']}"
        elif r["model"] not in MODELS:
            why = "unregistered_model"
        elif r["n_agents"] != 2 or r["aware"] or r["probe"] or r["arm"] != "contended":
            why = "unregistered_cell"
        elif r["family"] not in FAMILIES or not 0 <= r["instance"] < INSTANCES or r["seed"] not in SEEDS:
            why = "unregistered_unit"
        if why:
            bump(log["never_data"], why)
            continue
        groups.setdefault(r["id"], []).append(r)
    main: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    as_is: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for eid in sorted(groups):
        tries = sorted(groups[eid], key=lambda r: r["order_key"])
        chosen = tries[0]
        if len(tries) > 1:
            bump(log["counts"], "duplicate_transcripts_ignored", len(tries) - 1)
        key = (chosen["model"], chosen["config"], chosen["family"], chosen["instance"])
        as_is[key] = chosen
        why = "wrong_host" if chosen["host_bad"] else ("agent_error_or_refusal" if chosen["exclusion_trigger"] else None)
        if why:
            bump(log["counts"], why)
            log["excluded"].append({"key": list(map(str, key)), "reason": why})
        else:
            main[key] = chosen
    log["cap_truncated_episodes"] = sum(1 for r in main.values() if r["cap_truncated"])
    return {"main": main, "as_is": as_is, "log": log}


# ---------------------------------------------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------------------------------------------

def values_for(sample: Mapping[Tuple[Any, ...], Dict[str, Any]], model: str, h: str, metric: str = "fs") -> Dict[Tuple[Any, ...], float]:
    out = {}
    for fam in FAMILIES:
        for inst in range(INSTANCES):
            recs = {c: sample.get((model, c, fam, inst)) for c in NEEDS.get(h, CONFIGS)}
            if any(r is None for r in recs.values()):
                continue
            out[(fam, inst)] = cluster_value(h, {c: float(r[metric]) for c, r in recs.items()})
    return out


def pooled_values(per_model: Mapping[str, Mapping[Tuple[Any, ...], float]]) -> Dict[Tuple[Any, ...], float]:
    common = set.intersection(*(set(v) for v in per_model.values())) if per_model else set()
    return {k: sum(v[k] for v in per_model.values()) / len(per_model) for k in sorted(common)}


def run_suite(sample: Mapping[Tuple[Any, ...], Dict[str, Any]], n_boot: int, metric: str = "fs",
              sens: Optional[int] = None, invalid: Sequence[str] = (),
              stage: Optional[Mapping[str, str]] = None) -> List[Dict[str, Any]]:
    """Every confirmatory test. A model in ``invalid`` (check C1) is reported as invalid and enters no Holm family and
    no pooled test. The pooled test uses the models whose own test of that hypothesis runs (at least 2). ``stage``:
    model -> the decision of the registered Fable stage rule (floor_gate.json); "floor" labels its tests "not run"."""
    stage = stage or {}
    tests: List[Dict[str, Any]] = []
    fs_two = {m: sum(int(r["fs"]) for k, r in sample.items() if k[0] == m and k[1] == TWO) for m in MODELS}
    floor = {m: fs_two[m] < FLOOR_FAILURES for m in MODELS}  # always on fs_nonserializable (the Fable stage rule)
    for h in HYPOTHESES:
        kind = KIND.get(h, "greater")
        per = {m: values_for(sample, m, h, metric) for m in MODELS}
        runs = [m for m in MODELS if m not in invalid and len(per[m]) >= MIN_CLUSTERS]
        for m in list(MODELS) + [POOLED]:
            if m == POOLED:
                vals = pooled_values({x: per[x] for x in runs}) if len(runs) >= 2 else {}
            else:
                vals = per[m]
            entry = {"test": h, "model": m, "config": "s4", "id": f"{h}|{SHORT.get(m, m)}", "n_clusters": len(vals),
                     "min_units": MIN_CLUSTERS, "kind": kind, "primary": h in PRIMARY,
                     "models_pooled": [SHORT[x] for x in runs] if m == POOLED else None}
            if m in invalid:
                entry.update(status="invalid", estimate=None, p=None)
            elif len(vals) < MIN_CLUSTERS:
                entry.update(status="not_run_floor" if stage.get(m) == "floor" else "not_tested", estimate=None, p=None)
                if stage.get(m) == "stage1_incomplete":
                    entry["note"] = "Fable stage 1 incomplete: stage 2 not run"
            else:
                r = C.run_test(h, m, "s4", vals, kind, None, n_boot, sens=sens)
                entry.update(status="tested", **{k: v for k, v in r.items() if not k.startswith("_")})
                entry["_values"] = r.get("_values")
            tests.append(entry)
    for h in HYPOTHESES:
        members = [t for t in tests if t["test"] == h and t["status"] == "tested"]
        if not members:
            continue
        adj = C.holm([t["p"] for t in members])
        for t, a in zip(members, adj):
            t["p_adj"], t["holm_family_size"] = a, len(members)
            t["reject"] = a is not None and a < ALPHA
    for t in tests:
        t.setdefault("reject", None)
        t.setdefault("p_adj", None)
        t["floor"] = floor.get(t["model"], False)
        t["failed_under_s2text"] = fs_two.get(t["model"])
        t["claim"] = claim_text(t)
    return tests


def claim_text(t: Mapping[str, Any]) -> str:
    if t["status"] == "invalid":
        return "Invalid: lock-safety check C1 failed or could not run for this model."
    if t["status"] == "not_run_floor":
        return (f"Not run: floor (the registered stage rule found fewer than {FLOOR_FAILURES} failed episodes under the "
                f"Study 2 lock text).")
    if t["status"] != "tested":
        return f"Not tested ({t['n_clusters']} of {REGISTERED_CLUSTERS} clusters entered; at least {MIN_CLUSTERS} needed)."
    if t["test"] == "H6":
        lo, hi = t["ci95"]
        if t["reject"]:
            how = ("on the failure-rate scale, the drop from one part is smaller when the other part is present; "
                   "this is expected near zero failures and when each part removes a share of the failures, and is not "
                   "evidence that the parts overlap" if t["estimate"] > 0 else
                   "on the failure-rate scale, the drop from one part is larger when the other part is present")
            return f"Interaction {t['estimate']:.2f} (95 % [{lo:.2f}, {hi:.2f}], unadjusted): {how}."
        return f"No claim about the interaction (estimate {t['estimate']:.2f}); not evidence that the effects add up."
    if t["reject"]:
        return (f"{CLAIMS[t['test']]} by {t['estimate']:.2f} (one-sided 95 % lower bound {t['ci90'][0]:.2f}, "
                f"unadjusted).")
    if t.get("floor"):
        return (f"No claim: floor (fewer than {FLOOR_FAILURES} failed episodes under the Study 2 lock text), "
                f"so the test could not show a drop.")
    return f"No claim (estimate {t['estimate']:.2f}); not evidence of no effect."


# ---------------------------------------------------------------------------------------------------------------
# Checks, descriptives, sensitivity
# ---------------------------------------------------------------------------------------------------------------

def checks(as_is: Mapping[Tuple[Any, ...], Dict[str, Any]], transcripts_signals: Mapping[str, Dict[str, int]]) -> Dict[str, Any]:
    me = sum(len(r.get("me_violations") or []) for r in as_is.values())
    me_unchecked = sum(1 for r in as_is.values() if r.get("me_violations") is None)
    bad_signals = {k: v for k, v in transcripts_signals.items()
                   if k.split("|")[1] in (TWO, INSTR) and (v["waits"] or v["locked_reads"])}
    return {"lock_safety": {"violations": me, "episodes_not_checked": me_unchecked, "ok": me == 0 and me_unchecked == 0},
            "signals_only_where_offered": {"bad_cells": bad_signals, "ok": not bad_signals},
            "signal_counts": dict(sorted(transcripts_signals.items()))}


def share(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def descriptives(sample: Mapping[Tuple[Any, ...], Dict[str, Any]], n_boot: int) -> Dict[str, Any]:
    d: Dict[str, Any] = {"fs": {}, "mechanisms": {}, "protocol": {}, "basis": {}}
    for m in MODELS:
        for c in CONFIGS:
            eps = [r for k, r in sample.items() if k[0] == m and k[1] == c]
            d["fs"][f"{SHORT[m]}|{c}"] = {"episodes": len(eps), "failed": sum(r["fs"] for r in eps),
                                          "share": share([r["fs"] for r in eps])}
            d["basis"][f"{SHORT[m]}|{c}"] = share([r["basis"] for r in eps])
            d.setdefault("served", {})[f"{SHORT[m]}|{c}"] = sorted({s for r in eps for s in r.get("served", [])})
            mech = {"failed": 0, "read_then_lock": 0, "own_only": 0, "no_lock": 0, "other": 0}
            for r in eps:
                if not r["fs"]:
                    continue
                mech["failed"] += 1
                ms = [x for x in r["mechanisms"] if x in ("read_then_lock", "own_only", "no_lock")]
                if len(ms) == 1:
                    mech[ms[0]] += 1
                else:
                    mech["other"] += 1
            d["mechanisms"][f"{SHORT[m]}|{c}"] = mech
            codes = [r["order"][a] for r in eps for a in r["agents"]]
            multi = [r["agents"][a]["lock_scope"] for r in eps if r["family"] in MULTI_FAMILIES for a in r["agents"]]
            rbl = [bool(a["read_before_lock"]) for r in eps for a in r["agents"].values() if a["read_before_lock"] is not None]
            d["protocol"][f"{SHORT[m]}|{c}"] = {
                "agents": len(codes), "lock_first": share([x == "lock_first" for x in codes]),
                "read_then_lock": share([x == "read_then_lock" for x in codes]), "no_lock": share([x == "no_lock" for x in codes]),
                "scope_all": share([x == "all" for x in multi]), "read_before_lock_share": share(rbl), "rbl_eligible": len(rbl)}
    return d


def sensitivities(sel: Mapping[str, Any], main_tests: Sequence[Mapping[str, Any]], n_boot: int,
                  invalid: Sequence[str] = (), stage: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    main_rej = {t["id"]: t["reject"] for t in main_tests}

    def changed(tests: Sequence[Mapping[str, Any]]) -> List[str]:  # by reject flag only (the Study 3 lesson)
        return [t["id"] for t in tests if t["id"] in main_rej and t["status"] == "tested" and t["reject"] != main_rej[t["id"]]]
    # S1: excluded episodes kept as scored
    s1 = run_suite(sel["as_is"], n_boot, sens=1, invalid=invalid, stage=stage)
    out["S1_exclusions_kept"] = {"episodes_added": len(sel["as_is"]) - len(sel["main"]), "changed": changed(s1)}
    # S2: template level (family means, 8 units): exact sign-flip over 2^8; reported p only (no Holm, no verdict)
    out["S2_family_level"] = {t["id"]: t.get("p_family_level") for t in main_tests if t["status"] == "tested"}
    # S3: Holm within each model across the primary H1 to H3
    s3 = {}
    for m in list(MODELS) + [POOLED]:
        mt = [t for t in main_tests if t["model"] == m and t["status"] == "tested" and t["primary"]]
        adj = C.holm([t["p"] for t in mt])
        for t, a in zip(mt, adj):
            s3[t["id"]] = {"p_adj": a, "reject": a is not None and a < ALPHA, "changed": (a is not None and a < ALPHA) != t["reject"]}
    out["S3_holm_within_model"] = s3
    # S4: the basis-cycle verdict in place of fs_nonserializable
    s4 = run_suite(sel["main"], n_boot, metric="basis", sens=4, invalid=invalid, stage=stage)
    out["S4_basis_cycle"] = {"changed": changed(s4), "tests": [{k: t.get(k) for k in ("id", "estimate", "p", "p_adj", "reject")} for t in s4]}
    # S5: cap_truncated episodes excluded
    keep = {k: r for k, r in sel["main"].items() if not r["cap_truncated"]}
    s5 = run_suite(keep, n_boot, sens=5, invalid=invalid, stage=stage)
    out["S5_cap_truncated_excluded"] = {"episodes_removed": len(sel["main"]) - len(keep), "changed": changed(s5)}
    return out


# ---------------------------------------------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------------------------------------------

def fmt(x: Optional[float]) -> str:
    return r"\textemdash{}" if x is None else f"{x:.2f}"


def pfmt(p: Optional[float]) -> str:
    return r"\textemdash{}" if p is None else ("$<$0.001" if p < 0.001 else f"{p:.3f}")


def macro_name(*parts: str) -> str:
    s = "Siv" + "".join(p[:1].upper() + p[1:] for p in parts)
    return "".join(C._DIGITS.get(ch, ch) if ch.isdigit() else ch for ch in s if ch.isalnum())


def numbers_tex(res: Mapping[str, Any]) -> str:
    V: Dict[str, str] = {}
    for t in res["tests"]:
        m = SHORT.get(t["model"], "Pooled")
        base = (t["test"], m)
        V[macro_name(*base, "Est")] = fmt(t.get("estimate"))
        if t.get("ci95"):
            V[macro_name(*base, "Lo")], V[macro_name(*base, "Hi")] = fmt(t["ci95"][0]), fmt(t["ci95"][1])
        V[macro_name(*base, "P")] = pfmt(t.get("p"))
        V[macro_name(*base, "Padj")] = pfmt(t.get("p_adj"))
        V[macro_name(*base, "N")] = str(t["n_clusters"])
        V[macro_name(*base, "Reject")] = ({True: "yes", False: "no"}[t["reject"]] if t["status"] == "tested"
                                          else t["status"].replace("_", " "))
    for k, v in res["descriptive"]["fs"].items():
        m, c = k.split("|")
        V[macro_name("Fs", m, C.CFG_SHORT[c])] = fmt(v["share"])
        V[macro_name("Failed", m, C.CFG_SHORT[c])] = str(v["failed"])
        V[macro_name("Episodes", m, C.CFG_SHORT[c])] = str(v["episodes"])
    V[macro_name("Files")] = f"{res['inputs']['n_files']:,}".replace(",", "{,}")
    V[macro_name("Excluded")] = str(len(res["selection"]["excluded"]))
    V[macro_name("MeViolations")] = str(res["checks"]["lock_safety"]["violations"])
    V[macro_name("NBoot")] = f"{N_BOOT:,}".replace(",", "{,}")
    V[macro_name("MinClusters")] = str(MIN_CLUSTERS)
    V[macro_name("Clusters")] = str(REGISTERED_CLUSTERS)
    lines = ["% GENERATED by analysis7/analyze7.py -- do not edit.", f"% analyze7.py sha256 {res['analyze7_sha256']}",
             f"% core7.py sha256 {res['core7_sha256']}", f"% inputs: {res['inputs']['n_files']} transcripts, list sha256 {res['inputs']['list_sha256']}"]
    lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in sorted(V.items())]
    return "\n".join(lines) + "\n"


def stage_decisions(base: str, allow_dry_run: bool) -> Dict[str, str]:
    """model -> the last decision of the registered Fable stage rule (src7/floor_gate7.py's record)."""
    path = os.path.join(base, "floor_gate_dry.json" if allow_dry_run else "floor_gate.json")
    out: Dict[str, str] = {}
    if os.path.exists(path):
        for ln in open(path).read().splitlines():
            if ln.strip():
                d = json.loads(ln)
                out[d["model"]] = d["decision"]
    return out


def sha(p: str) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def run(base: str, out: str, allow_dry_run: bool, n_boot: int, src_dir: Optional[str]) -> Dict[str, Any]:
    dirs = C.discover(base, allow_dry_run)
    recs, names, signals = [], [], {}
    for path, tr in C.read_transcripts(dirs):
        names.append(os.path.basename(path))
        recs.append(C.normalize(tr, path, src_dir, allow_dry_run))
        key = f"{SHORT.get(tr.get('model'), tr.get('model'))}|{tr.get('config')}"
        s = signals.setdefault(key, {"episodes": 0, "waits": 0, "locked_reads": 0})
        s["episodes"] += 1
        for c in (tr.get("ledger") or {}).get("calls") or []:
            r = c.get("response") or {}
            s["waits"] += int("waited_rounds" in r)
            s["locked_reads"] += int(r.get("locked") is True)
    sel = select(recs, allow_dry_run)
    # C1: a model with a lock-safety violation, or an episode the check could not run on, is invalid
    invalid = sorted({r["model"] for r in sel["as_is"].values()
                      if r.get("me_violations") or r.get("me_violations") is None})
    stage = stage_decisions(base, allow_dry_run)
    tests = run_suite(sel["main"], n_boot, invalid=invalid, stage=stage)
    res: Dict[str, Any] = {
        "analyze7_sha256": sha(os.path.abspath(__file__)), "core7_sha256": sha(os.path.join(HERE, "core7.py")),
        "registration": "PREREGISTRATION_STUDY4.md",
        "inputs": {"n_files": len(names), "list_sha256": hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest(),
                   "dry_run": allow_dry_run},
        "selection": {"excluded": sel["log"]["excluded"], "never_data": sel["log"]["never_data"], "counts": sel["log"]["counts"],
                      "cap_truncated_episodes": sel["log"]["cap_truncated_episodes"], "main_episodes": len(sel["main"])},
        "tests": [{k: v for k, v in t.items() if not k.startswith("_")} for t in tests],
        "checks": checks(sel["as_is"], signals),
        "descriptive": descriptives(sel["main"], n_boot),
        "sensitivity": sensitivities(sel, tests, n_boot, invalid, stage),
        "fable_stage_rule": stage,
        "invalid_models": invalid,
    }
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump(res, f, indent=1, sort_keys=True, default=str)
    with open(os.path.join(out, "numbers.tex"), "w") as f:
        f.write(numbers_tex(res))
    return res


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--base", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--allow-dry-run", action="store_true")
    a.add_argument("--n-boot", type=int, default=N_BOOT)
    a.add_argument("--src", default=os.path.join(ROOT, "src7"))
    args = p.parse_args(argv)
    res = run(args.base, args.out, args.allow_dry_run, args.n_boot, args.src)
    print(f"{len(res['tests'])} tests; {res['selection']['main_episodes']} episodes in the main analysis; "
          f"wrote {args.out}/results.json and numbers.tex")
    for t in res["tests"]:
        print(f"  {NAMES[t['test']]} {SHORT.get(t['model'], 'pooled'):7s} {t['claim']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
