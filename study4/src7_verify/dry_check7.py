"""Checks over a full dry run's transcripts (fake models, no money): python3 src7_verify/dry_check7.py <base>

Study 4 (src7; derived from the Study 3 check). Run by ``run_conc_study4.sh --dry-run`` after the lanes. Study 4 runs
contended episodes only (no controls), under the together start, in four lock configurations, 16 instances: the
control rules hold vacuously, the grid count is 512 per model, and rule 13 reads "under ``locks_s2text`` and
``locks_instr`` no response carries ``waited_rounds`` or ``locked``; under ``locks_signals`` and ``locks`` the dry run
exercised both". Study 3 text follows.

Study 3 (derived from src5_verify/dry_check5.py). Run by ``run_conc_study3.sh --dry-run`` after the lanes. Study 3
has no message channel in any configuration and no rehearsal, so the message checks (1, 4) are kept only as
"never delivered". Added Study 3 checks:

12. no control agent has a perceivable signal (score7.perceivable_signal_calls); no control response carries
    ``waited_rounds`` or ``locked``;
13. under ``locks_s2text`` no response carries ``waited_rounds`` or ``locked`` (the Study 2 texts); under the Study 3
    lock text (``locks``, ``all_available``) the dry run exercised both (some reported waits, some locked reads);
14. every transcript records its start mode, equal to the one in its episode id; under the staggered start every
    non-lead agent's first call comes at least ``stagger_min`` rounds after a0's start round;
15. in every distinct-amount family the two agents' intents carry different amounts; in ``transfer_same_amount`` the
    same amount;
16. the full grid is there: per model, 7 conditions x 8 families x 8 instances x 2 arms = 896 episodes;
17. the fake model does not depend on the model id, so the call log of every cell must be identical for the three
    models: the sync path (Qwen) and the batch path (Haiku, Sonnet) run the same episodes.

It reads every transcript under ``<base>/*/dry_run/transcripts`` and fails (exit 1) unless:

1. the fake model exercised the channels the control-disjointness check is about (review V1 B4): some episodes
   granted locks and committed fenced writes; the peer-informed rehearsal delivered messages;
2. every control episode has 0 cross-agent *record* edges; control episodes with a delivered message occur only in
   the peer-informed configuration and are reported separately (their ``cross_agent_edges`` counts the messages);
3. in every control episode the fencing tokens on each record are 1, 2, ... in grant order and granted to one agent
   only (per-record counters: a token value carries nothing about the peer);
4. message ids are 1, 2, ... per recipient;
5. no grid configuration offers messages or names peers in the prompt (only ``all_peer_informed`` does);
6. a0's system prompt is byte-identical in each contended episode and its matched control;
7. the lease-aware mutual-exclusion gate (score7.mutual_exclusion_violations) finds nothing;
8. probe transcripts: one completion per agent, nothing executed, a0 absent from control probes;
9. (Round 3, review V2b C1) no agent of a grid-configuration control episode has a peer-caused contention signal
   (in the peer-informed rehearsal a delivered message is one, by definition);
10. (Round 3, task item 6) every expected_version 409 has the one neutral text (no "modified", no version);
11. (Round 3, task item 5) every lane's results pair each contended episode with its matched control, and the
    sensitivity re-score at 24 calls (rescore7) runs on every locks / all_available transcript.
"""

from __future__ import annotations

import collections
import csv
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("SRC7_DIR") or os.path.join(HERE, "..", "src7"))
from world7 import world_config  # noqa: E402
sys.dont_write_bytecode = True

from records7 import CallRecord, Ledger  # noqa: E402
from score7 import mutual_exclusion_violations  # noqa: E402
from world7 import PEER_INFORMED_CONFIGS, VERSION_MISMATCH_TEXT  # noqa: E402
import rescore7  # noqa: E402
import run7  # noqa: E402


def ledger_of(tr):
    led = Ledger()
    led.calls = [CallRecord(**{k: v for k, v in c.items()}) for c in tr["ledger"]["calls"]]
    led.flags = dict(tr["ledger"]["flags"])
    return led


def floor_decision(base: str):
    """The last decision of the Fable stage rule in this dry run (src7/floor_gate7.py), if any."""
    path = os.path.join(base, "floor_gate_dry.json")
    if not os.path.exists(path):
        return None
    lines = [ln for ln in open(path).read().splitlines() if ln.strip()]
    return json.loads(lines[-1])["decision"] if lines else None


def main(argv=None) -> int:
    base = (argv or sys.argv[1:])[0]
    paths = sorted(glob.glob(os.path.join(base, "*", "dry_run", "transcripts", "*.json")))
    problems = []
    stats = collections.Counter()
    a0_prompt = {}
    cell_logs = {}
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
        start = tr.get("start_mode")
        key = (tr["model"], cfg, start, tr["concurrency_aware_prompt"], tr["task"]["family"], tr["task"]["instance"], tr["seed"])
        stats[f"grid|{tr['model']}"] += 1
        sig = json.dumps([[c["agent_id"], c["tool"], c["args"], c["status"], c["step"]] for c in calls], sort_keys=True)
        cell_logs.setdefault((cfg, start, tr["task"]["factory"], tr["task"]["instance"], tr["seed"]), {})[tr["model"]] = sig
        # 14. start mode recorded and consistent with the id; the stagger held
        if start not in ("together", "staggered") or (("+stg__" in tr["episode_id"]) != (start == "staggered")):
            problems.append(f"{p}: start mode {start!r} does not match the episode id")
        if start == "staggered":
            st = led["flags"]["start_rounds"]
            ids = sorted(tr["agents"])
            for a in ids[1:]:
                first = min((c["step"] for c in calls if c["agent_id"] == a), default=None)
                if first is not None and first < st[ids[0]] + tr["schedule"]["stagger_min"]:
                    problems.append(f"{p}: {a} started at round {first}, before a0 start {st[ids[0]]} + stagger_min")
            stats["staggered_episodes"] += 1
        # 15. amounts
        fam = tr["task"]["family"]
        amts = {a: (re.search(r"\b(\d+(?:\.\d+)?)\b", t) or [None, None])[1] for a, t in tr["task"]["intents"].items()}
        if fam not in ("seat_same", "ticket_same") and len(amts) == 2:
            same = len(set(amts.values())) == 1
            if same != (fam == "transfer_same_amount"):
                problems.append(f"{p}: amounts {amts} in family {fam}")
        # 12, 13. Study 3 response fields
        s3f = [c for c in calls if "waited_rounds" in (c["response"] or {}) or "locked" in (c["response"] or {})]
        signals = world_config(cfg).coordination.lock_signals  # Study 4: locks_signals and locks carry the signals
        if (ctrl or not signals) and s3f:
            problems.append(f"{p}: {len(s3f)} responses with waited_rounds/locked in {'a control' if ctrl else cfg}")
        if not ctrl and signals:
            stats["s3_waits_reported"] += sum(1 for c in calls if c["tool"] == "acquire_lock" and "waited_rounds" in c["response"])
            stats["s3_locked_reads"] += sum(1 for c in calls if c["tool"] == "get_record" and c["response"].get("locked") is True)
        if ctrl and any(s_.get("perceivable_signals", 0) for s_ in sc["agents"].values()):
            problems.append(f"{p}: control agents with a perceivable signal")
        stats["agents_with_perceivable_signal"] += sum(1 for s_ in sc["agents"].values() if s_.get("perceivable_signals", 0))
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
        if world_config(cfg).coordination.locks and tr["n_agents"] == 2:
            st = rescore7.rescore_transcript(tr, 24)["status"]
            stats[f"rescore24_{st}"] += 1
        stats["cap_truncated"] += int(bool(sc.get("cap_truncated")))
    for lane in sorted(glob.glob(os.path.join(base, "*", "dry_run", "results.csv"))):
        with open(lane, newline="") as f:
            rows = list(csv.DictReader(f))
        # Study 4 has no controls: every episode is its own "pair"; check instead that no episode is written twice
        ids = [r["episode_id"] for r in rows]
        stats["lanes_checked_for_duplicates"] += 1
        if len(ids) != len(set(ids)):
            problems.append(f"{lane}: {len(ids) - len(set(ids))} duplicate episode rows")
    for key, d in a0_prompt.items():
        if len(d) == 2 and d["contended"] != d["control"]:
            problems.append(f"a0 prompt differs between contended and control: {key}")
        stats["matched_pairs"] += len(d) == 2
    for need in ("episodes_with_lock_grants", "episodes_with_fenced_writes", "s3_waits_reported",
                 "s3_locked_reads", "agents_with_perceivable_signal"):  # Study 4: no controls, no staggered start
        if not stats[need]:
            problems.append(f"channel not exercised: {need} = 0")
    if stats["episodes_with_delivered_messages"]:
        problems.append("messages delivered in a Study 4 dry run (no Study 4 configuration offers messages)")
    for k, logs in sorted(cell_logs.items(), key=str):  # 17. sync and batch paths ran the same episodes
        if len(set(logs.values())) > 1:
            problems.append(f"call logs differ between models for cell {k}: {sorted(logs)}")
        stats["cells_identical_across_models"] += len(set(logs.values())) == 1 and len(logs) > 1
    for k, v in stats.items():  # 16. the whole grid
        expected = 512  # Study 4: 4 lock configs x 8 families x 16 instances, contended only
        if k == "grid|claude-fable-5" and floor_decision(base) == "floor":
            expected = 128  # the registered Fable stage rule stopped Fable after stage 1 (locks_s2text)
        if k.startswith("grid|") and v != expected:
            problems.append(f"{k}: {v} episodes, expected {expected}")
    print("dry_check7:", dict(stats))
    for pr in problems[:40]:
        print("  !!", pr)
    print(f"dry_check7: {'OK' if not problems else f'{len(problems)} problems'} over {len(paths)} transcripts")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
