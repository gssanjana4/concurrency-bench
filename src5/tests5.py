"""Unit tests for the Study 2 harness (src5). Stdlib only, no network.

    cd src5 && python3 -m unittest tests5 -v
"""

from __future__ import annotations

import collections
import csv
import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import types
import unittest
from decimal import Decimal
from typing import Any, Dict

import agents5 as A
import budget5 as B
import design5
import instances5 as I
import model_agent5 as M
import plan5
import providers5
import run5
import tasks5 as T
import validity5 as V
from records5 import SharedStore
from scheduler5 import AgentSpec, ScheduleConfig, ToolCall, run_episode, schedule_seed
from score5 import mutual_exclusion_violations, score, score_episode
import world5
from world5 import ConcurrentWorld, CoordinationConfig, build_system_prompt, tool_schemas, world_config

HERE = os.path.dirname(os.path.abspath(__file__))


def world(task: T.Task, config: str = "none", **kw) -> ConcurrentWorld:
    return ConcurrentWorld(SharedStore(task.initial), world_config(config, **kw), task.agent_ids)


def sc_of(task: T.Task, w: ConcurrentWorld, config: str = "none"):
    w.ledger.flags["lock_events"] = list(w.lock_events)  # as the scheduler does at the end of an episode
    return score(task, w.ledger, w.store.snapshot(), config_name=config)


def inv_task(stock: int, amount: int, n: int = 2) -> T.Task:
    rec = "inventory:thing-x"
    ids = T.agent_ids(n)
    return T.Task("inv", "inventory", "conflict", {rec: stock}, {a: T.Decrement(rec, amount) for a in ids},
                  (T.non_negative(rec), T.no_oversubscription(rec), T.accounted((rec,))), family="inventory_last_unit")


def budget_task() -> T.Task:
    return I.build("budget_write_skew", 0, 2)


# --------------------------------------------------------------------------
# Locks: own-call leases, fencing, renew, blocking wait
# --------------------------------------------------------------------------


class Locks(unittest.TestCase):
    def setUp(self):
        self.task = inv_task(5, 1)
        self.rec = "inventory:thing-x"

    def test_lease_counts_only_the_holders_own_calls(self):
        w = world(self.task, "locks")
        r = w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 2})
        self.assertEqual((r["ok"], r["lease_remaining"]), (True, 2))
        tok = r["fencing_token"]
        for _ in range(10):  # the peer's calls and global rounds do not consume a0's lease
            w.tick()
            w.call("a1", "get_record", {"record_id": self.rec})
        self.assertEqual(w.lock_holder(self.rec), "a0")
        w.call("a0", "get_record", {"record_id": self.rec})           # 1st covered call
        r = w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "fencing_token": tok})  # 2nd covered call
        self.assertEqual((r["ok"], r["lease_remaining"]), (True, 0))
        r = w.call("a0", "update_record", {"record_id": self.rec, "value": 3, "fencing_token": tok})  # 3rd: lease over
        self.assertEqual((r["status"], r["error"]), (409, "fencing"))
        self.assertIn("ended", r["message"])
        self.assertIsNone(w.lock_holder(self.rec))

    def test_fencing_rules_while_locked(self):
        w = world(self.task, "locks")
        tok = w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 10})["fencing_token"]
        self.assertEqual(w.call("a1", "update_record", {"record_id": self.rec, "value": 0})["status"], 423)
        self.assertEqual(w.call("a1", "update_record", {"record_id": self.rec, "value": 0, "fencing_token": tok})["status"], 423)
        self.assertEqual(w.call("a0", "update_record", {"record_id": self.rec, "value": 4})["status"], 428)
        self.assertEqual(w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "fencing_token": tok + 7})["status"], 400)
        self.assertTrue(w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "fencing_token": tok})["ok"])
        self.assertEqual(len(w.ledger.effects), 1)
        r = w.call("a1", "update_record", {"record_id": self.rec, "value": 0})
        self.assertNotIn("current_version", r)  # versions stay hidden under locks (Study 1 leaked them in 423s)

    def test_stale_token_rejected_after_another_holder_kleppmann(self):
        w = world(self.task, "locks")
        t0 = w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 1})["fencing_token"]
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a0", "get_record", {"record_id": self.rec})  # a0's lease has ended
        t1 = w.call("a1", "acquire_lock", {"record_id": self.rec, "lease_calls": 5})["fencing_token"]
        self.assertGreater(t1, t0)
        self.assertEqual(w.call("a0", "update_record", {"record_id": self.rec, "value": 2, "fencing_token": t0})["status"], 423)
        w.call("a1", "release_lock", {"record_id": self.rec})
        r = w.call("a0", "update_record", {"record_id": self.rec, "value": 2, "fencing_token": t0})
        self.assertEqual(w.ledger.calls[-1].reason, "stale_fencing_token")
        self.assertEqual(r["status"], 409)
        self.assertEqual(w.ledger.effects, [])
        self.assertEqual(mutual_exclusion_violations(w.ledger), [])

    def test_renew_and_renew_after_expiry(self):
        w = world(self.task, "locks")
        tok = w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 1})["fencing_token"]
        r = w.call("a0", "renew_lock", {"record_id": self.rec, "lease_calls": 3})
        self.assertEqual((r["ok"], r["fencing_token"], r["lease_remaining"]), (True, tok, 3))
        for _ in range(4):
            w.call("a0", "get_record", {"record_id": self.rec})
        self.assertEqual(w.call("a0", "renew_lock", {"record_id": self.rec, "lease_calls": 3})["status"], 409)
        self.assertEqual(w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 21})["status"], 400)

    def test_locks_released_when_agent_ends_and_blocking_wait(self):
        def holder(ctx):
            yield ToolCall("acquire_lock", {"record_id": "inventory:thing-x", "lease_calls": 20})
            for _ in range(3):
                yield ToolCall("get_record", {"record_id": "inventory:thing-x"})
            return "left without releasing"

        def waiter(ctx):
            r = yield ToolCall("acquire_lock", {"record_id": "inventory:thing-x", "lease_calls": 5})
            return "granted" if r["ok"] else "refused"

        sch = ScheduleConfig(seed=1, gap_min=0, gap_max=0, start_jitter=0, latency_p=0.0, turn_cap=20)
        ep = run_episode(self.task, {"a0": AgentSpec("h", holder), "a1": AgentSpec("w", waiter)}, world_config("locks"),
                         ScheduleConfig(**{**sch.as_dict(), "seed": next(s for s in range(50) if self._a0_first(s))}))
        calls = [c for c in ep.ledger.calls if c.agent_id == "a1"]
        self.assertEqual(len(calls), 1)               # one call, held by the scheduler while it waits
        self.assertGreater(calls[0].waited_rounds, 0)
        self.assertTrue(calls[0].response["ok"])      # granted once a0 ended (its lock was released at its end)
        self.assertEqual(ep.ledger.end_for("a0").locks_held, ("inventory:thing-x",))
        self.assertTrue(score_episode(ep).agents["a0"].lock_leak)

    def _a0_first(self, seed):
        import random
        rng = random.Random(f"{seed}|order")
        order = ["a0", "a1"]
        rng.shuffle(order)
        return order[0] == "a0"


# --------------------------------------------------------------------------
# Tool contract and peer cues
# --------------------------------------------------------------------------


# V2 (review V2 F1): widened -- the v1 pattern could not match "every agent" or "others"
PEER_CUES = re.compile(r"another agent|someone else|other agents?'?|anyone else|by other|\bevery agent\b|\bothers\b|"
                       r"\bother (agent|caller|client)s?\b|\bpeers?\b|\bagents you can message\b", re.I)


class ToolContract(unittest.TestCase):
    def test_lock_descriptions_define_units_and_limits(self):
        s = {t["name"]: t for t in tool_schemas(CoordinationConfig.from_names("locks"))}
        d = s["acquire_lock"]["description"]
        for needle in ("your next lease_calls tool calls", "1-20", "fencing_token", "lease_remaining", "does not count",
                       f"{world5.LOCK_WAIT_ROUNDS} rounds"):
            self.assertIn(needle, d)
        self.assertEqual(s["acquire_lock"]["input_schema"]["properties"]["lease_calls"]["maximum"], 20)
        self.assertIn("renew_lock", s)
        self.assertIn("fencing_token", s["update_record"]["input_schema"]["properties"])
        self.assertIn("fencing_token", s["claim"]["input_schema"]["properties"])

    def test_peer_cue_pattern_catches_the_v1_lock_text(self):
        v1 = ("writes to the record are accepted only if they carry this fencing_token (others get 423). "
              "the call waits up to 6 rounds (in a round every agent makes at most one tool call)")
        self.assertEqual(len(PEER_CUES.findall(v1)), 2)

    def test_aware_off_texts_have_no_peer_cues(self):
        for cfg in design5.CONFIGS:
            coord = CoordinationConfig.from_names(cfg)
            self.assertFalse(coord.messages or coord.peer_informed, cfg)  # V2 F4: no messages in any grid config
            for t in tool_schemas(coord):
                self.assertNotIn(t["name"], ("send_message", "read_messages"))
                self.assertIsNone(PEER_CUES.search(json.dumps(t)), (cfg, t["name"]))
        for tpl in I.TEMPLATES:
            task = I.build(tpl, 0, 2)
            for a, intent in task.intents.items():
                text = intent.describe()
                self.assertIsNone(PEER_CUES.search(text), text)
                for other in task.agent_ids:  # no agent id inside record names (ticket holder = own id is fine)
                    for rid in intent.reads:
                        self.assertNotRegex(rid, rf"\b{other}\b")
                for cfg in design5.CONFIGS:
                    prompt = build_system_prompt(a, [x for x in task.agent_ids if x != a], text, world_config(cfg))
                    self.assertIsNone(PEER_CUES.search(prompt), (cfg, prompt))
        self.assertNotIn("Agents you can message", build_system_prompt("a0", ["a1"], "x", world_config("all_available")))
        # the labelled peer-informed configuration (never in the grid) names the peers
        self.assertIn("Agents you can message", build_system_prompt("a0", ["a1"], "x", world_config("all_peer_informed")))
        self.assertTrue(CoordinationConfig.from_names("all_peer_informed").peer_informed)
        self.assertTrue(set(world5.PEER_INFORMED_CONFIGS).isdisjoint(design5.CONFIGS))

    def test_all_available_offers_cas_and_locks_without_messages(self):
        c = CoordinationConfig.from_names("all_available")
        self.assertEqual(c.name, "all_available")
        self.assertTrue(c.expose_versions and c.conditional_writes == "available" and c.locks)
        self.assertFalse(c.messages)  # V2 F4
        self.assertFalse(CoordinationConfig.from_names("locks").expose_versions)
        self.assertEqual(design5.CONFIGS, ("none", "cas_available", "locks", "all_available"))


# --------------------------------------------------------------------------
# Scheduler
# --------------------------------------------------------------------------


class Scheduler(unittest.TestCase):
    def test_deterministic_given_seed_and_different_across_schedules(self):
        task = I.build("inventory_still_valid", 0, 2)
        fps, movers = set(), collections.Counter()
        for s in range(12):
            sch = V.schedule_for("inventory_still_valid", 0, s, 2, "none")
            e1 = run_episode(task, A.NAIVE, world_config("none"), sch)
            e2 = run_episode(task, A.NAIVE, world_config("none"), sch)
            self.assertEqual(e1.ledger.fingerprint(), e2.ledger.fingerprint())
            fps.add(e1.ledger.fingerprint())
            movers[score_episode(e1).interleaving["first_mover"]] += 1
        self.assertGreater(len(fps), 6)
        self.assertGreater(min(movers["a0"], movers["a1"]), 1)  # no fixed first mover

    def test_contended_and_control_share_the_schedule_seed(self):
        a = run5.cell_schedule({"task": "seat_same", "instance": 1, "seed": 0, "n_agents": 2, "config": "none"}, 0)
        b = run5.cell_schedule({"task": "seat_same_ctrl", "instance": 1, "seed": 0, "n_agents": 2, "config": "locks"}, 0)
        self.assertEqual(a.seed, b.seed)
        self.assertEqual((a.turn_cap, b.turn_cap), (24, 28))

    def test_rereading_can_help_under_study2_but_not_study1_like(self):
        rates = {}
        for label, ov in (("s2", None), ("s1", V.STUDY1_LIKE)):
            for pol in ("naive", "rereader"):
                eps = V.run_cell(pol, "inventory_still_valid", "none", 2, 2, 6, ov)
                rates[(label, pol)] = sum(sc.outcome == "failed" for _, sc in eps) / len(eps)
        self.assertEqual(rates[("s1", "rereader")], 1.0)
        self.assertLess(rates[("s2", "rereader")], rates[("s2", "naive")])

    def test_turn_cap_ending(self):
        def spin(ctx):
            while True:
                yield ToolCall("get_record", {"record_id": ctx.intent.reads[0]})

        ep = run_episode(inv_task(5, 1), AgentSpec("spin", spin), world_config("none"), ScheduleConfig(seed=3, turn_cap=5))
        sc = score_episode(ep)
        self.assertEqual(sc.cap_endings, 2)
        self.assertTrue(all(a.turns == 5 for a in sc.agents.values()))


# --------------------------------------------------------------------------
# Templates, controls, instances
# --------------------------------------------------------------------------


class Templates(unittest.TestCase):
    def test_controls_are_disjoint_and_matched(self):
        for fam in I.CONTENDED:
            for n in (2, 4):
                c, k = I.build(fam, 1, n), I.build(fam + "_ctrl", 1, n)
                self.assertTrue(c.shared_records(), fam)
                self.assertEqual(k.shared_records(), set(), fam)
                self.assertEqual(k.category, "control")
                self.assertEqual(c.intents["a0"].describe(), k.intents["a0"].describe())
                self.assertEqual(len(k.initial), n * len(c.initial))
                for a in c.agent_ids:
                    self.assertEqual(getattr(c.intents[a], "amount", None), getattr(k.intents[a], "amount", None))
                    self.assertEqual(len(c.intents[a].reads), len(k.intents[a].reads))

    def test_controls_have_zero_cross_agent_edges_under_every_policy(self):
        for fam in I.CONTENDED:
            for pol in ("naive", "rereader", "cas_retry", "lock_protected"):
                cfg = "all_available"
                for _, sc in V.run_cell(pol, fam + "_ctrl", cfg, 2, 1, 2):
                    self.assertEqual(sc.cross_agent_edges, 0)
                    self.assertEqual(sc.outcome, "clean")

    def test_instances_deterministic_and_disjoint_from_study1(self):
        s1 = I.study1_shapes()
        self.assertGreater(len(s1), 20)
        for fam in I.CONTENDED:
            for i in range(6):
                t = I.build(fam, i, 2)
                self.assertEqual(I.fingerprint(t), I.fingerprint(I.build(fam, i, 2)))
                if fam not in I.NAME_ONLY_FAMILIES:
                    self.assertNotIn(I.shape(t, fam), s1)
                for rid in t.initial:
                    self.assertNotRegex(rid, r"widget|concert-1|T-100|account:pool|dest-|team/|joint-a")


# --------------------------------------------------------------------------
# Checker
# --------------------------------------------------------------------------


class Checker(unittest.TestCase):
    rec = "inventory:thing-x"

    def test_lost_update_masked_by_double_application_is_flagged(self):  # T1 CEX-1
        task = inv_task(9, 3)
        w = world(task, "none")
        w.call("a1", "get_record", {"record_id": self.rec})
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 6})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 6})
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 3})
        sc = sc_of(task, w)
        self.assertFalse(sc.fs_nonserializable)   # final 3 = serial(a0, a1): the spec-level check is fooled
        self.assertTrue(sc.flags["lost_update"] and sc.flags["stale_overwrite"])
        self.assertTrue(sc.dsg_cycle)
        self.assertEqual((sc.outcome, sc.primary_label), ("failed", "lost_update"))

    def test_guard_violation_is_its_own_label(self):  # T1 CEX-4
        task = inv_task(1, 1)
        w = world(task, "cas_available")
        w.call("a1", "get_record", {"record_id": self.rec})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 0, "expected_version": 1})
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a0", "update_record", {"record_id": self.rec, "value": -1, "expected_version": 2})
        sc = sc_of(task, w, "cas_available")
        self.assertTrue(sc.agents["a0"].guard_violation)
        self.assertFalse(sc.dsg_cycle)
        self.assertEqual(sc.primary_label, "guard_violation")
        self.assertFalse(sc.flags["missing_leg"])

    def test_missing_leg_and_conservation(self):
        task = I.build("transfer_shared_source", 0, 2)
        it = task.intents["a0"]
        w = world(task, "cas_available")
        w.call("a0", "get_record", {"record_id": it.src})
        w.call("a0", "get_record", {"record_id": it.dst})
        w.call("a0", "update_record", {"record_id": it.dst, "value": str(task.initial[it.dst] + it.amount)})
        sc = sc_of(task, w)
        self.assertTrue(sc.flags["missing_leg"] and sc.flags["violated_at_end"])
        self.assertEqual(sc.primary_label, "missing_leg")

    def test_rollback_only_is_compensated_not_partial(self):
        task = budget_task()
        own0, own1 = task.intents["a0"].own, task.intents["a1"].own
        amt = task.intents["a0"].amount
        w = world(task, "none")
        for a in ("a0", "a1"):
            for r in task.intents[a].reads:
                w.call(a, "get_record", {"record_id": r})
        w.call("a0", "update_record", {"record_id": own0, "value": str(amt)})
        w.call("a1", "update_record", {"record_id": own1, "value": str(amt)})
        for r in task.intents["a1"].reads:
            w.call("a1", "get_record", {"record_id": r})
        w.call("a1", "update_record", {"record_id": own1, "value": "0.00"})  # a1 compensates
        sc = sc_of(task, w)
        self.assertEqual(sc.rolled_back_agents, ("a1",))
        self.assertEqual((sc.outcome, sc.primary_label), ("compensated", "compensated"))
        self.assertTrue(sc.flags["ever_violated"] and not sc.flags["violated_at_end"])
        self.assertTrue(sc.flags["compensated_after_violation"] and sc.flags["write_skew"])
        self.assertFalse(sc.fs_nonserializable)
        self.assertFalse(sc.agents["a1"].fulfilled)
        self.assertFalse(sc.flags["compensation_exposed"])  # a1's own verification read does not count

    def test_compensation_exposed(self):
        task = budget_task()
        own0 = task.intents["a0"].own
        w = world(task, "none")
        w.call("a0", "update_record", {"record_id": own0, "value": "5.00"})
        w.call("a1", "get_record", {"record_id": own0})   # reads the to-be-compensated version
        w.call("a0", "update_record", {"record_id": own0, "value": "0.00"})
        self.assertTrue(sc_of(task, w).flags["compensation_exposed"])

    def test_dsg_uses_every_read_cas_retry_is_cyclic_but_fs_serializable(self):
        task = inv_task(5, 1)
        w = world(task, "cas_available")
        w.call("a0", "get_record", {"record_id": self.rec})           # read v1
        w.call("a1", "get_record", {"record_id": self.rec})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 1})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 1})  # 409
        w.call("a0", "get_record", {"record_id": self.rec})           # re-read v2
        w.call("a0", "update_record", {"record_id": self.rec, "value": 3, "expected_version": 2})
        sc = sc_of(task, w, "cas_available")
        self.assertEqual(sc.outcome, "clean")
        self.assertTrue(sc.dsg_cycle)  # the aborted attempt's read is part of the session (no aborts in this API)
        self.assertFalse(sc.dsg_g1c)

    def test_out_of_intent_write_creating_money(self):  # T1 CEX-2
        task = I.build("joint_account_write_skew", 0, 2)
        it = task.intents["a0"]
        partner = it.partners[0]
        w = world(task, "none")
        for r in it.reads:
            w.call("a0", "get_record", {"record_id": r})
        w.call("a0", "update_record", {"record_id": it.target, "value": str(task.initial[it.target] - it.amount)})
        w.call("a0", "update_record", {"record_id": partner, "value": str(task.initial[partner] + Decimal("30"))})
        sc = sc_of(task, w)
        self.assertTrue(sc.flags["out_of_intent_write"])
        self.assertTrue(any(v.startswith("accounted") for v in sc.invariant_violations))
        self.assertEqual(sc.primary_label, "out_of_intent_write")

    def test_laundered_cas_flagged(self):
        task = inv_task(5, 1)
        w = world(task, "cas_available")
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4})
        r = w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 1})
        self.assertNotIn("current_version", r)  # Round 3: the 409 no longer reveals the version; a guessed one launders
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 2})
        sc = sc_of(task, w, "cas_available")
        self.assertTrue(sc.flags["laundered_cas"] and sc.flags["stale_overwrite"])
        self.assertFalse(sc.flags["lost_update"])  # no read basis: blind, not P4

    def test_promotion_no_op_is_not_out_of_intent_and_counts_as_promote(self):
        task = budget_task()
        it = task.intents["a0"]
        w = world(task, "cas_available")
        vers = {}
        for r in it.reads:
            vers[r] = w.call("a0", "get_record", {"record_id": r})["version"]
        for r in sorted(it.reads):
            w.call("a0", "update_record", {"record_id": r, "value": str(task.initial[r]), "expected_version": vers[r]})
        w.call("a0", "update_record", {"record_id": it.own, "value": str(it.amount), "expected_version": vers[it.own] + 1})
        sc = sc_of(task, w, "cas_available")
        self.assertEqual(sc.outcome, "clean")
        self.assertTrue(sc.agents["a0"].promote and sc.agents["a0"].fulfilled)
        self.assertFalse(sc.flags["out_of_intent_write"])

    def test_naive_write_skew_and_validity_summary(self):
        eps = V.run_cell("naive", "budget_write_skew", "none", 2, 2, 6)
        ws = [sc for _, sc in eps if sc.primary_label == "write_skew"]
        self.assertTrue(ws)
        self.assertTrue(all(sc.flags["write_skew"] and sc.dsg_cycle and sc.fs_nonserializable for sc in ws))


class CheckerEdgeCases(unittest.TestCase):
    rec = "inventory:thing-x"

    def test_lost_update_with_valid_serial_orders_is_fs_nonserializable(self):
        task = inv_task(5, 1)
        w = world(task, "none")
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a1", "get_record", {"record_id": self.rec})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4})
        sc = sc_of(task, w)
        self.assertTrue(sc.fs_nonserializable and sc.flags["lost_update"])
        self.assertFalse(sc.flags["write_skew"])  # single-record lost update is not A5B
        w = world(task, "none")  # rw edges both ways on the same record: still not A5B
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4})
        w.call("a1", "get_record", {"record_id": self.rec})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4})
        sc = sc_of(task, w)
        self.assertEqual(sum(e.kind == "rw" for e in sc.edges), 2)
        self.assertFalse(sc.flags["write_skew"])

    def test_g1c_cycle_from_wr_edges(self):
        task = I.build("transfer_shared_source", 0, 2)
        src, d0 = task.intents["a0"].src, task.intents["a0"].dst
        w = world(task, "none")
        w.call("a0", "update_record", {"record_id": src, "value": "1.00"})
        w.call("a1", "get_record", {"record_id": src})             # wr a0 -> a1
        w.call("a1", "update_record", {"record_id": d0, "value": "2.00"})
        w.call("a0", "get_record", {"record_id": d0})              # wr a1 -> a0
        sc = sc_of(task, w)
        self.assertTrue(sc.dsg_g1c and sc.dsg_cycle)

    def test_read_only_session_cycle_counts_in_dsg_not_in_committed_subgraph(self):
        task = I.build("transfer_shared_source", 0, 2)
        it = task.intents["a1"]
        w = world(task, "none")
        w.call("a0", "get_record", {"record_id": it.src})          # before the debit
        w.call("a1", "update_record", {"record_id": it.src, "value": str(task.initial[it.src] - it.amount)})
        w.call("a1", "update_record", {"record_id": it.dst, "value": str(task.initial[it.dst] + it.amount)})
        w.call("a0", "get_record", {"record_id": it.dst})          # after the credit: inconsistent snapshot
        sc = sc_of(task, w)
        self.assertTrue(sc.dsg_cycle)
        self.assertFalse(sc.dsg_cycle_committed)
        self.assertEqual(sc.outcome, "clean")

    def test_partial_restore_is_not_a_rollback(self):
        task = I.build("transfer_shared_source", 0, 2)
        it = task.intents["a0"]
        w = world(task, "none")
        src0, dst0 = task.initial[it.src], task.initial[it.dst]
        w.call("a0", "update_record", {"record_id": it.src, "value": str(src0 - it.amount)})
        w.call("a0", "update_record", {"record_id": it.dst, "value": str(dst0 + it.amount)})
        w.call("a0", "update_record", {"record_id": it.src, "value": str(src0)})  # puts back one leg only
        sc = sc_of(task, w)
        self.assertEqual(sc.rolled_back_agents, ())
        self.assertEqual(sc.outcome, "failed")

    def test_rollback_with_a_stale_write_is_failed_not_compensated(self):
        task = inv_task(5, 1)
        w = world(task, "none")
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a1", "get_record", {"record_id": self.rec})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4})   # stale
        w.call("a0", "update_record", {"record_id": self.rec, "value": 5})   # a0 "rolls back" over a1's write (stale)
        sc = sc_of(task, w)
        self.assertIn("a0", sc.rolled_back_agents)
        self.assertEqual(sc.outcome, "failed")

    def test_interleaving_overlap_with_three_agents(self):
        task = inv_task(9, 1, n=3)
        w = world(task, "none")
        w.call("a1", "get_record", {"record_id": self.rec})
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 8})
        w.call("a2", "get_record", {"record_id": self.rec})   # starts after a0 already wrote
        w.call("a1", "update_record", {"record_id": self.rec, "value": 8})
        w.call("a2", "update_record", {"record_id": self.rec, "value": 7})
        il = sc_of(task, w).interleaving
        self.assertFalse(il["reads_overlap"])
        self.assertEqual(il["first_mover"], "a0")
        self.assertEqual(il["pattern"], "R1R0W0R2W1W2")

    def test_value_changing_cas_write_to_a_read_record_is_not_promotion(self):
        task = I.build("joint_account_write_skew", 0, 2)
        it = task.intents["a0"]
        partner = it.partners[0]
        w = world(task, "cas_available")
        v = w.call("a0", "get_record", {"record_id": partner})["version"]
        w.call("a0", "update_record", {"record_id": partner, "value": str(task.initial[partner] + 1), "expected_version": v})
        sc = sc_of(task, w, "cas_available")
        self.assertFalse(sc.agents["a0"].promote)
        self.assertTrue(sc.flags["out_of_intent_write"])

    def test_only_the_holder_may_renew(self):
        task = inv_task(5, 1)
        w = world(task, "locks")
        w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 3})
        self.assertEqual(w.call("a1", "renew_lock", {"record_id": self.rec, "lease_calls": 3})["status"], 409)
        self.assertEqual(w.lock_holder(self.rec), "a0")

    def test_scheduler_draws_vary(self):
        task = I.build("inventory_still_valid", 0, 2)
        starts, gaps, firsts = set(), set(), collections.Counter()
        for s in range(20):
            sch = ScheduleConfig(seed=s, start_jitter=6, gap_min=0, gap_max=4, latency_p=0.0, turn_cap=24)
            ep = run_episode(task, A.NAIVE, world_config("none"), sch)
            starts.add(tuple(sorted(ep.ledger.flags["start_rounds"].items())))
            c0 = ep.ledger.calls_for("a0")
            gaps.add(c0[1].step - c0[0].step)
            same = ScheduleConfig(seed=s, start_jitter=0, gap_min=0, gap_max=0, latency_p=0.0, turn_cap=24)
            firsts[run_episode(task, A.NAIVE, world_config("none"), same).ledger.calls[0].agent_id] += 1
        self.assertGreater(len(starts), 5)
        self.assertGreater(len(gaps), 2)
        self.assertGreater(min(firsts["a0"], firsts["a1"]), 2)


# --------------------------------------------------------------------------
# Reference policy validity (compact) and the call cap
# --------------------------------------------------------------------------


class Validity(unittest.TestCase):
    def test_call_cap_formula(self):
        self.assertEqual([design5.call_cap(2, c) for c in design5.CONFIGS], [24, 24, 28, 28])
        self.assertEqual(design5.call_cap(4, "cas_available"), 40)

    def test_correct_policies_clean_within_cap_naive_fail(self):
        for fam in ("inventory_last_unit", "transfer_shared_source", "budget_write_skew", "joint_account_write_skew"):
            for pol in A.CORRECT[fam]:
                for cfg in design5.CONFIGS:
                    if not A.REFERENCE_POLICIES[pol].supported_by(world_config(cfg).coordination):
                        continue
                    cap = design5.call_cap(2, cfg)
                    for t in (fam, fam + "_ctrl"):
                        for _, sc in V.run_cell(pol, t, cfg, 2, 2, 4):
                            allowed = {"clean", "compensated"} if pol == "verify_and_compensate" and t == fam else {"clean"}
                            self.assertIn(sc.outcome, allowed, (pol, t, cfg, sc.primary_label))
                            self.assertEqual(sc.cap_endings, 0)
                            self.assertLessEqual(max(a.turns for a in sc.agents.values()), design5.CAP_MARGIN * cap)
            for pol in A.NAIVE_FOR[fam]:
                cfg = "all_available"
                fails = sum(sc.outcome == "failed" for _, sc in V.run_cell(pol, fam, cfg, 2, 4, 6))
                self.assertGreater(fails, 0, (pol, fam))

    def test_fencing_probes_never_fail(self):
        for fam in ("transfer_shared_source", "budget_write_skew"):
            for pol in A.PROBES:
                for ep, sc in V.run_cell(pol, fam, "locks", 2, 2, 3):
                    self.assertNotEqual(sc.outcome, "failed")
                    self.assertEqual(mutual_exclusion_violations(ep.ledger), [])


# --------------------------------------------------------------------------
# Model agent, runner, budget, planner
# --------------------------------------------------------------------------


class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="src5test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run5(self, args):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            code = run5.run_grid(args)
        return code, buf.getvalue()

    def test_dry_run_records_settings_and_resumes(self):
        args = ["--models", "claude-haiku-4-5-20251001", "--tasks", "families:transfer_shared_source", "--instances", "1",
                "--seeds", "0,1", "--out", self.tmp, "--dry-run", "--max-usd", "69"]
        code, out = self.run5(args)
        self.assertEqual(code, 0, out)
        d = os.path.join(self.tmp, "dry_run")
        trs = [json.load(open(os.path.join(d, "transcripts", f))) for f in os.listdir(os.path.join(d, "transcripts"))]
        self.assertEqual(len(trs), 2 * 4 * 2)
        for tr in trs:
            self.assertEqual(tr["study"], 2)
            self.assertEqual(tr["schedule"]["turn_cap"], design5.call_cap(2, tr["config"]))
            for a in tr["agents"].values():
                for t in a["turns"]:
                    for k in ("temperature_effective", "reasoning_tokens", "thinking_blocks", "model_served", "served_host",
                              "max_tokens_exceeded"):
                        self.assertIn(k, t)
        with open(os.path.join(d, "results.csv")) as f:
            self.assertEqual(f.readline().strip().split(","), run5.CSV_FIELDS)
        spend = [json.loads(x) for x in open(os.path.join(d, "spend.jsonl"))]
        self.assertTrue(all(e["provider_family"] == "anthropic" for e in spend))
        code, out = self.run5(args)
        self.assertIn("to run: 0", out)

    def test_family_cap_stops_only_its_family(self):
        other = os.path.join(self.tmp, "other.jsonl")
        with open(other, "w") as f:
            f.write(json.dumps({"model": "claude-sonnet-5", "cost_usd": 18.999}) + "\n")
        base = ["--tasks", "seat_same", "--instances", "1", "--seeds", "0", "--configs", "none", "--dry-run",
                "--extra-spend-logs", other, "--max-usd", "69"]
        code, out = self.run5(["--models", "claude-haiku-4-5-20251001", "--out", os.path.join(self.tmp, "a")] + base)
        self.assertEqual(code, 2, out)
        code, out = self.run5(["--models", "openrouter:qwen/qwen3.6-27b-20260422", "--out", os.path.join(self.tmp, "b")] + base)
        self.assertEqual(code, 0, out)
        fam = B.spend_by_family([other])
        self.assertEqual(round(fam["anthropic"], 3), 18.999)

    def test_qwen_host_is_enforced(self):
        self.assertEqual(M.OPENROUTER_ROUTING[M.QWEN_MODEL]["allow_fallbacks"], False)
        self.assertTrue(M.host_ok(M.QWEN_MODEL, "Alibaba") and M.host_ok(M.QWEN_MODEL, "Alibaba Cloud Int."))
        self.assertFalse(M.host_ok(M.QWEN_MODEL, "DeepInfra"))
        self.assertTrue(M.host_ok("openrouter:openai/gpt-5.5-20260423", "OpenAI"))

        class Stub:
            name = "openrouter"

            def complete(self, *a, **k):
                return providers5.Completion(blocks=[{"type": "text", "text": "hi"}], provider="openrouter",
                                             model_requested=M.QWEN_MODEL, model_served="qwen/qwen3.6-27b @DeepInfra",
                                             temperature_requested=0.0, temperature_effective="unverified",
                                             usage={"input": 1, "output": 1}, stop_reason="stop")

        task = inv_task(5, 1)
        rc = M.ModelRunConfig(model=M.QWEN_MODEL, provider=Stub(), world_config=world_config("none"), turn_cap=24)
        with self.assertRaises(M.ProviderFailure):
            run_episode(task, M.model_agent_spec(rc, {}), world_config("none"), ScheduleConfig(seed=1, turn_cap=24))

    def test_thinking_blocks_recorded_and_qwen_routing(self):
        blocks = providers5._blocks_from_anthropic([
            types.SimpleNamespace(type="thinking", thinking="let me think", signature="abc"),
            types.SimpleNamespace(type="text", text="hi")])
        self.assertEqual(blocks[0], {"type": "thinking", "thinking": "let me think", "signature_chars": 3})
        self.assertEqual(providers5.thinking_meta(blocks), {"thinking_blocks": 1, "thinking_chars": 12})
        self.assertEqual(M.routing_for(M.QWEN_MODEL)["order"], ["alibaba"])
        self.assertIsNone(M.routing_for("openrouter:openai/gpt-5.5-20260423"))
        self.assertEqual(M.provider_family(M.GEMINI_MODEL), "gemini")

    def test_local_ollama_model_uses_the_openai_compatible_path(self):
        import urllib.request
        sent = {}

        def fake_urlopen(req, timeout=None):
            sent["url"], sent["body"] = req.full_url, json.loads(req.data)
            return io.BytesIO(json.dumps({"model": "qwen3:8b", "choices": [{"message": {"role": "assistant", "content": "ok"},
                                                                              "finish_reason": "stop"}],
                                          "usage": {"prompt_tokens": 5, "completion_tokens": 1}}).encode())

        orig = urllib.request.urlopen
        urllib.request.urlopen = fake_urlopen
        try:
            prov, probe = M.make_provider("ollama:qwen3:8b")
            comp = prov.complete("ollama:qwen3:8b", "sys", tool_schemas(CoordinationConfig.from_names("none")),
                                 [{"role": "user", "content": "hi"}], 4096, 0.0)
        finally:
            urllib.request.urlopen = orig
        self.assertTrue(sent["url"].startswith("http://localhost:11434/"))
        self.assertEqual(sent["body"]["model"], "qwen3:8b")
        self.assertEqual(comp.blocks, [{"type": "text", "text": "ok"}])
        self.assertEqual(M.provider_family("ollama:qwen3:8b"), "local")

    def test_model_sub_cap(self):
        other = os.path.join(self.tmp, "other.jsonl")
        with open(other, "w") as f:
            f.write(json.dumps({"model": "claude-haiku-4-5-20251001", "cost_usd": 0.5}) + "\n")
        code, out = self.run5(["--models", "claude-haiku-4-5-20251001", "--out", os.path.join(self.tmp, "m"), "--tasks", "seat_same",
                               "--instances", "1", "--seeds", "0", "--configs", "none", "--dry-run", "--extra-spend-logs", other,
                               "--max-usd", "69", "--model-cap", "0.5"])
        self.assertEqual(code, 2, out)

    def test_planner_fits_every_cap_with_margin_and_the_v2_grid(self):
        plan = plan5.choose(plan5.load_costs(), dict(B.DEFAULT_FAMILY_CAPS), B.DEFAULT_TOTAL_CAP, 1.15, "nov")
        for fam, cap in B.DEFAULT_FAMILY_CAPS.items():
            self.assertLessEqual(plan["estimate_by_family"][fam] * 1.15, 0.9 * cap + 1e-9, fam)  # >= 10 % margin
        self.assertLessEqual(plan["estimate_total"] * 1.15, 0.9 * B.DEFAULT_TOTAL_CAP)
        core = [b for b in plan["blocks"] if b["priority"] == 1]
        eps = collections.Counter()
        for b in core:
            eps[b["model"]] += b["episodes"]
        self.assertEqual(eps["openrouter:openai/gpt-5.5-20260423"], 96)
        self.assertEqual(eps["claude-fable-5"], 16)  # Round 3: descriptive Fable core cut to 2 families (Anthropic margin)
        for m in ("openrouter:qwen/qwen3.6-27b-20260422", "claude-haiku-4-5-20251001", "claude-sonnet-5"):
            self.assertEqual(eps[m], 448)
        gem = [b for b in core if b["model"] == plan5.GEMINI_MODEL_ID]
        aware_on = {c for b in gem if True in b["aware"] for c in b["configs"]}
        self.assertEqual(aware_on, {"locks", "all_available"})
        self.assertTrue(all(b["aware"] == [False, True] for b in gem if True in b["aware"]))  # interleaved
        self.assertTrue(all(b["aware"] == [False] for b in core if b["model"] != plan5.GEMINI_MODEL_ID))
        probes = [b for b in plan["blocks"] if b.get("mode") == "probe"]
        self.assertEqual({b["model"] for b in probes}, set(plan5.MODELS) - {"claude-fable-5"})  # Round 3: Fable probes cut
        self.assertEqual({b["model"]: b["instances"] for b in probes},
                         {"openrouter:qwen/qwen3.6-27b-20260422": 6, "claude-haiku-4-5-20251001": 4,
                          "openrouter:openai/gpt-5.5-20260423": 2, "openrouter:google/gemini-4-argon-20261013": 8,
                          "claude-sonnet-5": 4})
        self.assertTrue(all(b["priority"] == 0 and b["aware"] == [False, True] and b["instances"] >= 1 for b in probes))
        self.assertGreater(plan5.probe_estimate(plan5.load_costs(), "claude-fable-5", "locks"), 0)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            path = os.path.join(self.tmp, "plan.json")
            with open(path, "w") as f:
                json.dump(plan, f)
            plan5.main(["--blocks", path])
        lines = [ln.split("\t") for ln in buf.getvalue().splitlines()]
        self.assertTrue(all(len(ln) == 11 for ln in lines))
        self.assertIn("both", {ln[8] for ln in lines})
        self.assertIn("probe", {ln[10] for ln in lines})


# --------------------------------------------------------------------------
# V2 fixes (pre-spend reviews V1 = DB, V2 = agent evaluation); CHANGES_V2.md maps each to these tests
# --------------------------------------------------------------------------


def ws_world(task, config):
    return world(task, config)


class V2Fixes(unittest.TestCase):
    rec = "inventory:thing-x"

    # ---- V1 B1: claim is a plain overwrite in every configuration
    def test_claim_is_a_plain_overwrite_in_every_config_and_cas_optional(self):
        task = I.build("seat_same", 0, 2)
        seat = task.intents["a0"].record
        for cfg in design5.CONFIGS:
            w = world(task, cfg)
            self.assertTrue(w.call("a0", "claim", {"record_id": seat, "holder": "x"})["ok"])
            r = w.call("a1", "claim", {"record_id": seat, "holder": "y"})
            self.assertTrue(r["ok"], cfg)  # v1: 409 under cas_available/all_available (server test-and-set)
            desc = {t["name"]: t for t in tool_schemas(CoordinationConfig.from_names(cfg))}["claim"]
            self.assertNotIn("409", desc["description"])
            self.assertEqual("expected_version" in desc["input_schema"]["properties"], cfg in ("cas_available", "all_available"))
        w = world(task, "cas_available")
        w.call("a0", "claim", {"record_id": seat, "holder": "x", "expected_version": 1})
        r = w.call("a1", "claim", {"record_id": seat, "holder": "y", "expected_version": 1})
        self.assertEqual((r["status"], w.ledger.calls[-1].reason), (409, "version_conflict"))
        sc = sc_of(task, w, "cas_available")
        self.assertTrue(sc.agents["a1"].cas)  # a conditional claim counts as CAS use

    def test_naive_claim_fails_under_every_config(self):
        for fam in ("seat_same", "ticket_same"):
            for cfg in design5.CONFIGS:
                eps = V.run_cell("naive_claim", fam, cfg, 2, 2, 4)
                self.assertGreater(sum(sc.outcome == "failed" for _, sc in eps), 0, (fam, cfg))
                self.assertTrue(all(sc.outcome == "clean" for _, sc in V.run_cell("naive_claim", fam + "_ctrl", cfg, 2, 1, 2)))

    # ---- V1 B2: think time before every completion
    def test_think_gap_follows_every_turn_not_only_the_first_read(self):
        def reads(ctx):
            for _ in range(4):
                yield ToolCall("get_record", {"record_id": ctx.intent.reads[0]})

        def batched(ctx):  # one "reply" of three calls, then a second reply of one call
            for i in range(3):
                yield ToolCall("get_record", {"record_id": ctx.intent.reads[0]}, i == 2)
            yield ToolCall("get_record", {"record_id": ctx.intent.reads[0]})

        sch = ScheduleConfig(seed=5, gap_min=3, gap_max=3, start_jitter=0, latency_p=0.0, turn_cap=24)
        task = inv_task(5, 1).restrict(["a0"])
        steps = [c.step for c in run_episode(task, AgentSpec("r", reads), world_config("none"), sch).ledger.calls]
        self.assertEqual([b - a for a, b in zip(steps, steps[1:])], [4, 4, 4])  # v1: gap after the first read only
        steps = [c.step for c in run_episode(task, AgentSpec("b", batched), world_config("none"), sch).ledger.calls]
        self.assertEqual([b - a for a, b in zip(steps, steps[1:])], [1, 1, 4])

    def test_model_agent_marks_the_last_call_of_each_reply(self):
        seen = []

        def two_reads(system, tools, messages):
            if sum(m["role"] == "assistant" for m in messages) == 0:
                return [{"type": "tool_use", "name": "get_record", "input": {"record_id": "inventory:thing-x"}}] * 2
            return [{"type": "text", "text": "done"}]

        rc = M.ModelRunConfig(model="fake-x", provider=M.FakeProvider(two_reads), world_config=world_config("none"), turn_cap=24)
        ctx = __import__("scheduler5").AgentContext("a0", inv_task(5, 1).intents["a0"], ("a1",), CoordinationConfig())
        gen = M.ModelAgent(ctx, rc).run()
        call = next(gen)
        seen.append(call.ends_turn)
        call = gen.send({"ok": True, "status": 200, "value": 5})
        seen.append(call.ends_turn)
        self.assertEqual(seen, [False, True])

    # ---- V1 B3: lock wait covers a correct holder
    def test_lock_wait_does_not_time_out_against_a_correct_holder(self):
        refused = 0
        for fam in ("budget_write_skew", "transfer_shared_source", "joint_account_write_skew"):
            for ep, _ in V.run_cell("lock_protected", fam, "locks", 2, 4, 4):
                refused += sum(1 for c in ep.ledger.calls if c.tool == "acquire_lock" and c.waited_rounds and c.status == 423)
        self.assertEqual(refused, 0)
        self.assertEqual(world5.LOCK_WAIT_ROUNDS, 150)  # Round 3 (V1b R1)

    # ---- V1 B4: control channels
    def test_fencing_tokens_are_per_record_so_controls_leak_nothing(self):
        task = I.build("budget_write_skew_ctrl", 0, 2)

        def lock_once(ctx):
            r = yield ToolCall("acquire_lock", {"record_id": ctx.intent.writes[0], "lease_calls": 5})
            yield ToolCall("release_lock", {"record_id": ctx.intent.writes[0]})
            return str(r.get("fencing_token"))

        def no_lock(ctx):
            yield ToolCall("get_record", {"record_id": ctx.intent.writes[0]})

        for s in range(8):
            toks = set()
            for peer in (lock_once, no_lock):
                spec = {"a0": AgentSpec("l", lock_once), "a1": AgentSpec("p", peer)}
                ep = run_episode(task, spec, world_config("locks"), V.schedule_for("budget_write_skew_ctrl", 0, s, 2, "locks"))
                toks.add(tuple(c.response.get("fencing_token") for c in ep.ledger.calls if c.agent_id == "a0" and c.tool == "acquire_lock"))
            self.assertEqual(toks, {(1,)})  # v1: a0's token was 2 when a1 locked its own private record first

    def test_message_ids_per_recipient_and_delivered_messages_are_cross_agent_edges(self):
        task = I.build("seat_same_ctrl", 0, 2)
        w = world(task, "all_peer_informed")
        self.assertEqual(w.call("a1", "send_message", {"to_agent": "a0", "text": "hi"})["message_id"], 1)
        self.assertEqual(w.call("a0", "send_message", {"to_agent": "a1", "text": "hi"})["message_id"], 1)  # v1: 2
        self.assertEqual(w.call("a1", "send_message", {"to_agent": "a0", "text": "again"})["message_id"], 2)
        w.call("a0", "read_messages", {})
        sc = sc_of(task, w, "all_peer_informed")
        self.assertEqual((sc.cross_agent_record_edges, sc.messages_delivered, sc.cross_agent_edges), (0, 2, 2))

    def test_dry_run_model_locks_and_messages(self):
        tmp = tempfile.mkdtemp(prefix="src5dry_")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = run5.run_grid(["--models", "claude-haiku-4-5-20251001", "--configs", "locks,all_peer_informed",
                                      "--tasks", "families:budget_write_skew", "--instances", "1", "--seeds", "0",
                                      "--out", tmp, "--dry-run"])
            self.assertEqual(code, 0)
            d = os.path.join(tmp, "dry_run", "transcripts")
            trs = []
            for f in os.listdir(d):
                with open(os.path.join(d, f)) as fh:
                    trs.append(json.load(fh))
            calls = [c for tr in trs for c in tr["ledger"]["calls"]]
            self.assertTrue(any(c["tool"] == "acquire_lock" and c["status"] == 200 for c in calls))
            self.assertTrue(any(c["committed"] and c.get("fencing_token") for c in calls))
            ctrl_msg = [tr for tr in trs if tr["task"]["category"] == "control" and tr["config"] == "all_peer_informed"]
            self.assertTrue(ctrl_msg and all(tr["score"]["messages_delivered"] > 0 for tr in ctrl_msg))
            self.assertTrue(all(tr["score"]["cross_agent_record_edges"] == 0 for tr in trs if tr["task"]["category"] == "control"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- V1 B5: fencing covers writes, not read-modify-write
    def test_lease_expired_text_is_neutral(self):
        w = world(inv_task(5, 1), "locks")
        tok = w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 1})["fencing_token"]
        w.call("a0", "get_record", {"record_id": self.rec})
        r = w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "fencing_token": tok})
        self.assertEqual(r["message"], f"409 Conflict: your lock on {self.rec} has ended.")
        for t in tool_schemas(CoordinationConfig.from_names("locks")):
            self.assertNotIn("acquire it again", json.dumps(t))

    def test_reacquire_without_reread_is_flagged_and_fails(self):
        eps = V.run_cell("reacquire_no_reread", "inventory_still_valid", "locks", 2, 2, 4)
        self.assertTrue(any(sc.outcome == "failed" and sc.flags["lost_update"] for _, sc in eps))
        self.assertTrue(all(sc.flags["fenced_stale_basis"] for _, sc in eps if sc.flags["lost_update"]))
        for ep, sc in eps:
            self.assertEqual(mutual_exclusion_violations(ep.ledger), [])  # every write fenced and in-lease ...
            for a in sc.agents.values():
                self.assertTrue(a.lock and a.lock_granted)
                if a.fenced_stale_basis:
                    self.assertIs(a.lock_effective, False)      # ... yet the lock was not effective

    def test_tokenless_write_after_lease_end_fails_and_is_not_effective_locking(self):
        eps = V.run_cell("lease_then_tokenless", "inventory_last_unit", "locks", 2, 2, 4)
        self.assertGreater(sum(sc.outcome == "failed" for _, sc in eps), 0)
        self.assertTrue(all(a.lock and a.lock_effective is False for _, sc in eps for a in sc.agents.values() if a.committed_writes))
        eps = V.run_cell("lock_protected", "inventory_last_unit", "locks", 2, 2, 4)
        self.assertTrue(all(a.lock_effective is (True if a.committed_writes else None) for _, sc in eps for a in sc.agents.values()))

    # ---- V1 B6: the mutual-exclusion gate checks leases (deliberately broken worlds)
    def test_lock_events_carry_ledger_seq(self):
        w = world(inv_task(5, 1), "locks")
        w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 1})
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a0", "get_record", {"record_id": self.rec})
        w.ledger.flags["lock_events"] = list(w.lock_events)
        self.assertEqual([(e["event"], e["seq"]) for e in w.lock_events], [("grant", 1), ("expire", 3)])

    def _broken(self, mutant):
        orig = ConcurrentWorld._check_lock
        ConcurrentWorld._check_lock = mutant
        try:
            def expired_writer(ctx):
                rid = ctx.intent.reads[0]
                r = yield ToolCall("acquire_lock", {"record_id": rid, "lease_calls": 1})
                v = yield ToolCall("get_record", {"record_id": rid})
                yield ToolCall("list_effects", {})
                yield ToolCall("update_record", {"record_id": rid, "value": v["value"] - 1, "fencing_token": r.get("fencing_token", 1)})
                yield ToolCall("update_record", {"record_id": rid, "value": v["value"] - 1})

            n = 0
            for s in range(8):
                ep = run_episode(inv_task(9, 1), AgentSpec("x", expired_writer), world_config("locks"),
                                 V.schedule_for("inventory_still_valid", 0, s, 2, "locks"))
                n += bool(mutual_exclusion_violations(ep.ledger))
            return n
        finally:
            ConcurrentWorld._check_lock = orig

    def test_mutex_gate_catches_a_world_that_accepts_expired_tokens(self):
        orig = ConcurrentWorld._check_lock

        def accept_expired(self, agent_id, record, args, log):
            if args.get("fencing_token") is not None and self._locks.get(record.record_id) is None:
                log["fencing_token"] = args["fencing_token"]
                return None
            return orig(self, agent_id, record, args, log)

        self.assertEqual(self._broken(accept_expired), 8)  # v1 gate: 0/8

    def test_mutex_gate_catches_a_world_that_lets_non_holders_write(self):
        orig = ConcurrentWorld._check_lock

        def ignore_locks(self, agent_id, record, args, log):
            if args.get("fencing_token") is not None:
                log["fencing_token"] = args["fencing_token"]
            return None

        self.assertGreater(self._broken(ignore_locks), 0)

    def test_mutex_gate_catches_a_tokenless_non_holder_write_while_locked(self):
        task = inv_task(5, 1)
        w = world(task, "locks")
        w._check_lock = lambda agent_id, record, args, log: None  # broken world: locks are not enforced at all
        w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 10})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4})  # tokenless, by a non-holder, lock live
        w.ledger.flags["lock_events"] = list(w.lock_events)
        out = mutual_exclusion_violations(w.ledger)
        self.assertEqual(len(out), 1)
        self.assertIn("while a0 held", out[0])
        w.call("a0", "update_record", {"record_id": self.rec, "value": 3})  # the holder, without its token
        w.ledger.flags["lock_events"] = list(w.lock_events)
        self.assertTrue(any("without its live token" in v for v in mutual_exclusion_violations(w.ledger)))

    def test_mutex_gate_is_clean_on_correct_lock_use(self):
        for fam in ("budget_write_skew", "transfer_shared_source", "seat_same"):
            for ep, _ in V.run_cell("lock_protected", fam, "all_available", 2, 2, 4):
                self.assertEqual(mutual_exclusion_violations(ep.ledger), [])

    # ---- V2 F2: primary lock measure is the attempt
    def test_refused_acquire_counts_as_lock_attempt_not_grant(self):
        w = world(inv_task(5, 1), "locks")
        w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 20})
        w.call("a1", "acquire_lock", {"record_id": self.rec, "lease_calls": 5}, waited_rounds=48)  # 423 after the wait
        w.call("a1", "acquire_lock", {"record_id": "inventory:nope", "lease_calls": 5})            # 404: not well-formed
        sc = sc_of(w_task := inv_task(5, 1), w, "locks")
        a1 = sc.agents["a1"]
        self.assertTrue(a1.lock and not a1.lock_granted)
        self.assertEqual((a1.lock_waits, a1.lock_waits_423, a1.first_protective), (1, 1, "lock"))
        self.assertIn("lock", a1.choices)
        self.assertIsNotNone(w_task)

    def test_protection_timing_relative_to_first_contention(self):
        task = inv_task(5, 1)
        w = world(task, "cas_available")
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4})
        w.call("a0", "get_record", {"record_id": self.rec})              # sees 4 != 5: contention signal
        w.call("a0", "update_record", {"record_id": self.rec, "value": 3, "expected_version": 2})
        a0 = sc_of(task, w, "cas_available").agents["a0"]
        self.assertEqual((a0.first_contention_call, a0.first_protective_call, a0.protect_before_contention), (1, 2, False))

    # ---- V2 F5: canonical record order and deadlock as an outcome
    def test_guard_records_listed_in_one_order_for_every_agent(self):
        for fam in ("budget_write_skew", "joint_account_write_skew"):
            for w in (0, 1):
                task = I.build(fam, w, 2)
                lists = set()
                for i in task.intents.values():
                    guard = sorted(set(i.reads) - {getattr(i, "cap", None)})
                    self.assertIn(", ".join(guard), i.describe())  # one canonical (sorted) order ...
                    lists.add(", ".join(guard))
                self.assertEqual(len(lists), 1, fam)                # ... the same for every agent

    def test_lock_order_deadlock_is_recorded_and_resolved(self):
        eps = V.run_cell("lock_own_first", "budget_write_skew", "locks", 2, 2, 4)
        self.assertTrue(any(sc.deadlock and sc.deadlock_rounds > 0 for _, sc in eps))
        self.assertTrue(all(sc.outcome != "failed" and not sc.stall for _, sc in eps))
        self.assertFalse(any(sc.deadlock for _, sc in V.run_cell("lock_protected", "budget_write_skew", "locks", 2, 2, 4)))

    # ---- V2 sec. 5: truncation and provider errors are their own end reasons
    def test_truncated_and_provider_error_end_reasons(self):
        for stop, reason in (("max_tokens", "truncated"), ("error", "provider_error"), ("end_turn", "returned")):
            def pol(system, tools, messages, stop=stop):
                return [{"type": "text", "text": "cut"}]

            class P(M.FakeProvider):
                def complete(self, *a, stop=stop, **k):
                    c = super().complete(*a, **k)
                    c.stop_reason = stop
                    return c

            task = inv_task(5, 1)
            rc = M.ModelRunConfig(model="fake-x", provider=P(pol), world_config=world_config("none"), turn_cap=24)
            ep = run_episode(task, M.model_agent_spec(rc, {}), world_config("none"), ScheduleConfig(seed=1, turn_cap=24))
            sc = score_episode(ep)
            self.assertEqual({a.end_reason for a in sc.agents.values()}, {reason})
            self.assertFalse(any(a.abandoned for a in sc.agents.values()) and reason != "returned")
            self.assertEqual(sc.agent_errors, 0 if reason == "returned" else 2)

    def test_gemini_temperature_recorded_as_ignored(self):
        import urllib.request
        orig = urllib.request.urlopen
        urllib.request.urlopen = lambda req, timeout=None: io.BytesIO(json.dumps({
            "model": "google/gemini-4-argon", "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1}}).encode())
        try:
            prov = providers5.OpenRouterProvider(api_key="x")
            g = prov.complete("openrouter:google/gemini-4-argon-20261013", "s", [], [{"role": "user", "content": "hi"}], 16, 0.0)
            q = prov.complete("openrouter:qwen/qwen3.6-27b-20260422", "s", [], [{"role": "user", "content": "hi"}], 16, 0.0)
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(g.temperature_effective, providers5.TEMPERATURE_IGNORED)
        self.assertEqual(q.temperature_effective, "unverified")

    # ---- V2 sec. 7: first-reply probes
    def test_probe_mode_one_completion_nothing_executed_a0_once(self):
        tmp = tempfile.mkdtemp(prefix="src5probe_")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = run5.run_grid(["--models", "claude-haiku-4-5-20251001", "--configs", "none,locks",
                                      "--tasks", "families:budget_write_skew,seat_same", "--instances", "1", "--seeds", "0",
                                      "--aware", "both", "--out", tmp, "--dry-run", "--probe"])
            self.assertEqual(code, 0)
            d = os.path.join(tmp, "dry_run", "transcripts")
            trs = {}
            for f in os.listdir(d):
                with open(os.path.join(d, f)) as fh:
                    trs[f] = json.load(fh)
            self.assertEqual(len(trs), 2 * 2 * 2 * 2)
            for f, tr in trs.items():
                self.assertTrue(f.endswith("__probe.json") and tr["probe"])
                self.assertEqual(tr["ledger"]["calls"], [])
                self.assertEqual(set(tr["agents"]), {"a1"} if tr["task"]["category"] == "control" else {"a0", "a1"})
                for a in tr["agents"].values():
                    self.assertEqual(a["completions"], 1)
                    self.assertIsNotNone(a["first_reply"])
                    self.assertIsNotNone(a["probe_calls"])
                self.assertEqual({e["reason"] for e in tr["ledger"]["agent_ends"]}, {"probe"})
            self.assertEqual(M.first_reply_code([{"name": "acquire_lock", "input": {}}, {"name": "get_record", "input": {}}]), "lock")
            self.assertEqual(M.first_reply_code([]), "no_call")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---- V1 non-blocking: per-write basis DSG, restricted compensation exposure
    def test_basis_dsg_removes_the_definitional_cas_retry_cycle(self):
        task = inv_task(5, 1)
        w = world(task, "cas_available")
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a1", "get_record", {"record_id": self.rec})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 1})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 1})  # 409
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 3, "expected_version": 2})
        sc = sc_of(task, w, "cas_available")
        self.assertTrue(sc.dsg_cycle and not sc.dsg_basis_cycle and not sc.fs_nonserializable)

    def test_fs_failure_can_be_acyclic(self):  # retracts v1 README "every fs failure is cyclic"
        task = I.build("transfer_shared_source", 0, 2)
        it = task.intents["a0"]
        w = world(task, "none")
        w.call("a0", "get_record", {"record_id": it.src})
        w.call("a0", "update_record", {"record_id": it.src, "value": str(task.initial[it.src] - it.amount)})
        sc = sc_of(task, w)
        self.assertTrue(sc.fs_nonserializable and not sc.dsg_cycle)

    def test_reading_a_restoring_compensation_version_is_not_exposure(self):
        task = budget_task()
        own0 = task.intents["a0"].own
        w = world(task, "none")
        w.call("a0", "update_record", {"record_id": own0, "value": "5.00"})
        w.call("a0", "update_record", {"record_id": own0, "value": "0.00"})   # compensation (restores 0.00)
        w.call("a1", "get_record", {"record_id": own0})                      # reads the restoring version
        w.call("a0", "update_record", {"record_id": own0, "value": "7.00"})   # retry
        w.call("a0", "update_record", {"record_id": own0, "value": "0.00"})   # compensates again
        self.assertFalse(sc_of(task, w).flags["compensation_exposed"])


# --------------------------------------------------------------------------
# Round 3 fixes (reviews V1b, V2b; CHANGES_V2.md "Round 3" maps each to these tests)
# --------------------------------------------------------------------------


def _slow_holder(extra: int):
    """A correct lock holder that makes ``extra`` innocent calls inside its critical section (review V1b R1, p10)."""
    def gen(ctx):
        intent = ctx.intent
        held = {}
        for rid in sorted(set(intent.reads)):
            r = yield ToolCall("acquire_lock", {"record_id": rid, "lease_calls": 20})
            if not r.get("ok"):
                for x in reversed(list(held)):
                    yield ToolCall("release_lock", {"record_id": x})
                return "refused"
            held[rid] = r["fencing_token"]
        vals = {}
        for rid in intent.reads:
            r = yield ToolCall("get_record", {"record_id": rid})
            vals[rid] = A.coerce_value(A.kind_of(rid), r["value"])
        for _ in range(extra):
            yield ToolCall("list_effects", {})
        new = intent.apply(vals)
        if new is not None:
            for rid in intent.writes:
                yield A._update(rid, new[rid], None, held.get(rid))
            yield ToolCall("get_record", {"record_id": intent.writes[0]})
        for x in reversed(list(held)):
            yield ToolCall("release_lock", {"record_id": x})
        return "done"
    return gen


def _verify_own_write(ctx):
    """Read, write, read the own write back (the common verify habit), then a CAS write with a version it never saw."""
    rid = ctx.intent.writes[0]
    got = yield from A._read(ctx.intent.reads)
    new = ctx.intent.apply(got[0])
    if new is None:
        return "declined"
    yield A._update(rid, new[rid], got[1].get(rid))
    yield ToolCall("get_record", {"record_id": rid})
    if ctx.coordination.conditional_writes != "off":
        yield A._update(rid, new[rid], 99)                       # own invalid expected_version: 409 invalid_version
    if ctx.coordination.locks:
        r = yield ToolCall("acquire_lock", {"record_id": rid, "lease_calls": 1})
        yield ToolCall("list_effects", {})
        yield ToolCall("list_effects", {})
        yield A._update(rid, new[rid], None, r.get("fencing_token"))  # own lease ended: 409 lease_expired
    return "done"


def _spin_after_write(ctx):
    """Naive write, then 22 reads of its own record, then a second (post-cap) write: makes more than 24 calls."""
    rid = ctx.intent.writes[0]
    got = yield from A._read(ctx.intent.reads)
    new = ctx.intent.apply(got[0])
    if new is not None:
        yield A._update(rid, new[rid])
    for _ in range(22):
        yield ToolCall("get_record", {"record_id": rid})
    if new is not None:
        yield A._update(rid, new[rid])
    return "done"


class Round3Fixes(unittest.TestCase):
    rec = "inventory:thing-x"

    # ---- R1 (V1b blocker): the lock wait covers the longest hold one lease allows
    def test_lock_wait_covers_the_longest_lease_hold_slow_holders_never_refused(self):
        d = design5.SCHEDULE_DEFAULTS
        self.assertGreaterEqual(world5.LOCK_WAIT_ROUNDS, (world5.MAX_LEASE_CALLS + 1) * (1 + d["gap_max"] + d["latency_max"]))
        acq = {t["name"]: t for t in tool_schemas(CoordinationConfig.from_names("locks"))}["acquire_lock"]["description"]
        self.assertIn("waits up to 150 rounds", acq)
        waits = refused = 0
        for fam in ("budget_write_skew", "transfer_shared_source", "joint_account_write_skew", "inventory_last_unit"):
            for extra in (2, 4, 11):  # Study 1 holders: median 3-6, p90 6-11 calls while holding
                for i in range(2):
                    for s in range(8):
                        ep = run_episode(I.build(fam, i, 2), AgentSpec(f"slow{extra}", _slow_holder(extra)),
                                         world_config("locks"), V.schedule_for(fam, i, s, 2, "locks"))
                        self.assertNotEqual(score_episode(ep).outcome, "failed")
                        for c in ep.ledger.calls:
                            if c.tool == "acquire_lock" and c.waited_rounds:
                                waits += 1
                                refused += c.status == 423
        self.assertGreater(waits, 100)
        self.assertEqual(refused, 0)

    def test_longer_wait_changes_nothing_for_the_correct_lock_policy(self):
        # lock_protected never waited 48 rounds, so its ledgers (calls, rounds, cost) are identical at 48 and 150
        for fam in ("budget_write_skew", "transfer_shared_source", "joint_account_write_skew", "seat_same"):
            for i in range(2):
                for s in range(4):
                    sched = V.schedule_for(fam, i, s, 2, "locks")
                    a = run_episode(I.build(fam, i, 2), A.LOCK_PROTECTED, world_config("locks", lock_wait_rounds=48), sched)
                    b = run_episode(I.build(fam, i, 2), A.LOCK_PROTECTED, world_config("locks"), sched)
                    self.assertEqual(a.ledger.fingerprint(), b.ledger.fingerprint())
                    self.assertLessEqual(max(x.turns for x in score_episode(b).agents.values()), 0.8 * design5.call_cap(2, "locks"))

    # ---- C1 (V2b blocker): the contention signal is caused by another agent, never by the agent itself
    def test_contention_signal_is_peer_caused_never_own(self):
        task = inv_task(5, 1)
        w = world(task, "all_available")
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 1})
        w.call("a0", "get_record", {"record_id": self.rec})                                       # own write read back
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 9})  # own invalid version
        tok = w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 1})["fencing_token"]
        w.call("a0", "list_effects", {})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "fencing_token": tok})  # own lease ended
        sc = sc_of(task, w, "all_available")
        self.assertEqual([c.reason for c in w.ledger.calls if c.status == 409], ["invalid_version", "lease_expired"])
        self.assertIsNone(sc.agents["a0"].first_contention_call)
        self.assertEqual(sc.agents["a0"].contention_signals, 0)
        w.call("a1", "get_record", {"record_id": self.rec})                                       # a0's version: a signal
        w.call("a1", "acquire_lock", {"record_id": self.rec, "lease_calls": 2})                   # token 2 after a0's lock
        sc = sc_of(task, w, "all_available")
        self.assertEqual((sc.agents["a1"].first_contention_call, sc.agents["a1"].contention_signals), (1, 2))

    def test_controls_have_no_contention_signal_under_any_reference_policy(self):
        verify = AgentSpec("verify_own_write", _verify_own_write)
        for cfg in design5.CONFIGS:
            coord = CoordinationConfig.from_names(cfg)
            for fam in I.CONTENDED:
                pols = [p for p, sp in A.REFERENCE_POLICIES.items() if sp.supported_by(coord) and A.applicable(p, fam)]
                for pol in pols + ["verify_own_write"]:
                    spec = verify if pol == "verify_own_write" else A.REFERENCE_POLICIES[pol]
                    for i in range(2):
                        for s in range(2):
                            t = fam + I.CONTROL_SUFFIX
                            ep = run_episode(I.build(t, i, 2), spec, world_config(cfg), V.schedule_for(t, i, s, 2, cfg))
                            for a in score_episode(ep).agents.values():
                                self.assertIsNone(a.first_contention_call, (cfg, fam, pol, a.agent_id))
                                self.assertEqual(a.contention_signals, 0)
        # ... while the contended arm of the same policies does see contention
        exposed = sum(a.contention_signals > 0 for _, sc in V.run_cell("verify_and_compensate", "budget_write_skew", "none", 2, 2, 4)
                      for a in sc.agents.values())
        self.assertGreater(exposed, 0)

    def test_a_protective_call_that_meets_contention_was_decided_before_it(self):
        task = inv_task(5, 1)
        w = world(task, "cas_available")
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 1})  # 409 version_conflict
        a0 = sc_of(task, w, "cas_available").agents["a0"]
        self.assertEqual((a0.first_protective_call, a0.first_contention_call), (2, 2))
        self.assertIs(a0.protect_before_contention, True)                  # V2 coded it as reactive (False)
        w = world(task, "locks")
        w.call("a1", "acquire_lock", {"record_id": self.rec, "lease_calls": 5})
        w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 5}, waited_rounds=7)  # held by the scheduler
        a0 = sc_of(task, w, "locks").agents["a0"]
        self.assertEqual(a0.first_contention_call, 1)                       # the wait itself is a signal
        self.assertIs(a0.protect_before_contention, True)
        self.assertIs(a0.lock_after_contention, False)

    def test_reactive_lock_after_a_peer_write(self):
        task = inv_task(5, 1)
        w = world(task, "locks")
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4})
        w.call("a0", "get_record", {"record_id": self.rec})                 # sees a1's version
        w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 3})
        a0 = sc_of(task, w, "locks").agents["a0"]
        self.assertEqual((a0.first_contention_call, a0.first_lock_call), (1, 2))
        self.assertIs(a0.lock_after_contention, True)
        self.assertIs(a0.protect_before_contention, False)
        self.assertIsNone(sc_of(task, w, "locks").agents["a1"].lock_after_contention)  # never tried to lock
        w = world(task, "locks")
        w.call("a1", "acquire_lock", {"record_id": self.rec, "lease_calls": 5})
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4})          # 423: a1 holds the lock
        a0 = sc_of(task, w, "locks").agents["a0"]
        self.assertEqual((w.ledger.calls[-1].status, a0.first_contention_call, a0.contention_signals), (423, 1, 1))

    # ---- V1b S1 / task item 3: a locked blind overwrite is not effective locking
    def test_locked_blind_overwrite_is_not_effective_locking(self):
        def blind_lock(ctx):
            rid = ctx.intent.writes[0]
            r = yield ToolCall("acquire_lock", {"record_id": rid, "lease_calls": 5})
            if not r.get("ok"):
                return "refused"
            yield ToolCall("claim", {"record_id": rid, "holder": ctx.agent_id, "fencing_token": r["fencing_token"]})
            yield ToolCall("release_lock", {"record_id": rid})
            return "done"

        n = 0
        for i in range(2):
            for s in range(4):
                ep = run_episode(I.build("ticket_same", i, 2), AgentSpec("blind_lock", blind_lock), world_config("locks"),
                                 V.schedule_for("ticket_same", i, s, 2, "locks"))
                sc = score_episode(ep)
                for a in sc.agents.values():
                    if a.committed_writes:
                        n += 1
                        self.assertIs(a.lock_effective, False)
                        self.assertEqual(a.fenced_unread_basis, a.fenced_writes)
        self.assertGreater(n, 0)
        for _, sc in V.run_cell("lock_protected", "ticket_same", "locks", 2, 2, 4):
            for a in sc.agents.values():
                self.assertIn(a.lock_effective, (True, None))
                self.assertEqual(a.fenced_unread_basis, 0)
        task = inv_task(5, 1)                      # read, then lock, then write with the token (read outside the lease)
        w = world(task, "locks")
        w.call("a0", "get_record", {"record_id": self.rec})
        tok = w.call("a0", "acquire_lock", {"record_id": self.rec, "lease_calls": 3})["fencing_token"]
        w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "fencing_token": tok})
        a0 = sc_of(task, w, "locks").agents["a0"]
        self.assertEqual((a0.fenced_writes, a0.fenced_unread_basis, a0.lock_effective), (1, 1, False))

    # ---- task item 6 (V2b finding 5): one neutral 409 text in both arms
    def test_version_mismatch_409_is_neutral_and_identical_in_both_arms(self):
        task = inv_task(5, 1)
        w = world(task, "cas_available")                       # contended: a1 wrote after a0's read
        w.call("a0", "get_record", {"record_id": self.rec})
        w.call("a1", "update_record", {"record_id": self.rec, "value": 4})
        r_cont = w.call("a0", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 1})
        w2 = world(task, "cas_available")                      # control: a version the record never had
        r_ctrl = w2.call("a0", "update_record", {"record_id": self.rec, "value": 4, "expected_version": 2})
        self.assertEqual((w.ledger.calls[-1].reason, w2.ledger.calls[-1].reason), ("version_conflict", "invalid_version"))
        self.assertEqual(r_cont, r_ctrl)
        msg = r_cont["message"]
        self.assertEqual(msg, f"409 Conflict: write to {self.rec} rejected: expected_version does not match the record's "
                              "current version.")
        self.assertNotIn("current_version", r_cont)
        self.assertNotIn("modified", msg)
        self.assertIsNone(re.search(r"\b(?!409\b)\d+\b", msg))   # no version number
        self.assertIsNone(PEER_CUES.search(msg))
        seat = I.build("seat_same", 0, 2)
        rid = seat.intents["a0"].writes[0]
        w3 = world(seat, "cas_available")
        r = w3.call("a0", "claim", {"record_id": rid, "expected_version": 5})
        self.assertEqual(r["message"], world5.VERSION_MISMATCH_TEXT.format(record_id=rid))
        for cfg in ("cas_available", "all_available"):
            for t in tool_schemas(CoordinationConfig.from_names(cfg)):
                self.assertNotIn("current version", json.dumps(t))

    # ---- task item 7 (V2b finding 6): the freeze covers the batch layer and the runner
    @unittest.skipUnless(os.path.isdir(os.path.join(HERE, "..", "src5_batch")), "needs the repo layout")
    def test_freeze_covers_the_batch_layer_and_the_runner(self):
        import freeze5
        fs = freeze5.files()
        for need in ("../src5_batch/batch_driver.py", "../src5_batch/harness.py", "../src5_batch/gemini_translate.py",
                     "../src5_batch/prices_batch.json", "../run_conc_study2.sh", "../src5_verify/dry_check5.py",
                     "freeze5.py", "run5.py", "plan_study2.json"):
            self.assertIn(need, fs)
        rows = "".join(f"| `{f}` | `{freeze5.sha(os.path.join(HERE, f))}` |\n" for f in fs)
        self.assertEqual(freeze5.problems(rows), [])
        bad = rows.replace(freeze5.sha(os.path.join(HERE, "../src5_batch/batch_driver.py")), "0" * 64)
        self.assertEqual(freeze5.problems(bad), ["../src5_batch/batch_driver.py: differs or unlisted"])
        dropped = "".join(ln + "\n" for ln in rows.splitlines() if "run_conc_study2.sh" not in ln)
        self.assertEqual(freeze5.problems(dropped), ["../run_conc_study2.sh: differs or unlisted"])

    # ---- task item 8 (V1b S3): cap-truncation stratum and the 24-call re-score
    def test_cap_truncated_outcome_stratum(self):
        seen = collections.Counter()
        for i in range(2):
            for s in range(8):
                sched = V.schedule_for("budget_write_skew", i, s, 2, "none")
                sched = ScheduleConfig(**{**sched.as_dict(), "turn_cap": 4})     # cut v&c between write and verify
                sc = score_episode(run_episode(I.build("budget_write_skew", i, 2), A.VERIFY_COMPENSATE, world_config("none"), sched))
                seen[sc.outcome_stratum] += 1
                self.assertEqual(sc.cap_truncated, sc.outcome == "failed" and sc.cap_endings > 0)
                self.assertEqual(sc.outcome_stratum, "cap_truncated" if sc.cap_truncated else sc.outcome)
        self.assertGreater(seen["cap_truncated"], 0)
        for _, sc in V.run_cell("naive", "budget_write_skew", "none", 2, 2, 4):     # failed without a cap ending
            self.assertFalse(sc.cap_truncated)
            self.assertEqual(sc.outcome_stratum, sc.outcome)
        self.assertIn("outcome_stratum", run5.CSV_FIELDS)
        self.assertIn("cap_truncated", run5.CSV_FIELDS)

    def test_rescore_at_cap_24_equals_a_real_run_at_cap_24_when_determinate(self):
        import rescore5
        import score5
        spec = AgentSpec("spin_after_write", _spin_after_write)
        status = collections.Counter()
        drop = ("rounds",)
        for tpl in ("inventory_last_unit", "inventory_last_unit_ctrl", "transfer_shared_source_ctrl", "seat_same"):
            for i in range(2):
                for s in range(3):
                    base = V.schedule_for(tpl, i, s, 2, "locks")
                    task = I.build(tpl, i, 2)
                    ep = run_episode(task, spec, world_config("locks"), base)                       # cap 28
                    real24 = run_episode(task, spec, world_config("locks"), ScheduleConfig(**{**base.as_dict(), "turn_cap": 24}))
                    r = score5.rescore_at_cap(task, ep.ledger, ep.store.snapshot(), 24, policies=ep.policies, config_name="locks")
                    status[r.status] += 1
                    self.assertTrue(r.truncated_agents and set(r.truncated_agents) <= set(task.agent_ids))
                    if r.status == "rescored":
                        want = {k: v for k, v in score_episode(real24).to_dict().items() if k not in drop}
                        got = {k: v for k, v in r.score.to_dict().items() if k not in drop}
                        self.assertEqual(got, want, (tpl, i, s))
                    # the transcript round trip gives the same re-score
                    tr = {"ledger": run5.ledger_json(ep.ledger), "final_store": run5.snapshot_json(ep.store),
                          "task": {"factory": tpl, "instance": i, "family": task.family, "category": task.category},
                          "n_agents": 2, "config": "locks", "episode_id": "x", "model": "m", "concurrency_aware_prompt": False,
                          "seed": s, "score": score_episode(ep).to_dict()}
                    row = rescore5.rescore_transcript(tr, 24)
                    self.assertEqual(row["status"], r.status)
                    if r.score is not None:
                        self.assertEqual(row["outcome"], r.score.outcome)
        self.assertGreater(status["rescored"], 0)
        self.assertGreater(status["indeterminate"], 0)
        ep = run_episode(inv_task(5, 1), A.LOCK_PROTECTED, world_config("locks"), ScheduleConfig(seed=2, turn_cap=28))
        self.assertEqual(score5.rescore_at_cap(ep.task, ep.ledger, ep.store.snapshot(), 24).status, "unchanged")

    # ---- task item 5 (V2b finding 4): pairs stay together; Gemini first
    def test_grid_puts_every_control_right_after_its_contended_cell(self):
        g = run5.build_grid(["m1", "m2"], ["none", "locks"], run5.resolve_tasks("families:inventory_last_unit,budget_write_skew"),
                            [0, 1], 2, [False, True], 2)
        self.assertEqual(len(g), 2 * 2 * 2 * 2 * 2 * 2 * 2)
        groups = run5.pair_groups(g)
        self.assertEqual(len(groups), len(g) // 2)
        for grp in groups:
            self.assertEqual([I.is_control(c["task"]) if hasattr(I, "is_control") else c["task"].endswith(I.CONTROL_SUFFIX)
                              for c in grp], [False, True])
            self.assertEqual({(c["model"], c["config"], c["aware"], c["instance"], c["seed"]) for c in grp}.__len__(), 1)
        # a cut anywhere removes whole replicates: schedule 0 of every family before any schedule 1
        self.assertTrue(all(c["seed"] == 0 for c in g[: len(g) // 2]))

    def test_a_cost_cap_stop_never_strands_a_contended_episode(self):
        tmp = tempfile.mkdtemp(prefix="src5pair_")
        try:
            args = ["--models", "claude-haiku-4-5-20251001", "--tasks", "families:inventory_last_unit,seat_same",
                    "--configs", "none,locks", "--instances", "2", "--seeds", "0", "--dry-run"]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run5.run_grid(args + ["--out", os.path.join(tmp, "full")]), 0)
            costs = sorted(float(json.loads(x)["cost_usd"]) for x in open(os.path.join(tmp, "full", "dry_run", "spend.jsonl")))
            per_ep = sum(costs) / 16
            stops = 0
            for k, left in enumerate((3.2, 5.1, 7.3, 9.9)):
                other = os.path.join(tmp, f"other{k}.jsonl")
                with open(other, "w") as f:
                    f.write(json.dumps({"model": "claude-haiku-4-5-20251001", "cost_usd": 19.0 - left * per_ep}) + "\n")
                out = os.path.join(tmp, f"cap{k}")
                with contextlib.redirect_stdout(io.StringIO()):
                    code = run5.run_grid(args + ["--out", out, "--extra-spend-logs", other, "--family-cap", "anthropic=19",
                                                 "--prior-input-tokens", "10"])
                rows = list(csv.DictReader(open(os.path.join(out, "dry_run", "results.csv")))) \
                    if os.path.exists(os.path.join(out, "dry_run", "results.csv")) else []
                stops += code == 2 and 0 < len(rows) < 16
                self.assertEqual(run5.unpaired(rows), [], (left, [r["episode_id"] for r in rows]))
                held = os.path.join(out, "dry_run", run5.HELD_DIR)
                self.assertEqual(os.listdir(held) if os.path.isdir(held) else [], [], left)  # the pair reservation held
            self.assertGreater(stops, 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_an_episode_is_written_only_together_with_its_matched_partner(self):
        tmp = tempfile.mkdtemp(prefix="src5hold_")
        try:
            tdir = os.path.join(tmp, "transcripts")
            os.makedirs(tdir)
            csv_path = os.path.join(tmp, "results.csv")
            cells = run5.build_grid(["claude-haiku-4-5-20251001"], ["none"], ["seat_same", "seat_same_ctrl"], [0], 2, [False], 1)
            pair = run5.pair_groups(cells)[0]
            trs = [run5.run_one(c, *M.make_provider(c["model"], dry_run=True), {}, turn_cap=0, max_tokens=1024,
                                temperature=0.0, prices=None, spend=None, dry_run=True) for c in pair]
            self.assertEqual(run5.commit_episode(tmp, tdir, csv_path, trs[0], pair), [])       # contended alone: held
            self.assertEqual(os.listdir(tdir), [])
            self.assertFalse(os.path.exists(csv_path))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run5.report_unpaired(tmp), [pair[0]["id"]])
            self.assertEqual(run5.commit_episode(tmp, tdir, csv_path, trs[1], pair), [c["id"] for c in pair])
            self.assertEqual(sorted(os.listdir(tdir)), sorted(c["id"] + ".json" for c in pair))
            self.assertEqual([r["episode_id"] for r in csv.DictReader(open(csv_path))], [c["id"] for c in pair])
            self.assertEqual(os.listdir(os.path.join(tmp, run5.HELD_DIR)), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @unittest.skipUnless(os.path.exists(os.path.join(HERE, "..", "run_conc_study2.sh")), "needs the repo layout")
    def test_runner_starts_the_gemini_lane_first(self):
        text = open(os.path.join(HERE, "..", "run_conc_study2.sh")).read()
        self.assertRegex(text, r"\nLANES=\(gemini anthropic openrouter\)")

    # ---- task item 4 (V2b finding 3): the tool text is priced; GPT probes cut; >= 10 % headroom everywhere
    def test_planner_prices_the_tool_text_and_keeps_headroom(self):
        costs = plan5.load_costs()
        for m in plan5.MODELS:
            self.assertGreater(plan5.menu_usd_per_completion(costs, m, "locks", "locks"), 0)
            self.assertGreater(plan5.menu_usd_per_completion(costs, m, "all_available", "locks"),
                               plan5.menu_usd_per_completion(costs, m, "locks", "locks"))
        self.assertEqual(plan5.menu_chars("locks"), len(json.dumps(tool_schemas(CoordinationConfig.from_names("locks")))))
        before = plan5.estimate(costs, "claude-sonnet-5", 2, "locks", "budget_write_skew", False)
        orig = world5.tool_schemas
        try:  # a longer tool text is priced: the planner reads the menu from the code
            world5.tool_schemas = lambda c, wc=None: orig(c, wc) + [{"name": "x", "description": "y" * 4000}]
            self.assertGreater(plan5.estimate(costs, "claude-sonnet-5", 2, "locks", "budget_write_skew", False), before)
        finally:
            world5.tool_schemas = orig
        plan = plan5.choose(costs, dict(B.DEFAULT_FAMILY_CAPS), B.DEFAULT_TOTAL_CAP, 1.15, "nov")
        for fam in B.FAMILIES:
            self.assertGreaterEqual(plan["headroom_by_family"][fam], 0.10, fam)
        self.assertEqual(plan["probe_instances"]["openrouter:openai/gpt-5.5-20260423"], 2)
        core = collections.Counter()
        for b in plan["blocks"]:
            if b["priority"] == 1:
                core[b["model"]] += b["episodes"]
        for m in ("openrouter:qwen/qwen3.6-27b-20260422", "claude-haiku-4-5-20251001", "claude-sonnet-5"):
            self.assertEqual(core[m], 448)  # 56 episodes per config x arm, never cut by the planner
            self.assertEqual(plan["probe_instances"][m], plan5.PROBE_K[m])
        # the input prices the planner uses agree with the price files
        prices = json.load(open(os.path.join(HERE, "prices.json")))["models"]
        self.assertEqual(plan5.INPUT_USD_PER_MTOK["claude-sonnet-5"], 0.5 * prices["claude-sonnet-5"]["input"])
        self.assertEqual(plan5.INPUT_USD_PER_MTOK["claude-fable-5"], 0.5 * prices["claude-fable-5"]["input"])
        self.assertEqual(plan5.INPUT_USD_PER_MTOK["claude-haiku-4-5-20251001"], 0.5 * prices["claude-haiku-4-5"]["input"])
        self.assertEqual(plan5.INPUT_USD_PER_MTOK["openrouter:qwen/qwen3.6-27b-20260422"], prices["openrouter:qwen/qwen3.6-27b"]["input"])
        self.assertEqual(plan5.INPUT_USD_PER_MTOK["openrouter:openai/gpt-5.5-20260423"],
                         prices["openrouter:openai/gpt-5.5-20260423"]["input"])
        pb = os.path.join(HERE, "..", "src5_batch", "prices_batch.json")
        if os.path.exists(pb):
            per = json.load(open(pb))["models"]["openrouter:google/gemini-4-argon"]["periods"]
            self.assertEqual(plan5.INPUT_USD_PER_MTOK["openrouter:google/gemini-4-argon-20261013"], per[0]["batch_published"]["input"])



# ---- Round 4: refusal and safety stops are their own end reasons (V2b note 9)
GEMINI_SAFETY_NATIVES = ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII")


def _refusal_episode(model: str, provider: Any):
    """Every agent's first completion is the given provider's reply; scored episode of inv_task(5, 1), config none.
    Returns (episode, score, agent records)."""
    rc = M.ModelRunConfig(model=model, provider=provider, world_config=world_config("none"), turn_cap=24)
    recs: Dict[str, Dict[str, Any]] = {}
    ep = run_episode(inv_task(5, 1), M.model_agent_spec(rc, recs), world_config("none"), ScheduleConfig(seed=1, turn_cap=24))
    return ep, score_episode(ep), recs


def _openrouter_reply(body: Dict[str, Any], model: str):
    import urllib.request
    orig = urllib.request.urlopen
    urllib.request.urlopen = lambda req, timeout=None: io.BytesIO(json.dumps(body).encode())
    try:
        return _refusal_episode(model, providers5.OpenRouterProvider(api_key="x"))
    finally:
        urllib.request.urlopen = orig


class Round4Refusals(unittest.TestCase):
    def assert_refusal_end(self, sc, reason: str) -> None:
        self.assertEqual({a.end_reason for a in sc.agents.values()}, {reason})
        self.assertFalse(any(a.abandoned for a in sc.agents.values()))     # never counted as abandoning
        self.assertFalse(any(a.unnecessary_give_up for a in sc.agents.values()))
        self.assertEqual(sc.agent_errors, 0)                                # not a harness error either

    def test_anthropic_refusal_stop_ends_refusal_not_returned(self):
        class Client:
            class messages:
                @staticmethod
                def create(**kw):
                    return types.SimpleNamespace(
                        content=[types.SimpleNamespace(type="text", text="I can't help with that.")], stop_reason="refusal",
                        usage=types.SimpleNamespace(input_tokens=5, output_tokens=3), model=kw["model"])

        ep, sc, recs = _refusal_episode("claude-haiku-4-5-20251001", providers5.AnthropicProvider(client=Client()))
        self.assert_refusal_end(sc, "refusal")
        self.assertTrue(all(r["stop_reason"] == "refusal" and r["final_text"] == "I can't help with that." for r in recs.values()))
        self.assertEqual({e.reason for e in ep.ledger.agent_ends}, {"refusal"})
        # an ordinary end_turn with the same text still ends "returned" (and counts as abandoning)
        Client.messages.create = staticmethod(lambda **kw: types.SimpleNamespace(
            content=[types.SimpleNamespace(type="text", text="done")], stop_reason="end_turn",
            usage=types.SimpleNamespace(input_tokens=5, output_tokens=3), model=kw["model"]))
        _, sc2, _ = _refusal_episode("claude-haiku-4-5-20251001", providers5.AnthropicProvider(client=Client()))
        self.assertEqual({a.end_reason for a in sc2.agents.values()}, {"returned"})
        self.assertTrue(all(a.abandoned for a in sc2.agents.values()))

    def test_openrouter_content_filter_stop_ends_content_filter_not_returned(self):
        body = {"model": "openai/gpt-5.5-20260423", "provider": "OpenAI",
                "choices": [{"message": {"role": "assistant", "content": None}, "finish_reason": "content_filter"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 0}}
        _, sc, _ = _openrouter_reply(body, "openrouter:openai/gpt-5.5-20260423")
        self.assert_refusal_end(sc, "content_filter")
        body["choices"][0]["finish_reason"] = "stop"
        _, sc2, _ = _openrouter_reply(body, "openrouter:openai/gpt-5.5-20260423")
        self.assertEqual({a.end_reason for a in sc2.agents.values()}, {"returned"})

    def test_every_gemini_safety_finish_and_a_blocked_prompt_end_content_filter(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "gemini_translate_r4", os.path.join(HERE, "..", "src5_batch", "gemini_translate.py"))
        G = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(G)
        req = {"contents": [{"role": "user", "parts": [{"text": M.START_MESSAGE}]}]}
        usage = {"promptTokenCount": 50, "candidatesTokenCount": 0, "thoughtsTokenCount": 0}
        replies = {n: {"candidates": [{"finishReason": n, "safetyRatings": []}], "usageMetadata": usage,
                       "modelVersion": "gemini-4-argon"} for n in GEMINI_SAFETY_NATIVES}
        replies["blocked_prompt"] = {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": usage,
                                     "modelVersion": "gemini-4-argon"}
        for name, g in replies.items():
            body = G.to_openrouter_response(g, req, "gemini-4-argon")
            self.assertEqual(body["choices"][0]["finish_reason"], "content_filter", name)
            _, sc, recs = _openrouter_reply(body, M.GEMINI_MODEL)
            self.assert_refusal_end(sc, "content_filter")
            native = "SAFETY" if name == "blocked_prompt" else name
            self.assertEqual({r["turns"][-1]["provider_meta"]["native_finish_reason"] for r in recs.values()}, {native})
        ok = G.to_openrouter_response({"candidates": [{"content": {"parts": [{"text": "done"}]}, "finishReason": "STOP"}],
                                       "usageMetadata": usage}, req, "gemini-4-argon")
        _, sc, _ = _openrouter_reply(ok, M.GEMINI_MODEL)
        self.assertEqual({a.end_reason for a in sc.agents.values()}, {"returned"})

    def test_refusal_end_reasons_are_known_to_scheduler_and_scorer(self):
        import scheduler5
        import score5
        self.assertEqual(set(M.REFUSAL_END.values()), set(score5.REFUSAL_ENDS))
        self.assertTrue(set(score5.REFUSAL_ENDS) <= set(scheduler5.AGENT_STOP_REASONS))
        self.assertTrue(set(score5.REFUSAL_ENDS) <= set(score5.NON_FINISH_ENDS))
        self.assertFalse(set(score5.REFUSAL_ENDS) & set(score5.ERROR_ENDS))


if __name__ == "__main__":
    unittest.main()
