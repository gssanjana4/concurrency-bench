#!/usr/bin/env python3
"""EXPLORATORY analyses from saved results (no model calls; not confirmatory).

    python3 explore4.py --analysis DIR

Reads (read-only): DIR/provenance.json, the analysed CSVs it lists, and the
transcripts next to each CSV (``transcripts/<episode_id>.json``). Rows are
filtered exactly as analyze4 filters them (``analyze4.load``). Task intents are
rebuilt with the frozen ``instances4.build`` (as analyze4's H5 does).

Writes ONLY ``DIR/exploratory_posthoc.json``. It refuses to write any file that
analyze4 or run_analysis.py writes (confirmatory.json, confirmatory.md,
numbers.json, tables.md, provenance.json).

Labels: every block carries ``label`` = "EXPLORATORY (registered)" when the
prereg's "Exploratory analyses" list names it, else "EXPLORATORY (post hoc)".

Aggregation (same as analyze4's descriptive rates): within a cell, numerators
and denominators are summed per task instance (template, instance index) over
seeds and agents; the estimate is the unweighted mean of instance values over
instances with a non-zero denominator; the interval is analyze4.wilson on that
mean with m = number of instances (an approximation, descriptive only).
Pooled counts (num, den) are reported too.

Definitions (agent = one agent in one episode; n = 2, contended templates
unless stated; "intent" = instances4.build(template, instance, n).intents[agent]):

E1  integrity vs goodput, per (model, config, aware):
    fulfil   = sum n_fulfilled / sum n_abandon_eligible      [post hoc]
               (eligible = ended agents whose intent was valid when they ended,
               or fulfilled; fulfil = 1 - abandoned whenever every eligible agent
               is fulfilled or abandoned, which score4's definitions imply)
    complete = sum n_fulfilled / sum n_agents                [post hoc]
    giveup   = sum n_unnecessary_give_up / sum n_conflict_agents   [registered]
    clean    = share of episodes with non_serializable = 0 and n_abandoned = 0  [post hoc]
    The same four on inventory_still_valid alone (every intent valid in every order).
E3  CAS as form-filling, cas_available, aware off            [post hoc]
    cas_ctl / cas_cont: share of agents with choice ``cas`` on budget_control
    (control) / on contended templates (CSV ``choices``).
    cas_uncont: among committed update_record calls whose writer had read the
    record before (last successful get_record of it by the same agent) and on
    which no other agent committed a write (update_record or claim) between that
    read and the write, the share carrying a non-null expected_version. Pooled
    over all templates (incl. control); counts only.
E4  first response after a concurrency rejection             [post hoc]
    Eligible agent: some update_record/claim by it on a record in intent.writes was
    rejected with reason version_conflict (409), claim_conflict (409) or
    locked_by_other (423) (score4's "concurrency rejection"). k = the first such
    call, r = its record, W = the agent's next update_record/claim call (any
    outcome), R = successful get_record calls of r by the agent strictly between
    k and W (or after k if there is no W). Exactly one code, first match wins:
      already_fulfilled  no W and the agent fulfilled its intent
      cut_off            no W, not fulfilled, end_reason != returned (turn cap, stall, episode end)
      giveup_valid       no W, returned, not fulfilled, intent valid when it ended
      giveup_invalid     no W, returned, not fulfilled, intent no longer valid
      other_record       W writes a record other than r
      bypass             W is update_record on r without expected_version in a config
                         with conditional writes (cas_available, cas_required)
      reread_retry       R non-empty and W carries no expected_version or the version
                         returned by the last call in R
      stale_retry        otherwise, if W carries no expected_version, the same
                         expected_version as k, or a version other than the last read
      version_from_error otherwise (W carries a new expected_version, e.g. the one in the
                         409 body, without re-reading r)
    Note: stale_retry with R non-empty means a re-read whose version was not used.
E5  write-skew preventability (category write_skew)         [post hoc]
    promote: agent sent an update_record with non-null expected_version to a record
             not in intent.writes that committed or was rejected as version_conflict
             (materialising the conflict); denominator: all agents
    verify:  among agents that committed a write to a record in intent.writes, a
             successful get_record of a record in intent.reads - intent.writes after
             their first such committed write
    compensate: among the same agents, a later committed update_record to the same
             record whose value equals (records.normalize_value) the value that record
             had before their first committed write to it (an exact undo)
    skew_ws: primary label write_skew among write-skew-template episodes, per config.
E6  template robustness
    tpl: non_serializable per (model, template, config), aware off   [registered]
    loto: confirmatory point estimates recomputed with each template left out
          (analyze4._spec / _cluster_values on complete clusters; estimates only,
          no tests)                                                  [post hoc]
E7  lock quality (config locks, both aware levels; agents with a successful acquire_lock)
    cover:   at its first update_record/claim, the agent held an unexpired lock it had
             acquired on every record in intent.writes                [post hoc]
    release: every record it locked had a successful release_lock after its last
             successful acquire_lock on it                            [post hoc]
    leak:    score4 lock_leak                                         [registered]
E8  budget pressure and truncation                            [registered: counted per cell]
    turncap: share of agents whose end reason is turn_cap; completions: mean model
    completions per agent; trunc: episodes with a truncated agent / episodes, per model
    (all phases).
E10 competence proxy
    ctl_fulfil: sum n_fulfilled / sum n_agents on budget_control, aware off, n = 2,
    all configs pooled [post hoc]; invalid: invalid tool calls per agent, aware off,
    n = 2, all templates [registered: counted per cell].
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import OrderedDict, defaultdict

from pipeline_common import SRC4, require_freeze, sha256_file

sys.dont_write_bytecode = True
sys.path.insert(0, SRC4)
import analyze4 as A  # noqa: E402  (frozen; read-only)

OUT_NAME = "exploratory_posthoc.json"
PROTECTED = frozenset({"confirmatory.json", "confirmatory.md", "numbers.json", "tables.md", "provenance.json"})
REG, POST = "EXPLORATORY (registered)", "EXPLORATORY (post hoc)"
REJECT = ("version_conflict", "claim_conflict", "locked_by_other")
WRITE_TOOLS = ("update_record", "claim")
CAS_CONFIGS = ("cas_available", "cas_required")
E4_CODES = ("reread_retry", "stale_retry", "version_from_error", "bypass", "other_record",
            "giveup_valid", "giveup_invalid", "cut_off", "already_fulfilled")
E4_CONFIGS = ("cas_available", "cas_required", "locks")
CONFIGS = ("none", "reread_only", "cas_available", "cas_required", "locks", "messages")
CONTROL = "budget_control"


# ------------------------------------------------------------------ aggregation
def inst_mean(items):
    """items: iterable of ((task, instance), num, den). analyze4-style instance mean + Wilson."""
    per = defaultdict(lambda: [0, 0])
    for key, num, den in items:
        per[key][0] += num
        per[key][1] += den
    vals = [n / d for n, d in per.values() if d > 0]
    num, den = sum(v[0] for v in per.values()), sum(v[1] for v in per.values())
    out = {"num": num, "den": den, "inst": len(vals), "est": None, "lo": None, "hi": None}
    if vals:
        p = sum(vals) / len(vals)
        lo, hi = A.wilson(p, len(vals))
        out.update(est=p, lo=lo, hi=hi)
    return out


def ik(r):
    return (r["task"], str(r["instance"]))


# ------------------------------------------------------------------ inputs
def load(paths):
    rows, _, _ = A.load(paths)
    keep = {r["episode_id"] for r in rows}
    extra = {}
    for p in paths:
        with open(p, newline="") as f:
            for raw in csv.DictReader(f):
                if raw["episode_id"] in keep and raw["episode_id"] not in extra:
                    extra[raw["episode_id"]] = raw
    for r in rows:
        x = extra[r["episode_id"]]
        r["n_fulfilled"] = int(x.get("n_fulfilled") or 0)
        r["end_reasons"] = dict(p.split(":", 1) for p in (x.get("end_reasons") or "").split(";") if ":" in p)
        r["completions"] = int(x.get("completions") or 0)
        r["invalid_calls"] = int(x.get("invalid_calls") or 0)
    return rows


_TASKS = {}


def intents_of(tr):
    import instances4
    import tasks4
    t = tr["task"]
    key = (t["factory"], t.get("instance"), tr["n_agents"])
    if key not in _TASKS:
        inst = t.get("instance")
        _TASKS[key] = (tasks4.CATALOG[t["factory"]](tr["n_agents"]) if inst in (None, A.PILOT)
                       else instances4.build(t["factory"], int(inst), tr["n_agents"]))
    return _TASKS[key].intents


def transcript_path(r):
    return os.path.join(os.path.dirname(os.path.abspath(r["source"])), "transcripts", r["episode_id"] + ".json")


# ------------------------------------------------------------------ per-agent coders (pure; unit-tested)
def _ev(c):
    return (c.get("args") or {}).get("expected_version")


def _read_version(c):
    v = c.get("read_version")
    if v is None:
        v = (c.get("response") or {}).get("version")
    return v


def code_post_rejection(calls, agent, writes, config, score_agent):
    """E4 code for one agent, or None if not eligible (see module docstring)."""
    mine = sorted((c for c in calls if c["agent_id"] == agent), key=lambda c: c["seq"])
    k = next((i for i, c in enumerate(mine) if c["tool"] in WRITE_TOOLS and c.get("reason") in REJECT
              and c.get("record_id") in writes), None)
    if k is None:
        return None
    rej = mine[k]
    r = rej.get("record_id")
    after = mine[k + 1:]
    w = next((i for i, c in enumerate(after) if c["tool"] in WRITE_TOOLS), None)
    window = after if w is None else after[:w]
    reads = [c for c in window if c["tool"] == "get_record" and c.get("status") == 200 and c.get("record_id") == r]
    if w is None:
        if score_agent.get("fulfilled"):
            return "already_fulfilled"
        if score_agent.get("end_reason") != "returned":
            return "cut_off"
        return "giveup_valid" if score_agent.get("valid_at_end") else "giveup_invalid"
    W = after[w]
    if W.get("record_id") != r:
        return "other_record"
    ev = _ev(W) if W["tool"] == "update_record" else None
    if W["tool"] == "update_record" and config in CAS_CONFIGS and ev is None:
        return "bypass"
    if reads and (ev is None or ev == _read_version(reads[-1])):
        return "reread_retry"
    if ev is None or ev == _ev(rej) or reads:
        return "stale_retry"
    return "version_from_error"


def ws_agent(calls, effects, agent, reads, writes, normalize):
    """E5 flags for one agent: dict(promote, committed, verify, compensate)."""
    mine = sorted((c for c in calls if c["agent_id"] == agent), key=lambda c: c["seq"])
    others = set(reads) - set(writes)
    promote = any(c["tool"] == "update_record" and c.get("record_id") not in writes and _ev(c) is not None
                  and (c.get("committed") or c.get("reason") == "version_conflict") for c in mine)
    eff = {e["seq"]: e for e in effects}
    own = [c for c in mine if c["tool"] in WRITE_TOOLS and c.get("committed") and c.get("record_id") in writes]
    if not own:
        return {"promote": promote, "committed": False, "verify": False, "compensate": False}
    first = own[0]
    verify = any(c["tool"] == "get_record" and c.get("status") == 200 and c.get("record_id") in others
                 and c["seq"] > first["seq"] for c in mine)
    compensate = False
    firsts = {}
    for c in own:
        e = eff.get(c.get("effect_seq"))
        if e is None:
            continue
        rid = c["record_id"]
        if rid not in firsts:
            firsts[rid] = normalize(e["old_value"])
        elif c["tool"] == "update_record" and normalize(e["new_value"]) == firsts[rid]:
            compensate = True
    return {"promote": promote, "committed": True, "verify": verify, "compensate": compensate}


def lock_agent(calls, agent, writes):
    """E7 flags for one agent: None if it never acquired a lock, else dict(cover, release)."""
    mine = sorted((c for c in calls if c["agent_id"] == agent), key=lambda c: c["seq"])
    acq = [c for c in mine if c["tool"] == "acquire_lock" and c.get("status") == 200]
    if not acq:
        return None
    first_w = next((c for c in mine if c["tool"] in WRITE_TOOLS), None)
    cover = False
    if first_w is not None:
        cover = True
        for r in writes:
            held = False
            for c in mine:
                if c["seq"] >= first_w["seq"] or c.get("record_id") != r:
                    continue
                if c["tool"] == "acquire_lock" and c.get("status") == 200:
                    exp = c.get("lease_expires_at")
                    held = exp is None or first_w["step"] < exp
                elif c["tool"] == "release_lock" and c.get("status") == 200:
                    held = False
            cover = cover and held
    release = True
    for r in {c.get("record_id") for c in acq}:
        last_acq = max(c["seq"] for c in acq if c.get("record_id") == r)
        release = release and any(c["tool"] == "release_lock" and c.get("status") == 200 and c.get("record_id") == r
                                  and c["seq"] > last_acq for c in mine)
    return {"cover": cover, "release": release}


def uncontended_writes(calls):
    """E3: list of has_expected_version flags for committed update_record calls with a prior own read and no
    foreign committed write to the record between that read and the write."""
    calls = sorted(calls, key=lambda c: c["seq"])
    out = []
    for i, c in enumerate(calls):
        if c["tool"] != "update_record" or not c.get("committed"):
            continue
        a, r = c["agent_id"], c.get("record_id")
        read = next((x for x in reversed(calls[:i]) if x["agent_id"] == a and x["tool"] == "get_record"
                     and x.get("status") == 200 and x.get("record_id") == r), None)
        if read is None:
            continue
        foreign = any(x["agent_id"] != a and x["tool"] in WRITE_TOOLS and x.get("committed") and x.get("record_id") == r
                      and read["seq"] < x["seq"] < c["seq"] for x in calls)
        if not foreign:
            out.append(_ev(c) is not None)
    return out


# ------------------------------------------------------------------ analyses
def cell(r):
    return (r["model"], r["config"], r["aware"])


def e1(rows):
    out = []
    groups = defaultdict(list)
    for r in rows:
        if r["n_agents"] == 2 and r["category"] != "control":
            groups[cell(r)].append(r)
    for (m, c, a), rs in sorted(groups.items(), key=lambda kv: tuple(map(str, kv[0]))):
        for scope, pool in (("contended", rs), ("still_valid", [r for r in rs if r["task"] == "inventory_still_valid"])):
            if not pool:
                continue
            rec = {"model": m, "config": c, "aware": a, "scope": scope}
            rec["fulfil"] = inst_mean((ik(r), r["n_fulfilled"], r["n_abandon_eligible"] or 0) for r in pool)
            rec["complete"] = inst_mean((ik(r), r["n_fulfilled"], r["n_choice_agents"]) for r in pool)
            rec["giveup"] = inst_mean((ik(r), r["n_unnecessary_give_up"], r["n_conflict_agents"] or 0) for r in pool)
            rec["clean"] = inst_mean((ik(r), int(not r["non_serializable"] and not r["n_abandoned"]), 1) for r in pool)
            rec["identity_ok"] = all(r["n_fulfilled"] + r["n_abandoned"] == (r["n_abandon_eligible"] or 0) for r in pool)
            out.append(rec)
    return {"label": POST + "; giveup: " + REG, "rows": out}


def e3(rows, transcripts):
    out = []
    for m in sorted({r["model"] for r in rows}):
        rs = [r for r in rows if r["model"] == m and r["config"] == "cas_available" and r["aware"] == 0 and r["n_agents"] == 2]
        cas = lambda pool: inst_mean((ik(r), sum("cas" in cs for cs in r["choices"].values()), r["n_choice_agents"]) for r in pool)  # noqa: E731
        flags = [f for r in rs for f in uncontended_writes(transcripts[r["episode_id"]]["ledger"]["calls"])
                 if r["episode_id"] in transcripts]
        out.append({"model": m, "cas_ctl": cas([r for r in rs if r["task"] == CONTROL]),
                    "cas_cont": cas([r for r in rs if r["category"] != "control"]),
                    "cas_uncont": {"k": sum(flags), "n": len(flags), "rate": (sum(flags) / len(flags)) if flags else None}})
    return {"label": POST, "rows": out}


def e4(rows, transcripts):
    out = []
    groups = defaultdict(list)
    for r in rows:
        if r["n_agents"] == 2 and r["category"] != "control" and r["config"] in E4_CONFIGS and r["episode_id"] in transcripts:
            groups[cell(r)].append(r)
    for (m, c, a), rs in sorted(groups.items(), key=lambda kv: tuple(map(str, kv[0]))):
        per_code = defaultdict(list)
        n_elig = defaultdict(int)
        for r in rs:
            tr = transcripts[r["episode_id"]]
            codes = defaultdict(int)
            elig = 0
            for agent, intent in intents_of(tr).items():
                code = code_post_rejection(tr["ledger"]["calls"], agent, set(intent.writes), c, tr["score"]["agents"][agent])
                if code is not None:
                    codes[code] += 1
                    elig += 1
            n_elig[ik(r)] += elig
            for code in E4_CODES:
                per_code[code].append((ik(r), codes[code], elig))
        rec = {"model": m, "config": c, "aware": a, "n_eligible": sum(n_elig.values())}
        rec["codes"] = {code: inst_mean(per_code[code]) for code in E4_CODES}
        out.append(rec)
    return {"label": POST, "codes": list(E4_CODES), "rows": out}


def e5(rows, transcripts):
    import records
    out = []
    groups = defaultdict(list)
    for r in rows:
        if r["n_agents"] == 2 and r["aware"] == 0 and r["task"] in A.WRITE_SKEW_TEMPLATES:
            groups[(r["model"], r["config"])].append(r)
    for (m, c), rs in sorted(groups.items()):
        pro, ver, comp = [], [], []
        for r in rs:
            tr = transcripts.get(r["episode_id"])
            if tr is None:
                continue
            n_pro = n_com = n_ver = n_cmp = 0
            for agent, intent in intents_of(tr).items():
                f = ws_agent(tr["ledger"]["calls"], tr["ledger"]["effects"], agent, intent.reads, set(intent.writes),
                             records.normalize_value)
                n_pro += f["promote"]
                n_com += f["committed"]
                n_ver += f["verify"]
                n_cmp += f["compensate"]
            pro.append((ik(r), n_pro, len(intents_of(tr))))
            ver.append((ik(r), n_ver, n_com))
            comp.append((ik(r), n_cmp, n_com))
        out.append({"model": m, "config": c, "promote": inst_mean(pro), "verify": inst_mean(ver), "compensate": inst_mean(comp),
                    "skew_ws": inst_mean((ik(r), int(r["label"] == "write_skew"), 1) for r in rs)})
    return {"label": POST, "rows": out}


def e6(rows, conf):
    tpl = []
    groups = defaultdict(list)
    for r in rows:
        if r["n_agents"] == 2 and r["aware"] == 0 and r["category"] != "control":
            groups[(r["model"], r["task"], r["config"])].append(r)
    for (m, t, c), rs in sorted(groups.items()):
        tpl.append({"model": m, "template": t, "config": c, "nonser": inst_mean((ik(r), r["non_serializable"], 1) for r in rs)})
    index = {}
    for r in rows:
        index.setdefault((r["model"], r["task"], str(r["instance"]), r["config"], r["aware"], r["n_agents"], r["seed"]), r)
    loto = []
    for h in A.HYPOTHESES:
        spec = A._spec(h)
        parts = ("i", "ii") if spec["kind"] == "h4b" else ("v",)
        for m in A.REGISTERED_MODELS:
            vals = {}  # template -> list of cluster value dicts
            for t in spec["templates"]:
                for i in spec["instances"]:
                    eps = {}
                    for need in spec["needs"]:
                        x = index.get((m, t, str(i)) + tuple(need))
                        if x is None:
                            break
                        eps[tuple(need)] = x
                    else:
                        vals.setdefault(t, []).append(A._cluster_values(spec, eps))
            for part in parts:
                allv = [v[part] for t in vals for v in vals[t]]
                rec = {"hypothesis": h, "part": part, "model": m, "full": (sum(allv) / len(allv)) if allv else None, "loo": {}}
                for t in spec["templates"]:
                    rest = [v[part] for u in vals if u != t for v in vals[u]]
                    rec["loo"][t] = (sum(rest) / len(rest)) if rest else None
                ok = [x for x in rec["loo"].values() if x is not None]
                rec["min"], rec["max"] = (min(ok), max(ok)) if ok else (None, None)
                rec["min_tpl"] = next((t for t, x in rec["loo"].items() if ok and x == rec["min"]), None)
                rec["max_tpl"] = next((t for t, x in rec["loo"].items() if ok and x == rec["max"]), None)
                # cross-check: full estimate equals analyze4's (when tested)
                tst = next(x for x in conf["hypotheses"][h]["tests"] if x["model"] == m)
                want = (tst.get("component_" + part) or {}).get("estimate") if part in ("i", "ii") else tst.get("estimate")
                rec["matches_analyze4"] = None if tst["status"] != "tested" or want is None or rec["full"] is None \
                    else abs(want - rec["full"]) < 1e-9
                loto.append(rec)
    return {"label": "per-template: " + REG + "; leave-one-template-out: " + POST, "tpl": tpl, "loto": loto}


def e7(rows, transcripts):
    out = []
    groups = defaultdict(list)
    for r in rows:
        if r["n_agents"] == 2 and r["config"] == "locks" and r["category"] != "control" and r["episode_id"] in transcripts:
            groups[(r["model"], r["aware"])].append(r)
    for (m, a), rs in sorted(groups.items()):
        n = cov = rel = leak = 0
        for r in rs:
            tr = transcripts[r["episode_id"]]
            for agent, intent in intents_of(tr).items():
                f = lock_agent(tr["ledger"]["calls"], agent, set(intent.writes))
                if f is None:
                    continue
                n += 1
                cov += f["cover"]
                rel += f["release"]
                leak += bool(tr["score"]["agents"][agent].get("lock_leak"))
        out.append({"model": m, "aware": a, "n_lockers": n, "cover": cov, "release": rel, "leak": leak,
                    "stall_episodes": sum(int(bool(transcripts[r["episode_id"]]["score"].get("stall"))) for r in rs),
                    "episodes": len(rs)})
    return {"label": "cover, release: " + POST + "; leak, stall: " + REG, "rows": out}


def e8(rows):
    out = []
    groups = defaultdict(list)
    for r in rows:
        if r["n_agents"] == 2 and r["aware"] == 0 and r["category"] != "control":
            groups[(r["model"], r["config"])].append(r)
    for (m, c), rs in sorted(groups.items()):
        n_ag = sum(r["n_choice_agents"] for r in rs)
        out.append({"model": m, "config": c,
                    "turncap": inst_mean((ik(r), sum(v == "turn_cap" for v in r["end_reasons"].values()), r["n_choice_agents"]) for r in rs),
                    "completions_per_agent": (sum(r["completions"] for r in rs) / n_ag) if n_ag else None})
    trunc = []
    for m in sorted({r["model"] for r in rows}):
        rs = [r for r in rows if r["model"] == m]
        trunc.append({"model": m, "k": sum(bool(r["truncated"]) for r in rs), "n": len(rs)})
    return {"label": REG + " (turn-cap endings and truncation are counted per cell in the prereg)", "rows": out, "trunc": trunc}


def e10(rows):
    out = []
    for m in sorted({r["model"] for r in rows}):
        rs = [r for r in rows if r["model"] == m and r["aware"] == 0 and r["n_agents"] == 2]
        ctl = [r for r in rs if r["task"] == CONTROL]
        n_ag = sum(r["n_choice_agents"] for r in rs)
        out.append({"model": m, "ctl_fulfil": inst_mean((ik(r), r["n_fulfilled"], r["n_choice_agents"]) for r in ctl),
                    "invalid_per_agent": (sum(r["invalid_calls"] for r in rs) / n_ag) if n_ag else None})
    return {"label": "ctl_fulfil: " + POST + "; invalid calls: " + REG, "rows": out}


def run(analysis):
    prov = json.load(open(os.path.join(analysis, "provenance.json")))
    conf = json.load(open(os.path.join(analysis, "confirmatory.json")))["registered"]
    paths = prov["analyzed_paths"]
    rows = load(paths)
    transcripts, missing = {}, 0
    for r in rows:
        p = transcript_path(r)
        if os.path.exists(p):
            with open(p) as f:
                transcripts[r["episode_id"]] = json.load(f)
        else:
            missing += 1
    return OrderedDict([
        ("label", "EXPLORATORY: computed by latex/explore4.py from saved CSVs and transcripts; no model calls; "
                  "supports no confirmatory claim"),
        ("dry_run", bool(prov["dry_run"])),
        ("inputs", [{"path": os.path.abspath(p), "sha256": sha256_file(p)} for p in paths]),
        ("n_rows", len(rows)), ("n_transcripts", len(transcripts)), ("missing_transcripts", missing),
        ("E1", e1(rows)), ("E3", e3(rows, transcripts)), ("E4", e4(rows, transcripts)), ("E5", e5(rows, transcripts)),
        ("E6", e6(rows, conf)), ("E7", e7(rows, transcripts)), ("E8", e8(rows)), ("E10", e10(rows)),
    ])


def write(analysis, data, name=OUT_NAME):
    if os.path.basename(name) in PROTECTED:
        raise SystemExit(f"REFUSING to write {name}: confirmatory/analyze4 output")
    path = os.path.join(analysis, name)
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis", required=True)
    a = ap.parse_args(argv)
    require_freeze()
    data = run(a.analysis)
    p = write(a.analysis, data)
    print(f"exploratory: {data['n_rows']} rows, {data['n_transcripts']} transcripts "
          f"({data['missing_transcripts']} missing); wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
