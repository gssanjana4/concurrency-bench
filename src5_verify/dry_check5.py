"""Checks over a full dry run's transcripts (fake models, no money): python3 src5_verify/dry_check5.py <base>

Run by ``run_conc_study2.sh --dry-run`` after the lanes and the channel rehearsal. It reads every transcript under
``<base>/*/dry_run/transcripts`` and ``<base>/rehearsal/dry_run/transcripts`` and fails (exit 1) unless:

1. the fake model exercised the channels the control-disjointness check is about (review V1 B4): some episodes
   granted locks and committed fenced writes; the peer-informed rehearsal delivered messages;
2. every control episode has 0 cross-agent *record* edges; control episodes with a delivered message occur only in
   the peer-informed configuration and are reported separately (their ``cross_agent_edges`` counts the messages);
3. in every control episode the fencing tokens on each record are 1, 2, ... in grant order and granted to one agent
   only (per-record counters: a token value carries nothing about the peer);
4. message ids are 1, 2, ... per recipient;
5. no grid configuration offers messages or names peers in the prompt (only ``all_peer_informed`` does);
6. a0's system prompt is byte-identical in each contended episode and its matched control;
7. the lease-aware mutual-exclusion gate (score5.mutual_exclusion_violations) finds nothing;
8. probe transcripts: one completion per agent, nothing executed, a0 absent from control probes;
9. (Round 3, review V2b C1) no agent of a grid-configuration control episode has a peer-caused contention signal
   (in the peer-informed rehearsal a delivered message is one, by definition);
10. (Round 3, task item 6) every expected_version 409 has the one neutral text (no "modified", no version);
11. (Round 3, task item 5) every lane's results pair each contended episode with its matched control, and the
    sensitivity re-score at 24 calls (rescore5) runs on every locks / all_available transcript.
"""

from __future__ import annotations

import collections
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("SRC5_DIR") or os.path.join(HERE, "..", "src5"))
sys.dont_write_bytecode = True

from records5 import CallRecord, Ledger  # noqa: E402
from score5 import mutual_exclusion_violations  # noqa: E402
from world5 import PEER_INFORMED_CONFIGS, VERSION_MISMATCH_TEXT  # noqa: E402
import rescore5  # noqa: E402
import run5  # noqa: E402


def ledger_of(tr):
    led = Ledger()
    led.calls = [CallRecord(**{k: v for k, v in c.items()}) for c in tr["ledger"]["calls"]]
    led.flags = dict(tr["ledger"]["flags"])
    return led


def main(argv=None) -> int:
    base = (argv or sys.argv[1:])[0]
    paths = sorted(glob.glob(os.path.join(base, "*", "dry_run", "transcripts", "*.json")))
    problems = []
    stats = collections.Counter()
    a0_prompt = {}
    for p in paths:
        tr = json.load(open(p))
        cfg, sc, led = tr["config"], tr["score"], tr["ledger"]
        ctrl = tr["task"]["category"] == "control"
        stats["episodes"] += 1
        if tr.get("probe"):
            stats["probe_episodes"] += 1
            for a, rec in tr["agents"].items():
                if rec["completions"] != 1 or rec["executions"]:
                    problems.append(f"{p}: probe agent {a} made {rec['completions']} completions, {len(rec['executions'])} calls")
            if ctrl and "a0" in tr["agents"]:
                problems.append(f"{p}: a0 probed under the control (its prompt equals the contended one)")
            continue
        calls = led["calls"]
        if any(c["tool"] == "acquire_lock" and c["status"] == 200 for c in calls):
            stats["episodes_with_lock_grants"] += 1
        if any(c["committed"] and c.get("fencing_token") is not None for c in calls):
            stats["episodes_with_fenced_writes"] += 1
        if sc.get("messages_delivered"):
            stats["episodes_with_delivered_messages"] += 1
        sysmsgs = {a: r["system"] for a, r in tr["agents"].items()}
        if cfg not in PEER_INFORMED_CONFIGS:
            if any("Agents you can message" in s for s in sysmsgs.values()):
                problems.append(f"{p}: peer list in a grid configuration {cfg}")
            if any(c["tool"] in ("send_message", "read_messages") and c["status"] == 200 for c in calls):
                problems.append(f"{p}: messaging succeeded in grid configuration {cfg}")
        key = (tr["model"], cfg, tr["concurrency_aware_prompt"], tr["task"]["family"], tr["task"]["instance"], tr["seed"])
        a0_prompt.setdefault(key, {})["control" if ctrl else "contended"] = sysmsgs.get("a0")
        if ctrl:
            stats["control_episodes"] += 1
            if sc.get("cross_agent_record_edges", 0):
                problems.append(f"{p}: control with {sc['cross_agent_record_edges']} cross-agent record edges")
            if sc.get("messages_delivered"):
                stats["control_episodes_with_messages"] += 1
                if cfg not in PEER_INFORMED_CONFIGS:
                    problems.append(f"{p}: control with delivered messages outside the peer-informed configuration")
            grants = collections.defaultdict(list)
            for ev in led["flags"].get("lock_events", []):
                if ev["event"] == "grant":
                    grants[ev["record_id"]].append((ev["token"], ev["holder"]))
            for rid, g in grants.items():
                stats["control_lock_grants"] += len(g)
                if [t for t, _ in g] != list(range(1, len(g) + 1)) or len({h for _, h in g}) != 1:
                    problems.append(f"{p}: control tokens on {rid} not a private 1..k sequence: {g}")
        by_recipient = collections.defaultdict(list)
        for c in calls:
            if c["tool"] == "read_messages" and c["status"] == 200:
                by_recipient[c["agent_id"]] += [m["message_id"] for m in c["response"].get("messages", [])]
        for r, ids in by_recipient.items():
            if ids and ids != list(range(1, len(ids) + 1)):
                problems.append(f"{p}: message ids to {r} not 1..k: {ids}")
        mx = mutual_exclusion_violations(ledger_of(tr))
        if mx:
            problems.append(f"{p}: mutual exclusion violations {mx[:3]}")
        if ctrl and cfg not in PEER_INFORMED_CONFIGS:  # a delivered peer message is a signal; reported apart (rule 2)
            sig = {a: s_.get("contention_signals", 0) for a, s_ in sc["agents"].items()}
            if any(sig.values()):
                problems.append(f"{p}: control agents with a contention signal {sig}")
        for c in calls:
            if c["reason"] in ("version_conflict", "invalid_version"):
                stats["version_409s"] += 1
                if c["response"].get("message") != VERSION_MISMATCH_TEXT.format(record_id=c["record_id"]) \
                        or "current_version" in c["response"]:
                    problems.append(f"{p}: 409 text {c['response']}")
        if cfg in ("locks", "all_available") and tr["n_agents"] == 2:
            st = rescore5.rescore_transcript(tr, 24)["status"]
            stats[f"rescore24_{st}"] += 1
        stats["cap_truncated"] += int(bool(sc.get("cap_truncated")))
    for lane in sorted(glob.glob(os.path.join(base, "*", "dry_run", "results.csv"))):
        with open(lane, newline="") as f:
            rows = list(csv.DictReader(f))
        bad = run5.unpaired(rows)
        stats["lanes_checked_for_pairs"] += 1
        if bad:
            problems.append(f"{lane}: {len(bad)} episodes without their matched partner, e.g. {bad[:3]}")
    for key, d in a0_prompt.items():
        if len(d) == 2 and d["contended"] != d["control"]:
            problems.append(f"a0 prompt differs between contended and control: {key}")
        stats["matched_pairs"] += len(d) == 2
    for need in ("episodes_with_lock_grants", "episodes_with_fenced_writes", "episodes_with_delivered_messages",
                 "control_lock_grants", "control_episodes_with_messages"):
        if not stats[need]:
            problems.append(f"channel not exercised: {need} = 0")
    print("dry_check5:", dict(stats))
    for pr in problems[:40]:
        print("  !!", pr)
    print(f"dry_check5: {'OK' if not problems else f'{len(problems)} problems'} over {len(paths)} transcripts")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
