"""Mutation testing for the Study 2 harness (src5), the approach of src4_verify/mutate.py.

V2: mutants for every pre-spend fix (reviews V1 B1-B6, V2 F1-F9; ids W12, W16-W23, C07-C09, S23-S32, A04-A05, K01,
M01-M06, P01, R01, L01) on top of the v1 set; mutants whose source text changed were re-targeted (W08, W09, W13).
Round 3: W24-W26, S33-S43 (S37 re-targeted after its first form -- "a held acquire is not a signal" -- survived:
it is equivalent, since a held acquire always ends in a 423 or in a grant after another agent's lock, both already
signals), L02-L06, P02-P04, F01-F02 (reviews V1b, V2b; task items 1-8); W13, W16, W17, S32
re-targeted. Round 4: M07-M15 (refusal and safety stops as their own end reasons, V2b note 9). The copy keeps the repo layout so mutants of ../run_conc_study2.sh and freeze5 are tested too.

Each mutant is one exact, unique string replacement applied to a fresh copy of /home/claude/src5 in a temp
directory (the original files are never touched); the suite (tests5) runs on the copy. A mutant is *killed* if
the suite fails. ``metric`` marks mutants whose survival would change a reported number.

    python3 src5_verify/mutate5.py [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, NamedTuple

SRC = os.environ.get("SRC5_DIR", "/home/claude/src5")
STUDY1_INSTANCES = "/home/claude/src4/instances_full.json"


class Mutant(NamedTuple):
    mid: str
    file: str
    old: str
    new: str
    desc: str
    metric: bool


M: List[Mutant] = [
    # ---------------------------------------------------------------- world5: locks and fencing
    Mutant("W01", "world5.py", "            lock.calls_left -= 1\n", "            lock.calls_left -= 0\n", "leases never consumed", True),
    Mutant("W02", "world5.py", "            if lock.calls_left < 0:", "            if lock.calls_left < -1:", "lease off by one", True),
    Mutant("W03", "world5.py", "            self._consume_leases(agent_id)\n", "", "own calls do not consume leases", True),
    Mutant("W04", "world5.py", "            if lock.holder != agent_id:\n                log[\"conflict\"] = True\n                return 423",
           "            if False:\n                log[\"conflict\"] = True\n                return 423", "other agents may write locked records", True),
    Mutant("W05", "world5.py", "            if tok is None:\n                return 428", "            if False:\n                return 428", "holder may write without token", True),
    Mutant("W06", "world5.py", "            if tok < latest:", "            if tok > latest:", "stale token check inverted", True),
    Mutant("W07", "world5.py", "            return 409, \"lease_expired\"", "            return None  # ", "expired token accepted", True),
    Mutant("W08", "world5.py", "        if lock is None or lock.holder != agent_id:\n            return 409, \"not_lock_holder\", {\"error\": \"not_lock_holder\",\n                                            \"message\": f\"409 Conflict: you do not hold a lock on {rid}.\"}",
           "        if lock is None:\n            return 409, \"not_lock_holder\", {\"error\": \"not_lock_holder\",\n                                            \"message\": f\"409 Conflict: you do not hold a lock on {rid}.\"}",
           "anyone may renew a lock", True),
    Mutant("W09", "world5.py", "            self._next_token[rid] = token + 1\n", "            self._next_token[rid] = token\n", "fencing tokens not increasing", True),
    Mutant("W10", "world5.py", "        return {\"current_version\": record.version} if self.config.coordination.expose_versions else {}",
           "        return {\"current_version\": record.version}", "423 leaks versions under locks", False),
    Mutant("W11", "world5.py", "        if lease > self.config.max_lease_calls:", "        if False:", "no maximum lease", False),
    Mutant("W12", "world5.py", "        if record.value == holder:\n            body2: Dict[str, Any]",
           "        if record.value is not None and record.value != holder and self.config.coordination.conditional_writes != CAS_OFF:\n"
           "            return self._conflict(record, \"already has a different holder\", \"claim_conflict\", log)\n"
           "        if record.value == holder:\n            body2: Dict[str, Any]", "V1 B1: claim test-and-set again under CAS", True),
    Mutant("W13", "world5.py", "        if expected is not None and expected != record.version:\n            body = self._conflict(record, \"version_conflict\", log)\n            if not self._written_by_other_since(record.record_id, expected, agent_id):\n                log[\"conflict\"] = False\n                return body[0], \"invalid_version\", body[2]\n            return body\n        return 200, None, self._commit(agent_id, record, value, \"update_record\"",
           "        if expected is not None and expected > record.version:\n            body = self._conflict(record, \"version_conflict\", log)\n            if not self._written_by_other_since(record.record_id, expected, agent_id):\n                log[\"conflict\"] = False\n                return body[0], \"invalid_version\", body[2]\n            return body\n        return 200, None, self._commit(agent_id, record, value, \"update_record\"",
           "CAS accepts stale versions", True),
    Mutant("W16", "world5.py", "        if expected is not None and expected != record.version:\n            body = self._conflict(record, \"version_conflict\", log)\n            if not self._written_by_other_since(record.record_id, expected, agent_id):\n                log[\"conflict\"] = False\n                return body[0], \"invalid_version\", body[2]\n            return body\n        if record.value == holder:",
           "        if False:\n            body = self._conflict(record, \"version_conflict\", log)\n            if not self._written_by_other_since(record.record_id, expected, agent_id):\n                log[\"conflict\"] = False\n                return body[0], \"invalid_version\", body[2]\n            return body\n        if record.value == holder:",
           "V1 B1: claim ignores expected_version", True),
    Mutant("W17", "world5.py", "LOCK_WAIT_ROUNDS = 150  #", "LOCK_WAIT_ROUNDS = 6  #", "V1 B3: lock wait back to 6 rounds", True),
    Mutant("W24", "world5.py", "LOCK_WAIT_ROUNDS = 150  #", "LOCK_WAIT_ROUNDS = 48  #", "R3 R1: lock wait back to V2's 48 rounds", True),
    Mutant("W25", "world5.py", "        return 409, reason, {\"error\": \"conflict\", \"message\": VERSION_MISMATCH_TEXT.format(record_id=record.record_id)}",
           "        return 409, reason, {\"error\": \"conflict\", \"message\": f\"409 Conflict: {record.record_id} was modified; current version is {record.version}.\",\n                             \"current_version\": record.version}",
           "R3 item 6: 409 says 'was modified' and leaks the current version", False),
    Mutant("W26", "world5.py", "            if not self._written_by_other_since(record.record_id, expected, agent_id):\n                log[\"conflict\"] = False\n                return body[0], \"invalid_version\", body[2]\n            return body\n        return 200, None, self._commit(agent_id, record, value, \"update_record\"",
           "            if not self._written_by_other_since(record.record_id, expected, agent_id):\n                log[\"conflict\"] = False\n                return body[0], \"invalid_version\", {**body[2], \"message\": body[2][\"message\"] + \" (no other write)\"}\n            return body\n        return 200, None, self._commit(agent_id, record, value, \"update_record\"",
           "R3 item 6: invalid_version text differs from version_conflict (arm cue)", False),
    Mutant("W18", "world5.py", "            token = self._next_token.get(rid, 1)\n", "            token = sum(self._next_token.values()) + 1\n",
           "V1 B4: global fencing-token counter (control channel)", True),
    Mutant("W19", "world5.py", "        msg = Message(self._inbox_count[to_agent], agent_id, to_agent, text, self.clock)",
           "        msg = Message(len(self._messages) + 1, agent_id, to_agent, text, self.clock)", "V1 B4: global message ids", True),
    Mutant("W20", "world5.py", "                \"message\": f\"409 Conflict: your lock on {rid} has ended.\"}",
           "                \"message\": f\"409 Conflict: your lock on {rid} has ended; acquire it again.\"}", "V1 B5: steering 409 text", False),
    Mutant("W21", "world5.py", "                                         \"step\": self.clock, \"own_call\": self._own_calls[agent_id], \"seq\": self._seq_now()})",
           "                                         \"step\": self.clock, \"own_call\": self._own_calls[agent_id]})", "V1 B6: expire events without seq", True),
    Mutant("W22", "world5.py", "                 \"(writes without it get 423). When", "                 \"(others get 423). When", "V2 F1: peer cue back in lock text", False),
    Mutant("W23", "world5.py", "ALIASES: Dict[str, str] = {\"all_available\": \"cas_available+locks\",",
           "ALIASES: Dict[str, str] = {\"all_available\": \"cas_available+locks+messages\",", "V2 F4: messages (peer list) in all_available", True),
    Mutant("W14", "world5.py", "        if lock is None or lock.holder == agent_id:\n            return False", "        if True:\n            return False",
           "acquire never waits", True),
    Mutant("W15", "world5.py", "    if config.coordination.messages and peers:", "    if peers:", "peer list shown without messages (cue)", False),
    # ---------------------------------------------------------------- scheduler5
    Mutant("C01", "scheduler5.py", "        world.release_all(r.agent_id)\n", "", "locks not released at agent end", True),
    Mutant("C02", "scheduler5.py", "                delay += r.rng_gap.randint(schedule.gap_min, schedule.gap_max)", "                delay += schedule.gap_max",
           "fixed think time (Study 1 lockstep)", True),
    Mutant("C07", "scheduler5.py", "            if getattr(call, \"ends_turn\", True):", "            if call.tool in READ_TOOLS:",
           "V1 B2: think gap after reads only", True),
    Mutant("C08", "scheduler5.py", "                deadlock_rounds += 1\n", "                deadlock_rounds += 0\n", "V2 F5: deadlock not recorded", True),
    Mutant("C09", "scheduler5.py", "                    if isinstance(stop.value, AgentStop) and stop.value.reason in AGENT_STOP_REASONS:",
           "                    if False:", "V2 sec. 5: truncation ends as returned", True),
    Mutant("C03", "scheduler5.py", "        r.resume_at = 1 + random.Random(f\"{s}|{agent_id}|start\").randint(0, schedule.start_jitter)", "        r.resume_at = 1",
           "no start jitter", True),
    Mutant("C04", "scheduler5.py", "        order_rng.shuffle(order)\n", "", "fixed round order (first mover a0)", True),
    Mutant("C05", "scheduler5.py", "                if clock - r.wait_start < world_config.lock_wait_rounds:", "                if False:",
           "blocking lock wait disabled", True),
    Mutant("C06", "scheduler5.py", "            if r.turns >= schedule.turn_cap:", "            if r.turns > schedule.turn_cap:", "turn cap off by one", True),
    # ---------------------------------------------------------------- score5
    Mutant("S01", "score5.py", "            return prefix if key[1] == target else None", "            return prefix", "serial witness ignores final state", True),
    Mutant("S02", "score5.py", "    for reader, reads in all_reads(ledger).items():\n        for record, version in reads:",
           "    for reader, reads in all_reads(ledger).items():\n        for record, version in sorted(reads)[-1:]:", "DSG uses last read only", True),
    Mutant("S03", "score5.py", "            if src is not None and src != reader:\n                edges.add(Edge(src, reader, \"wr\"",
           "            if False:\n                edges.add(Edge(src, reader, \"wr\"", "drop wr edges", True),
    Mutant("S04", "score5.py", "            if nxt is not None and nxt != reader:\n                edges.add(Edge(reader, nxt, \"rw\"",
           "            if False:\n                edges.add(Edge(reader, nxt, \"rw\"", "drop rw edges", True),
    Mutant("S05", "score5.py", "        if nxt is not None and nxt != agent:\n            edges.add(Edge(agent, nxt, \"ww\"",
           "        if False:\n            edges.add(Edge(agent, nxt, \"ww\"", "drop ww edges", True),
    Mutant("S06", "score5.py", "    return [e.seq for e in ledger.effects if bases[e.seq][0] < e.old_version and bases[e.seq][1] is not None]",
           "    return [e.seq for e in ledger.effects if bases[e.seq][0] < e.old_version]", "lost_update = any stale write (blind incl.)", True),
    Mutant("S07", "score5.py", "    return [e.seq for e in ledger.effects if bases[e.seq][0] < e.old_version]\n",
           "    return [e.seq for e in ledger.effects if bases[e.seq][0] < e.old_version - 1]\n", "stale off by one", True),
    Mutant("S08", "score5.py", "        if isinstance(ev, int) and ev > bases[e.seq][0]:", "        if False:", "laundered CAS never flagged", True),
    Mutant("S09", "score5.py", "    committed = tuple(sorted({e.agent_id for e in actions} - rb))", "    committed = tuple(sorted({e.agent_id for e in actions}))",
           "rolled-back agents counted as committed", True),
    Mutant("S10", "score5.py", "        rolled = agent_id in rb\n", "        rolled = False\n", "no rollback detection per agent", True),
    Mutant("S11", "score5.py", "        guard_violation = committed_any and not rolled and bool(guard_bad) and not missing",
           "        guard_violation = False", "guard violation never flagged", True),
    Mutant("S12", "score5.py", "                   and bool(acted_records & set(intent.writes)) and not set(intent.writes) <= acted_records)",
           "                   and False)", "missing leg never flagged", True),
    Mutant("S13", "score5.py", "        out_of_intent = bool(acted_records - set(intent.writes))", "        out_of_intent = False",
           "out-of-intent never flagged", True),
    Mutant("S14", "score5.py", "            if e1.src == e2.dst and e1.dst == e2.src and e1.record != e2.record:",
           "            if e1.src == e2.dst and e1.dst == e2.src:", "write skew allows same record", True),
    Mutant("S15", "score5.py", "        if any(inv.check(initial, s, ledger, task) for s in states):", "        if inv.check(initial, states[-1], ledger, task):",
           "ever_violated = final only", True),
    Mutant("S16", "score5.py", "            if reader != a and reads & undone:", "            if reads & undone:", "exposure counts the compensator itself", True),
    Mutant("S17", "score5.py", "    elif flags[\"compensated\"] and not fs_bad and not flags[\"violated_at_end\"] and not any(flags[k] for k in hard):",
           "    elif flags[\"compensated\"]:", "compensated even when the final state is broken", True),
    Mutant("S18", "score5.py", "            if color[m] == GREY:", "            if color[m] == BLACK:", "cycle detection broken", True),
    Mutant("S19", "score5.py", "    cycle = find_cycle(sessions(ledger), edges)", "    cycle = find_cycle(committed, edges)",
           "DSG node set = committed only", True),
    Mutant("S20", "score5.py", "            and normalize_value(by_seq[c.effect_seq].new_value) == normalize_value(by_seq[c.effect_seq].old_value)",
           "            and True", "promote counts value-changing writes", True),
    Mutant("S21", "score5.py", "    overlap = bool(writers) and all(fr < min((s for b, s in first_write.items() if b != a), default=10 ** 12)",
           "    overlap = bool(writers) and all(fr < max((s for b, s in first_write.items() if b != a), default=10 ** 12)",
           "reads_overlap uses max", True),
    Mutant("S22", "score5.py", "        fulfilled = set(intent.writes) <= written and not rolled", "        fulfilled = bool(set(intent.writes) & written)",
           "fulfilled = any written record", True),
    Mutant("S23", "score5.py", "        cross_agent_edges=cross + len(msgs), flags=flags,", "        cross_agent_edges=cross, flags=flags,",
           "V1 B4: delivered messages not counted as cross-agent edges", True),
    Mutant("S24", "score5.py", "        if w is not None and w.grant_seq is not None and read_seq is not None and read_seq < w.grant_seq:",
           "        if False:", "V1 B5: fenced_stale_basis never flagged", True),
    Mutant("S25", "score5.py", "            elif w.grant_seq is not None and not _live(w, c.seq):", "            elif False:",
           "V1 B6: mutex gate ignores the lease window", True),
    Mutant("S26", "score5.py", "                if w.holder != c.agent_id:\n                    out.append(f\"call {c.seq}: {c.agent_id} wrote",
           "                if False:\n                    out.append(f\"call {c.seq}: {c.agent_id} wrote", "V1 B6: mutex gate ignores non-holder writes", True),
    Mutant("S27", "score5.py", "            lock=any(c.tool == \"acquire_lock\" and c.reason not in WELL_FORMED_REFUSALS for c in calls),",
           "            lock=any(c.tool == \"acquire_lock\" and c.status == 200 for c in calls),", "V2 F2: lock coded as granted only", True),
    Mutant("S28", "score5.py", "        dsg_basis_cycle=find_cycle(bnodes, bedges) is not None,", "        dsg_basis_cycle=find_cycle(sessions(ledger), edges) is not None,",
           "basis DSG = all-reads DSG", True),
    Mutant("S29", "score5.py", "                  if e.seq != last_by_rec[e.record_id] and normalize_value(e.new_value) != restore[e.record_id]}",
           "                  if e.seq != last_by_rec[e.record_id]}", "exposure counts restoring versions", True),
    Mutant("S30", "score5.py", "            cas=any(c.tool in WRITE_TOOLS and c.args.get(\"expected_version\") is not None",
           "            cas=any(c.tool == \"update_record\" and c.args.get(\"expected_version\") is not None", "conditional claim not counted as CAS", True),
    Mutant("S31", "score5.py", "        unfulfilled_but_valid = (not fulfilled) and valid_at_end and end_reason not in NON_FINISH_ENDS",
           "        unfulfilled_but_valid = (not fulfilled) and valid_at_end", "truncated agents counted as abandoning", True),
    Mutant("S32", "score5.py", "    before = None if first_prot_call is None or first_sig is None else first_prot_call <= first_sig",
           "    before = None if first_prot_call is None or first_sig is None else first_prot_call <= first_sig + 1", "protection timing off by one", True),
    # ---------------------------------------------------------------- Round 3 (reviews V1b, V2b; task items 1-8)
    Mutant("S33", "score5.py", "            src = installer.get((c.record_id, c.read_version))\n            sig = sig or (src is not None and src != a)",
           "            src = installer.get((c.record_id, c.read_version))\n            sig = sig or src is not None",
           "R3 C1: an own write read back counts as contention", True),
    Mutant("S34", "score5.py", "        sig = c.status == 423 or (c.status == 409 and c.conflict)", "        sig = c.status in (409, 423)",
           "R3 C1: own 409s (invalid_version, lease_expired) count as contention", True),
    Mutant("S35", "score5.py", "    before = None if first_prot_call is None or first_sig is None else first_prot_call <= first_sig",
           "    before = None if first_prot_call is None or first_sig is None else first_prot_call < first_sig",
           "R3 C1: a protective call that meets contention coded as reactive (V2 rule)", True),
    Mutant("S36", "score5.py", "            if c.reason is None and granted.get(c.record_id, set()) - {a}:\n                sig = True",
           "            if False:\n                sig = True", "R3 C1: a lock grant after another agent's lock is not a signal", True),
    Mutant("S37", "score5.py", "        sig = c.status == 423 or (c.status == 409 and c.conflict)", "        sig = c.status == 409 and c.conflict",
           "R3 C1: a 423 (write refused by another agent's lock) is not a signal", True),
    Mutant("S38", "score5.py", "    lock_after = None if first_lock_call is None else (first_sig is not None and first_lock_call > first_sig)",
           "    lock_after = None if first_lock_call is None else (first_sig is not None and first_lock_call >= first_sig)",
           "R3 C1: lock_after_contention counts a lock that met the signal", True),
    Mutant("S39", "score5.py", "                                  and not any(by_seq[s].agent_id == agent_id for s in unread_basis))),",
           "                                  )),", "R3 item 3: a locked blind overwrite counts as effective locking", True),
    Mutant("S40", "score5.py", "        if g is None or not any(g < r < c.seq for r in reads.get((c.agent_id, c.record_id), [])):",
           "        if g is None or not any(r < c.seq for r in reads.get((c.agent_id, c.record_id), [])):",
           "R3 item 3: a read before the grant counts as read under the token", True),
    Mutant("S41", "score5.py", "    cap_trunc = outcome == \"failed\" and any(s.end_reason == \"turn_cap\" for s in agents.values())",
           "    cap_trunc = False", "R3 item 8: cap_truncated never set", True),
    Mutant("S42", "score5.py", "            if c.record_id in foot:\n                return \"indeterminate\"",
           "            if False:\n                return \"indeterminate\"", "R3 item 8: 24-call re-score ignores what the cut agent changed later", True),
    Mutant("S43", "score5.py", "    over = tuple(a for a in task.agent_ids if any((c.own_call or 0) > cap for c in ledger.calls_for(a)))",
           "    over = tuple(a for a in task.agent_ids if any((c.own_call or 0) > cap + 1 for c in ledger.calls_for(a)))",
           "R3 item 8: re-score cap off by one", True),
    Mutant("L02", "run5.py", "        fams[f].sort(key=lambda t: t.endswith(I.CONTROL_SUFFIX))  # contended first, then its control",
           "        fams[f].sort(key=lambda t: not t.endswith(I.CONTROL_SUFFIX))", "R3 item 5: control before contended", False),
    Mutant("L03", "run5.py", "            estimate = sum(episode_estimate(observed, c) for c in group)",
           "            estimate = episode_estimate(observed, cell)", "R3 item 5: no pair reservation (per-episode gate)", True),
    Mutant("L04", "run5.py", "    if not all(done(c) or is_held(c) for c in pair):\n        return []",
           "    if False:\n        return []", "R3 item 5: an episode is written without its matched partner", True),
    Mutant("L05", "run5.py", "    for seed in seeds:\n        for i in range(max(k_instances, 1)):\n            for fam, fam_tasks in fams.items():",
           "    for fam, fam_tasks in fams.items():\n        for i in range(max(k_instances, 1)):\n            for seed in seeds:",
           "R3 item 5: family-major order (a cut drops whole families)", True),
    Mutant("L06", "../run_conc_study2.sh", "LANES=(gemini anthropic openrouter)", "LANES=(anthropic openrouter gemini)",
           "R3 item 5: Gemini lane not first", True),
    Mutant("P02", "plan5.py", "    \"openrouter:openai/gpt-5.5-20260423\": 2,\n    \"openrouter:google/gemini-4-argon-20261013\": 8,",
           "    \"openrouter:openai/gpt-5.5-20260423\": 4,\n    \"openrouter:google/gemini-4-argon-20261013\": 8,",
           "R3 item 4: GPT probes back to 4 instances", True),
    Mutant("P03", "plan5.py", "    return extra * INPUT_USD_PER_MTOK[model] * cache * gem / 1e6", "    return 0.0",
           "R3 item 4: tool-text tokens not priced", True),
    Mutant("P04", "plan5.py", "    extra = max(0, menu_chars(config) - int(costs[\"study1_menu_chars\"][c1])) / CHARS_PER_TOKEN",
           "    extra = max(0, 2000 - int(costs[\"study1_menu_chars\"][c1])) / CHARS_PER_TOKEN",
           "R3 item 4: menu size not read from the code (a longer tool text is not priced)", True),
    Mutant("F01", "freeze5.py", "    out = _listed(\"\", SRC5_EXTS, \"\") + _listed(\"../src5_batch\", BATCH_EXTS, \"../src5_batch/\")",
           "    out = _listed(\"\", SRC5_EXTS, \"\")", "R3 item 7: freeze omits the batch layer", True),
    Mutant("F02", "freeze5.py", "EXTRA = (\"../src5_verify/dry_check5.py\", \"../run_conc_study2.sh\")", "EXTRA = ()",
           "R3 item 7: freeze omits the runner and dry_check5", True),
    # ---------------------------------------------------------------- tasks5 / instances5
    Mutant("T01", "tasks5.py", "        if all(normalize_value(last[k]) == normalize_value(first[k]) for k in keys):",
           "        if any(normalize_value(last[k]) == normalize_value(first[k]) for k in keys):", "rollback = any record restored", True),
    Mutant("T02", "tasks5.py", "        if actual != expected:", "        if False:", "accounting invariant disabled", True),
    Mutant("T03", "tasks5.py", "        return values[self.record] >= self.amount\n", "        return values[self.record] >= 0\n", "Decrement guard ignores amount", True),
    Mutant("T04", "tasks5.py", "        return spent + self.amount <= values[self.cap]", "        return spent <= values[self.cap]", "budget guard ignores own spend", True),
    Mutant("T05", "tasks5.py", "        initial.update(part.initial)\n        intents[a] = part.intents[a]", "        initial.update(parts[0].initial)\n        intents[a] = parts[0].intents[a]",
           "control shares one record group", True),
    Mutant("T06", "tasks5.py", "    return Invariant(f\"sum_within_cap[{cap}]\", check, \"constraint\")", "    return Invariant(f\"sum_within_cap[{cap}]\", check, \"conservation\")",
           "cap not checked for ever_violated", True),
    Mutant("I01", "instances5.py", "    return build(p.tags[0])", "    return build(p.tags[1])", "contended group differs from a0's control group", True),
    Mutant("I02", "instances5.py", "            dsts = {a: f\"account:{p.dest_prefix}-{tag}-{p.words[i]}\" for i, a in enumerate(ids)}",
           "            dsts = {a: f\"account:{p.dest_prefix}-{tag}-{a}\" for i, a in enumerate(ids)}", "agent ids in record names (cue)", False),
    Mutant("I03", "instances5.py", "        if shape(_draw(family, index, attempt, 2), family) not in taken:", "        if True:",
           "no disjointness from Study 1", False),
    # ---------------------------------------------------------------- agents5 / design5 / budget5
    Mutant("A01", "agents5.py", "            seq = [(r, values[r]) for r in sorted(intent.reads)] + [(own, new[own])]",
           "            seq = [(own, new[own])] + [(r, values[r]) for r in sorted(intent.reads) if r != own]", "promotion after the own write", True),
    Mutant("A02", "agents5.py", "                tok = held.get(rid) if fence else None", "                tok = None", "lock_protected writes unfenced", True),
    Mutant("A03", "agents5.py", "        back = yield _update(own, values[own], my_version if cas else None)", "        back = {\"ok\": True}",
           "verify_and_compensate never compensates", True),
    Mutant("A04", "agents5.py", "    offset = (BACKOFF_OFFSET + 2 * attempt) if _rank(ctx.agent_id) % 2 else 0", "    offset = 0",
           "V1 B2: weak (purely random, short) back-off", True),
    Mutant("A05", "agents5.py", "    for _ in range(TOKENLESS_IDLE_CALLS):\n        yield ToolCall(\"list_effects\", {})",
           "    for _ in range(0):\n        yield ToolCall(\"list_effects\", {})", "lease_then_tokenless writes right after expiry", False),
    Mutant("K01", "tasks5.py", "        recs = \", \".join(sorted((self.own,) + self.others))", "        recs = \", \".join((self.own,) + self.others)",
           "V2 F5: own record first in the budget text (opposite lock orders)", True),
    Mutant("M01", "model_agent5.py", "    QWEN_MODEL: {\"order\": [os.environ.get(\"STUDY2_QWEN_PROVIDER\", \"alibaba\")], \"allow_fallbacks\": False},",
           "    QWEN_MODEL: {\"order\": [os.environ.get(\"STUDY2_QWEN_PROVIDER\", \"alibaba\")], \"allow_fallbacks\": True},", "V2 F6: Qwen fallbacks allowed", True),
    Mutant("M02", "model_agent5.py", "        if host_bad:", "        if False:", "V2 F6: completions from another host accepted", True),
    Mutant("M03", "model_agent5.py", "                    return AgentStop(TRUNCATION_END.get(comp.stop_reason, \"truncated\"), report)",
           "                    return report", "V2 sec. 5: truncated agent ends as returned", True),
    Mutant("M04", "model_agent5.py", "                    response = yield ToolCall(tu[\"name\"], call_args, i == len(tool_uses) - 1)",
           "                    response = yield ToolCall(tu[\"name\"], call_args)", "V1 B2: every call of a reply ends a turn", True),
    Mutant("M05", "model_agent5.py", "    locks = \"acquire_lock\" in names\n", "    locks = False\n", "V1 B4: dry-run model never locks", True),
    Mutant("M06", "model_agent5.py", "            if rc.probe:", "            if False:", "probe agents execute their calls", True),
    # ---------------------------------------------------------------- Round 4: refusal and safety stops
    Mutant("M07", "model_agent5.py", "                if comp.stop_reason in REFUSAL_END:\n                    return AgentStop(REFUSAL_END[comp.stop_reason], report)\n",
           "", "R4: refusal / safety stops end 'returned' again", True),
    Mutant("M08", "model_agent5.py", "REFUSAL_END = {\"refusal\": \"refusal\", \"content_filter\": \"content_filter\"}",
           "REFUSAL_END = {\"refusal\": \"refusal\"}", "R4: OpenRouter / Gemini content_filter ends 'returned'", True),
    Mutant("M09", "model_agent5.py", "REFUSAL_END = {\"refusal\": \"refusal\", \"content_filter\": \"content_filter\"}",
           "REFUSAL_END = {\"refusal\": \"refusal\", \"content_filter\": \"refusal\"}", "R4: content_filter not distinct from refusal", False),
    Mutant("M10", "scheduler5.py", "AGENT_STOP_REASONS = (\"truncated\", \"provider_error\", \"probe\", \"refusal\", \"content_filter\")",
           "AGENT_STOP_REASONS = (\"truncated\", \"provider_error\", \"probe\")", "R4: scheduler records refusal ends as 'returned'", True),
    Mutant("M11", "score5.py", "NON_FINISH_ENDS = ERROR_ENDS + REFUSAL_ENDS + (\"probe\",)",
           "NON_FINISH_ENDS = ERROR_ENDS + (\"probe\",)", "R4: refused agents counted as abandoning", True),
    Mutant("M12", "score5.py", "ERROR_ENDS = (\"truncated\", \"provider_error\", \"error\")",
           "ERROR_ENDS = (\"truncated\", \"provider_error\", \"error\", \"refusal\", \"content_filter\")",
           "R4: refusals counted as harness errors (agent_errors)", True),
    Mutant("M13", "../src5_batch/gemini_translate.py", "CONTENT_FILTER = {\"SAFETY\", \"RECITATION\", \"BLOCKLIST\", \"PROHIBITED_CONTENT\", \"SPII\",",
           "CONTENT_FILTER = {\"SAFETY\", \"RECITATION\", \"BLOCKLIST\", \"PROHIBITED_CONTENT\",",
           "R4: Gemini SPII finish becomes 'error' (provider_error)", True),
    Mutant("M14", "../src5_batch/gemini_translate.py", "    if native in CONTENT_FILTER:\n        return \"content_filter\"",
           "    if native in CONTENT_FILTER:\n        return \"tool_calls\" if has_calls else \"stop\"", "R4: Gemini safety finishes read as normal stops", True),
    Mutant("M15", "../src5_batch/gemini_translate.py", "        finish = \"content_filter\"\n    choice",
           "        finish = \"stop\"\n    choice", "R4: a blocked Gemini prompt reads as a normal stop", True),
    Mutant("P01", "providers5.py", "            eff = TEMPERATURE_IGNORED if slug.startswith(TEMPERATURE_IGNORED_SLUGS) else \"unverified\"",
           "            eff = \"unverified\"", "V2 sec. 5: Gemini temperature recorded as unverified", False),
    Mutant("R01", "run5.py", "    return tuple(a for a in task.agent_ids if prompt(task, a) != prompt(cont, a))", "    return task.agent_ids",
           "probe: a0 probed twice (control prompt identical)", True),
    Mutant("L01", "plan5.py", "    limit = {f: (1.0 - margin) * caps[f] for f in FAMILIES}", "    limit = {f: caps[f] for f in FAMILIES}",
           "planner ignores the 10 % margin", True),
    Mutant("D01", "design5.py", "    return 8 * n + 8 + (4 if coord.locks else 0)", "    return 12", "Study 1 fixed cap of 12", True),
    Mutant("B01", "budget5.py", "        if family in self.family_caps:\n            lefts.append(self.family_caps[family] - spent.get(family, 0.0))",
           "        if False:\n            lefts.append(self.family_caps[family] - spent.get(family, 0.0))", "family caps ignored", True),
    Mutant("B02", "budget5.py", "    return e.get(\"provider_family\") or provider_family(str(e.get(\"model\", \"\")))", "    return \"openrouter\"",
           "every entry counted as openrouter", True),
]


def run_suite(d: str) -> bool:
    env = dict(os.environ, STUDY1_INSTANCES=STUDY1_INSTANCES, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-m", "unittest", "tests5"], cwd=d, env=env, capture_output=True, text=True, timeout=900)
    return r.returncode == 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json", default=None)
    a = p.parse_args()
    results = []
    base = tempfile.mkdtemp(prefix="mut5_")
    try:
        # Round 3: the copy keeps the repo layout (src5 next to src5_batch, src5_verify/dry_check5.py and
        # run_conc_study2.sh), so the freeze and runner tests run and mutants of those files can be killed
        clean_root = os.path.join(base, "clean")
        clean = os.path.join(clean_root, "src5")
        shutil.copytree(SRC, clean, ignore=shutil.ignore_patterns("__pycache__", "validity"))
        repo = os.path.dirname(os.path.abspath(SRC))
        shutil.copytree(os.path.join(repo, "src5_batch"), os.path.join(clean_root, "src5_batch"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        os.makedirs(os.path.join(clean_root, "src5_verify"))
        shutil.copy2(os.path.join(repo, "src5_verify", "dry_check5.py"), os.path.join(clean_root, "src5_verify"))
        shutil.copy2(os.path.join(repo, "run_conc_study2.sh"), clean_root)
        if not run_suite(clean):
            print("baseline suite fails on the unmutated copy")
            return 1
        for m in M:
            droot = os.path.join(base, m.mid)
            shutil.copytree(clean_root, droot)
            d = os.path.join(droot, "src5")
            path = os.path.join(d, m.file)
            src = open(path).read()
            n = src.count(m.old)
            if n != 1:
                results.append({**m._asdict(), "status": f"INVALID ({n} matches)"})
                print(f"{m.mid} INVALID ({n} matches): {m.desc}")
                shutil.rmtree(droot, ignore_errors=True)
                continue
            with open(path, "w") as f:
                f.write(src.replace(m.old, m.new))
            survived = run_suite(d)
            status = "SURVIVED" if survived else "killed"
            results.append({**m._asdict(), "status": status})
            print(f"{m.mid} {status:8s} {m.desc}", flush=True)
            shutil.rmtree(droot, ignore_errors=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    killed = sum(r["status"] == "killed" for r in results)
    valid = sum(r["status"] in ("killed", "SURVIVED") for r in results)
    surv = [r for r in results if r["status"] == "SURVIVED"]
    print(f"\n{killed}/{valid} valid mutants killed; survivors: {[r['mid'] for r in surv]}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(results, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
