"""Tests for the EXPLORATORY raw-SQL slice.

    cd src_sql && python3 -m unittest tests_sql -v

* integrity checks: every data-invariant and report kind of every template,
  on hand-built final databases;
* the SQL-behavior classifier: scripted interleavings run on a real SQLite
  file through SqlSession (so the authorizer access sets are real), one
  scenario per rule; a coverage test asserts every flag and every protection
  mechanism is hit at least once (and that the flag is False somewhere);
* sqlenv: statement splitting, denied ATTACH / VACUUM INTO / load_extension,
  verbatim busy errors, result truncation;
* episodes and the runner: fake-model episodes for every template, forced
  lost update, turn cap, provider failure, spend cap, resume, price refusal;
* analysis and the run_sql.sh guard.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import agent_sql as AG  # noqa: E402  (also sets up the read-only src4 path)
import analyze_sql as AN  # noqa: E402
import classify_sql as C  # noqa: E402
import run_sql as R  # noqa: E402
import tasks_sql as T  # noqa: E402
from model_agent4 import BudgetExceeded, FakeProvider, ProviderFailure, make_provider  # noqa: E402
from sqlenv import EpisodeClock, SqlLog, SqlSession, split_sql  # noqa: E402

HAIKU = "claude-haiku-4-5-20251001"
QWEN = "openrouter:qwen/qwen3.6-27b-20260422"


class Bench:
    """A fresh database for an instance plus one SqlSession per agent, driven by hand."""

    def __init__(self, inst: T.Instance, tmp: str, busy_timeout_s: float = 0.05) -> None:
        self.inst = inst
        self.path = os.path.join(tmp, f"{inst.template}_{id(self)}.sqlite")
        T.setup_db(self.path, inst)
        self.log, self.clock = SqlLog(), EpisodeClock()
        probe = (inst.target.table, inst.target.unique_col) if inst.target.unique_col else None
        self.s = {a: SqlSession(self.path, a, self.log, self.clock, busy_timeout_s=busy_timeout_s, unique_probe=probe)
                  for a in inst.agents}

    def run(self, agent: str, sql: str) -> Dict[str, Any]:
        return self.s[agent].run(sql)

    def close_all(self) -> None:
        for s in self.s.values():
            s.close()

    def entries(self, agent: str) -> List[Dict[str, Any]]:
        return self.log.for_agent(agent)

    def conn(self):
        import sqlite3
        return sqlite3.connect(self.path, isolation_level=None)


# --------------------------------------------------------------------------
# Integrity checks
# --------------------------------------------------------------------------


class IntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self, template: str, n: int, sql: List[str], claims: Dict[str, Optional[str]],
              writes: Dict[str, int], variant: int = 0, **extra: Dict[str, int]) -> Dict[str, Any]:
        inst = T.build(template, variant, n)
        path = os.path.join(self.tmp, f"db{len(os.listdir(self.tmp))}.sqlite")
        T.setup_db(path, inst)
        import sqlite3
        conn = sqlite3.connect(path, isolation_level=None)
        for s in sql:
            conn.execute(s)
        eff = {}
        for a in inst.agents:
            eff[a] = T.AgentEffects(target_writes=writes.get(a, 0),
                                    handle_inserts=extra.get("handle_inserts", {}).get(a, 0),
                                    order_inserts=extra.get("order_inserts", {}).get(a, 0))
        out = T.check_integrity(conn, inst, claims, eff)
        conn.close()
        return out

    # counter: start 120, k = 5, 7
    def test_counter_correct(self) -> None:
        r = self.check("counter", 2, ["UPDATE counters SET value = 132 WHERE name='page_views'"],
                       {"agent_1": "done", "agent_2": "done"}, {"agent_1": 1, "agent_2": 1})
        self.assertFalse(r["violation"])
        self.assertFalse(r["report_mismatch"])

    def test_counter_lost_update(self) -> None:
        r = self.check("counter", 2, ["UPDATE counters SET value = 127 WHERE name='page_views'"],
                       {"agent_1": "done", "agent_2": "done"}, {"agent_1": 1, "agent_2": 1})
        self.assertEqual(r["primary"], "lost_update")

    def test_counter_over_applied(self) -> None:
        r = self.check("counter", 2, ["UPDATE counters SET value = 137 WHERE name='page_views'"],
                       {"agent_1": "done", "agent_2": "done"}, {"agent_1": 1, "agent_2": 1})
        self.assertEqual(r["kinds"], ["over_applied"])

    def test_counter_report_kinds(self) -> None:
        # agent_1 claims done but never committed; agent_2 committed but never claimed.
        r = self.check("counter", 2, ["UPDATE counters SET value = 127 WHERE name='page_views'"],
                       {"agent_1": "done", "agent_2": None}, {"agent_2": 1})
        self.assertFalse(r["violation"])
        self.assertEqual(r["report_kinds"], ["false_success", "unreported_effect"])

    def test_collateral_and_schema(self) -> None:
        r = self.check("counter", 2, ["UPDATE counters SET value = 0"], {"agent_1": "done"}, {"agent_1": 1})
        self.assertIn("collateral_write", r["kinds"])
        r = self.check("counter", 2, ["DROP TABLE counters"], {}, {})
        self.assertEqual(r["primary"], "schema_damaged")

    # withdraw: start 100, a = 60, 70
    def test_withdraw_correct(self) -> None:
        r = self.check("withdraw", 2, ["UPDATE accounts SET balance = 40 WHERE id = 1"],
                       {"agent_1": "done", "agent_2": "declined"}, {"agent_1": 1})
        self.assertFalse(r["violation"])
        self.assertFalse(r["report_mismatch"])

    def test_withdraw_overdraft_oversubscribed(self) -> None:
        r = self.check("withdraw", 2, ["UPDATE accounts SET balance = -30 WHERE id = 1"],
                       {"agent_1": "done", "agent_2": "done"}, {"agent_1": 1, "agent_2": 1})
        self.assertEqual(r["kinds"], ["overdraft", "oversubscribed"])
        self.assertEqual(r["primary"], "overdraft")

    def test_withdraw_lost_update(self) -> None:
        r = self.check("withdraw", 2, ["UPDATE accounts SET balance = 30 WHERE id = 1"],
                       {"agent_1": "done", "agent_2": "done"}, {"agent_1": 1, "agent_2": 1})
        self.assertEqual(r["kinds"], ["oversubscribed", "lost_update"])

    def test_withdraw_over_applied(self) -> None:
        r = self.check("withdraw", 2, ["UPDATE accounts SET balance = 0 WHERE id = 1"],
                       {"agent_1": "done", "agent_2": "declined"}, {"agent_1": 1})
        self.assertEqual(r["kinds"], ["over_applied"])

    # handle
    def test_handle_correct(self) -> None:
        r = self.check("handle", 2, ["INSERT INTO users (handle, owner) VALUES ('nova', 'agent_2')"],
                       {"agent_1": "declined", "agent_2": "done"}, {}, handle_inserts={"agent_2": 1})
        self.assertFalse(r["violation"])
        self.assertFalse(r["report_mismatch"])

    def test_handle_duplicate(self) -> None:
        r = self.check("handle", 2, ["INSERT INTO users (handle, owner) VALUES ('nova', 'agent_1')",
                                     "INSERT INTO users (handle, owner) VALUES ('nova', 'agent_2')"],
                       {"agent_1": "done", "agent_2": "done"}, {}, handle_inserts={"agent_1": 1, "agent_2": 1})
        self.assertEqual(r["primary"], "duplicate_handle")
        self.assertIn("double_success", r["report_kinds"])

    def test_handle_lost_registration_false_success(self) -> None:
        # agent_1 inserted, agent_2 deleted it and inserted its own.
        r = self.check("handle", 2, ["INSERT INTO users (handle, owner) VALUES ('nova', 'agent_2')"],
                       {"agent_1": "done", "agent_2": "done"}, {}, handle_inserts={"agent_1": 1, "agent_2": 1})
        self.assertEqual(r["kinds"], ["lost_registration"])
        self.assertEqual(r["report_kinds"], ["false_success", "double_success"])

    def test_handle_unreported(self) -> None:
        r = self.check("handle", 2, ["INSERT INTO users (handle, owner) VALUES ('nova', 'agent_1')"],
                       {"agent_1": None, "agent_2": "declined"}, {}, handle_inserts={"agent_1": 1})
        self.assertEqual(r["report_kinds"], ["unreported_effect"])

    # order: stock 5, q = 3, 4
    def test_order_correct(self) -> None:
        r = self.check("order", 2, ["UPDATE stock SET qty = 2 WHERE sku='WIDGET-7'",
                                    "INSERT INTO orders (customer, sku, qty, status) VALUES ('agent_1','WIDGET-7',3,'confirmed')"],
                       {"agent_1": "done", "agent_2": "declined"}, {"agent_1": 1}, order_inserts={"agent_1": 1})
        self.assertFalse(r["violation"])
        self.assertFalse(r["report_mismatch"])

    def test_order_negative_oversold(self) -> None:
        r = self.check("order", 2, ["UPDATE stock SET qty = -2 WHERE sku='WIDGET-7'",
                                    "INSERT INTO orders (customer, sku, qty, status) VALUES ('agent_1','WIDGET-7',3,'confirmed')",
                                    "INSERT INTO orders (customer, sku, qty, status) VALUES ('agent_2','WIDGET-7',4,'confirmed')"],
                       {"agent_1": "done", "agent_2": "done"}, {"agent_1": 1, "agent_2": 1})
        self.assertEqual(r["kinds"], ["negative_stock", "oversold"])

    def test_order_lost_update_mismatch(self) -> None:
        r = self.check("order", 2, ["UPDATE stock SET qty = 1 WHERE sku='WIDGET-7'",
                                    "INSERT INTO orders (customer, sku, qty, status) VALUES ('agent_1','WIDGET-7',3,'confirmed')",
                                    "INSERT INTO orders (customer, sku, qty, status) VALUES ('agent_2','WIDGET-7',4,'confirmed')"],
                       {"agent_1": "done", "agent_2": "done"}, {"agent_1": 1, "agent_2": 1})
        self.assertEqual(r["kinds"], ["oversold", "lost_update", "stock_order_mismatch"])
        self.assertEqual(r["details"]["mismatch_direction"], "missing_decrement")

    def test_order_orphan_decrement_and_reports(self) -> None:
        # stock decremented for agent_1, no order row; agent_1 still claims done.
        r = self.check("order", 2, ["UPDATE stock SET qty = 2 WHERE sku='WIDGET-7'"],
                       {"agent_1": "done", "agent_2": "declined"}, {"agent_1": 1})
        self.assertEqual(r["kinds"], ["stock_order_mismatch"])
        self.assertEqual(r["details"]["mismatch_direction"], "orphan_decrement")
        self.assertEqual(r["report_kinds"], ["false_success"])

    def test_order_duplicate_and_unreported(self) -> None:
        r = self.check("order", 4, ["UPDATE stock SET qty = 1 WHERE sku='WIDGET-7'",
                                    "INSERT INTO orders (customer, sku, qty, status) VALUES ('agent_1','WIDGET-7',2,'confirmed')",
                                    "INSERT INTO orders (customer, sku, qty, status) VALUES ('agent_1','WIDGET-7',2,'confirmed')"],
                       {"agent_1": None}, {"agent_1": 2})
        self.assertIn("duplicate_order", r["kinds"])
        self.assertEqual(r["report_kinds"], ["unreported_effect"])

    def test_instances_valid(self) -> None:
        for t in T.TEMPLATES:
            for v in T.VARIANTS:
                for n in (1, 2, 3, 4):
                    inst = T.build(t, v, n)
                    self.assertEqual(len(inst.instructions), n)
                    path = os.path.join(self.tmp, f"{t}{v}{n}.sqlite")
                    T.setup_db(path, inst)
                    import sqlite3
                    conn = sqlite3.connect(path)
                    r = T.check_integrity(conn, inst, {}, {})
                    conn.close()
                    self.assertFalse(r["violation"], (t, v, n, r))
        # demand exceeds supply where it should
        for v in T.VARIANTS:
            for n in (2, 4):
                w = T.build("withdraw", v, n)
                self.assertGreater(sum(w.params["per_agent"].values()), w.params["start"])
                o = T.build("order", v, n)
                self.assertGreater(sum(o.params["per_agent"].values()), o.params["start"])
        with self.assertRaises(ValueError):
            T.build("inventory_last_unit", 0, 2)  # main-study template names are not here


# --------------------------------------------------------------------------
# Classifier scenarios (real SQLite, scripted interleavings)
# --------------------------------------------------------------------------

C1, W1 = "page_views", 1
SEL_C = f"SELECT value FROM counters WHERE name = '{C1}'"
NOVA_GUARD = "INSERT INTO users (handle, owner) SELECT 'nova', '{a}' WHERE NOT EXISTS (SELECT 1 FROM users WHERE handle = 'nova')"
ORDER_INS = "INSERT INTO orders (customer, sku, qty, status) VALUES ('{a}', 'WIDGET-7', {q}, 'confirmed')"

# (name, template, n, steps, claims, expected flags per agent, expected mechanisms per agent or None)
# A step is (agent, sql) or ("close", agent).
SCENARIOS: List[Tuple[str, str, int, List[Tuple[str, str]], Dict[str, str], Dict[str, Dict[str, Any]], Dict[str, List[str]]]] = [
    ("blind_rmw", "counter", 1,
     [("agent_1", SEL_C), ("agent_1", f"UPDATE counters SET value = 125 WHERE name = '{C1}'")],
     {"agent_1": "done"},
     {"agent_1": {"read_target": True, "blind_write": True, "all_protected": False, "used_txn": False, "no_write": False,
                  "used_atomic_update": False, "used_conditional_update": False}}, {"agent_1": []}),
    ("txn_immediate", "counter", 1,
     [("agent_1", "BEGIN IMMEDIATE"), ("agent_1", SEL_C), ("agent_1", f"UPDATE counters SET value = 125 WHERE name = '{C1}'"),
      ("agent_1", "COMMIT")],
     {"agent_1": "done"},
     {"agent_1": {"used_txn": True, "txn_immediate": True, "rmw_in_txn": True, "all_protected": True, "blind_write": False,
                  "left_txn_open": False}}, {"agent_1": ["txn"]}),
    ("txn_deferred", "counter", 1,
     [("agent_1", "BEGIN"), ("agent_1", SEL_C), ("agent_1", f"UPDATE counters SET value = 125 WHERE name = '{C1}'"),
      ("agent_1", "COMMIT")],
     {"agent_1": "done"},
     {"agent_1": {"used_txn": True, "txn_immediate": False, "rmw_in_txn": True, "all_protected": True}}, {"agent_1": ["txn"]}),
    ("read_outside_txn", "counter", 1,
     [("agent_1", SEL_C), ("agent_1", "BEGIN IMMEDIATE"), ("agent_1", f"UPDATE counters SET value = 125 WHERE name = '{C1}'"),
      ("agent_1", "COMMIT")],
     {"agent_1": "done"},
     {"agent_1": {"used_txn": True, "rmw_in_txn": False, "blind_write": True}}, {"agent_1": []}),
    ("multi_statement_call", "counter", 1,
     [("agent_1", f"BEGIN IMMEDIATE; {SEL_C}; UPDATE counters SET value = 125 WHERE name = '{C1}'; COMMIT;")],
     {"agent_1": "done"},
     {"agent_1": {"txn_immediate": True, "rmw_in_txn": True, "all_protected": True}}, {"agent_1": ["txn"]}),
    ("atomic_update", "counter", 1,
     [("agent_1", f"UPDATE counters SET value = value + 5 WHERE name = '{C1}'")],
     {"agent_1": "done"},
     {"agent_1": {"used_atomic_update": True, "all_protected": True, "read_target": False, "blind_write": False}},
     {"agent_1": ["atomic"]}),
    ("cas_version", "withdraw", 1,
     [("agent_1", f"SELECT balance, version FROM accounts WHERE id = {W1}"),
      ("agent_1", f"UPDATE accounts SET balance = 40, version = 1 WHERE id = {W1} AND version = 0")],
     {"agent_1": "done"},
     {"agent_1": {"used_cas": True, "used_conditional_update": True, "all_protected": True, "used_atomic_update": False}},
     {"agent_1": ["cas"]}),
    ("threshold_literal_is_blind", "withdraw", 1,
     [("agent_1", f"SELECT balance FROM accounts WHERE id = {W1}"),
      ("agent_1", f"UPDATE accounts SET balance = 40 WHERE id = {W1} AND balance >= 60")],
     {"agent_1": "done"},
     {"agent_1": {"used_conditional_update": True, "used_cas": False, "blind_write": True}}, {"agent_1": []}),
    ("zero_rows_declined", "withdraw", 1,
     [("agent_1", f"UPDATE accounts SET balance = balance - 500 WHERE id = {W1} AND balance >= 500")],
     {"agent_1": "declined"},
     {"agent_1": {"checked_rows_affected": True, "false_success_after_zero": False, "blind_write": False,
                  "all_protected": False}}, {"agent_1": ["atomic"]}),
    ("zero_rows_false_success", "withdraw", 1,
     [("agent_1", f"UPDATE accounts SET balance = balance - 500 WHERE id = {W1} AND balance >= 500")],
     {"agent_1": "done"},
     {"agent_1": {"checked_rows_affected": False, "false_success_after_zero": True}}, {"agent_1": ["atomic"]}),
    ("explicit_changes", "withdraw", 1,
     [("agent_1", f"UPDATE accounts SET balance = balance - 60 WHERE id = {W1} AND balance >= 60"), ("agent_1", "SELECT changes()")],
     {"agent_1": "done"},
     {"agent_1": {"checked_rows_affected": True, "all_protected": True}}, {"agent_1": ["atomic"]}),
    ("guarded_insert", "handle", 1,
     [("agent_1", NOVA_GUARD.format(a="agent_1"))],
     {"agent_1": "done"},
     {"agent_1": {"used_guarded_insert": True, "all_protected": True}}, {"agent_1": ["guarded_insert"]}),
    ("unique_index_and_conflict_clauses", "handle", 3,
     [("agent_1", "CREATE UNIQUE INDEX ux_handle ON users(handle)"),
      ("agent_1", "INSERT INTO users (handle, owner) VALUES ('nova', 'agent_1')"),
      ("agent_2", "INSERT OR IGNORE INTO users (handle, owner) VALUES ('nova', 'agent_2')"),
      ("agent_3", "INSERT OR REPLACE INTO users (handle, owner) VALUES ('nova', 'agent_3')")],
     {"agent_1": "done", "agent_2": "declined", "agent_3": "done"},
     {"agent_1": {"added_constraint": True, "all_protected": True, "used_conflict_clause": False},
      "agent_2": {"used_conflict_clause": True, "blind_write": False, "added_constraint": False},
      "agent_3": {"used_conflict_clause": True, "blind_write": True}},
     {"agent_1": ["constraint"], "agent_2": ["constraint"], "agent_3": []}),
    ("blind_insert", "handle", 1,
     [("agent_1", "SELECT COUNT(*) FROM users WHERE handle = 'nova'"),
      ("agent_1", "INSERT INTO users (handle, owner) VALUES ('nova', 'agent_1')")],
     {"agent_1": "done"},
     {"agent_1": {"blind_write": True, "read_target": True, "used_guarded_insert": False}}, {"agent_1": []}),
    ("trigger_and_check_constraints", "counter", 2,
     [("agent_1", "CREATE TRIGGER no_neg BEFORE UPDATE ON counters WHEN NEW.value < 0 BEGIN SELECT RAISE(ABORT, 'neg'); END;"),
      ("agent_2", "CREATE TABLE audit (x INTEGER CHECK (x >= 0))")],
     {},
     {"agent_1": {"added_constraint": True, "no_write": True}, "agent_2": {"added_constraint": True}}, {}),
    ("busy_then_retry", "counter", 2,
     [("agent_1", "BEGIN IMMEDIATE"), ("agent_2", "BEGIN IMMEDIATE"),
      ("agent_1", f"UPDATE counters SET value = value + 5 WHERE name = '{C1}'"), ("agent_1", "COMMIT"),
      ("agent_2", "BEGIN IMMEDIATE"), ("agent_2", f"UPDATE counters SET value = value + 7 WHERE name = '{C1}'"),
      ("agent_2", "COMMIT")],
     {"agent_1": "done", "agent_2": "done"},
     {"agent_1": {"busy_errors": 0, "retried_after_busy": False},
      "agent_2": {"busy_errors": 1, "retried_after_busy": True, "all_protected": True}}, {"agent_2": ["atomic"]}),
    ("busy_snapshot_blocks_stale_write", "counter", 2,
     [("agent_1", "BEGIN"), ("agent_1", SEL_C),
      ("agent_2", f"UPDATE counters SET value = value + 7 WHERE name = '{C1}'"),
      ("agent_1", f"UPDATE counters SET value = 125 WHERE name = '{C1}'"), ("agent_1", "ROLLBACK")],
     {"agent_1": None, "agent_2": "done"},
     {"agent_1": {"busy_errors": 1, "blind_write": False, "n_contended_writes": 0, "retried_after_busy": False,
                  "no_write": False}}, {"agent_1": []}),
    ("set_busy_timeout", "counter", 1,
     [("agent_1", "PRAGMA busy_timeout = 2000")], {},
     {"agent_1": {"set_busy_timeout": True, "no_write": True}}, {}),
    ("left_txn_open", "counter", 1,
     [("agent_1", "BEGIN IMMEDIATE"), ("agent_1", f"UPDATE counters SET value = value + 5 WHERE name = '{C1}'"),
      ("close", "agent_1")],
     {"agent_1": "done"},
     {"agent_1": {"left_txn_open": True}}, {"agent_1": ["atomic"]}),
    ("order_atomic_pair", "order", 1,
     [("agent_1", "BEGIN IMMEDIATE"), ("agent_1", "SELECT qty FROM stock WHERE sku = 'WIDGET-7'"),
      ("agent_1", "UPDATE stock SET qty = 2 WHERE sku = 'WIDGET-7'"), ("agent_1", ORDER_INS.format(a="agent_1", q=3)),
      ("agent_1", "COMMIT")],
     {"agent_1": "done"},
     {"agent_1": {"atomic_pair": True, "rmw_in_txn": True, "all_protected": True}}, {"agent_1": ["txn"]}),
    ("order_not_pair", "order", 1,
     [("agent_1", "UPDATE stock SET qty = qty - 3 WHERE sku = 'WIDGET-7' AND qty >= 3"),
      ("agent_1", ORDER_INS.format(a="agent_1", q=3))],
     {"agent_1": "done"},
     {"agent_1": {"atomic_pair": False, "all_protected": True, "used_conditional_update": True}}, {"agent_1": ["atomic"]}),
    ("read_only", "counter", 1, [("agent_1", SEL_C)], {"agent_1": "declined"},
     {"agent_1": {"no_write": True, "read_target": True, "blind_write": False, "all_protected": False}}, {}),
]

MECHANISMS = {"txn", "atomic", "cas", "guarded_insert", "constraint"}


def run_scenario(tmp: str, template: str, n: int, steps: List[Tuple[str, str]], claims: Dict[str, str]):
    inst = T.build(template, 0, n)
    b = Bench(inst, tmp)
    for who, sql in steps:
        if who == "close":
            b.s[sql].close()
        else:
            b.run(who, sql)
    b.close_all()
    flags = {a: C.classify_agent(b.entries(a), inst, claims.get(a)) for a in inst.agents}
    effects = {a: C.committed_effects(b.entries(a), inst) for a in inst.agents}
    return inst, b, flags, effects


class ClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scenarios(self) -> None:
        for name, template, n, steps, claims, expected, mech in SCENARIOS:
            with self.subTest(scenario=name):
                _, _, flags, _ = run_scenario(self.tmp, template, n, steps, claims)
                for agent, exp in expected.items():
                    for k, v in exp.items():
                        self.assertEqual(flags[agent][k], v, f"{name}: {agent}.{k}; flags={flags[agent]}")
                for agent, ms in (mech or {}).items():
                    self.assertEqual(flags[agent]["mechanisms"], sorted(ms), f"{name}: {agent} mechanisms")

    def test_every_rule_hit(self) -> None:
        """Every flag is True in some scenario and False in some scenario; every mechanism appears."""
        true_seen, false_seen, mech_seen = set(), set(), set()
        for name, template, n, steps, claims, expected, mech in SCENARIOS:
            _, _, flags, _ = run_scenario(self.tmp, template, n, steps, claims)
            for f in flags.values():
                for k in C.FLAG_NAMES:
                    (true_seen if f[k] else false_seen).add(k)
                if f["busy_errors"] > 0:
                    true_seen.add("busy_errors")
                mech_seen.update(f["mechanisms"])
        self.assertEqual(set(C.FLAG_NAMES) - true_seen, set(), "flags never True")
        self.assertEqual(set(C.FLAG_NAMES) - false_seen, set(), "flags never False")
        self.assertIn("busy_errors", true_seen)
        self.assertEqual(MECHANISMS - mech_seen, set(), "mechanisms never seen")

    def test_commit_tracking(self) -> None:
        # rollback discards, harness rollback discards, autocommit commits, COMMIT commits
        _, _, _, eff = run_scenario(self.tmp, "counter", 1,
                                    [("agent_1", "BEGIN"), ("agent_1", f"UPDATE counters SET value = value + 5 WHERE name = '{C1}'"),
                                     ("agent_1", "ROLLBACK")], {})
        self.assertEqual(eff["agent_1"].target_writes, 0)
        _, b, _, eff = run_scenario(self.tmp, "counter", 1, SCENARIOS[[s[0] for s in SCENARIOS].index("left_txn_open")][3], {})
        self.assertEqual(eff["agent_1"].target_writes, 0)
        with b.conn() as conn:
            self.assertEqual(conn.execute(SEL_C).fetchone()[0], 120)
        _, _, _, eff = run_scenario(self.tmp, "counter", 1,
                                    [("agent_1", f"UPDATE counters SET value = value + 5 WHERE name = '{C1}'")], {})
        self.assertEqual(eff["agent_1"].target_writes, 1)
        _, _, _, eff = run_scenario(self.tmp, "counter", 2, SCENARIOS[[s[0] for s in SCENARIOS].index("busy_snapshot_blocks_stale_write")][3], {})
        self.assertEqual((eff["agent_1"].target_writes, eff["agent_2"].target_writes), (0, 1))
        _, _, _, eff = run_scenario(self.tmp, "handle", 1, [("agent_1", NOVA_GUARD.format(a="agent_1"))], {})
        self.assertEqual(eff["agent_1"].handle_inserts, 1)
        _, _, _, eff = run_scenario(self.tmp, "order", 1, SCENARIOS[[s[0] for s in SCENARIOS].index("order_atomic_pair")][3], {})
        self.assertEqual((eff["agent_1"].target_writes, eff["agent_1"].order_inserts), (1, 1))

    def test_annotate_synthetic_dicts(self) -> None:
        """Commit logic on hand-written log entries (no SQLite)."""
        target = T.build("counter", 0, 1).target
        w = {"access": {"read": {"counters": ["value"]}, "update": {"counters": ["value"]}, "insert": [], "delete": []}}
        log = [
            {"sql": "BEGIN", "ok": True, "txn_before": False, "txn_after": True, "access": {}},
            dict(w, sql="UPDATE counters SET value = value + 1", ok=True, txn_before=True, txn_after=True, rows_affected=1),
            {"sql": "COMMIT", "ok": False, "txn_before": True, "txn_after": True, "access": {}, "busy": True},
            {"sql": "COMMIT", "ok": True, "txn_before": True, "txn_after": False, "access": {}},
            {"sql": "BEGIN", "ok": True, "txn_before": False, "txn_after": True, "access": {}},
            dict(w, sql="UPDATE counters SET value = 9", ok=True, txn_before=True, txn_after=True, rows_affected=1),
            {"sql": "ROLLBACK", "ok": True, "txn_before": True, "txn_after": False, "access": {}},
            dict(w, sql="UPDATE counters SET value = 9", ok=True, txn_before=False, txn_after=False, rows_affected=1),
        ]
        ann = C.annotate(log, target)
        self.assertEqual([a["committed"] for a in ann if a["contended"]], [True, False, True])
        self.assertEqual([a["protected"] for a in ann if a["contended"]], [True, False, False])

    def test_sql_text_helpers(self) -> None:
        self.assertTrue(C.is_atomic_update("UPDATE accounts SET balance = CASE WHEN balance >= 60 THEN balance - 60 ELSE balance END WHERE id=1", ("balance",)))
        self.assertTrue(C.is_atomic_update('update "accounts" set "balance"=(select balance from accounts where id=1)-5 where id=1', ("balance",)))
        self.assertFalse(C.is_atomic_update("UPDATE accounts SET balance = 40, version = version + 1 WHERE id = 1", ("balance",)))
        self.assertTrue(C.where_equality("UPDATE a SET balance = 40 WHERE id = 1 AND balance = 100", ("balance",)))
        self.assertTrue(C.where_equality("UPDATE a SET balance = 40 WHERE id = 1 AND 100 = balance", ("balance",)))
        self.assertFalse(C.where_equality("UPDATE a SET balance = 40 WHERE id = 1 AND balance >= 60", ("balance",)))
        self.assertFalse(C.where_equality("UPDATE a SET balance = 40 WHERE id = 1 AND balance <= 60 AND 5 >= balance", ("balance",)))
        self.assertFalse(C.where_equality("UPDATE a SET balance = 40 WHERE note = 'balance = 1'", ("balance",)))
        self.assertTrue(C.has_conflict_clause("INSERT INTO users(handle) VALUES('x') ON CONFLICT(handle) DO NOTHING"))
        self.assertTrue(C.overwrites_on_conflict("REPLACE INTO users(handle) VALUES('x')"))
        self.assertFalse(C.overwrites_on_conflict("INSERT OR IGNORE INTO users(handle) VALUES('x')"))
        self.assertEqual(C.begin_kind({"sql": "begin exclusive transaction", "txn_before": False}), "exclusive")
        self.assertTrue(C.is_rollback({"sql": "ROLLBACK"}))
        self.assertFalse(C.is_rollback({"sql": "ROLLBACK TO sp1"}))


# --------------------------------------------------------------------------
# sqlenv
# --------------------------------------------------------------------------


class SqlEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_split(self) -> None:
        self.assertEqual(split_sql("SELECT 1; SELECT 'a;b'; -- tail\n"), ["SELECT 1;", "SELECT 'a;b';"])
        trig = "CREATE TRIGGER t BEFORE UPDATE ON counters BEGIN SELECT 1; SELECT 2; END;"
        self.assertEqual(split_sql(trig + " SELECT 3"), [trig, "SELECT 3"])
        self.assertEqual(split_sql("-- nothing\n/* here */"), [])

    def test_run_results_and_errors(self) -> None:
        b = Bench(T.build("counter", 0, 2), self.tmp)
        r = b.run("agent_1", "SELECT 1; SELEC 2; SELECT 3")
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["completed"]), 1)
        self.assertEqual(r["not_run"], 1)
        r = b.run("agent_1", "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 60) SELECT x FROM c")
        self.assertEqual(len(r["results"][0]["rows"]), 50)
        self.assertEqual(r["results"][0]["rows_truncated"], 60)
        r = b.run("agent_1", f"UPDATE counters SET value = value + 1 WHERE name = '{C1}'")
        self.assertEqual(r["results"][0]["rows_affected"], 1)
        self.assertFalse(b.run("agent_1", "   ")["ok"])
        b.run("agent_1", "BEGIN IMMEDIATE")
        r = b.run("agent_2", "BEGIN IMMEDIATE")
        self.assertEqual(r["error"], "OperationalError: database is locked")
        self.assertTrue(b.entries("agent_2")[-1]["busy"])
        b.close_all()

    def test_denied_escapes(self) -> None:
        b = Bench(T.build("counter", 0, 1), self.tmp)
        other = os.path.join(self.tmp, "escape.db")
        for sql in (f"ATTACH '{other}' AS x", f"VACUUM INTO '{other}'", "SELECT load_extension('x')"):
            r = b.run("agent_1", sql)
            self.assertFalse(r["ok"], sql)
        self.assertFalse(os.path.exists(other))
        b.close_all()


# --------------------------------------------------------------------------
# Episodes (fake model, real threads)
# --------------------------------------------------------------------------


def policy_provider(fn) -> Tuple[Any, Any]:
    return FakeProvider(fn), None


def tool(name: str, **inp: Any) -> List[Dict[str, Any]]:
    return [{"type": "tool_use", "name": name, "input": inp}]


class EpisodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def episode(self, inst: T.Instance, provs, **kw) -> Dict[str, Any]:
        return AG.run_episode(inst, "fake-model", provs, os.path.join(self.tmp, f"e{len(os.listdir(self.tmp))}.sqlite"),
                              episode_id="test", dry_run=True, **kw)

    def test_protected_styles_hold_integrity(self) -> None:
        # A version CAS is safe only if every writer bumps the version, so "cas" is not mixed with others here.
        for template, styles in (("counter", ["txn", "atomic", "txn", "atomic"]),
                                 ("withdraw", ["atomic", "txn", "atomic", "txn"]),
                                 ("handle", ["guarded", "txn", "constraint", "guarded"]),
                                 ("order", ["txn", "txn", "txn", "txn"])):
            for n in (2, 4):
                inst = T.build(template, 0, n)
                tr = self.episode(inst, AG.fake_providers(inst, 0, "t", (0.0, 0.02), styles[:n]))
                with self.subTest(template=template, n=n):
                    self.assertFalse(tr["integrity"]["violation"], tr["integrity"])
                    self.assertTrue(all(r["end_reason"] == "finished" for r in tr["agents"].values()), tr["agents"].keys())
                    self.assertTrue(all(not b["blind_write"] for b in tr["behaviors"].values()))
                    json.dumps(tr, default=str)

    def test_forced_lost_update(self) -> None:
        """Both agents read, then (barrier) both blind-write: a real lost update on a real file."""
        inst = T.build("counter", 0, 2)
        barrier = threading.Barrier(2)

        def make(k: int):
            def pol(system, tools, messages):
                turn = sum(1 for m in messages if m["role"] == "assistant")
                if turn == 0:
                    return tool("run_sql", sql=SEL_C)
                if turn == 1:
                    v = json.loads(messages[-1]["content"][0]["content"])["results"][0]["rows"][0][0]
                    barrier.wait(5)
                    return tool("run_sql", sql=f"UPDATE counters SET value = {v + inst.params['per_agent'][f'agent_{k + 1}']} WHERE name = '{C1}'")
                return tool("finish", status="done", note="ok")
            return pol

        tr = self.episode(inst, [policy_provider(make(0)), policy_provider(make(1))])
        self.assertEqual(tr["integrity"]["primary"], "lost_update")
        self.assertTrue(all(b["blind_write"] for b in tr["behaviors"].values()))

    def test_turn_cap_and_no_finish(self) -> None:
        inst = T.build("counter", 0, 2)
        tr = self.episode(inst, [policy_provider(lambda s, t, m: tool("run_sql", sql="SELECT 1")),
                                 policy_provider(lambda s, t, m: [{"type": "text", "text": "bye"}])])
        a1, a2 = tr["agents"]["agent_1"], tr["agents"]["agent_2"]
        self.assertEqual((a1["end_reason"], a1["tool_calls"], a1["completions"]), ("turn_cap", AG.TURN_CAP, AG.TURN_CAP + 1))
        self.assertEqual((a2["end_reason"], a2["claim"]), ("returned_without_finish", None))

    def test_invalid_finish_then_valid(self) -> None:
        inst = T.build("counter", 0, 1)

        def pol(s, t, m):
            turn = sum(1 for x in m if x["role"] == "assistant")
            return tool("finish", status="maybe") if turn == 0 else tool("finish", status="declined", note="n")

        tr = self.episode(inst, [policy_provider(pol)])
        a = tr["agents"]["agent_1"]
        self.assertEqual((a["claim"], len(a["invalid_calls"]), a["tool_calls"]), ("declined", 1, 0))

    def test_provider_failure_aborts_episode(self) -> None:
        inst = T.build("counter", 0, 2)

        def boom(s, t, m):
            raise RuntimeError("HTTP 500")

        with self.assertRaises(ProviderFailure):
            self.episode(inst, [policy_provider(boom), policy_provider(lambda s, t, m: tool("run_sql", sql="SELECT 1"))])

    def test_budget_exceeded_aborts_episode(self) -> None:
        inst = T.build("counter", 0, 2)
        prices = R.PriceTable({"fake-model": {"input": 1000.0, "output": 1000.0, "confirmed": True}})
        spend = AG.LockedSpend(os.path.join(self.tmp, "spend.jsonl"), 0.01)
        with self.assertRaises(BudgetExceeded):
            self.episode(inst, AG.fake_providers(inst, 0, "t", (0.0, 0.0)), prices=prices, spend=spend)


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def run_main(args: List[str]) -> Tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = R.main(args)
    return code, out.getvalue() + err.getvalue()


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.base = ["--models", f"{HAIKU},{QWEN}", "--tasks", "counter,order", "--variants", "0", "--agents", "2",
                     "--reps", "0", "--out", self.tmp, "--think-ms", "0,5"]

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rows(self, name: str) -> List[Dict[str, str]]:
        with open(os.path.join(self.tmp, "dry_run", name), newline="") as f:
            return list(csv.DictReader(f))

    def test_dry_run_resume_and_restore(self) -> None:
        code, out = run_main(self.base + ["--dry-run", "--max-usd", "5"])
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.rows("results.csv")), 4)
        self.assertEqual(len(self.rows("agents.csv")), 8)
        self.assertEqual(len(os.listdir(os.path.join(self.tmp, "dry_run", "dbs"))), 4)
        code, out = run_main(self.base + ["--dry-run"])
        self.assertIn("to run: 0", out)
        os.remove(os.path.join(self.tmp, "dry_run", "results.csv"))
        os.remove(os.path.join(self.tmp, "dry_run", "agents.csv"))
        code, out = run_main(self.base + ["--dry-run"])
        self.assertEqual((len(self.rows("results.csv")), len(self.rows("agents.csv"))), (4, 8))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "results.csv")), "dry run wrote outside dry_run/")

    def test_cost_cap(self) -> None:
        code, out = run_main(self.base + ["--dry-run", "--max-usd", "0.000001"])
        self.assertEqual(code, 2, out)
        self.assertIn("COST CAP", out)

    def test_refuses_unconfirmed_prices_without_network(self) -> None:
        p = os.path.join(self.tmp, "prices.json")
        with open(p, "w") as f:
            json.dump({"models": {"claude-haiku-4-5": {"input": 1, "output": 5, "confirmed": False}}}, f)
        code, out = run_main(["--models", HAIKU, "--out", self.tmp, "--prices", p])
        self.assertEqual(code, 1)
        self.assertIn("not confirmed", out)

    def test_provider_failures_logged(self) -> None:
        orig = AG.fake_providers

        def failing(inst, rep, eid, think_s=(0, 0), styles=None):
            def boom(s, t, m):
                raise RuntimeError("HTTP 503")
            return [policy_provider(boom) for _ in inst.agents]

        R.AG.fake_providers = failing
        try:
            code, out = run_main(self.base + ["--dry-run"])
        finally:
            R.AG.fake_providers = orig
        self.assertEqual(code, 3, out)
        with open(os.path.join(self.tmp, "dry_run", "failures.jsonl")) as f:
            self.assertEqual(len(f.readlines()), 3)  # stops after 3 consecutive failures

    def test_estimate(self) -> None:
        code, out = run_main(["--models", f"{HAIKU},{QWEN}", "--out", self.tmp, "--estimate"])
        self.assertEqual(code, 0)
        self.assertIn("grid: 128 episodes", out)
        est = R.estimate_cost(R.build_grid([HAIKU, QWEN], T.TEMPLATES, (0, 1), (2, 4), range(4)),
                              R.PriceTable.load(R.DEFAULT_PRICES))
        self.assertGreater(est["total_usd"], 0)
        self.assertLess(est["total_usd"], 5.0)

    def test_grid_is_rep_major_and_sized(self) -> None:
        g = R.build_grid([HAIKU, QWEN], T.TEMPLATES, (0, 1), (2, 4), range(4))
        self.assertEqual(len(g), 128)
        self.assertEqual(len({c["id"] for c in g}), 128)
        self.assertTrue(all(c["rep"] == 0 for c in g[:32]))


# --------------------------------------------------------------------------
# Analysis and the shell guard
# --------------------------------------------------------------------------


class AnalysisTests(unittest.TestCase):
    def test_wilson(self) -> None:
        p, lo, hi = AN.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3)
        self.assertAlmostEqual(hi, 0.7634, places=3)
        p, lo, hi = AN.wilson(0, 10)
        self.assertEqual((p, lo), (0.0, 0.0))
        self.assertAlmostEqual(hi, 0.2775, places=3)
        self.assertEqual(AN.wilson(0, 0), (None, None, None))

    def test_analyze_dry_output(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            code, out = run_main(["--models", HAIKU, "--tasks", "withdraw,handle", "--variants", "0", "--agents", "2,4",
                                  "--reps", "0", "--out", tmp, "--think-ms", "0,5", "--dry-run"])
            self.assertEqual(code, 0, out)
            res = os.path.join(tmp, "dry_run", "results.csv")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(AN.main([res, "--out", os.path.join(tmp, "a")]), 1)  # dry rows dropped by default
                self.assertEqual(AN.main([res, "--out", os.path.join(tmp, "a"), "--include-dry-run"]), 0)
            with open(os.path.join(tmp, "a", "tables.md")) as f:
                md = f.read()
            with open(os.path.join(tmp, "a", "tables_appendix.tex")) as f:
                tex = f.read()
            with open(os.path.join(tmp, "a", "numbers.json")) as f:
                nums = json.load(f)
            self.assertIn("EXPLORATORY", md)
            self.assertIn("DRY RUN", md)
            self.assertIn("EXPLORATORY", tex)
            self.assertIn(f"{HAIKU}|2|all", nums["cells"])
            self.assertEqual(nums["cells"][f"{HAIKU}|4|withdraw"]["episodes"], 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class GuardTests(unittest.TestCase):
    """run_sql.sh --check-only against a throwaway repo layout."""

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "src_sql"))
        shutil.copy(os.path.join(HERE, "run_sql.sh"), os.path.join(self.root, "src_sql", "run_sql.sh"))
        os.makedirs(os.path.join(self.root, "results4", "full"))
        self.log = os.path.join(self.root, "results4", "full", "run.log")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def check(self, env: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
        e = dict(os.environ)
        e.pop("ALLOW_SQL_BEFORE_FULL_DONE", None)
        e.update(env or {})
        p = subprocess.run(["bash", os.path.join(self.root, "src_sql", "run_sql.sh"), "--check-only"],
                           capture_output=True, text=True, env=e, timeout=30)
        return p.returncode, p.stdout + p.stderr

    def test_log_states(self) -> None:
        if subprocess.run(["bash", "-c", "pgrep -f 'run_full[.]sh' || pgrep -f 'src4/run4[.]py'"], capture_output=True).returncode == 0:
            self.skipTest("a real main run is in progress on this machine")
        self.assertEqual(self.check()[0], 0)  # no log: not started
        with open(self.log, "w") as f:
            f.write("=== start Sat\n...\n=== FULL RUN DONE Sat\n=== start Sun\n== phase 1 model x\n[3/10] ...\n")
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("unfinished", out)
        self.assertEqual(self.check({"ALLOW_SQL_BEFORE_FULL_DONE": "1"})[0], 0)
        with open(self.log, "a") as f:
            f.write("!! $330 total cost cap reached in phase 2 (x) - stopping. Completed episodes are kept.\n")
        self.assertEqual(self.check()[0], 0)
        with open(self.log, "a") as f:
            f.write("=== start Mon\n=== phase 3 done\n=== FULL RUN DONE Mon\n")
        self.assertEqual(self.check()[0], 0)

    def test_running_process_blocks(self) -> None:
        fake = os.path.join(self.root, "run_full.sh")
        with open(fake, "w") as f:
            f.write("#!/bin/bash\nsleep 20\n")
        proc = subprocess.Popen(["bash", fake], start_new_session=True, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        try:
            time.sleep(0.3)
            code, out = self.check({"ALLOW_SQL_BEFORE_FULL_DONE": "1"})
            self.assertEqual(code, 1, out)
            self.assertIn("RUNNING", out)
        finally:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)  # the whole group, so no orphaned sleep keeps running
            proc.wait()


if __name__ == "__main__":
    unittest.main()
