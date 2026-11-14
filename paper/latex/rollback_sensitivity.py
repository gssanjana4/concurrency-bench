#!/usr/bin/env python3
"""POST HOC sensitivity: rollback-only episodes rescored as serializable (NOT pre-registered, NOT confirmatory).

    python3 rollback_sensitivity.py --analysis DIR [--audit ../audit/H5_AUDIT.csv]

Why. The registered scorer (src4/score4.py, unchanged) counts an agent as *committed* once it has made an
action, even if it later wrote the record back. An agent that wrote, saw the conflict and restored its own
record is therefore committed and unfulfilled, no serial order of the committed intents can include its
intent, and the episode is scored ``non_serializable`` with primary label ``partial_action``. This follows
the registered definition, so the registered numbers stay the confirmatory result. This script asks how the
registered estimates would read if such rollback-only episodes were treated as serializable.

Rule (fixed before looking at the rescored estimates; matches the independent audit, audit/H5_AUDIT.md):
an episode is *rollback-only* if
  1. it is scored ``non_serializable`` with primary label ``partial_action`` (a ``stale_overwrite`` or
     ``write_skew`` label is never changed);
  2. it has no invariant violation;
  3. at least one committed agent has zero net effect: for every record it wrote, its last committed write
     restored the value the record had just before its first committed write (ledger ``effects``); and
  4. the final store equals a valid serial execution of the remaining committed agents' intents
     (frozen ``score4.serial_witness``).
Such an episode is relabelled serializable (no label). Nothing else changes.

Then the frozen ``analyze4.confirmatory`` is run on the relabelled rows and the H1, H4b and H6 estimates
(and, for completeness, the tests) are reported as POST HOC. H4a (``stale_overwrite``) and H4b
(``write_skew``) cannot change by construction; H2/H3 do not use labels.

Self-check: for every episode the script recomputes ``serial_witness`` on the recorded committed set and
asserts it reproduces the recorded ``non_serializable`` (the scorer is reproduced before it is varied).

Writes only DIR/rollback_sensitivity.json. Never writes analyze4 or run_analysis outputs, never touches src4
(FREEZE verified first).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict

from pipeline_common import PAPER, SRC4, require_freeze, sha256_file

sys.dont_write_bytecode = True
sys.path.insert(0, SRC4)
import analyze4 as A  # noqa: E402  (frozen; imported, never modified)
import instances4  # noqa: E402
import records  # noqa: E402
import score4  # noqa: E402

OUT_NAME = "rollback_sensitivity.json"
PROTECTED = {"confirmatory.json", "confirmatory.md", "numbers.json", "tables.md", "provenance.json",
             "exploratory_posthoc.json"}
LABEL = "POST HOC sensitivity (not pre-registered, not confirmatory): rollback-only partial_action episodes relabelled serializable"


def transcript_path(row):
    return os.path.join(os.path.dirname(os.path.abspath(row["source"])), "transcripts", row["episode_id"] + ".json")


def build_task(tr):
    t = tr["task"]
    return instances4.build(t["factory"], int(t["instance"]), tr["n_agents"])


def coerce(store):
    return {rid: records.coerce_value(records.kind_of(rid), v["value"] if isinstance(v, dict) else v) for rid, v in store.items()}


def net_zero_agents(tr):
    first_old, last_new = defaultdict(dict), defaultdict(dict)
    for e in sorted(tr["ledger"]["effects"], key=lambda e: e["seq"]):
        a, r = e["agent_id"], e["record_id"]
        kind = records.kind_of(r)
        if r not in first_old[a]:
            first_old[a][r] = records.normalize_value(records.coerce_value(kind, e["old_value"]))
        last_new[a][r] = records.normalize_value(records.coerce_value(kind, e["new_value"]))
    return {a for a in first_old if all(last_new[a][r] == first_old[a][r] for r in first_old[a])}


def classify(tr):
    """Return (reproduced_ok, rollback_only, net_zero_committed_agents)."""
    task = build_task(tr)
    initial = dict(task.initial)
    final = coerce(tr["final_store"])
    sc = tr["score"]
    committed = set(sc["committed_agents"])
    witness = score4.serial_witness(task, committed, initial, final)
    reproduced = (witness is None) == bool(sc["non_serializable"])
    if not (sc["non_serializable"] and sc["primary_label"] == "partial_action" and not sc["invariant_violation"]):
        return reproduced, False, []
    nz = sorted(net_zero_agents(tr) & committed)
    if not nz:
        return reproduced, False, []
    ok = score4.serial_witness(task, committed - set(nz), initial, final) is not None
    return reproduced, ok, nz


def h5_lock_lease(rows):
    """Counted H5 agents under ``locks`` whose rejected write came at or after the expiry of their own lease on that
    record (a granted ``acquire_lock`` on it earlier, ``lease_expires_at`` <= step of the rejection)."""
    per = defaultdict(Counter)
    for r in rows:
        if r["task"] != A.H5_TEMPLATE or r["config"] != "locks" or r["n_agents"] != 2:
            continue
        with open(transcript_path(r)) as f:
            tr = json.load(f)
        calls = tr["ledger"]["calls"]
        for a in A.h5_from_transcript(tr):
            if not a["partial"]:
                continue
            ag = a["agent"]
            rej = next(c for c in calls if c["agent_id"] == ag and c["tool"] in ("update_record", "claim")
                       and c.get("reason") in A.H5_REJECT_REASONS)
            acq = [c for c in calls if c["agent_id"] == ag and c["tool"] == "acquire_lock" and c["status"] == 200
                   and c["record_id"] == rej["record_id"] and c["step"] < rej["step"]]
            per[r["model"]]["cases"] += 1
            per[r["model"]]["own_lease_expired"] += bool(acq) and acq[-1]["lease_expires_at"] is not None \
                and acq[-1]["lease_expires_at"] <= rej["step"]
    tot = Counter()
    for c in per.values():
        tot.update(c)
    return {"per_model": {m: dict(c) for m, c in per.items()}, "cases": tot["cases"], "own_lease_expired": tot["own_lease_expired"]}


def summarize(conf):
    out = {}
    for h in ("H1", "H4b", "H6"):
        hh = conf["hypotheses"][h]
        out[h] = {"verdict": hh["verdict"], "tests": []}
        for t in hh["tests"]:
            d = {k: t.get(k) for k in ("model", "status", "estimate", "ci_low", "ci_high", "p", "p_holm", "reject", "method",
                                       "n_complete_clusters")}
            for part in ("component_i", "component_ii"):
                if part in t:
                    d[part] = {k: t[part].get(k) for k in ("estimate", "ci_low", "ci_high", "p", "method")}
            out[h]["tests"].append(d)
    return out


def audit_counts(path):
    """Per-model counts from the independent H5 transcript audit (audit/H5_AUDIT.csv), if present."""
    if not path or not os.path.exists(path):
        return None
    per = defaultdict(Counter)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["set"] != "numerator":
                continue
            c = per[r["model"]]
            c["numerator"] += 1
            if r["classification"] == "CONFIRMED":
                c["confirmed"] += 1
                c["confirmed_turn_cap" if r["end_reason"] == "turn_cap" else "confirmed_returned"] += 1
            else:
                c["not_confirmed"] += 1
                c["rollback" if r["net_effect"].startswith("NET_ZERO") else "other_not_confirmed"] += 1
            c["same_turn"] += r["credit_issued_same_turn_as_rejected_write"] == "True"
    return {"source": os.path.relpath(path, PAPER), "per_model": {m: dict(c) for m, c in per.items()}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--audit", default=os.path.join(PAPER, "audit", "H5_AUDIT.csv"))
    a = ap.parse_args(argv)
    require_freeze()
    prov = json.load(open(os.path.join(a.analysis, "provenance.json")))
    paths = prov["analyzed_paths"]
    rows, _, _ = A.load(paths)
    failed = set().union(*(A.failed_episode_ids(p) for p in paths))

    per_model = defaultdict(Counter)
    per_cfg = defaultdict(Counter)
    reproduced_bad, missing = [], 0
    relabel = set()
    examples = defaultdict(list)
    for r in rows:
        p = transcript_path(r)
        if not os.path.exists(p):
            missing += 1
            continue
        with open(p) as f:
            tr = json.load(f)
        ok, rb, nz = classify(tr)
        if not ok:
            reproduced_bad.append(r["episode_id"])
        if r["non_serializable"] and r["label"] == "partial_action" and r["category"] != "control":
            per_model[r["model"]]["partial_action"] += 1
            if rb:
                per_model[r["model"]]["rollback_only"] += 1
                per_cfg[(r["model"], r["config"])]["rollback_only"] += 1
        if rb:
            relabel.add(r["episode_id"])
            if len(examples[r["model"]]) < 3:
                examples[r["model"]].append({"episode_id": r["episode_id"], "net_zero_agents": nz})
    if reproduced_bad:
        raise SystemExit(f"scorer not reproduced for {len(reproduced_bad)} episodes, e.g. {reproduced_bad[:3]}")

    new_rows = []
    for r in rows:
        if r["episode_id"] in relabel:
            r = dict(r, non_serializable=0, label="")
        new_rows.append(r)
    conf = A.confirmatory(new_rows, None, failed)
    reg = json.load(open(os.path.join(a.analysis, "confirmatory.json")))["registered"]

    out = {
        "label": LABEL,
        "rule": "non_serializable + partial_action + no invariant violation + >=1 committed agent with zero net effect "
                "+ final store = serial execution of the other committed agents",
        "analyze4_sha256": require_freeze()["analyze4.py"],
        "inputs": [{"path": os.path.abspath(p), "sha256": sha256_file(p)} for p in paths],
        "dry_run": bool(prov["dry_run"]),
        "n_rows": len(rows), "missing_transcripts": missing,
        "scorer_reproduced_all": True,
        "n_relabelled": len(relabel),
        "contended_partial_action_by_model": {m: dict(c) for m, c in per_model.items()},
        "rollback_only_by_model_config": {f"{m}|{c}": v["rollback_only"] for (m, c), v in sorted(per_cfg.items())},
        "examples": dict(examples),
        "registered": summarize(reg),
        "rescored": summarize(conf),
        "h5_audit": audit_counts(a.audit),
        "h5_locks_lease": h5_lock_lease(rows),
    }
    dst = os.path.join(a.analysis, OUT_NAME)
    assert os.path.basename(dst) not in PROTECTED
    with open(dst, "w") as f:
        json.dump(out, f, indent=1, default=str)
        f.write("\n")
    tot = Counter()
    for c in per_model.values():
        tot.update(c)
    print(f"rollback sensitivity (POST HOC): {len(relabel)} episodes relabelled; contended partial_action "
          f"{tot['rollback_only']}/{tot['partial_action']} rollback-only; wrote {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
