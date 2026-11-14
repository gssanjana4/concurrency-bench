"""Unit tests for the concurrency benchmark (``python3 -m unittest tests4 -v``)."""

from __future__ import annotations

import json
import unittest
from decimal import Decimal
from typing import Any, Dict, Sequence, Tuple

import agents4 as A
import tasks4 as T
from records import (
    Ledger,
    LedgerIntegrityError,
    SharedStore,
    ValidationError,
    WriteEffect,
    coerce_value,
    verify_ledger,
)
from scheduler import AGENT_COUNTS, AgentSpec, ScheduleConfig, ToolCall, run_episode, run_paired
from score4 import (
    EpisodeScore,
    abandoned_rate,
    coordination_choice_rates,
    find_cycle,
    invariant_violation_rate,
    non_serializable_rate,
    unnecessary_give_up_rate,
    is_serializable,
    score,
    score_episode,
    score_paired,
    serial_witness,
)
from world4 import (
    CONCURRENCY_NOTICE,
    ConcurrentWorld,
    CoordinationConfig,
    build_system_prompt,
    tool_schemas,
    world_config,
)

GAP = ScheduleConfig(seed=0, read_write_gap=2)


def run(task: T.Task, spec: Any, spec_cfg: str, schedule: ScheduleConfig = GAP, **wc: Any) -> Tuple[Any, EpisodeScore]:
    """Run and score one episode."""
    ep = run_episode(task, spec, world_config(spec_cfg, **wc), schedule)
    return ep, score_episode(ep)


def manual(task: T.Task, cfg: str, script: Sequence[Tuple[str, str, Dict[str, Any]]]) -> Tuple[ConcurrentWorld, EpisodeScore]:
    """Execute a hand-written interleaving of tool calls and score it (no scheduler)."""
    store = SharedStore(task.initial)
    world = ConcurrentWorld(store, world_config(cfg), task.agent_ids)
    for agent, tool, args in script:
        world.tick()
        world.call(agent, tool, args)
    return world, score(task, store.ledger, store.snapshot())


# --------------------------------------------------------------------------
# records
# --------------------------------------------------------------------------


class RecordsTest(unittest.TestCase):
    def test_versions_and_ledger(self) -> None:
        store = SharedStore({"inventory:w": 3, "account:x": "10.00", "budget:b/cap": 5, "seat:e/1": None})
        self.assertEqual(store.get("inventory:w").version, 1)
        e = store.commit("a0", "inventory:w", 2, "update_record", {"value": 2}, step=1)
        self.assertEqual((e.old_value, e.new_value, e.old_version, e.new_version, e.seq), (3, 2, 1, 2, 1))
        store.commit("a1", "inventory:w", 1, "update_record", {"value": 1}, step=2)
        self.assertEqual(store.get("inventory:w").version, 3)
        self.assertEqual(len(store.ledger.effects), 2)
        verify_ledger(store.ledger, store.snapshot())

    def test_coercion(self) -> None:
        self.assertEqual(coerce_value("account", 0.1), Decimal("0.10"))
        self.assertEqual(coerce_value("budget", "60"), Decimal("60.00"))
        self.assertEqual(coerce_value("inventory", " 4 "), 4)
        for kind, bad in [("inventory", True), ("inventory", 1.5), ("account", "1.001"), ("seat", ""), ("account", "nan")]:
            with self.assertRaises(ValidationError):
                coerce_value(kind, bad)

    def test_coercion_rejects_overflow_negative_zero_and_non_ascii(self) -> None:
        for kind, bad in [("account", "9" * 40), ("budget", "1e30"), ("account", "-0.00"), ("account", -0.0),
                          ("inventory", "-0"), ("inventory", "\u0663"), ("account", "\u0663.00"), ("account", "1_0")]:
            with self.assertRaises(ValidationError, msg=(kind, bad)):
                coerce_value(kind, bad)

    def test_score_rejects_tampered_snapshot(self) -> None:
        task = T.inventory_last_unit(2)
        w, _ = manual(task, "none", [("a0", "update_record", {"record_id": "inventory:widget", "value": 0})])
        snap = w.store.snapshot()
        snap["inventory:widget"] = (0, 7)
        with self.assertRaises(LedgerIntegrityError):
            score(task, w.ledger, snap)

    def test_verify_ledger_detects_tampering(self) -> None:
        store = SharedStore({"inventory:w": 3})
        store.commit("a0", "inventory:w", 2, "update_record", {}, step=1)
        bad = Ledger()
        bad.effects.append(WriteEffect("a0", "inventory:w", 3, 2, 1, 3, 1, "update_record", {}, 1))
        with self.assertRaises(LedgerIntegrityError):
            verify_ledger(bad, store.snapshot())


# --------------------------------------------------------------------------
# world
# --------------------------------------------------------------------------


class WorldTest(unittest.TestCase):
    def world(self, cfg: str, records: Dict[str, Any] = None, **kw: Any) -> ConcurrentWorld:
        return ConcurrentWorld(SharedStore(records or {"inventory:w": 1, "seat:e/1": None}), world_config(cfg, **kw), ("a0", "a1"))

    def test_presets_and_combinations(self) -> None:
        self.assertEqual(CoordinationConfig.from_names("none").available_tools(), ("get_record", "update_record", "claim", "list_effects"))
        combo = CoordinationConfig.from_names("cas_available+locks+messages")
        self.assertEqual(combo.name, "cas_available+locks+messages")
        self.assertIn("send_message", combo.available_tools())
        self.assertEqual(CoordinationConfig.from_names("cas_available+cas_required").conditional_writes, "required")
        with self.assertRaises(ValueError):
            CoordinationConfig.from_names("none+locks")
        with self.assertRaises(ValueError):
            CoordinationConfig(conditional_writes="available", expose_versions=False)

    def test_versions_hidden_without_reread(self) -> None:
        w = self.world("none")
        self.assertNotIn("version", w.call("a0", "get_record", {"record_id": "inventory:w"}))
        self.assertEqual(w.ledger.calls[-1].read_version, 1)  # still logged server-side
        self.assertIn("version", self.world("reread_only").call("a0", "get_record", {"record_id": "inventory:w"}))

    def test_conditional_write_conflict_message_and_no_commit(self) -> None:
        w = self.world("cas_available")
        self.assertTrue(w.call("a0", "update_record", {"record_id": "inventory:w", "value": 0, "expected_version": 1})["ok"])
        r = w.call("a1", "update_record", {"record_id": "inventory:w", "value": 0, "expected_version": 1})
        self.assertEqual(r["status"], 409)
        self.assertEqual(r["current_version"], 2)
        self.assertIn("409 Conflict", r["message"])
        self.assertIn("current version is 2", r["message"])
        self.assertEqual(len(w.ledger.effects), 1)
        self.assertTrue(w.ledger.calls[-1].conflict)
        self.assertFalse(w.ledger.calls[-1].committed)

    def test_invalid_version_is_not_a_concurrency_conflict(self) -> None:
        w = self.world("cas_available")
        r = w.call("a0", "update_record", {"record_id": "inventory:w", "value": 0, "expected_version": 9})  # future version
        self.assertEqual(r["status"], 409)
        self.assertEqual((w.ledger.calls[-1].reason, w.ledger.calls[-1].conflict), ("invalid_version", False))
        w.call("a0", "update_record", {"record_id": "inventory:w", "value": 0, "expected_version": 1})
        w.call("a0", "update_record", {"record_id": "inventory:w", "value": 0, "expected_version": 1})  # superseded by own write
        self.assertEqual((w.ledger.calls[-1].reason, w.ledger.calls[-1].conflict), ("invalid_version", False))
        w.call("a1", "update_record", {"record_id": "inventory:w", "value": 0, "expected_version": 1})  # superseded by a0
        self.assertEqual((w.ledger.calls[-1].reason, w.ledger.calls[-1].conflict), ("version_conflict", True))
        self.assertEqual(len(w.ledger.effects), 1)

    def test_expected_version_rejected_when_cas_off(self) -> None:
        r = self.world("reread_only").call("a0", "update_record", {"record_id": "inventory:w", "value": 0, "expected_version": 1})
        self.assertEqual(r["status"], 400)

    def test_cas_required(self) -> None:
        w = self.world("cas_required")
        r = w.call("a0", "update_record", {"record_id": "inventory:w", "value": 0})
        self.assertEqual(r["status"], 428)
        self.assertEqual(len(w.ledger.effects), 0)

    def test_silent_lww_only_without_cas(self) -> None:
        w = self.world("none")
        w.call("a0", "claim", {"record_id": "seat:e/1"})
        r = w.call("a1", "claim", {"record_id": "seat:e/1"})
        self.assertTrue(r["ok"])
        self.assertEqual(w.store.get("seat:e/1").value, "a1")
        w2 = self.world("cas_available")
        w2.call("a0", "claim", {"record_id": "seat:e/1"})
        self.assertEqual(w2.call("a1", "claim", {"record_id": "seat:e/1"})["status"], 409)
        self.assertEqual(w2.call("a0", "claim", {"record_id": "seat:e/1"})["status"], 200)  # noop for holder
        self.assertEqual(len(w2.ledger.effects), 1)

    def test_locks_block_other_writers_and_expire(self) -> None:
        w = self.world("locks")
        w.tick()
        self.assertTrue(w.call("a0", "acquire_lock", {"record_id": "inventory:w", "lease_steps": 2})["ok"])
        self.assertEqual(w.call("a1", "acquire_lock", {"record_id": "inventory:w", "lease_steps": 2})["status"], 423)
        self.assertEqual(w.call("a1", "update_record", {"record_id": "inventory:w", "value": 0})["status"], 423)
        self.assertEqual(len(w.ledger.effects), 0)
        w.tick()
        self.assertEqual(w.lock_holder("inventory:w"), "a0")
        w.tick()
        self.assertIsNone(w.lock_holder("inventory:w"))  # lease of 2 rounds over
        self.assertTrue(w.call("a1", "update_record", {"record_id": "inventory:w", "value": 0})["ok"])

    def test_locks_without_expiry(self) -> None:
        w = self.world("locks", lock_expiry=False)
        w.call("a0", "acquire_lock", {"record_id": "inventory:w", "lease_steps": 1})
        for _ in range(100):
            w.tick()
        self.assertEqual(w.lock_holder("inventory:w"), "a0")
        self.assertEqual(w.call("a1", "release_lock", {"record_id": "inventory:w"})["status"], 409)

    def test_messages(self) -> None:
        w = self.world("messages")
        w.call("a0", "send_message", {"to_agent": "a1", "text": "hi"})
        self.assertEqual(w.call("a1", "read_messages", {})["messages"], [{"message_id": 1, "from": "a0", "text": "hi"}])
        self.assertEqual(w.call("a1", "read_messages", {})["messages"], [])
        self.assertEqual(w.call("a0", "send_message", {"to_agent": "a0", "text": "x"})["status"], 404)

    def test_unavailable_tools_and_bad_args(self) -> None:
        w = self.world("none")
        self.assertEqual(w.call("a0", "acquire_lock", {"record_id": "inventory:w", "lease_steps": 1})["status"], 404)
        self.assertEqual(w.call("a0", "send_message", {"to_agent": "a1", "text": "x"})["status"], 404)
        self.assertEqual(w.call("a0", "get_record", {"record_id": "inventory:nope"})["status"], 404)
        self.assertEqual(w.call("a0", "update_record", {"record_id": "inventory:w", "value": "abc"})["status"], 400)
        self.assertEqual(w.call("a0", "update_record", {"record_id": "inventory:w"})["status"], 400)
        self.assertEqual(len(w.ledger.effects), 0)
        self.assertEqual(len(w.ledger.calls), 5)

    def test_tool_schemas_per_config(self) -> None:
        names = lambda cfg: [s["name"] for s in tool_schemas(CoordinationConfig.from_names(cfg))]  # noqa: E731
        self.assertEqual(names("none"), ["get_record", "update_record", "claim", "list_effects"])
        self.assertEqual(names("locks+messages")[-4:], ["acquire_lock", "release_lock", "send_message", "read_messages"])
        upd = lambda cfg: next(s for s in tool_schemas(CoordinationConfig.from_names(cfg)) if s["name"] == "update_record")  # noqa: E731
        self.assertNotIn("expected_version", upd("reread_only")["input_schema"]["properties"])
        self.assertIn("expected_version", upd("cas_available")["input_schema"]["properties"])
        self.assertNotIn("expected_version", upd("cas_available")["input_schema"]["required"])
        self.assertIn("expected_version", upd("cas_required")["input_schema"]["required"])
        for preset in ("none", "reread_only", "cas_available", "cas_required", "locks", "messages"):
            json.dumps(tool_schemas(CoordinationConfig.from_names(preset)))

    def test_concurrency_prompt_is_plumbing_only(self) -> None:
        on = build_system_prompt("a0", ("a1",), "Sell 1.", world_config("none", concurrency_aware_prompt=True))
        off = build_system_prompt("a0", ("a1",), "Sell 1.", world_config("none"))
        self.assertIn(CONCURRENCY_NOTICE, on)
        self.assertNotIn(CONCURRENCY_NOTICE, off)
        task = T.inventory_last_unit(2)
        sched = GAP
        a = run_episode(task, A.NAIVE, world_config("none", concurrency_aware_prompt=True), sched)
        b = run_episode(task, A.NAIVE, world_config("none"), sched)
        self.assertEqual(a.ledger.fingerprint(), b.ledger.fingerprint())


# --------------------------------------------------------------------------
# tasks
# --------------------------------------------------------------------------


class TasksTest(unittest.TestCase):
    def test_catalog_builds_for_all_counts(self) -> None:
        for n in AGENT_COUNTS:
            tasks = T.all_tasks(n)
            self.assertEqual(len({t.name for t in tasks}), len(tasks))
            for t in tasks:
                self.assertEqual(len(t.intents), n)
                self.assertTrue(t.invariants)

    def test_categories_have_the_claimed_structure(self) -> None:
        for n in AGENT_COUNTS:
            for t in T.all_tasks(n):
                serial_ok = t.serially_valid_for_all()
                if t.category in ("still_valid", "control"):
                    self.assertTrue(serial_ok, t.name)
                else:
                    self.assertFalse(serial_ok, t.name)
                if t.category == "write_skew":
                    writes = [w for i in t.intents.values() for w in i.writes]
                    self.assertEqual(len(writes), len(set(writes)), "write-skew agents must write disjoint records")

    def test_noop_writeback_is_not_a_take(self) -> None:
        _, s = manual(T.inventory_last_unit(2), "none", [
            ("a0", "get_record", {"record_id": "inventory:widget"}), ("a0", "update_record", {"record_id": "inventory:widget", "value": 0}),
            ("a1", "get_record", {"record_id": "inventory:widget"}), ("a1", "update_record", {"record_id": "inventory:widget", "value": 0}),
        ])
        self.assertEqual(s.committed_agents, ("a0",))
        self.assertFalse(s.non_serializable or s.invariant_violation)
        self.assertFalse(s.agents["a1"].fulfilled)

    def test_cap_judged_at_initial_value_and_cap_change_flagged(self) -> None:
        _, s = manual(T.budget_control(2), "none", [("a0", "update_record", {"record_id": "budget:team/cap", "value": "500.00"})])
        self.assertTrue(any(v.startswith("unchanged[budget:team/cap]") for v in s.invariant_violations))
        self.assertFalse(any(v.startswith("sum_within_cap") for v in s.invariant_violations))
        _, s = manual(T.budget_write_skew(2), "none", [
            ("a0", "update_record", {"record_id": "budget:team/cap", "value": "1000.00"}),
            ("a0", "update_record", {"record_id": "budget:team/spend-a0", "value": "600.00"}),
        ])
        for prefix in ("sum_within_cap[budget:team/cap]", "unchanged[budget:team/cap]"):
            self.assertTrue(any(v.startswith(prefix) for v in s.invariant_violations), (prefix, s.invariant_violations))

    def test_intent_semantics(self) -> None:
        self.assertIsNone(T.Decrement("inventory:w", 1).apply({"inventory:w": 0}))
        self.assertEqual(T.Claim("seat:s", "x").apply({"seat:s": "x"}), {"seat:s": "x"})
        self.assertIsNone(T.Claim("seat:s", "x").apply({"seat:s": "y"}))
        g = T.GuardedSpend("budget:b/s0", ("budget:b/s1",), "budget:b/cap", "60")
        vals = {"budget:b/cap": Decimal(100), "budget:b/s0": Decimal(0), "budget:b/s1": Decimal(60)}
        self.assertIsNone(g.apply(vals))


# --------------------------------------------------------------------------
# scheduler
# --------------------------------------------------------------------------


class SchedulerTest(unittest.TestCase):
    def test_same_seed_identical_ledger(self) -> None:
        sched = ScheduleConfig(seed=7, read_write_gap=1, start_jitter=3)
        for spec, cfg in [(A.NAIVE, "none"), (A.CAREFUL_CAS, "cas_available"), (A.LOCK_USER, "locks"), (A.MESSENGER, "messages")]:
            a = run_episode(T.inventory_still_valid(4), spec, world_config(cfg), sched)
            b = run_episode(T.inventory_still_valid(4), spec, world_config(cfg), sched)
            self.assertEqual(a.ledger.fingerprint(), b.ledger.fingerprint())
            self.assertEqual(score_episode(a).to_dict(), score_episode(b).to_dict())

    def test_seed_changes_interleaving(self) -> None:
        prints = {
            run_episode(T.inventory_still_valid(4), A.CAREFUL_CAS, world_config("cas_available"), ScheduleConfig(seed=s, read_write_gap=1)).ledger.fingerprint()
            for s in range(6)
        }
        self.assertGreater(len(prints), 1)

    def test_gap_is_sweepable(self) -> None:
        lost = {
            gap: score_episode(run_episode(T.inventory_last_unit(2), A.NAIVE, world_config("none"), ScheduleConfig(seed=s, read_write_gap=gap))).non_serializable
            for gap in (0, 2)
            for s in [0]
        }
        self.assertTrue(lost[2])
        # without a gap, naive agents race when they start together and not when start jitter separates them
        zero = [
            score_episode(run_episode(T.inventory_last_unit(2), A.NAIVE, world_config("none"), ScheduleConfig(seed=s, start_jitter=3))).non_serializable
            for s in range(20)
        ]
        self.assertIn(False, zero)
        self.assertIn(True, zero)

    def test_turn_cap(self) -> None:
        def spinner(ctx: Any):
            while True:
                yield ToolCall("get_record", {"record_id": ctx.intent.reads[0]})

        ep, s = run(T.inventory_last_unit(2), AgentSpec("spinner", spinner), "none", ScheduleConfig(turn_cap=5))
        for agent in s.agents.values():
            self.assertEqual(agent.end_reason, "turn_cap")
            self.assertEqual(agent.turns, 5)
            self.assertTrue(agent.abandoned)

    def test_agent_error_is_contained(self) -> None:
        def broken(ctx: Any):
            yield ToolCall("get_record", {"record_id": ctx.intent.reads[0]})
            raise RuntimeError("boom")

        _, s = run(T.inventory_last_unit(2), AgentSpec("broken", broken), "none")
        self.assertEqual({a.end_reason for a in s.agents.values()}, {"error"})

    def test_policy_requirements_enforced(self) -> None:
        with self.assertRaises(ValueError):
            run_episode(T.inventory_last_unit(2), A.CAREFUL_CAS, world_config("none"))
        with self.assertRaises(ValueError):
            run_episode(T.inventory_last_unit(2), A.LOCK_USER, world_config("cas_available"))

    def test_paired_run(self) -> None:
        paired = run_paired(T.inventory_last_unit(2), A.NAIVE, world_config("none"), GAP)
        self.assertEqual(paired.solo.agent_ids, ("a0",))
        self.assertEqual(paired.contended.agent_ids, ("a0", "a1"))
        ps = score_paired(paired)
        self.assertTrue(ps.fulfilled_solo)
        self.assertFalse(ps.solo.non_serializable or ps.solo.invariant_violation)
        self.assertTrue(ps.contended.non_serializable)
        self.assertTrue(ps.harmed_by_contention)
        clean = score_paired(run_paired(T.inventory_last_unit(2), A.CAREFUL_CAS, world_config("cas_available"), GAP))
        self.assertFalse(clean.harmed_by_contention)


# --------------------------------------------------------------------------
# scoring: headline behaviours
# --------------------------------------------------------------------------


class ScoringTest(unittest.TestCase):
    def test_naive_pair_with_gap_oversells(self) -> None:
        ep, s = run(T.inventory_last_unit(2), A.NAIVE, "none")
        self.assertEqual(len(ep.ledger.effects), 2)
        self.assertEqual(ep.store.get("inventory:widget").value, 0)  # final value looks fine...
        self.assertTrue(s.non_serializable)  # ...but one sale was lost
        self.assertTrue(s.stale_overwrite)
        self.assertFalse(s.write_skew)
        self.assertTrue(s.graph_cycle)
        self.assertTrue(any("no_oversubscription" in v for v in s.invariant_violations))
        self.assertEqual({a.choices for a in s.agents.values()}, {("none",)})

    def test_naive_seat_double_booking(self) -> None:
        _, s = run(T.seat_same(2), A.NAIVE, "none")
        self.assertTrue(s.non_serializable)
        self.assertTrue(any("no_holder_overwrite" in v for v in s.invariant_violations))

    def test_naive_account_goes_negative_with_three(self) -> None:
        task = T.Task(
            "overdraw3", "account", "conflict", {"account:x": "100.00"},
            {a: T.Decrement("account:x", "40.00") for a in T.agent_ids(3)},
            (T.non_negative("account:x"),),
        )
        # blind absolute writes cannot drive a balance negative; the oversell shows as non_serializable
        _, s = run(task, A.NAIVE, "none")
        self.assertTrue(s.non_serializable)

    def test_rereader_narrows_but_does_not_close_the_window(self) -> None:
        losses = [
            run(T.inventory_last_unit(2), A.REREADER, "reread_only", ScheduleConfig(seed=s, read_write_gap=2))[1].non_serializable
            for s in range(20)
        ]
        self.assertIn(True, losses)  # same-round reread+write by both agents still races
        _, s = run(T.inventory_last_unit(2), A.REREADER, "reread_only")
        self.assertEqual({a.choices for a in s.agents.values()}, {("reread",)})

    def test_careful_cas_pair_clean(self) -> None:
        for task in (T.inventory_last_unit(2), T.seat_same(2), T.ticket_same(2), T.account_overdraw(2), T.transfer_shared_source(2)):
            ep, s = run(task, A.CAREFUL_CAS, "cas_available")
            self.assertFalse(s.non_serializable, task.name)
            self.assertFalse(s.graph_cycle, task.name)
            self.assertEqual(s.invariant_violations, [], task.name)
            self.assertEqual(s.unnecessary_give_ups, (), task.name)
            self.assertEqual(s.abandoned, (), task.name)
            self.assertTrue(all("cas" in a.choices for a in s.agents.values()))

    def test_still_valid_careful_cas_commits_both(self) -> None:
        ep, s = run(T.inventory_still_valid(2), A.CAREFUL_CAS, "cas_available")
        self.assertTrue(s.conflict_observed)
        self.assertEqual(ep.store.get("inventory:widget").value, 3)
        self.assertTrue(all(a.fulfilled for a in s.agents.values()))
        self.assertFalse(s.non_serializable)
        self.assertEqual(s.unnecessary_give_ups, ())
        self.assertIn("reread", next(a for a in s.agents.values() if a.conflicts_seen).choices)

    def test_still_valid_give_up_is_unnecessary(self) -> None:
        ep, s = run(T.inventory_still_valid(2), A.GIVE_UP_ON_CONFLICT, "cas_available")
        self.assertEqual(ep.store.get("inventory:widget").value, 4)
        self.assertEqual(len(s.unnecessary_give_ups), 1)
        quitter = s.agents[s.unnecessary_give_ups[0]]
        self.assertEqual(quitter.conflicts_seen, 1)
        self.assertFalse(quitter.fulfilled)
        self.assertTrue(quitter.abandoned)
        self.assertFalse(s.non_serializable)  # integrity intact; the cost is lost work

    def test_give_up_on_true_conflict_is_not_unnecessary(self) -> None:
        _, s = run(T.inventory_last_unit(2), A.GIVE_UP_ON_CONFLICT, "cas_available")
        self.assertTrue(s.conflict_observed)
        self.assertEqual(s.unnecessary_give_ups, ())
        self.assertEqual(s.abandoned, ())

    def test_mixed_policies_still_valid(self) -> None:
        _, s = run(T.inventory_still_valid(2), {"a0": A.CAREFUL_CAS, "a1": A.GIVE_UP_ON_CONFLICT}, "cas_available",
                   ScheduleConfig(seed=0, read_write_gap=2))
        self.assertTrue(s.agents["a0"].fulfilled)
        for seed in range(10):
            _, s = run(T.inventory_still_valid(2), {"a0": A.CAREFUL_CAS, "a1": A.GIVE_UP_ON_CONFLICT}, "cas_available",
                       ScheduleConfig(seed=seed, read_write_gap=2))
            self.assertNotIn("a0", s.unnecessary_give_ups)

    def test_write_skew_passes_cas_but_violates_invariant(self) -> None:
        for task in (T.budget_write_skew(2), T.joint_account_write_skew(2)):
            ep, s = run(task, A.CAREFUL_CAS, "cas_available")
            self.assertFalse(any(c.conflict for c in ep.ledger.calls), task.name)  # CAS never fired
            self.assertTrue(all(a.cas for a in s.agents.values()))
            self.assertTrue(s.invariant_violation, task.name)
            self.assertTrue(s.non_serializable, task.name)
            self.assertTrue(s.write_skew, task.name)
            self.assertFalse(s.stale_overwrite, task.name)
            self.assertTrue(s.graph_cycle, task.name)
            self.assertEqual({e.kind for e in s.edges}, {"rw"})

    def test_write_skew_also_under_cas_required(self) -> None:
        _, s = run(T.budget_write_skew(2), A.CAREFUL_CAS, "cas_required")
        self.assertTrue(s.write_skew and s.invariant_violation)

    def test_write_skew_prevented_by_locks_and_messages(self) -> None:
        for spec, cfg in [(A.LOCK_USER, "locks"), (A.MESSENGER, "messages")]:
            for task in (T.budget_write_skew(2), T.joint_account_write_skew(2)):
                _, s = run(task, spec, cfg)
                self.assertFalse(s.invariant_violation, (spec.name, task.name))
                self.assertFalse(s.non_serializable, (spec.name, task.name))

    def test_naive_under_cas_required_cannot_overwrite(self) -> None:
        ep, s = run(T.inventory_last_unit(2), A.NAIVE, "cas_required")
        self.assertFalse(s.non_serializable)
        self.assertEqual(len(ep.ledger.effects), 1)

    def test_controls_clean_for_every_policy(self) -> None:
        for spec, cfg in [(A.NAIVE, "none"), (A.REREADER, "reread_only"), (A.CAREFUL_CAS, "cas_available"),
                          (A.GIVE_UP_ON_CONFLICT, "cas_available"), (A.LOCK_USER, "locks"), (A.MESSENGER, "messages")]:
            for factory in (T.inventory_control, T.seat_control, T.ticket_control):
                _, s = run(factory(2), spec, cfg)
                self.assertFalse(s.non_serializable or s.invariant_violation or s.conflict_observed, (spec.name, factory.__name__))
                self.assertTrue(all(a.fulfilled for a in s.agents.values()))

    def test_lock_user_clean(self) -> None:
        for task in (T.inventory_last_unit(2), T.seat_same(2), T.transfer_shared_source(2), T.transfer_opposite(2)):
            _, s = run(task, A.LOCK_USER, "locks")
            self.assertFalse(s.non_serializable or s.invariant_violation or s.stall, task.name)
            self.assertEqual(s.lock_leaks, ())
            self.assertEqual(s.locks_held_at_end, {})

    def test_messenger_clean(self) -> None:
        _, s = run(T.inventory_last_unit(2), A.MESSENGER, "messages")
        self.assertFalse(s.non_serializable or s.invariant_violation)
        for a in s.agents.values():
            self.assertEqual(a.choices, ("message",))
            self.assertGreater(a.messages_received, 0)

    def test_messenger_waiting_on_non_messenger_stalls(self) -> None:
        _, s = run(T.inventory_last_unit(2), {"a0": A.MESSENGER, "a1": A.NAIVE}, "messages")
        self.assertTrue(s.stall)
        self.assertEqual(s.agents["a0"].end_reason, "stalled")


# --------------------------------------------------------------------------
# scoring: locks, TTL, stall
# --------------------------------------------------------------------------


class LockScoringTest(unittest.TestCase):
    def test_lock_leaker_without_expiry_leaks_and_stalls(self) -> None:
        _, s = run(T.inventory_still_valid(2), A.LOCK_LEAKER, "locks", lock_expiry=False)
        self.assertEqual(len(s.lock_leaks), 1)
        leaker = s.lock_leaks[0]
        self.assertEqual(s.agents[leaker].locks_held_at_end, ("inventory:widget",))
        self.assertEqual(s.locks_held_at_end, {"inventory:widget": leaker})
        self.assertTrue(s.stall)
        victim = next(a for a in s.agents if a != leaker)
        self.assertEqual(s.agents[victim].end_reason, "stalled")
        self.assertTrue(s.agents[victim].abandoned)  # stock remained
        self.assertFalse(s.agents[victim].unnecessary_give_up)  # no write conflict, did not return

    def test_lock_leak_recovered_by_ttl(self) -> None:
        sched = ScheduleConfig(seed=0, read_write_gap=0, stall_rounds=20)
        _, s = run(T.inventory_still_valid(2), {"a0": A.lock_leaker(lease_steps=8), "a1": A.LOCK_USER}, "locks", sched)
        self.assertEqual(s.lock_leaks, ("a0",))  # still a leak: held when the leaker ended
        self.assertEqual(s.locks_held_at_end, {})  # but expired before the episode ended
        self.assertFalse(s.stall)
        self.assertTrue(all(a.fulfilled for a in s.agents.values()))

    def test_lease_shorter_than_critical_section_loses_update(self) -> None:
        _, s = run(T.inventory_last_unit(2), A.lock_user(lease_steps=1), "locks", ScheduleConfig(seed=0, read_write_gap=3))
        self.assertTrue(s.non_serializable)
        self.assertTrue(s.invariant_violation)
        _, s = run(T.inventory_last_unit(2), A.lock_user(lease_steps=20), "locks", ScheduleConfig(seed=0, read_write_gap=3))
        self.assertFalse(s.non_serializable)

    def test_unordered_locking_deadlock_is_stall(self) -> None:
        stalls = [
            run(T.transfer_opposite(2), A.lock_user(ordered=False), "locks", ScheduleConfig(seed=seed), lock_expiry=False)[1]
            for seed in range(10)
        ]
        stalled = [s for s in stalls if s.stall]
        self.assertTrue(stalled)
        for s in stalled:
            self.assertEqual({a.end_reason for a in s.agents.values()}, {"stalled"})
            self.assertEqual(set(s.lock_leaks), {"a0", "a1"})
            self.assertFalse(s.non_serializable or s.invariant_violation)
        self.assertFalse(any(s.stall for s in (run(T.transfer_opposite(2), A.LOCK_USER, "locks", ScheduleConfig(seed=seed), lock_expiry=False)[1] for seed in range(10))))

    def test_deadlock_broken_by_ttl(self) -> None:
        _, s = run(T.transfer_opposite(2), A.lock_user(lease_steps=3, ordered=False), "locks", ScheduleConfig(seed=0, stall_rounds=10))
        self.assertFalse(s.stall)

    def test_stall_threshold(self) -> None:
        def waiter(ctx: Any):
            while True:
                yield ToolCall("read_messages", {})

        _, s = run(T.inventory_last_unit(2), AgentSpec("waiter", waiter), "messages", ScheduleConfig(stall_rounds=4))
        self.assertTrue(s.stall)
        self.assertEqual(s.rounds, 4)
        self.assertEqual({a.turns for a in s.agents.values()}, {4})

    def test_lock_expiry_ablation_differs_with_default_schedule(self) -> None:
        on = run(T.inventory_still_valid(2), A.LOCK_LEAKER, "locks", ScheduleConfig(seed=0), lock_expiry=True)[1]
        off = run(T.inventory_still_valid(2), A.LOCK_LEAKER, "locks", ScheduleConfig(seed=0), lock_expiry=False)[1]
        self.assertFalse(on.stall)
        self.assertTrue(all(a.fulfilled for a in on.agents.values()))  # the leaked lock expired; the victim waited
        self.assertTrue(off.stall)
        self.assertEqual(len(off.abandoned), 1)

    def test_gap_suspension_is_not_stall(self) -> None:
        _, s = run(T.inventory_last_unit(2), A.NAIVE, "none", ScheduleConfig(read_write_gap=30, stall_rounds=2))
        self.assertFalse(s.stall)


# --------------------------------------------------------------------------
# scoring: serial-order check vs dependency graph
# --------------------------------------------------------------------------


class SerializabilityTest(unittest.TestCase):
    def test_handcrafted_non_serializable(self) -> None:
        task = T.inventory_still_valid(2)
        _, s = manual(task, "none", [
            ("a0", "get_record", {"record_id": "inventory:widget"}),
            ("a1", "get_record", {"record_id": "inventory:widget"}),
            ("a0", "update_record", {"record_id": "inventory:widget", "value": 4}),
            ("a1", "update_record", {"record_id": "inventory:widget", "value": 4}),
        ])
        self.assertTrue(s.non_serializable and s.graph_cycle and s.stale_overwrite)
        self.assertEqual(s.cycle[0], s.cycle[-1])
        self.assertEqual({(e.kind, e.src, e.dst) for e in s.edges}, {("ww", "a0", "a1"), ("rw", "a1", "a0")})
        self.assertFalse(s.invariant_violation)  # stock 4 >= 0 and 2 takes <= 5: only non_serializable catches it

    def test_handcrafted_serial(self) -> None:
        task = T.inventory_still_valid(2)
        _, s = manual(task, "none", [
            ("a0", "get_record", {"record_id": "inventory:widget"}),
            ("a0", "update_record", {"record_id": "inventory:widget", "value": 4}),
            ("a1", "get_record", {"record_id": "inventory:widget"}),
            ("a1", "update_record", {"record_id": "inventory:widget", "value": 3}),
            ("a0", "get_record", {"record_id": "inventory:widget"}),  # post-hoc verification read
        ])
        self.assertFalse(s.non_serializable or s.graph_cycle)
        self.assertEqual(s.serial_witness, ("a0", "a1"))
        self.assertEqual({(e.kind, e.src, e.dst) for e in s.edges}, {("ww", "a0", "a1"), ("wr", "a0", "a1")})

    def test_handcrafted_write_skew(self) -> None:
        task = T.budget_write_skew(2)
        reads = [(a, "get_record", {"record_id": r}) for a in ("a0", "a1") for r in task.intents[a].reads]
        _, s = manual(task, "cas_available", reads + [
            ("a0", "update_record", {"record_id": "budget:team/spend-a0", "value": "60.00", "expected_version": 1}),
            ("a1", "update_record", {"record_id": "budget:team/spend-a1", "value": "60.00", "expected_version": 1}),
        ])
        self.assertTrue(s.non_serializable and s.graph_cycle and s.write_skew and s.invariant_violation)
        self.assertFalse(s.stale_overwrite)

    def test_serial_witness_enumerates_orders(self) -> None:
        task = T.Task(
            "orders", "inventory", "still_valid", {"inventory:w": 10},
            {"a0": T.Decrement("inventory:w", 1), "a1": T.Decrement("inventory:w", 2), "a2": T.Decrement("inventory:w", 4)},
            (),
        )
        init = dict(task.initial)
        self.assertTrue(is_serializable(task, ["a0", "a1", "a2"], init, {"inventory:w": 3}))
        self.assertFalse(is_serializable(task, ["a0", "a1", "a2"], init, {"inventory:w": 6}))
        self.assertTrue(is_serializable(task, ["a2"], init, {"inventory:w": 6}))
        # order-dependent validity: only a1-before-a0 leaves the seat with a1
        seat = T.Task("s", "seat", "conflict", {"seat:x": None}, {"a0": T.Claim("seat:x", "p"), "a1": T.Claim("seat:x", "q")}, ())
        self.assertIsNone(serial_witness(seat, ["a0", "a1"], {"seat:x": None}, {"seat:x": "q"}))
        self.assertEqual(serial_witness(seat, ["a1"], {"seat:x": None}, {"seat:x": "q"}), ("a1",))

    def test_find_cycle(self) -> None:
        from score4 import Edge
        self.assertIsNone(find_cycle(["a", "b", "c"], [Edge("a", "b", "ww", "r", 1), Edge("b", "c", "wr", "r", 2)]))
        cyc = find_cycle(["a", "b", "c"], [Edge("a", "b", "ww", "r", 1), Edge("b", "c", "wr", "r", 2), Edge("c", "a", "rw", "r", 2)])
        self.assertEqual(cyc, ("a", "b", "c", "a"))

    SINGLE_RECORD = (T.inventory_last_unit, T.inventory_still_valid, T.seat_same, T.ticket_same, T.account_overdraw, T.account_still_valid)
    POLICIES = ((A.NAIVE, "none"), (A.REREADER, "reread_only"), (A.CAREFUL_CAS, "cas_available"),
                (A.GIVE_UP_ON_CONFLICT, "cas_available"), (A.LOCK_USER, "locks"), (A.lock_user(lease_steps=1), "locks"),
                (A.MESSENGER, "messages"))

    def test_checks_agree_on_single_record_and_two_agent_skew_tasks(self) -> None:
        seen = {True: 0, False: 0}
        cases = [(f, n) for f in self.SINGLE_RECORD for n in (2, 3)]
        cases += [(f, 2) for f in (T.budget_write_skew, T.joint_account_write_skew)]
        for factory, n in cases:
            for spec, cfg in self.POLICIES:
                for seed in range(6):
                    for gap in (0, 2):
                        _, s = run(factory(n), spec, cfg, ScheduleConfig(seed=seed, read_write_gap=gap, start_jitter=2, turn_cap=200))
                        self.assertEqual(s.non_serializable, s.graph_cycle, (factory.__name__, n, spec.name, seed, gap))
                        seen[s.non_serializable] += 1
        self.assertGreater(seen[True], 50)
        self.assertGreater(seen[False], 50)

    def test_checks_agree_on_single_record_with_blind_writers(self) -> None:
        def blind(ctx: Any):
            new = ctx.intent.apply(dict(task.initial))
            for r in ctx.intent.writes:
                if r.startswith(("seat:", "ticket:")):
                    yield ToolCall("claim", {"record_id": r, "holder": new[r]})
                else:
                    yield ToolCall("update_record", {"record_id": r, "value": str(new[r])})

        seen = {True: 0, False: 0}
        for factory in self.SINGLE_RECORD:
            task = factory(3)
            for mix in ({"a0"}, {"a0", "a2"}, {"a0", "a1", "a2"}):
                specs = {a: (AgentSpec("blind", blind) if a in mix else A.NAIVE) for a in task.agent_ids}
                for seed in range(4):
                    _, s = run(task, specs, "none", ScheduleConfig(seed=seed, read_write_gap=2, start_jitter=2))
                    self.assertEqual(s.non_serializable, s.graph_cycle, (factory.__name__, sorted(mix), seed))
                    if s.non_serializable:
                        self.assertTrue(s.stale_overwrite and not s.write_skew)
                    seen[s.non_serializable] += 1
        self.assertGreater(seen[True], 10)
        self.assertGreater(seen[False], 3)

    def test_acyclic_implies_serializable(self) -> None:
        for factory in T.CATALOG.values():
            for spec, cfg in self.POLICIES:
                for seed in range(4):
                    _, s = run(factory(3), spec, cfg, ScheduleConfig(seed=seed, read_write_gap=1, start_jitter=2, turn_cap=200))
                    if not s.graph_cycle and not s.partial_commits:
                        self.assertFalse(s.non_serializable, (factory.__name__, spec.name, seed))

    def test_graph_is_stricter_on_commuting_effects(self) -> None:
        stricter = [
            s for seed in range(10)
            for s in [run(T.budget_control(2), A.NAIVE, "none", ScheduleConfig(seed=seed, read_write_gap=2))[1]]
            if s.graph_cycle and not s.non_serializable
        ]
        self.assertTrue(stricter)
        for s in stricter:
            self.assertFalse(s.invariant_violation)


# --------------------------------------------------------------------------
# agent counts
# --------------------------------------------------------------------------


class AgentCountTest(unittest.TestCase):
    def test_counts_2_4_8(self) -> None:
        for n in AGENT_COUNTS:
            _, s = run(T.inventory_last_unit(n), A.NAIVE, "none")
            self.assertTrue(s.non_serializable, n)
            self.assertGreater(len(s.committed_agents), 1)

            ep, s = run(T.inventory_last_unit(n), A.CAREFUL_CAS, "cas_available")
            self.assertFalse(s.non_serializable or s.invariant_violation, n)
            self.assertEqual(len(ep.ledger.effects), 1)
            self.assertEqual(s.abandoned, ())

            ep, s = run(T.inventory_still_valid(n), A.CAREFUL_CAS, "cas_available")
            self.assertTrue(all(a.fulfilled for a in s.agents.values()), n)
            self.assertEqual(ep.store.get("inventory:widget").value, max(5, n) - n)

            _, s = run(T.inventory_still_valid(n), A.LOCK_USER, "locks", ScheduleConfig(seed=0, read_write_gap=2, turn_cap=400))
            self.assertTrue(all(a.fulfilled for a in s.agents.values()), n)
            self.assertFalse(s.stall)

            _, s = run(T.seat_same(n), A.MESSENGER, "messages", ScheduleConfig(seed=0, read_write_gap=2, turn_cap=400))
            self.assertFalse(s.non_serializable or s.invariant_violation, n)

            _, s = run(T.budget_write_skew(n), A.CAREFUL_CAS, "cas_available")
            self.assertTrue(s.write_skew and s.invariant_violation, n)

            _, s = run(T.inventory_still_valid(n), A.GIVE_UP_ON_CONFLICT, "cas_available")
            self.assertGreaterEqual(len(s.unnecessary_give_ups), 1, n)

    def test_aggregate_rates_use_explicit_denominators(self) -> None:
        solo = run(T.inventory_still_valid(2).restrict(["a0"]), A.GIVE_UP_ON_CONFLICT, "cas_available")[1]
        quit_ = run(T.inventory_still_valid(2), A.GIVE_UP_ON_CONFLICT, "cas_available")[1]
        lost = run(T.inventory_last_unit(2), A.NAIVE, "none")[1]
        eps = [solo, quit_, lost]
        self.assertEqual((non_serializable_rate(eps).numerator, non_serializable_rate(eps).denominator), (1, 2))  # solo excluded
        self.assertEqual(invariant_violation_rate(eps).denominator, 2)
        ug = unnecessary_give_up_rate(eps)
        self.assertEqual((ug.numerator, ug.denominator), (1, 1))  # only the quitter saw a conflict
        ab = abandoned_rate(eps)
        self.assertEqual(ab.numerator, 1)
        self.assertEqual(ab.denominator, 5)  # every agent here could act; none ended with an invalid intent
        lost_cas = run(T.inventory_last_unit(2), A.GIVE_UP_ON_CONFLICT, "cas_available")[1]
        self.assertEqual(abandoned_rate([lost_cas]).denominator, 1)  # the loser's intent was invalid when it ended
        rates = coordination_choice_rates(eps)
        self.assertEqual({r.denominator for r in rates.values()}, {5})
        self.assertEqual(rates["cas"].numerator, 3)
        self.assertEqual(rates["none"].numerator, 2)
        self.assertIsNone(non_serializable_rate([solo]).value)

    def test_scores_are_json_serialisable(self) -> None:
        for n in AGENT_COUNTS:
            for task in T.all_tasks(n):
                _, s = run(task, A.CAREFUL_CAS, "cas_available+locks+messages", ScheduleConfig(seed=1, read_write_gap=1))
                json.dumps(s.to_dict())


if __name__ == "__main__":
    unittest.main()
