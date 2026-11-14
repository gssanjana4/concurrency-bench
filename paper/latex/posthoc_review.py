#!/usr/bin/env python3
"""POST HOC analyses requested by the pre-submission reviews (saved data only; no model calls; not confirmatory).

    python3 posthoc_review.py --analysis DIR

Reads (read-only): DIR/provenance.json, DIR/confirmatory.json, the analysed CSVs and their transcripts (rows filtered
exactly as ``analyze4.load`` filters them), and the SQL-slice CSV (``$RESULTS_SQL/results.csv``, default
``../../results_sql``). Imports the frozen analysis (``analyze4``) and the exploratory helpers of ``explore4.py``
read-only. Writes ONLY ``DIR/posthoc_review.json``. Every block is labelled POST HOC (not pre-registered, supports
no confirmatory claim). None of these analyses was planned before the data; all were defined after reading the
three reviews of 2026-11-02 (``review/R1_methods.md``, ``R2_novelty.md``, ``R3_repro_compliance.md``).

Blocks and definitions
----------------------
template_boot (R1 W3)   For H1, H2, H3, H4a, H4b and H6, the registered cluster values (``analyze4._spec`` /
    ``_cluster_values`` on complete clusters, as registered) are averaged within each template, and the frozen
    ``analyze4.cluster_bootstrap`` is run on the template means instead of the instance values (same theta0,
    alternative, B and seed scheme; key prefixed ``TPL|``); degenerate template means fall back to the exact sign
    test on templates, as registered for instances. Holm across the six models, as registered. Because every
    template has the same number of complete clusters here, the template-level estimate equals the registered one.
    Also: one-way ANOVA ICC(1) of the instance cluster values with templates as groups (None when undefined), the
    per-template means, the number of templates whose mean differs from theta0 (H3: from zero), and for H6 the
    number of clusters whose non_serializable outcome differs across n = 2, 4, 8.
exact_bounds (R1 W7)    For every registered test component whose cluster values are all equal (degenerate
    bootstrap), the exact one-sided 95% Clopper-Pearson lower bound on the share of clusters at the observed value
    when k of k clusters are there: 0.05 ** (1 / k). It treats clusters as independent, which they are not (7
    templates); it replaces nothing in the registered decision.
control_use (R2 W2)     Share of agents making the offered choice (lock under ``locks``, message under ``messages``,
    cas under ``cas_available``) on the uncontended control template ``budget_control`` vs. the contended
    templates, n = 2, per aware level; mean of task-instance rates (explore4.inst_mean). ``cas_cont_update``: the
    five contended templates whose writes go through ``update_record`` (seat/ticket ``claim`` templates excluded).
store_goodput (R1 W5)   An agent is *store-fulfilled* if it fulfilled its intent in its own view (score4
    ``fulfilled``) and none of its last effects on the records it wrote was lost: no later committed write by
    another agent to that record has a basis (``records.write_bases`` rule, recomputed on the ledger JSON) older
    than the version the agent's last effect produced while overwriting that version or a later one. Rate = store-
    fulfilled / ``n_abandon_eligible`` (same denominator as E1 fulfilment), contended templates, n = 2, per model,
    config and aware level. It differs from E1 ``fulfil`` exactly by fulfilled agents whose effect a stale
    overwrite removed.
lease_split (R1 W6)     ``locks``, n = 2, contended, both aware levels. For each agent with a granted
    ``acquire_lock``, at its first write attempt (``update_record``/``claim``) on each record of its write set:
    ``held`` (its last granted lock on the record, not released since, has ``step < lease_expires_at``),
    ``expired`` (that lock had expired, ``lease_expires_at <= step``), ``released`` or ``never_locked``. Agent class
    ``expired`` if any write record is ``expired``. Episodes are split by whether any agent is ``expired``, with
    pooled non_serializable counts per group. Also the requested ``lease_steps`` of granted locks.
same_reply (R1 W4, Q2)  ``transfer_shared_source``, n = 2, all configs and both aware levels: share of agents with at
    least one ``update_record`` call whose model reply (one completion) contained ``update_record`` calls on both
    records of its write set.
serving (R1 W4/W9)      Qwen hosts per episode from ``model_served``; first and last episode start time per model
    (transcript ``run_info``).
sql (R1 W13)            Design counts and per-cell violation counts of the exploratory SQL slice, recomputed from
    its results.csv (existence statements only).
template_boot also gives the exact sign-flip test (all sign patterns of the template means) and the exact sign test on
    template means, each with Holm across models (review T3 section 4).
review2 (reviews T1-T4, 2026-11-03)   Defined after the data and after four further internal reviews; definitions in each
    function's docstring: sign_tests, h6_detectable, graph_agreement, stale_facts, cas_leak, partial_split, ws_transient,
    control_and_habit, schedule_facts, turn_cap, qwen_hosts_locks, gemini_settings, orchestrators. graph_agreement and
    stale_facts are registered exploratory items that were not reported before.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, OrderedDict, defaultdict

from pipeline_common import PAPER, SRC4, require_freeze, sha256_file

sys.dont_write_bytecode = True
sys.path.insert(0, SRC4)
import analyze4 as A  # noqa: E402  (frozen; read-only)
import explore4 as X  # noqa: E402  (exploratory helpers; read-only use)

OUT_NAME = "posthoc_review.json"
PROTECTED = {"confirmatory.json", "confirmatory.md", "numbers.json", "tables.md", "provenance.json",
             "exploratory_posthoc.json", "rollback_sensitivity.json", "reference_policies.json"}
POST = "POST HOC (defined after the data and the 2026-11-02 reviews; not pre-registered; not confirmatory)"
CONTROL = "budget_control"
CLAIM_TEMPLATES = ("seat_same", "ticket_same")
RESULTS_SQL = os.environ.get("RESULTS_SQL", os.path.join(os.path.dirname(PAPER), "results_sql"))


# ------------------------------------------------------------------ small pure helpers (unit-tested)
def cp_lower_all(k, alpha=0.05):
    """Exact one-sided (1 - alpha) Clopper-Pearson lower bound for k successes in k trials."""
    return None if k <= 0 else alpha ** (1.0 / k)


def icc1(groups):
    """One-way ANOVA ICC(1) for equal-sized groups (list of lists); None when undefined."""
    groups = [g for g in groups if g]
    if len(groups) < 2 or len({len(g) for g in groups}) != 1 or len(groups[0]) < 2:
        return None
    k = len(groups[0])
    allv = [v for g in groups for v in g]
    gm = sum(allv) / len(allv)
    msb = k * sum((sum(g) / k - gm) ** 2 for g in groups) / (len(groups) - 1)
    msw = sum((v - sum(g) / k) ** 2 for g in groups for v in g) / (len(groups) * (k - 1))
    den = msb + (k - 1) * msw
    return None if den <= 0 else (msb - msw) / den


def signflip_exact(values, theta0, alternative):
    """Exact one-sided sign-flip permutation p of the mean of ``values`` against ``theta0`` (zero deviations
    dropped; all 2^m sign patterns enumerated, so m must be small, e.g. 7 template means). 1.0 if all equal theta0."""
    import itertools
    d = [v - theta0 for v in values if abs(v - theta0) > A.EPS]
    if not d:
        return 1.0
    assert len(d) <= 16, "exact enumeration is meant for template means"
    obs = math.fsum(d)
    hit = tot = 0
    for signs in itertools.product((1, -1), repeat=len(d)):
        t = math.fsum(a * b for a, b in zip(signs, d))
        tot += 1
        hit += (t >= obs - A.EPS) if alternative == "greater" else (t <= obs + A.EPS)
    return hit / tot


def bases(calls, effects):
    """effect seq -> basis version, the records.write_bases rule on ledger JSON."""
    effect_call = {c["effect_seq"]: c["seq"] for c in calls if c.get("committed")}
    new_version = {e["seq"]: e["new_version"] for e in effects}
    by_agent = defaultdict(list)
    for c in sorted(calls, key=lambda c: c["seq"]):
        by_agent[c["agent_id"]].append(c)
    out = {}
    for e in effects:
        ws = effect_call[e["seq"]]
        b = 1
        for c in by_agent[e["agent_id"]]:
            if c["seq"] >= ws:
                break
            if c.get("record_id") != e["record_id"]:
                continue
            if c["tool"] == "get_record" and c.get("status") == 200 and c.get("read_version") is not None:
                b = max(b, c["read_version"])
            elif c.get("committed") and c.get("effect_seq") is not None:
                b = max(b, new_version[c["effect_seq"]])
        out[e["seq"]] = b
    return out


def lost_agents(calls, effects):
    """Agents whose last effect on some record was overwritten by a later stale write of another agent."""
    bs = bases(calls, effects)
    eff = sorted(effects, key=lambda e: e["seq"])
    last = {}
    for e in eff:
        last[(e["agent_id"], e["record_id"])] = e
    lost = set()
    for (a, r), e in last.items():
        v = e["new_version"]
        for f in eff:
            if f["seq"] > e["seq"] and f["record_id"] == r and f["agent_id"] != a and bs[f["seq"]] < v <= f["old_version"]:
                lost.add(a)
                break
    return lost


def lease_class(calls, agent, writes):
    """lease_split class of one agent: None (never granted a lock) or (class, per-record states)."""
    mine = sorted((c for c in calls if c["agent_id"] == agent), key=lambda c: c["seq"])
    if not any(c["tool"] == "acquire_lock" and c.get("status") == 200 for c in mine):
        return None
    states = {}
    for r in writes:
        w = next((c for c in mine if c["tool"] in X.WRITE_TOOLS and c.get("record_id") == r), None)
        if w is None:
            states[r] = "no_write"
            continue
        st, exp = "never_locked", None
        for c in mine:
            if c["seq"] >= w["seq"] or c.get("record_id") != r:
                continue
            if c["tool"] == "acquire_lock" and c.get("status") == 200:
                st, exp = "locked", c.get("lease_expires_at")
            elif c["tool"] == "release_lock" and c.get("status") == 200 and st == "locked":
                st = "released"
        if st == "locked":
            st = "held" if exp is None or w["step"] < exp else "expired"
        states[r] = st
    vals = set(states.values())
    cls = "expired" if "expired" in vals else ("held" if vals <= {"held", "no_write"} and "held" in vals else "other")
    return cls, states


def same_reply_both_legs(agent_rec, writes):
    """True if one model completion contained update_record calls on every record in ``writes``."""
    ws = set(writes)
    for t in agent_rec.get("turns") or []:
        recs = {(b.get("input") or {}).get("record_id") for b in (t.get("content") or [])
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "update_record"}
        if ws <= recs:
            return True
    return False


# ------------------------------------------------------------------ analyses
def index_rows(rows):
    idx = {}
    for r in rows:
        idx.setdefault((r["model"], r["task"], str(r["instance"]), r["config"], r["aware"], r["n_agents"], r["seed"]), r)
    return idx


def template_boot(rows, conf):
    idx = index_rows(rows)
    out = OrderedDict()
    for h in A.HYPOTHESES:
        spec = A._spec(h)
        parts = ("i", "ii") if spec["kind"] == "h4b" else ("v",)
        recs = []
        for m in A.REGISTERED_MODELS:
            by_t = OrderedDict()
            varies = 0
            for t in spec["templates"]:
                for i in spec["instances"]:
                    eps = {}
                    for need in spec["needs"]:
                        x = idx.get((m, t, str(i)) + tuple(need))
                        if x is None:
                            break
                        eps[tuple(need)] = x
                    else:
                        by_t.setdefault(t, []).append(A._cluster_values(spec, eps))
                        if spec["kind"] == "slope":
                            varies += len({r["non_serializable"] for r in eps.values()}) > 1
            rec = {"model": m, "n_templates": len(by_t), "n_clusters": sum(len(v) for v in by_t.values()), "parts": {}}
            for part in parts:
                th0, alt = ((0.5, "greater") if part == "i" else (A.H4B_MARGIN, "less")) if spec["kind"] == "h4b" \
                    else (spec["theta0"], spec["alternative"])
                means = OrderedDict((t, sum(v[part] for v in vs) / len(vs)) for t, vs in by_t.items())
                bt = A.cluster_bootstrap(list(means.values()), th0, alt, f"TPL|{h}|{m}|{part}")
                bt["p_signflip"] = signflip_exact(list(means.values()), th0, alt)
                bt["template_means"] = means
                bt["icc"] = icc1([[v[part] for v in vs] for vs in by_t.values()])
                bt["n_templates_off_null"] = sum(abs(x - th0) > A.EPS for x in means.values())
                reg = next(x for x in conf["hypotheses"][h]["tests"] if x["model"] == m)
                want = (reg.get("component_" + part) or {}).get("estimate") if part in ("i", "ii") else reg.get("estimate")
                bt["equals_registered_estimate"] = want is not None and abs(want - bt["estimate"]) < 1e-9
                rec["parts"][part] = bt
            rec["p"] = max(rec["parts"][p]["p"] for p in parts)
            rec["p_sign"] = max(rec["parts"][p]["p_sign"] for p in parts)
            rec["p_signflip"] = max(rec["parts"][p]["p_signflip"] for p in parts)
            if spec["kind"] == "slope":
                rec["h6_clusters_varying_with_n"] = varies
            recs.append(rec)
        for r, a in zip(recs, A.holm([r["p"] for r in recs])):
            r["p_holm"] = a
            r["reject"] = a <= A.ALPHA
        for meth in ("sign", "signflip"):  # exact template-level tests (review T3 section 4), Holm across models
            for r, a in zip(recs, A.holm([r["p_" + meth] for r in recs])):
                r[f"p_{meth}_holm"] = a
                r[f"reject_{meth}"] = a <= A.ALPHA
        reg_rej = {x["model"]: bool(x["reject"]) for x in conf["hypotheses"][h]["tests"]}
        out[h] = {"n_reject": sum(r["reject"] for r in recs), "n_reject_registered": sum(reg_rej.values()),
                  "n_reject_sign": sum(r["reject_sign"] for r in recs),
                  "n_reject_signflip": sum(r["reject_signflip"] for r in recs),
                  "lost": [r["model"] for r in recs if reg_rej[r["model"]] and not r["reject"]],
                  "gained": [r["model"] for r in recs if r["reject"] and not reg_rej[r["model"]]], "tests": recs}
    return {"label": POST + "; template-level (7-cluster) sensitivity of the registered tests", "hypotheses": out}


def exact_bounds(conf):
    out = []
    for h in A.HYPOTHESES:
        for t in conf["hypotheses"][h]["tests"]:
            comps = [("i", t["component_i"]), ("ii", t["component_ii"])] if "component_i" in t else [("v", t)]
            for part, c in comps:
                if c.get("degenerate"):
                    k = c["n_clusters"] if "n_clusters" in c else t["n_complete_clusters"]
                    out.append({"hypothesis": h, "part": part, "model": t["model"], "value": c["estimate"], "k": k,
                                "bound": cp_lower_all(k)})
    return {"label": POST + "; exact one-sided 95% Clopper-Pearson lower bound on the share of clusters at the "
                     "observed value (k of k), for degenerate cells only", "rows": out}


def control_use(rows):
    out = []
    n2 = [r for r in rows if r["n_agents"] == 2]
    share = lambda pool, ch: X.inst_mean((X.ik(r), sum(ch in cs for cs in r["choices"].values()), r["n_choice_agents"])  # noqa: E731
                                         for r in pool)
    for m in A.REGISTERED_MODELS:
        for a in (0, 1):
            rec = {"model": m, "aware": a}
            for cfg, ch, key in (("locks", "lock", "lock"), ("messages", "message", "msg"), ("cas_available", "cas", "cas")):
                pool = [r for r in n2 if r["model"] == m and r["aware"] == a and r["config"] == cfg]
                rec[key + "_ctl"] = share([r for r in pool if r["task"] == CONTROL], ch)
                rec[key + "_cont"] = share([r for r in pool if r["category"] != "control"], ch)
                if cfg == "cas_available":
                    rec["cas_cont_update"] = share([r for r in pool if r["category"] != "control"
                                                    and r["task"] not in CLAIM_TEMPLATES], ch)
            out.append(rec)
    return {"label": POST + " (control-template choice use; R2 W2)", "rows": out}


def store_goodput(rows, transcripts):
    groups = defaultdict(list)
    for r in rows:
        if r["n_agents"] == 2 and r["category"] != "control" and r["episode_id"] in transcripts:
            groups[(r["model"], r["config"], r["aware"])].append(r)
    out = []
    for (m, c, a), rs in sorted(groups.items(), key=lambda kv: tuple(map(str, kv[0]))):
        items, lost_n = [], 0
        for r in rs:
            tr = transcripts[r["episode_id"]]
            lost = lost_agents(tr["ledger"]["calls"], tr["ledger"]["effects"])
            ful = {ag for ag, s in tr["score"]["agents"].items() if s.get("fulfilled")}
            k = len(ful - lost)
            lost_n += len(ful & lost)
            items.append((X.ik(r), k, r["n_abandon_eligible"] or 0))
        rec = {"model": m, "config": c, "aware": a, "store_fulfil": X.inst_mean(items), "fulfilled_but_lost": lost_n}
        out.append(rec)
    return {"label": POST + " (store-based fulfilment; R1 W5)", "rows": out}


def lease_split(rows, transcripts):
    out = []
    groups = defaultdict(list)
    for r in rows:
        if r["n_agents"] == 2 and r["config"] == "locks" and r["category"] != "control" and r["episode_id"] in transcripts:
            groups[(r["model"], r["aware"])].append(r)
    for (m, a), rs in sorted(groups.items()):
        ag = Counter()
        ep = defaultdict(lambda: [0, 0])
        leases = []
        for r in rs:
            tr = transcripts[r["episode_id"]]
            calls = tr["ledger"]["calls"]
            leases += [(c.get("args") or {}).get("lease_steps") for c in calls if c["tool"] == "acquire_lock" and c.get("status") == 200]
            any_exp = False
            for agent, intent in X.intents_of(tr).items():
                lc = lease_class(calls, agent, list(intent.writes))
                if lc is None:
                    ag["no_lock"] += 1
                    continue
                ag["lockers"] += 1
                ag[lc[0]] += 1
                any_exp = any_exp or lc[0] == "expired"
            g = ep["expired" if any_exp else "not_expired"]
            g[0] += int(r["non_serializable"])
            g[1] += 1
        leases = sorted(x for x in leases if isinstance(x, int))
        out.append({"model": m, "aware": a, "agents": dict(ag),
                    "episodes": {k: {"non_serializable": v[0], "n": v[1]} for k, v in ep.items()},
                    "lease_steps": {"n": len(leases), "median": leases[len(leases) // 2] if leases else None,
                                    "min": leases[0] if leases else None, "max": leases[-1] if leases else None,
                                    "share_le_gap": (sum(x <= 2 for x in leases) / len(leases)) if leases else None}})
    return {"label": POST + " (lock-lease expiry split; R1 W6)", "rows": out}


def same_reply(rows, transcripts):
    per = defaultdict(Counter)
    for r in rows:
        if r["n_agents"] != 2 or r["task"] != A.H5_TEMPLATE or r["episode_id"] not in transcripts:
            continue
        tr = transcripts[r["episode_id"]]
        for agent, intent in X.intents_of(tr).items():
            rec = tr["agents"].get(agent) or {}
            wrote = any(c["agent_id"] == agent and c["tool"] == "update_record" for c in tr["ledger"]["calls"])
            if not wrote:
                continue
            c = per[(r["model"], "all")]
            c["n"] += 1
            c["k"] += same_reply_both_legs(rec, intent.writes)
            if r["config"] in A.H5_CONFIGS:
                c2 = per[(r["model"], "h5_configs")]
                c2["n"] += 1
                c2["k"] += same_reply_both_legs(rec, intent.writes)
    return {"label": POST + " (both transfer legs in one reply; R1 W4/Q2)",
            "rows": [{"model": m, "scope": s, "k": c["k"], "n": c["n"]} for (m, s), c in sorted(per.items())]}


def serving(rows, transcripts):
    hosts = Counter()
    mixed = 0
    qwen = [r for r in rows if "qwen" in r["model"]]
    for r in qwen:
        hs = {x.split("@", 1)[-1].strip() for x in (r.get("model_served") or "").split("|") if x}
        mixed += len(hs) > 1
        for h in hs:
            hosts[h] += 1
    dates = {}
    for r in rows:
        tr = transcripts.get(r["episode_id"])
        s = (tr or {}).get("run_info", {}).get("started_utc")
        if s:
            d = dates.setdefault(r["model"], [s, s])
            d[0], d[1] = min(d[0], s), max(d[1], s)
    return {"label": POST + " (serving facts)", "qwen_hosts_episodes": dict(hosts.most_common()),
            "qwen_episodes": len(qwen), "qwen_mixed_host_episodes": mixed,
            "run_dates": {m: {"first": v[0], "last": v[1]} for m, v in dates.items()}}


def sql_slice(path):
    if not os.path.exists(path):
        return None
    rs = [r for r in csv.DictReader(open(path, newline="")) if str(r.get("dry_run", "0")) in ("", "0")]
    cells = defaultdict(lambda: [0, 0])
    kinds = defaultdict(Counter)
    for r in rs:
        k = (r["model"], r["task"], int(r["n_agents"]))
        cells[k][0] += int(r["violation"])
        cells[k][1] += 1
        for v in filter(None, (r.get("violation_kinds") or "").split("|")):
            kinds[k][v] += 1
    return {"label": "EXPLORATORY, post hoc, not pre-registered (SQL slice counts recomputed from results.csv)",
            "source_sha256": sha256_file(path), "n_episodes": len(rs),
            "n_agents": sum(int(r["n_agents"]) for r in rs),
            "models": sorted({r["model"] for r in rs}), "templates": sorted({r["task"] for r in rs}),
            "variants": sorted({r["variant"] for r in rs}), "reps": sorted({r["rep"] for r in rs}, key=int),
            "ns": sorted({int(r["n_agents"]) for r in rs}),
            "cost_usd": sum(float(r.get("cost_usd") or 0) for r in rs),
            "cells": [{"model": m, "template": t, "n": n, "violations": v[0], "episodes": v[1], "kinds": dict(kinds[(m, t, n)])}
                      for (m, t, n), v in sorted(cells.items())]}


# ------------------------------------------------------------------ POST HOC analyses after the four hard reviews (2026-11-03)
POST2 = ("POST HOC (defined after the data and the 2026-11-03 reviews review/T1-T4; not pre-registered; not confirmatory)")
SINGLE = tuple(A.SINGLE_RECORD_TEMPLATES)
WS = tuple(A.WRITE_SKEW_TEMPLATES)


def ledger_from(tr):
    """Rebuild the frozen ``records.Ledger`` from a transcript's ledger JSON (read-only use of frozen classes)."""
    import records as R
    L = R.Ledger()
    cv = lambda rid, v: R.coerce_value(R.kind_of(rid), v)  # noqa: E731
    for e in tr["ledger"]["effects"]:
        L.effects.append(R.WriteEffect(agent_id=e["agent_id"], record_id=e["record_id"], old_value=cv(e["record_id"], e["old_value"]),
                                       new_value=cv(e["record_id"], e["new_value"]), old_version=e["old_version"],
                                       new_version=e["new_version"], seq=e["seq"], tool=e["tool"], args=e["args"], step=e["step"]))
    for c in tr["ledger"]["calls"]:
        L.calls.append(R.CallRecord(**c))
    for a in tr["ledger"]["agent_ends"]:
        a = dict(a)
        a["locks_held"] = tuple(a["locks_held"])
        L.agent_ends.append(R.AgentEnd(**a))
    L.flags = dict(tr["ledger"]["flags"])
    return L


def task_of(tr):
    import instances4
    t = tr["task"]
    return instances4.build(t["factory"], int(t["instance"]), tr["n_agents"])


def sign_tests(conf):
    """The registered exact sign test, reported for every registered test (the registration requires it), plus a Holm
    adjustment of the sign-test p across models (that adjustment is post hoc). H4b: max over the two components."""
    out = OrderedDict()
    for h in A.HYPOTHESES:
        recs = []
        for t in conf["hypotheses"][h]["tests"]:
            comps = [t["component_i"], t["component_ii"]] if "component_i" in t else [t]
            ps = [c.get("p_sign") for c in comps]
            recs.append({"model": t["model"], "p_sign": None if None in ps else max(ps),
                         "k": [c.get("sign_k") for c in comps], "n": [c.get("sign_n") for c in comps],
                         "registered_reject": bool(t.get("reject"))})
        tested = [r for r in recs if r["p_sign"] is not None]
        for r, a in zip(tested, A.holm([r["p_sign"] for r in tested])):
            r["p_sign_holm"] = a
            r["reject_sign"] = a <= A.ALPHA
        out[h] = {"tests": recs, "n_reject_sign": sum(bool(r.get("reject_sign")) for r in recs),
                  "lost": [r["model"] for r in recs if r["registered_reject"] and not r.get("reject_sign")]}
    return {"label": "Registered exact sign test (reported for every test, as registered); its Holm adjustment is "
                     + POST2, "hypotheses": out}


def h6_detectable(conf):
    """Smallest number k of the H6 clusters that must flip 0 -> 1 between n=2 and n=8 (per-cluster slope 0.5, the rest 0)
    for the frozen registered bootstrap to reach p <= alpha and p <= alpha/6 (first Holm step). Uses the frozen
    analyze4.cluster_bootstrap with a POST-prefixed key. With x = log2 n in {1,2,3} the per-cluster OLS slope equals
    (y8 - y2)/2, so the n=4 episodes do not enter the statistic."""
    m = max(t["n_complete_clusters"] for t in conf["hypotheses"]["H6"]["tests"])
    fam = len(conf["hypotheses"]["H6"]["tests"])
    res = {}
    for k in range(1, m + 1):
        vals = [0.5] * k + [0.0] * (m - k)
        res[k] = A.cluster_bootstrap(vals, 0.0, "greater", f"POST|H6power|{k}")["p"]
    k05 = next((k for k in range(1, m + 1) if res[k] <= A.ALPHA), None)
    kh = next((k for k in range(1, m + 1) if res[k] <= A.ALPHA / fam), None)
    ests = [t["estimate"] for t in conf["hypotheses"]["H6"]["tests"] if t.get("estimate") is not None]
    return {"label": POST2 + " (H6 minimal detectable effect under the registered test)", "m": m, "p_by_k": res,
            "k_alpha": k05, "k_alpha_first_holm": kh, "family": fam, "max_estimate": max(ests) if ests else None,
            "n_positive_estimates": sum(e > A.EPS for e in ests)}


def graph_agreement(rows):
    """Registered exploratory item: graph_cycle vs non_serializable agreement, 2x2 over all analysed episodes, and in the
    scopes where the paper used to claim equality (single-record templates; two-agent write-skew templates)."""
    def tab(pool):
        c = Counter((int(r["non_serializable"]), int(r["graph_cycle"])) for r in pool)
        return {"ns1_gc1": c[(1, 1)], "ns1_gc0": c[(1, 0)], "ns0_gc1": c[(0, 1)], "ns0_gc0": c[(0, 0)], "n": len(pool)}
    return {"label": "Registered EXPLORATORY item (graph_cycle vs non_serializable agreement), reported after the T1 review",
            "all": tab(rows), "single_record": tab([r for r in rows if r["task"] in SINGLE]),
            "write_skew_n2": tab([r for r in rows if r["task"] in WS and r["n_agents"] == 2]),
            "control": tab([r for r in rows if r["category"] == "control"])}


def stale_facts(rows, raw):
    """n_stale_writes (registered exploratory): episodes with at least one stale overwrite per config (all phases and
    templates); stale overwrites in episodes scored serializable (lost update masked)."""
    nsw = lambda r: int(raw[r["episode_id"]].get("n_stale_writes") or 0)  # noqa: E731
    by_cfg = defaultdict(lambda: [0, 0])
    hidden = Counter()
    for r in rows:
        v = by_cfg[r["config"]]
        v[0] += nsw(r) > 0
        v[1] += 1
        if nsw(r) > 0 and not r["non_serializable"]:
            hidden[(r["task"], r["config"])] += 1
    return {"label": "Registered EXPLORATORY item (n_stale_writes), reported after the T1 review",
            "episodes_with_stale_by_config": {c: {"k": v[0], "n": v[1]} for c, v in by_cfg.items()},
            "hidden_lost_updates": sum(hidden.values()),
            "hidden_by_template_config": {f"{t}|{c}": n for (t, c), n in hidden.items()},
            "hidden_templates": sorted({t for t, _ in hidden})}


def cas_leak(rows, transcripts):
    """Committed conditional writes (cas_available, cas_required) by the source of their expected_version: a version
    the agent read, one its own write returned, or one seen only in a 409/423 response body. Stale = the write's
    recorded basis is older than the version it overwrote."""
    cnt = Counter()
    eps = set()
    for r in rows:
        if r["config"] not in X.CAS_CONFIGS or r["episode_id"] not in transcripts:
            continue
        tr = transcripts[r["episode_id"]]
        calls = sorted(tr["ledger"]["calls"], key=lambda c: c["seq"])
        eff = {e["seq"]: e for e in tr["ledger"]["effects"]}
        bs = bases(calls, list(eff.values()))
        seen = defaultdict(set)
        for c in calls:
            a, rid = c["agent_id"], c.get("record_id")
            ev = (c.get("args") or {}).get("expected_version")
            if c["tool"] == "update_record" and ev is not None and c.get("committed"):
                src = {s for v, s in seen[(a, rid)] if v == ev}
                k = "read" if "read" in src else "own_write" if "own_write" in src else "error_body" if "error_body" in src else "unseen"
                cnt[k] += 1
                e = eff[c["effect_seq"]]
                if k == "error_body" and bs[e["seq"]] < e["old_version"]:
                    cnt["error_body_stale"] += 1
                    eps.add(r["episode_id"])
            if c["tool"] == "get_record" and c.get("status") == 200 and c.get("read_version") is not None:
                seen[(a, rid)].add((c["read_version"], "read"))
            if c.get("committed") and c.get("effect_seq") is not None:
                seen[(a, rid)].add((eff[c["effect_seq"]]["new_version"], "own_write"))
            cur = (c.get("response") or {}).get("current_version")
            if cur is not None and rid:
                seen[(a, rid)].add((cur, "error_body"))
    stale_eps = [r for r in rows if r["config"] in X.CAS_CONFIGS and r["label"] == "stale_overwrite"]
    return {"label": POST2 + " (version leaked by the 409 body)", "committed_cas_by_version_source": dict(cnt),
            "error_body_stale_episodes": len(eps), "stale_overwrite_label_episodes": len(stale_eps),
            "stale_overwrite_label_by_config": dict(Counter(r["config"] for r in stale_eps))}


def partial_split(rows, transcripts):
    """Contended partial_action episodes (all n), with non-exclusive mechanism flags read from the ledger:
    missing_leg: a committed-unfulfilled agent with a multi-record write set made no action on some record of it;
    compensated: a committed agent's writes net to zero (rollback_sensitivity's net-zero rule);
    guard_violation: a committed-unfulfilled agent that does not net to zero made a non-restoring action although its
    intent's guard fails on the state it acted on (intent.apply returns None). Also: stale_overwrite episodes with a partial commit."""
    import records as R
    import score4
    from rollback_sensitivity import net_zero_agents
    flags = Counter()
    n = 0
    hidden_partial = 0
    for r in rows:
        if r["category"] == "control" or r["episode_id"] not in transcripts:
            continue
        tr = transcripts[r["episode_id"]]
        sc = tr["score"]
        if sc["primary_label"] == "stale_overwrite" and sc["partial_commits"]:
            hidden_partial += 1
        if sc["primary_label"] != "partial_action":
            continue
        n += 1
        task = task_of(tr)
        L = ledger_from(tr)
        init = dict(task.initial)
        acts = R.action_effects(L, init)
        bss = R.write_bases(L)
        effc = {c.effect_seq: c.seq for c in L.calls if c.committed}
        f = set()
        if set(net_zero_agents(tr)) & set(sc["committed_agents"]):
            f.add("compensated")
        nz = set(net_zero_agents(tr))
        for a in sc["partial_commits"]:
            it = task.intents[a]
            own = [e for e in acts if e.agent_id == a]
            if len(it.writes) > 1 and not set(it.writes) <= {e.record_id for e in own}:
                f.add("missing_leg")
            if a in nz:
                continue  # a compensating agent's restoring write is not a guard violation
            before = {}
            for e in own:
                before.setdefault(e.record_id, R.normalize_value(e.old_value))
            for e in own:
                if R.normalize_value(e.new_value) == before[e.record_id]:
                    continue  # a write that restores the agent's starting value is compensation
                if it.apply(score4._acted_state(L, init, a, it.reads, e, own, bss, effc)) is None:
                    f.add("guard_violation")
                    break
        for k in f:
            flags[k] += 1
        flags["none_of_these"] += not f
        flags["compensated_only"] += f == {"compensated"}
    return {"label": POST2 + " (partial_action mechanisms; flags overlap)", "n": n, "flags": dict(flags),
            "stale_overwrite_with_partial_commit": hidden_partial}


def ws_transient(rows, transcripts):
    """Write-skew templates, cas_available, n=2, aware off: per model, episodes in which some constraint invariant
    (every task invariant except the 'unchanged' cap check) was violated after some committed write (ledger replay),
    violated in the final store, labelled write_skew, and with a graph cycle."""
    out = defaultdict(Counter)
    for r in rows:
        if r["task"] not in WS or r["config"] != "cas_available" or r["n_agents"] != 2 or r["aware"] or r["episode_id"] not in transcripts:
            continue
        tr = transcripts[r["episode_id"]]
        task = task_of(tr)
        L = ledger_from(tr)
        init = dict(task.initial)
        vals = dict(init)
        ever = False
        for e in L.effects:
            vals[e.record_id] = e.new_value
            if any(inv.violations(init, vals, L, task) for inv in task.invariants if not inv.name.startswith("unchanged")):
                ever = True
        c = out[r["model"]]
        c["episodes"] += 1
        c["ever_violated"] += ever
        c["final_violated"] += bool(tr["score"]["invariant_violation"])
        c["write_skew_label"] += r["label"] == "write_skew"
        c["graph_cycle"] += int(r["graph_cycle"])
    return {"label": POST2 + " (H4b: constraint violated at any point vs at the end)",
            "rows": [{"model": m, **dict(c)} for m, c in out.items()]}


def first_reply(tr, agent):
    rec = tr["agents"].get(agent) or {}
    t = (rec.get("turns") or [None])[0]
    return [] if not t else [b for b in (t.get("content") or []) if isinstance(b, dict) and b.get("type") == "tool_use"]


def control_and_habit(rows, transcripts):
    """Control template budget_control (n=2): graph cycles per model (all configs and aware levels); lock share on
    budget_control vs its structural twin budget_write_skew (locks, aware off); and, under locks, aware off, n=2
    (all templates), the agents whose first model reply already requested a lock, before any record value was seen."""
    out = []
    n2 = [r for r in rows if r["n_agents"] == 2]
    share = lambda pool: X.inst_mean((X.ik(r), sum("lock" in cs for cs in r["choices"].values()), r["n_choice_agents"]) for r in pool)  # noqa: E731
    for m in A.REGISTERED_MODELS:
        ctl = [r for r in n2 if r["model"] == m and r["task"] == CONTROL]
        lk = [r for r in n2 if r["model"] == m and r["config"] == "locks" and not r["aware"]]
        first = [0, 0]
        for r in lk:
            tr = transcripts.get(r["episode_id"])
            if not tr:
                continue
            for agent in tr["agents"]:
                first[1] += 1
                first[0] += any(b.get("name") == "acquire_lock" for b in first_reply(tr, agent))
        out.append({"model": m, "control_graph_cycle": sum(int(r["graph_cycle"]) for r in ctl), "control_episodes": len(ctl),
                    "lock_control": share([r for r in lk if r["task"] == CONTROL]),
                    "lock_budget_ws": share([r for r in lk if r["task"] == "budget_write_skew"]),
                    "first_reply_lock": first[0], "first_reply_agents": first[1]})
    return {"label": POST2 + " (contended control; first-reply locks)", "rows": out}


def schedule_facts(rows, transcripts):
    """Phase-one contended n=2 episodes in which every agent made a successful read and some write committed: every
    agent's first successful read precedes the first committed write of the episode (read overlap); and which agent
    made the episode's first call, by seed."""
    ok = [0, 0]
    first_mover = Counter()
    for r in rows:
        if r["n_agents"] != 2 or r["category"] == "control" or r["episode_id"] not in transcripts:
            continue
        tr = transcripts[r["episode_id"]]
        calls = sorted(tr["ledger"]["calls"], key=lambda c: c["seq"])
        if calls:
            first_mover[(int(r["seed"]), calls[0]["agent_id"])] += 1
        fr, fc = {}, []
        for c in calls:
            if c["tool"] == "get_record" and c.get("status") == 200:
                fr.setdefault(c["agent_id"], c["step"])
            if c.get("committed"):
                fc.append(c["step"])
        if not fc or len(fr) != len(tr["agents"]):
            continue
        ok[1] += 1
        ok[0] += max(fr.values()) < min(fc)
    return {"label": POST2 + " (one synchronized interleaving per seed)", "reads_before_first_commit": ok[0],
            "episodes": ok[1], "first_mover": {f"s{s}|{a}": n for (s, a), n in sorted(first_mover.items())}}


def turn_cap(rows, transcripts):
    """Agents whose end reason is turn_cap, per model (all phases), per model x config x n, in the H6 cells at n=8
    (cas_available, aware off, contended), and on the multi-record write-skew and control templates at n=8, aware off
    (agents capped, and capped agents with no committed action)."""
    per_model = defaultdict(lambda: [0, 0])
    cell = defaultdict(lambda: [0, 0])
    n8 = defaultdict(lambda: [0, 0, 0])
    h6 = defaultdict(lambda: [0, 0])
    for r in rows:
        ends = r["end_reasons"]
        k = sum(v == "turn_cap" for v in ends.values())
        per_model[r["model"]][0] += k
        per_model[r["model"]][1] += len(ends)
        c = cell[(r["model"], r["config"], r["n_agents"])]
        c[0] += k
        c[1] += len(ends)
        if r["n_agents"] == 8 and r["config"] == "cas_available" and not r["aware"] and r["category"] != "control" \
                and r["episode_id"] in transcripts:
            sc = transcripts[r["episode_id"]]["score"]
            v = h6[r["model"]]
            v[0] += sum(s["end_reason"] == "turn_cap" for s in sc["agents"].values())
            v[1] += len(sc["agents"])
        if r["n_agents"] == 8 and r["task"] in WS + (CONTROL,) and not r["aware"] and r["episode_id"] in transcripts:
            sc = transcripts[r["episode_id"]]["score"]
            committed = set(sc["committed_agents"])
            v = n8[(r["model"], r["config"])]
            for a, s in sc["agents"].items():
                v[1] += 1
                if s["end_reason"] == "turn_cap":
                    v[0] += 1
                    v[2] += a not in committed
    return {"label": POST2 + " (turn-cap endings)",
            "per_model": {m: {"k": v[0], "n": v[1]} for m, v in per_model.items()},
            "cells": [{"model": m, "config": c, "n": n, "k": v[0], "agents": v[1]} for (m, c, n), v in sorted(cell.items(), key=str)],
            "h6_n8_cas": {m: {"capped": v[0], "agents": v[1]} for m, v in h6.items()},
            "n8_multi_record": [{"model": m, "config": c, "capped": v[0], "agents": v[1], "capped_no_commit": v[2]}
                                for (m, c), v in sorted(n8.items())]}


def qwen_hosts_locks(rows, transcripts):
    """Qwen, locks, aware off, n=2, contended: lock share by the host that served the agent's first completion."""
    per = defaultdict(lambda: [0, 0])
    for r in rows:
        if "qwen" not in r["model"] or r["config"] != "locks" or r["aware"] or r["n_agents"] != 2 or r["category"] == "control":
            continue
        tr = transcripts.get(r["episode_id"])
        if not tr:
            continue
        for a, rec in tr["agents"].items():
            t = (rec.get("turns") or [None])[0]
            host = ((t or {}).get("model_served") or "").split("@", 1)[-1].strip() or "unknown"
            per[host][0] += bool(tr["score"]["agents"][a].get("lock"))
            per[host][1] += 1
    return {"label": POST2 + " (Qwen lock use by serving host)", "hosts": {h: {"k": v[0], "n": v[1]} for h, v in per.items()}}


def gemini_settings(rows, transcripts):
    """Gemini agents (all phases): first completion reporting 0 reasoning tokens; temperature actually sent."""
    zero = tot = sent0 = 0
    for r in rows:
        if "gemini" not in r["model"] or r["episode_id"] not in transcripts:
            continue
        for rec in transcripts[r["episode_id"]]["agents"].values():
            t = (rec.get("turns") or [None])[0]
            if not t:
                continue
            tot += 1
            zero += ((t.get("usage") or {}).get("reasoning") or 0) == 0
            sent0 += (t.get("provider_meta") or {}).get("temperature_sent") == 0.0
    return {"label": POST2 + " (Gemini batch settings as logged)", "agents": tot, "first_completion_zero_reasoning": zero,
            "temperature_sent_zero": sent0}


def orchestrators():
    """Unfrozen orchestration code: sha256 recorded by src4_batch/switch_facts.py at the last run start
    (results4/full/batch_switch_facts_latest.json) against the local copy of src4_batch/."""
    from pipeline_common import RESULTS, ROOT
    facts = os.path.join(RESULTS, "batch_switch_facts_latest.json")
    batch = os.environ.get("SRC4_BATCH", os.path.join(ROOT, "src4_batch"))
    if not os.path.exists(facts):
        return None
    d = json.load(open(facts))
    rows = []
    for f, h in sorted(d.get("src4_batch_sha256", {}).items()):
        p = os.path.join(batch, f)
        local = sha256_file(p) if os.path.exists(p) else None
        rows.append({"file": f, "recorded_sha256": h, "local": "missing" if local is None else ("same" if local == h else "differs")})
    for f in ("prices_batch.json",):
        p = os.path.join(batch, f)
        if os.path.exists(p):
            rows.append({"file": f, "recorded_sha256": None, "local_sha256": sha256_file(p), "local": "not recorded"})
    return {"label": "Unfrozen orchestration code (hashes as recorded at the last run start; not in FREEZE.md)",
            "recorded_at": d.get("at_utc"), "rows": rows}


def review2(rows, transcripts, conf, raw):
    for r in rows:
        r["graph_cycle"] = int(raw[r["episode_id"]].get("graph_cycle") or 0)
    return OrderedDict([
        ("label", POST2), ("sign_tests", sign_tests(conf)), ("h6_detectable", h6_detectable(conf)),
        ("graph_agreement", graph_agreement(rows)), ("stale", stale_facts(rows, raw)), ("cas_leak", cas_leak(rows, transcripts)),
        ("partial_split", partial_split(rows, transcripts)), ("ws_transient", ws_transient(rows, transcripts)),
        ("control", control_and_habit(rows, transcripts)), ("schedule", schedule_facts(rows, transcripts)),
        ("turn_cap", turn_cap(rows, transcripts)), ("qwen_hosts_locks", qwen_hosts_locks(rows, transcripts)),
        ("gemini", gemini_settings(rows, transcripts)), ("orchestrators", orchestrators()),
    ])


def run(analysis):
    prov = json.load(open(os.path.join(analysis, "provenance.json")))
    conf = json.load(open(os.path.join(analysis, "confirmatory.json")))["registered"]
    paths = prov["analyzed_paths"]
    rows = X.load(paths)
    raw = {}
    for p in paths:
        with open(p, newline="") as f:
            for x in csv.DictReader(f):
                raw.setdefault(x["episode_id"], x)
    for r in rows:
        r["model_served"] = raw[r["episode_id"]].get("model_served", "")
    transcripts, missing = {}, 0
    for r in rows:
        p = X.transcript_path(r)
        if os.path.exists(p):
            with open(p) as f:
                transcripts[r["episode_id"]] = json.load(f)
        else:
            missing += 1
    return OrderedDict([
        ("label", POST + "; computed by latex/posthoc_review.py from saved CSVs and transcripts; no model calls"),
        ("dry_run", bool(prov["dry_run"])),
        ("inputs", [{"path": os.path.abspath(p), "sha256": sha256_file(p)} for p in paths]),
        ("n_rows", len(rows)), ("missing_transcripts", missing),
        ("template_boot", template_boot(rows, conf)), ("exact_bounds", exact_bounds(conf)),
        ("control_use", control_use(rows)), ("store_goodput", store_goodput(rows, transcripts)),
        ("lease_split", lease_split(rows, transcripts)), ("same_reply", same_reply(rows, transcripts)),
        ("serving", serving(rows, transcripts)), ("sql", sql_slice(os.path.join(RESULTS_SQL, "results.csv"))),
        ("review2", review2(rows, transcripts, conf, raw)),
    ])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis", required=True)
    a = ap.parse_args(argv)
    require_freeze()
    data = run(a.analysis)
    dst = os.path.join(a.analysis, OUT_NAME)
    assert os.path.basename(dst) not in PROTECTED
    with open(dst, "w") as f:
        json.dump(data, f, indent=1, default=str)
        f.write("\n")
    tb = data["template_boot"]["hypotheses"]
    print("posthoc review (POST HOC): template-level rejections " +
          ", ".join(f"{h} {v['n_reject']}/{len(v['tests'])} (registered {v['n_reject_registered']})" for h, v in tb.items()) +
          f"; wrote {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
