"""Tests for the pre-registration changes (``python3 -m unittest tests_full4 -v``).

* sub-label taxonomy of ``non_serializable`` (exclusive, exhaustive, precedence) over every
  episode scored by tests4 and the independent verifier suite, and over a randomized sweep;
* task instances (instances4): determinism, K, pilot disjointness, invariant logic per template;
* the aware prompt axis (exactly one sentence of difference);
* run4 additions (instance axis, CSV schema guard, one cap across spend logs);
* analyze4 on synthetic CSVs (Wilson CI, instance-level aggregation, pairing, permutation test, Holm, exclusions);
* plan_full cost estimates.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from typing import Any, Dict, List

import agents4 as A
import analyze4
import instances4 as I
import model_agent4 as M
import plan_full
import run4
import score4
import tasks4 as T
from scheduler import AgentSpec, ScheduleConfig, ToolCall, run_episode
from score4 import SUB_LABELS, EpisodeScore, primary_label, score_episode, sub_label_rates, non_serializable_rate
from world4 import CONCURRENCY_NOTICE, build_system_prompt, world_config

HERE = os.path.dirname(os.path.abspath(__file__))
VERIFY_DIR = os.environ.get("SRC4_VERIFY_DIR", os.path.join(os.path.dirname(HERE), "src4_verify"))


def quiet(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rv = fn(*a, **kw)
    return rv, buf.getvalue()


def check_labels(tc: unittest.TestCase, s: EpisodeScore, ctx: Any = None) -> None:
    flags = [lab for lab in SUB_LABELS if getattr(s, lab)]
    if s.non_serializable:
        tc.assertEqual(len(flags), 1, ctx)                      # exactly one primary label
        tc.assertEqual(flags[0], s.primary_label, ctx)
    else:
        tc.assertEqual(flags, [], ctx)
        tc.assertIsNone(s.primary_label, ctx)
    tc.assertEqual(s.primary_label, primary_label(s.non_serializable, s.stale_overwrite_seqs, s.partial_commits), ctx)
    if s.primary_label == "stale_overwrite":
        tc.assertTrue(s.stale_overwrite_seqs, ctx)
    if s.primary_label == "partial_action":
        tc.assertFalse(s.stale_overwrite_seqs, ctx)
        tc.assertTrue(s.partial_commits, ctx)
    if s.primary_label == "write_skew":
        tc.assertFalse(s.stale_overwrite_seqs or s.partial_commits, ctx)
    d = s.to_dict()
    tc.assertEqual(d["primary_label"], s.primary_label)
    tc.assertNotIn("lost_update", d)


# --------------------------------------------------------------------------
# 1. Taxonomy
# --------------------------------------------------------------------------


class TaxonomyTest(unittest.TestCase):
    def test_precedence_function(self) -> None:
        self.assertIsNone(primary_label(False, [3], ("a0",)))
        self.assertEqual(primary_label(True, [3], ("a0",)), "stale_overwrite")
        self.assertEqual(primary_label(True, [], ("a0",)), "partial_action")
        self.assertEqual(primary_label(True, [], ()), "write_skew")

    def test_inconsistent_labels_rejected(self) -> None:
        _, ep = None, run_episode(T.inventory_last_unit(2), A.NAIVE, world_config("none"), ScheduleConfig(seed=0, read_write_gap=2))
        s = score_episode(ep)
        kw = {f: getattr(s, f) for f in EpisodeScore.__dataclass_fields__}
        for bad in ({"write_skew": True}, {"stale_overwrite": False}, {"primary_label": "write_skew"},
                    {"non_serializable": False}):
            with self.assertRaises(ValueError, msg=bad):
                EpisodeScore(**{**kw, **bad})

    def test_transfer_credit_after_rejected_debit_is_partial_action(self) -> None:
        """The pilot case: 409 on the debit, credit committed anyway (money created)."""
        task = T.transfer_shared_source(2)
        P, D0, D1 = "account:pool", "account:dest-a0", "account:dest-a1"
        from tests4 import manual
        _, s = manual(task, "cas_available", [
            ("a0", "get_record", {"record_id": P}), ("a1", "get_record", {"record_id": P}),
            ("a1", "get_record", {"record_id": D1}), ("a0", "get_record", {"record_id": D0}),
            ("a1", "update_record", {"record_id": P, "value": "40.00", "expected_version": 1}),
            ("a1", "update_record", {"record_id": D1, "value": "60.00", "expected_version": 1}),
            ("a0", "update_record", {"record_id": P, "value": "40.00", "expected_version": 1}),   # 409
            ("a0", "update_record", {"record_id": D0, "value": "60.00", "expected_version": 1}),  # credit anyway
        ])
        self.assertTrue(s.non_serializable)
        self.assertEqual(s.primary_label, "partial_action")
        self.assertEqual(s.partial_commits, ("a0",))
        self.assertTrue(any("conserved" in v for v in s.invariant_violations))  # invariant_violation is separate
        check_labels(self, s)

    def test_exhaustive_over_existing_test_scenarios(self) -> None:
        """Every EpisodeScore built while running tests4 and the verifier suite gets exactly one label."""
        seen: List[EpisodeScore] = []
        orig = EpisodeScore.__post_init__

        def spy(self_: EpisodeScore) -> None:
            orig(self_)
            seen.append(self_)

        loader = unittest.TestLoader()
        suites = [loader.loadTestsFromName("tests4")]
        if os.path.exists(os.path.join(VERIFY_DIR, "tests_verify.py")):
            sys.path.insert(0, VERIFY_DIR)
            try:
                suites.append(loader.loadTestsFromName("tests_verify"))
            finally:
                sys.path.remove(VERIFY_DIR)
        EpisodeScore.__post_init__ = spy  # type: ignore[method-assign]
        try:
            result = unittest.TestResult()
            unittest.TestSuite(suites).run(result)
        finally:
            EpisodeScore.__post_init__ = orig  # type: ignore[method-assign]
        self.assertEqual(result.errors + result.failures, [], "existing suites must stay green")
        self.assertGreater(len(seen), 1000)
        counts = {lab: 0 for lab in SUB_LABELS}
        for s in seen:
            check_labels(self, s, s.task)
            if s.primary_label:
                counts[s.primary_label] += 1
        for lab in SUB_LABELS:
            self.assertGreater(counts[lab], 0, (lab, counts))

    def test_randomized_sweep_scripted_agents(self) -> None:
        def blind(ctx: Any):
            new = ctx.intent.apply(dict(ctx_initial[0]))
            for r in (new or {}):
                if r.startswith(("seat:", "ticket:")):
                    yield ToolCall("claim", {"record_id": r, "holder": new[r]})
                else:
                    yield ToolCall("update_record", {"record_id": r, "value": str(new[r])})

        def first_leg_only(ctx: Any):
            reads = {}
            for r in ctx.intent.reads:
                reads[r] = (yield ToolCall("get_record", {"record_id": r})).get("value")
            try:
                new = ctx.intent.apply({r: T.coerce_value(T.kind_of(r), v) for r, v in reads.items()})
            except Exception:  # noqa: BLE001
                return
            for r in list(ctx.intent.writes)[:1]:
                if new and r in new and not r.startswith(("seat:", "ticket:")):
                    yield ToolCall("update_record", {"record_id": r, "value": str(new[r])})

        ctx_initial: List[Any] = [None]
        policies = [A.NAIVE, A.REREADER, A.CAREFUL_CAS, A.GIVE_UP_ON_CONFLICT, A.LOCK_USER,
                    A.lock_user(lease_steps=1, ordered=False), A.MESSENGER, A.LOCK_LEAKER,
                    AgentSpec("blind", blind)] + [AgentSpec("first_leg_only", first_leg_only)] * 3
        configs = ["none", "reread_only", "cas_available", "cas_required", "locks", "messages", "cas_available+locks+messages"]
        rng = random.Random(20261031)
        counts = {lab: 0 for lab in SUB_LABELS}
        n_eps = 0
        for _ in range(500):
            n = rng.choice((2, 2, 3, 4))
            if rng.random() < 0.15:
                task = rng.choice((T.transfer_shared_source, T.transfer_opposite))(n)
            elif rng.random() < 0.5:
                task = rng.choice(list(T.CATALOG.values()))(n)
            else:
                task = I.build(rng.choice(I.TEMPLATES), rng.randrange(4), n)
            ctx_initial[0] = task.initial
            cfg = rng.choice(configs)
            wc = world_config(cfg)
            specs = {}
            for a in task.agent_ids:
                spec = rng.choice(policies)
                specs[a] = spec if spec.supported_by(wc.coordination) else A.NAIVE
            sched = ScheduleConfig(seed=rng.randrange(10**6), read_write_gap=rng.choice((0, 1, 2, 3)),
                                   start_jitter=rng.choice((0, 2)), turn_cap=60)
            s = score_episode(run_episode(task, specs, wc, sched))
            check_labels(self, s, (task.name, cfg, {a: sp.name for a, sp in specs.items()}))
            n_eps += 1
            if s.primary_label:
                counts[s.primary_label] += 1
        self.assertEqual(n_eps, 500)
        for lab in SUB_LABELS:
            self.assertGreater(counts[lab], 5, counts)

    def test_sub_label_rates_sum_to_non_serializable_rate(self) -> None:
        eps = [score_episode(run_episode(f(2), A.NAIVE, world_config("none"), ScheduleConfig(seed=s, read_write_gap=2)))
               for f in (T.inventory_last_unit, T.budget_write_skew, T.transfer_shared_source, T.budget_control) for s in range(3)]
        rates = sub_label_rates(eps)
        self.assertEqual(sum(r.numerator for r in rates.values()), non_serializable_rate(eps).numerator)
        self.assertEqual({r.denominator for r in rates.values()}, {len(eps)})


# --------------------------------------------------------------------------
# 2. Instances
# --------------------------------------------------------------------------


class InstancesTest(unittest.TestCase):
    def test_k_and_names(self) -> None:
        for t in I.TEMPLATES:
            insts = I.instances(t)
            self.assertEqual(len(insts), I.DEFAULT_K)
            self.assertEqual(len({x.name for x in insts}), I.DEFAULT_K)
            self.assertEqual(len({I.fingerprint(x) for x in insts}), I.DEFAULT_K, t)  # distinct parameters

    def test_disjoint_from_pilot(self) -> None:
        self.assertNotIn("pilot", I.FULL_SPACE)
        for t in I.TEMPLATES:
            pilot = I.pilot_task(t, 2)
            pilot_records = set(pilot.initial)
            for i in range(8):  # well beyond K
                inst = I.build(t, i, 2)
                self.assertNotEqual(I.fingerprint(inst), I.fingerprint(pilot), (t, i))
                self.assertFalse(pilot_records & set(inst.initial), (t, i))  # no shared record name either
                self.assertNotEqual(inst.name, pilot.name)

    def test_deterministic_across_processes(self) -> None:
        code = ("import sys; sys.path.insert(0, %r); import instances4 as I, json\n"
                "print(json.dumps([I.describe_instance(I.build(t, i, n)) for t in I.TEMPLATES for i in range(4) for n in (2, 8)], sort_keys=True))") % HERE
        outs = set()
        for h in ("0", "1", "999"):
            p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                               env=dict(os.environ, PYTHONHASHSEED=h), timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr)
            outs.add(p.stdout)
        self.assertEqual(len(outs), 1)

    def test_wordings_two_paraphrases_text_only(self) -> None:
        for t in I.TEMPLATES:
            insts = I.instances(t)
            self.assertEqual([next(iter(x.intents.values())).wording for x in insts], [0, 1, 0, 1])
            for inst in insts:
                for a, intent in inst.intents.items():
                    other = type(intent)(**{**vars(intent), "wording": 1 - intent.wording})
                    self.assertNotEqual(intent.describe(), other.describe(), t)
                    for rid in intent.reads:          # every record named in both wordings
                        self.assertIn(rid, other.describe())
                    self.assertEqual(intent.apply(inst.initial), other.apply(inst.initial))
            # pilot wording unchanged
            self.assertEqual(next(iter(I.pilot_task(t, 2).intents.values())).wording, 0)

    def test_same_invariant_logic_as_template(self) -> None:
        strip = lambda name: name.split("[")[0]  # noqa: E731
        for t in I.TEMPLATES:
            for n in (2, 4, 8):
                pilot = I.pilot_task(t, n)
                for i in range(4):
                    inst = I.build(t, i, n)
                    self.assertEqual((inst.category, inst.kind), (pilot.category, pilot.kind))
                    self.assertEqual(sorted(strip(v.name) for v in inst.invariants), sorted(strip(v.name) for v in pilot.invariants))
                    self.assertEqual({type(x).__name__ for x in inst.intents.values()}, {type(x).__name__ for x in pilot.intents.values()})
                    self.assertEqual(inst.agent_ids, pilot.agent_ids)
                    ctx = (t, i, n)
                    if inst.category == "conflict":
                        self.assertFalse(inst.serially_valid_for_all(), ctx)
                    else:
                        self.assertEqual(inst.serially_valid_for_all(), inst.category in ("still_valid", "control"), ctx)
                    for intent in inst.intents.values():
                        self.assertTrue(intent.is_valid(inst.initial), ctx)  # every agent can act alone
                    if t in ("inventory_last_unit", "transfer_shared_source", "budget_write_skew"):
                        a0, a1 = inst.agent_ids[:2]  # exactly one fits
                        after = {**inst.initial, **inst.intents[a0].apply(inst.initial)}
                        self.assertFalse(inst.intents[a1].is_valid(after), ctx)

    def test_n_scaling_keeps_parameters(self) -> None:
        for t in I.TEMPLATES:
            for i in range(4):
                a, b = I.build(t, i, 2), I.build(t, i, 8)
                self.assertEqual(a.intents["a0"].describe().replace("a1", "X").split()[0], b.intents["a0"].describe().split()[0])
                shared = set(a.initial) & set(b.initial)
                self.assertTrue(shared, (t, i))

    def test_scripted_agents_behave_as_on_catalog(self) -> None:
        for i in range(4):
            for t in ("inventory_last_unit", "seat_same", "ticket_same", "transfer_shared_source"):
                _, s = None, score_episode(run_episode(I.build(t, i, 2), A.CAREFUL_CAS, world_config("cas_available"), ScheduleConfig(seed=0, read_write_gap=2)))
                self.assertFalse(s.non_serializable or s.invariant_violation, (t, i))
            for t in ("budget_write_skew", "joint_account_write_skew"):
                s = score_episode(run_episode(I.build(t, i, 2), A.CAREFUL_CAS, world_config("cas_available"), ScheduleConfig(seed=0, read_write_gap=2)))
                self.assertEqual(s.primary_label, "write_skew", (t, i))
                self.assertTrue(s.invariant_violation)
            s = score_episode(run_episode(I.build("inventory_last_unit", i, 2), A.NAIVE, world_config("none"), ScheduleConfig(seed=0, read_write_gap=2)))
            self.assertEqual(s.primary_label, "stale_overwrite")

    def test_instance_file_cli(self) -> None:
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "inst.json")
            quiet(lambda: sys.argv.__setitem__(slice(None), ["instances4", "--write", path]) or I.main())
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(len(data["instances"]), 8 * 4 * 3)
        finally:
            shutil.rmtree(d)


# --------------------------------------------------------------------------
# 3. Aware axis
# --------------------------------------------------------------------------


class AwareAxisTest(unittest.TestCase):
    def test_exactly_one_sentence_differs(self) -> None:
        self.assertEqual(CONCURRENCY_NOTICE.count("."), 1)
        self.assertTrue(CONCURRENCY_NOTICE.endswith("."))
        self.assertIn("same records at the same time", CONCURRENCY_NOTICE)
        for cfg in ("none", "locks", "messages", "cas_available+locks+messages"):
            off = build_system_prompt("a0", ["a1"], "Task text.", world_config(cfg))
            on = build_system_prompt("a0", ["a1"], "Task text.", world_config(cfg, concurrency_aware_prompt=True))
            self.assertEqual(on, off + "\n" + CONCURRENCY_NOTICE)

    def test_grid_axis_and_transcripts(self) -> None:
        g = run4.build_grid(["m"], ["none", "locks"], ["seat_same"], [0], 2, [False, True], 2)
        self.assertEqual(len(g), 2 * 2 * 2)
        self.assertEqual(len({c["id"] for c in g}), 8)
        d = tempfile.mkdtemp()
        try:
            code, log = quiet(run4.run_grid, ["--models", "fake-model", "--configs", "locks", "--tasks", "seat_same,budget_write_skew",
                                              "--instances", "2", "--aware", "both", "--seeds", "0", "--out", d, "--dry-run"])
            self.assertEqual(code, 0, log)
            tdir = os.path.join(d, "dry_run", "transcripts")
            by: Dict[str, Dict[bool, Dict[str, Any]]] = {}
            for fn in os.listdir(tdir):
                with open(os.path.join(tdir, fn)) as f:
                    tr = json.load(f)
                by.setdefault(f"{tr['task']['name']}", {})[tr["concurrency_aware_prompt"]] = tr
            self.assertEqual(len(by), 4)
            for pair in by.values():
                for a in pair[False]["agents"]:
                    self.assertEqual(pair[True]["agents"][a]["system"], pair[False]["agents"][a]["system"] + "\n" + CONCURRENCY_NOTICE)
        finally:
            shutil.rmtree(d)


# --------------------------------------------------------------------------
# run4 additions
# --------------------------------------------------------------------------


class Run4AdditionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.dir)

    def test_instances_run_and_csv_columns(self) -> None:
        out = os.path.join(self.dir, "o")
        code, log = quiet(run4.run_grid, ["--models", "fake-model", "--configs", "none,cas_available", "--tasks", "pilot",
                                          "--instances", "4", "--seeds", "0", "--out", out, "--dry-run"])
        self.assertEqual(code, 0, log)
        with open(os.path.join(out, "dry_run", "results.csv"), newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2 * 8 * 4)
        self.assertEqual(list(rows[0]), run4.CSV_FIELDS)
        self.assertNotIn("lost_update", run4.CSV_FIELDS)
        self.assertEqual({r["instance"] for r in rows}, {"0", "1", "2", "3"})
        self.assertEqual({r["wording"] for r in rows}, {"0", "1"})
        for r in rows:
            labels = [lab for lab in SUB_LABELS if r[lab] == "1"]
            self.assertEqual(labels, [r["primary_label"]] if r["non_serializable"] == "1" else [])
        # the dry-run policy understands both wordings: every template commits at least one write in each wording
        committed = {(r["task"], r["wording"]) for r in rows if int(r["n_committed"]) > 0}
        self.assertEqual(len(committed), 16)

    def test_refuses_legacy_csv_header(self) -> None:
        out = os.path.join(self.dir, "legacy")
        os.makedirs(os.path.join(out, "dry_run"))
        with open(os.path.join(out, "dry_run", "results.csv"), "w") as f:
            f.write("episode_id,lost_update\nx,1\n")
        code, log = quiet(run4.run_grid, ["--models", "fake-model", "--tasks", "seat_same", "--out", out, "--dry-run"])
        self.assertEqual(code, 1)
        self.assertIn("different header", log)

    def test_extra_spend_logs_share_one_cap(self) -> None:
        other = os.path.join(self.dir, "other", "spend.jsonl")
        os.makedirs(os.path.dirname(other))
        with open(other, "w") as f:
            f.write(json.dumps({"cost_usd": 0.95}) + "\n")
        prices = os.path.join(self.dir, "p.json")
        with open(prices, "w") as f:
            json.dump({"models": {"fake-model": {"input": 1.0, "output": 5.0, "confirmed": True}}}, f)
        args = ["--models", "fake-model", "--configs", "none", "--tasks", "seat_same", "--instances", "4", "--seeds", "0,1",
                "--out", os.path.join(self.dir, "o"), "--dry-run", "--prices", prices, "--max-usd", "1.0",
                "--prior-input-tokens", "1", "--max-tokens", "1"]
        code, log = quiet(run4.run_grid, args)
        code2, log2 = quiet(run4.run_grid, args + ["--extra-spend-logs", other])
        self.assertEqual(code, 0, log)
        self.assertEqual(code2, 0, log2)  # finished already
        args3 = [x if x != os.path.join(self.dir, "o") else os.path.join(self.dir, "o2") for x in args]
        args3[args3.index("--max-usd") + 1] = "0.951"
        code3, log3 = quiet(run4.run_grid, args3 + ["--extra-spend-logs", other])
        self.assertEqual(code3, 2, log3)
        self.assertIn("counted toward the cap: $0.9500", log3)
        # every written episode finished under the shared cap; at most the one aborted episode's calls overshoot
        tdir = os.path.join(self.dir, "o2", "dry_run", "transcripts")
        written = 0.0
        for fn in os.listdir(tdir):
            with open(os.path.join(tdir, fn)) as f:
                written += json.load(f)["totals"]["cost_usd"]
        self.assertLessEqual(written + 0.95, 0.951 + 1e-9)
        self.assertLess(len(os.listdir(tdir)), 8)


# --------------------------------------------------------------------------
# 4. analyze4
# --------------------------------------------------------------------------


def _row(**kw: Any) -> Dict[str, Any]:
    base = {f: "" for f in run4.CSV_FIELDS}
    base.update({"model": "m", "config": "none", "aware_prompt": 0, "task": "inventory_last_unit", "instance": 0, "wording": 0,
                 "category": "conflict", "kind": "inventory", "n_agents": 2, "seed": 0, "non_serializable": 0, "primary_label": "",
                 "stale_overwrite": 0, "partial_action": 0, "write_skew": 0, "invariant_violation": 0,
                 "choices": "a0:none;a1:none", "n_abandoned": 0, "n_abandon_eligible": 2, "n_unnecessary_give_up": 0,
                 "n_conflict_agents": 0, "dry_run": 0})
    base.update(kw)
    lab = base["primary_label"]
    if lab:
        base["non_serializable"] = 1
        base[lab] = 1
    base["episode_id"] = base.get("episode_id") or "|".join(str(base[k]) for k in ("model", "config", "aware_prompt", "task", "instance", "n_agents", "seed"))
    return base


def _write_csv(path: str, rows: List[Dict[str, Any]], fields: List[str] = run4.CSV_FIELDS) -> str:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


class AnalyzeStatsTest(unittest.TestCase):
    def test_wilson_known_values(self) -> None:
        lo, hi = analyze4.wilson(0.5, 10)
        self.assertAlmostEqual(lo, 0.236593, places=5)
        self.assertAlmostEqual(hi, 0.763407, places=5)
        lo, hi = analyze4.wilson(0.0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.277530, places=5)
        lo, hi = analyze4.wilson(1.0, 28)
        self.assertAlmostEqual(lo, 1 - analyze4.wilson(0.0, 28)[1], places=12)
        self.assertAlmostEqual(hi, 1.0, places=12)
        with self.assertRaises(ValueError):
            analyze4.wilson(0.5, 0)

    def test_holm(self) -> None:
        self.assertEqual([round(x, 10) for x in analyze4.holm([0.01, 0.04, 0.03, 0.005])], [0.03, 0.06, 0.06, 0.02])
        self.assertEqual(analyze4.holm([0.5, None, 0.01]), [0.5, None, 0.02])
        self.assertEqual(analyze4.holm([0.6, 0.7]), [1.0, 1.0])  # capped and monotone
        self.assertEqual(analyze4.holm([]), [])

    def test_sign_flip_exact_and_monte_carlo(self) -> None:
        t = analyze4.sign_flip_test([1.0, 1.0, 1.0])
        self.assertEqual((t["p_two_sided"], t["p_greater"], t["p_less"], t["method"]), (0.25, 0.125, 1.0, "exact"))
        t = analyze4.sign_flip_test([0.5, 0.0, -0.5, 0.0])
        self.assertEqual(t["mean"], 0.0)
        self.assertEqual(t["p_two_sided"], 1.0)
        self.assertEqual(analyze4.sign_flip_test([0.0, 0.0])["p_two_sided"], 1.0)
        self.assertIsNone(analyze4.sign_flip_test([])["p_two_sided"])
        diffs = [1.0] * 20
        mc = analyze4.sign_flip_test(diffs, key="k")
        self.assertEqual(mc["method"], "monte_carlo")
        self.assertAlmostEqual(mc["p_greater"], 1 / (analyze4.N_PERM + 1) * (1 + mc["p_greater"] * 0), delta=5e-4)
        self.assertEqual(mc, analyze4.sign_flip_test(diffs, key="k"))  # deterministic


class AnalyzePipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.dir)

    def run_analyze(self, paths: List[str], *extra: str) -> Dict[str, Any]:
        out = os.path.join(self.dir, "analysis")
        code, log = quiet(analyze4.main, list(paths) + ["--out", out, *extra])
        self.assertEqual(code, 0, log)
        with open(os.path.join(out, "numbers.json")) as f:
            numbers = json.load(f)
        with open(os.path.join(out, "tables.md")) as f:
            self.assertIn("## Exclusions", f.read())
        return numbers

    @staticmethod
    def rate(numbers, metric, scope="contended", **cell):
        hits = [r for r in numbers["rates"] if r["metric"] == metric and r["scope"] == scope
                and all(r[k] == v for k, v in cell.items())]
        assert len(hits) == 1, (metric, cell, hits)
        return hits[0]

    def test_instance_level_aggregation_and_ci(self) -> None:
        rows = [
            _row(instance=0, seed=0, primary_label="stale_overwrite"), _row(instance=0, seed=1),   # instance rate 0.5
            _row(instance=1, seed=0, primary_label="write_skew"),                                  # 1.0 (one seed only)
            _row(instance=2, seed=0), _row(instance=2, seed=1),                                    # 0.0
            _row(task="budget_control", category="control", instance=0, seed=0, primary_label="write_skew"),
        ]
        n = self.run_analyze([_write_csv(os.path.join(self.dir, "r.csv"), rows)])
        r = self.rate(n, "non_serializable", model="m", config="none", aware=0, n_agents=2)
        self.assertEqual((r["numerator"], r["denominator"], r["n_instances"]), (2, 5, 3))
        self.assertAlmostEqual(r["estimate"], 0.5)          # mean of instance rates, not pooled 2/5
        lo, hi = analyze4.wilson(0.5, 3)
        self.assertAlmostEqual(r["ci_low"], lo)
        self.assertAlmostEqual(r["ci_high"], hi)
        self.assertAlmostEqual(self.rate(n, "stale_overwrite", model="m")["estimate"], 0.5 / 3)
        self.assertAlmostEqual(self.rate(n, "write_skew", model="m")["estimate"], 1 / 3)
        self.assertEqual(self.rate(n, "partial_action", model="m")["numerator"], 0)
        all_scope = self.rate(n, "non_serializable", scope="all", model="m")
        self.assertEqual((all_scope["n_instances"], all_scope["numerator"]), (4, 3))  # control instance is its own unit

    def test_agent_level_rates(self) -> None:
        rows = [
            _row(instance=0, seed=0, choices="a0:cas|reread;a1:none", n_conflict_agents=2, n_unnecessary_give_up=1,
                 n_abandon_eligible=1, n_abandoned=1),
            _row(instance=0, seed=1, choices="a0:lock;a1:lock", n_conflict_agents=0, n_abandon_eligible=2),
            _row(instance=1, seed=0, choices="a0:message;a1:none", n_conflict_agents=1, n_unnecessary_give_up=0),
        ]
        n = self.run_analyze([_write_csv(os.path.join(self.dir, "r.csv"), rows)])
        self.assertAlmostEqual(self.rate(n, "cas", model="m")["estimate"], (1 / 4 + 0) / 2)
        self.assertAlmostEqual(self.rate(n, "none", model="m")["estimate"], (1 / 4 + 1 / 2) / 2)
        self.assertAlmostEqual(self.rate(n, "lock", model="m")["estimate"], (2 / 4 + 0) / 2)
        ug = self.rate(n, "unnecessary_give_up", model="m")
        self.assertEqual((ug["numerator"], ug["denominator"]), (1, 3))
        self.assertAlmostEqual(ug["estimate"], (1 / 2 + 0 / 1) / 2)
        ab = self.rate(n, "abandoned", model="m")
        self.assertAlmostEqual(ab["estimate"], (1 / 3 + 0 / 2) / 2)

    def test_pairing_permutation_and_holm(self) -> None:
        rows = []
        for model in ("m1", "m2"):
            for i in range(5):
                for seed in (0, 1):
                    rows.append(_row(model=model, config="none", aware_prompt=0, instance=i, seed=seed, primary_label="stale_overwrite"))
                    on_label = "" if (model == "m1" or i < 2) else "stale_overwrite"
                    rows.append(_row(model=model, config="none", aware_prompt=1, instance=i, seed=seed, primary_label=on_label))
                    rows.append(_row(model=model, config="cas_available", aware_prompt=0, instance=i, seed=seed))
        rows.append(_row(model="m1", config="none", aware_prompt=1, instance=0, seed=7))  # unpaired seed: dropped
        n = self.run_analyze([_write_csv(os.path.join(self.dir, "r.csv"), rows)])
        comps = [c for c in n["comparisons"] if c["metric"] == "non_serializable"]
        aw = {c["model"]: c for c in comps if c["comparison"] == "aware"}
        self.assertEqual(aw["m1"]["n_instances"], 5)
        self.assertEqual(aw["m1"]["n_paired_episodes"], 10)
        self.assertEqual(aw["m1"]["n_unpaired_episodes"], 1)
        self.assertAlmostEqual(aw["m1"]["mean_diff"], -1.0)
        self.assertAlmostEqual(aw["m1"]["p_two_sided"], 2 / 32)
        self.assertAlmostEqual(aw["m1"]["p_less"], 1 / 32)
        self.assertAlmostEqual(aw["m2"]["mean_diff"], -2 / 5)
        self.assertAlmostEqual(aw["m2"]["p_two_sided"], 2 / 4)       # 2 non-zero diffs: exact over 4 sign vectors
        self.assertEqual(aw["m1"]["family"], "aware|non_serializable|n2")
        self.assertEqual(aw["m1"]["family_size"], 2)
        adj = analyze4.holm([aw["m1"]["p_two_sided"], aw["m2"]["p_two_sided"]])
        self.assertAlmostEqual(aw["m1"]["p_holm"], adj[0])
        self.assertAlmostEqual(aw["m2"]["p_holm"], adj[1])
        cfg = [c for c in comps if c["comparison"] == "config"]
        self.assertEqual({(c["model"], c["treatment"], c["aware"]) for c in cfg}, {("m1", "cas_available", 0), ("m2", "cas_available", 0)})
        for c in cfg:
            self.assertAlmostEqual(c["mean_diff"], -1.0)
            self.assertEqual(c["family_size"], 2)

    def test_exclusions_and_legacy_alias(self) -> None:
        d1 = os.path.join(self.dir, "p1")
        os.makedirs(d1)
        rows = [_row(instance=0, seed=0, primary_label="partial_action"), _row(instance=1, seed=0, dry_run=1),
                _row(instance="pilot", seed=0), _row(instance=0, seed=0, primary_label="partial_action")]  # duplicate id
        p1 = _write_csv(os.path.join(d1, "results.csv"), rows)
        with open(os.path.join(d1, "failures.jsonl"), "w") as f:
            f.write(json.dumps({"episode_id": rows[0]["episode_id"], "error": "503"}) + "\n")   # recovered later
            f.write(json.dumps({"episode_id": "never-finished", "error": "503"}) + "\n")
        legacy_fields = ["episode_id", "model", "config", "aware_prompt", "task", "category", "kind", "n_agents", "seed",
                         "lost_update", "graph_cycle", "stale_overwrite", "write_skew", "invariant_violation", "choices",
                         "n_abandoned", "n_unnecessary_give_up", "dry_run"]
        legacy = [{"episode_id": f"L{k}", "model": "old", "config": "none", "aware_prompt": 0, "task": "seat_same",
                   "category": "conflict", "kind": "seat", "n_agents": 2, "seed": k, "lost_update": lu, "graph_cycle": lu,
                   "stale_overwrite": so, "write_skew": ws, "invariant_violation": 0, "choices": "a0:none;a1:none",
                   "n_abandoned": 0, "n_unnecessary_give_up": 0, "dry_run": 0}
                  for k, (lu, so, ws) in enumerate([(1, 1, 0), (1, 0, 1), (1, 0, 0), (0, 1, 0)])]
        p2 = _write_csv(os.path.join(self.dir, "legacy.csv"), legacy, legacy_fields)
        n = self.run_analyze([p1, p2])
        ex = n["exclusions"]
        self.assertEqual((ex["rows_read"], ex["dry_run"], ex["pilot_instance"], ex["duplicate_episode_id"]), (8, 1, 5, 1))
        self.assertEqual((ex["provider_failure_missing"], ex["provider_failure_recovered"]), (1, 1))
        self.assertEqual(n["meta"]["n_rows_analyzed"], 1)
        n = self.run_analyze([p2], "--include-pilot")
        self.assertEqual(n["exclusions"]["legacy_schema_rows"], 4)
        get = lambda m: self.rate(n, m, model="old")["numerator"]  # noqa: E731
        self.assertEqual((get("non_serializable"), get("stale_overwrite"), get("write_skew"), get("partial_action")), (3, 1, 1, 1))
        self.assertEqual(self.rate(n, "unnecessary_give_up", model="old")["n_instances"], 0)  # denominators unknown in legacy rows

    def test_real_dry_run_csv_end_to_end(self) -> None:
        out = os.path.join(self.dir, "o")
        quiet(run4.run_grid, ["--models", "fake-model", "--configs", "none,cas_available", "--tasks", "pilot", "--instances", "2",
                              "--aware", "both", "--seeds", "0,1", "--out", out, "--dry-run"])
        csv_path = os.path.join(out, "dry_run", "results.csv")
        n = self.run_analyze([csv_path])
        self.assertEqual(n["exclusions"]["dry_run"], 2 * 8 * 2 * 2 * 2)   # dry runs are excluded by rule
        with open(csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["dry_run"] = "0"
        n = self.run_analyze([_write_csv(os.path.join(self.dir, "as_real.csv"), rows)])
        self.assertEqual(n["meta"]["n_rows_analyzed"], 128)
        cell = self.rate(n, "non_serializable", model="fake-model", config="none", aware=0, n_agents=2)
        self.assertEqual(cell["n_instances"], 14)
        kinds = {(c["comparison"], c["metric"]) for c in n["comparisons"]}
        self.assertIn(("aware", "lock"), kinds)
        self.assertIn(("config", "stale_overwrite"), kinds)


# --------------------------------------------------------------------------
# plan_full
# --------------------------------------------------------------------------


class PlanFullTest(unittest.TestCase):
    def test_episode_estimates(self) -> None:
        e = plan_full.episode_estimate
        self.assertAlmostEqual(e("claude-haiku-4-5-20251001", 2), 0.0098)
        self.assertAlmostEqual(e("openrouter:qwen/qwen3.6-27b-20260422", 2), 0.0047)
        self.assertAlmostEqual(e("claude-sonnet-5", 2), 2 * 0.0098)
        self.assertAlmostEqual(e("claude-fable-5", 2), 10 * 0.0098)
        self.assertAlmostEqual(e("openrouter:openai/gpt-5.5-20260423", 2), 3 * 0.0098)
        self.assertAlmostEqual(e("openrouter:google/gemini-4-argon-20261013", 2), 3 * 0.0098)
        self.assertAlmostEqual(e("claude-haiku-4-5-20251001", 4), 0.0098 * 2 * 1.1)
        self.assertAlmostEqual(e("claude-haiku-4-5-20251001", 8), 0.0098 * 4 * 1.1 ** 2)

    def test_budget_gate(self) -> None:
        d = tempfile.mkdtemp()
        try:
            log = os.path.join(d, "spend.jsonl")
            with open(log, "w") as f:
                f.write(json.dumps({"cost_usd": 9.0}) + "\n")
            base = ["--phase", "2", "--models", "claude-haiku-4-5-20251001", "--configs", "none,cas_available,locks", "--aware", "both",
                    "--instances", "2", "--seeds", "0", "--agents", "4", "--out", os.path.join(d, "p2")]
            code, out = quiet(plan_full.main, base + ["--max-usd", "20", "--spend-logs", log])
            self.assertEqual(code, 0, out)
            self.assertIn("96 episodes", out)
            code, out = quiet(plan_full.main, base + ["--max-usd", "10", "--spend-logs", log])
            self.assertEqual(code, 5, out)
            self.assertIn("SKIPPING phase 2", out)
        finally:
            shutil.rmtree(d)


# --------------------------------------------------------------------------
# 5. analyze4.confirmatory (pre-registered tests) and model-id price matching
# --------------------------------------------------------------------------


def _norm(**kw: Any) -> Dict[str, Any]:
    r = analyze4.normalize_row({k: str(v) for k, v in _row(**kw).items()})
    r["source"] = "nowhere/results.csv"
    return r


def _full_grid(models, label_fn=lambda m, cfg, aware, task, i, n, s: "", choice_fn=lambda m, cfg, aware, task, i, n, s: "a0:none;a1:none"):
    """Every registered confirmatory episode for ``models`` (phase 1 + phases 2-3, n2 counterparts in phase 1)."""
    rows = []
    for m in models:
        for task in analyze4.CONTENDED_TEMPLATES + ("budget_control",):
            cat = "control" if task == "budget_control" else "conflict"
            for cfg in ("none", "reread_only", "cas_available", "cas_required", "locks", "messages"):
                for aware in (0, 1):
                    for i in range(4):
                        for s in (0, 1):
                            rows.append(_norm(model=m, config=cfg, aware_prompt=aware, task=task, category=cat, instance=i, seed=s,
                                              primary_label=label_fn(m, cfg, aware, task, i, 2, s),
                                              choices=choice_fn(m, cfg, aware, task, i, 2, s)))
            for n in (4, 8):
                for cfg in ("none", "cas_available", "locks"):
                    for aware in (0, 1):
                        for i in range(2):
                            rows.append(_norm(model=m, config=cfg, aware_prompt=aware, task=task, category=cat, instance=i, seed=0,
                                              n_agents=n, primary_label=label_fn(m, cfg, aware, task, i, n, 0),
                                              choices=";".join(f"a{k}:none" for k in range(n))))
    return rows


class ConfirmatoryStatsTest(unittest.TestCase):
    def test_bootstrap_deterministic_and_p_formula(self) -> None:
        vals = [0.0, 0.5, 1.0, 1.0, 0.5, 1.0, 0.5, 1.0]
        a = analyze4.cluster_bootstrap(vals, 0.5, "greater", "k", n_boot=2000)
        b = analyze4.cluster_bootstrap(vals, 0.5, "greater", "k", n_boot=2000)
        self.assertEqual(a, b)
        self.assertNotEqual(a["p_bootstrap"], analyze4.cluster_bootstrap(vals, 0.5, "greater", "other", n_boot=2000)["p_bootstrap"])
        # reproduce the registered p-value formula from the same RNG stream
        rng = random.Random(f"{analyze4.BOOT_SEED}|k")
        stats = [sum(rng.choices(vals, k=len(vals))) / len(vals) for _ in range(2000)]
        self.assertAlmostEqual(a["p_bootstrap"], (1 + sum(t <= 0.5 + 1e-12 for t in stats)) / 2001)
        self.assertEqual(a["method"], "bootstrap")
        self.assertAlmostEqual(a["estimate"], sum(vals) / 8)
        self.assertLessEqual(a["ci_low"], a["estimate"])
        self.assertGreaterEqual(a["ci_high"], a["estimate"])
        less = analyze4.cluster_bootstrap(vals, 0.9, "less", "k", n_boot=2000)
        rng = random.Random(f"{analyze4.BOOT_SEED}|k")
        stats = [sum(rng.choices(vals, k=len(vals))) / len(vals) for _ in range(2000)]
        self.assertAlmostEqual(less["p_bootstrap"], (1 + sum(t >= 0.9 - 1e-12 for t in stats)) / 2001)

    def test_degenerate_rates_use_exact_sign_test(self) -> None:
        t = analyze4.cluster_bootstrap([1.0] * 28, 0.5, "greater", "x", n_boot=500)
        self.assertTrue(t["degenerate"])
        self.assertEqual(t["method"], "sign_test")
        self.assertAlmostEqual(t["p"], 0.5 ** 28)
        self.assertAlmostEqual(t["p_bootstrap"], 1 / 501)        # reported, not used
        t = analyze4.cluster_bootstrap([0.0] * 28, 0.25, "less", "x", n_boot=500)
        self.assertEqual((t["method"], t["sign_k"], t["sign_n"]), ("sign_test", 28, 28))
        t = analyze4.cluster_bootstrap([0.5] * 10, 0.5, "greater", "x", n_boot=500)   # all ties: no evidence
        self.assertEqual((t["p"], t["sign_n"]), (1.0, 0))
        t = analyze4.cluster_bootstrap([0.0] * 14, 0.0, "greater", "x", n_boot=500)   # zero slope everywhere
        self.assertEqual(t["p"], 1.0)
        self.assertAlmostEqual(analyze4.binom_sign_p(7, 8), 9 / 256)
        self.assertEqual(analyze4.binom_sign_p(0, 0), 1.0)
        self.assertIsNone(analyze4.cluster_bootstrap([], 0.5, "greater", "x")["p"])

    def test_episode_id_parse_matches_run4(self) -> None:
        eid = run4.episode_id("openrouter:qwen/qwen3.6-27b-20260422", "cas_available", True, "seat_same", 4, 0, 1)
        self.assertEqual(analyze4.parse_episode_id(eid),
                         (run4.safe_name("openrouter:qwen/qwen3.6-27b-20260422"), "cas_available", 1, "seat_same", "1", 4, 0))
        self.assertIsNone(analyze4.parse_episode_id(run4.episode_id("m", "none", False, "seat_same", 2, 0)))  # pilot id


class ConfirmatoryDecisionTest(unittest.TestCase):
    M6 = tuple(f"m{k}" for k in range(6))

    def conf(self, rows, models=None, **kw):
        return analyze4.confirmatory(rows, h5=[], models=models or self.M6, n_boot=400, **kw)

    def test_registered_cluster_counts_and_h1_all_models(self) -> None:
        rows = _full_grid(self.M6, label_fn=lambda m, cfg, a, t, i, n, s: "stale_overwrite" if cfg == "none" else "")
        c = self.conf(rows)
        counts = {h: c["hypotheses"][h]["tests"][0]["n_registered_clusters"] for h in analyze4.HYPOTHESES}
        self.assertEqual(counts, {"H1": 28, "H2": 28, "H3": 28, "H4a": 16, "H4b": 8, "H6": 14})
        h1 = c["hypotheses"]["H1"]
        self.assertEqual(h1["verdict"], "supported")
        self.assertEqual(h1["family_size"], 6)
        for t in h1["tests"]:
            self.assertEqual(t["method"], "sign_test")              # rate 1: degenerate -> exact sign test
            self.assertAlmostEqual(t["p"], 0.5 ** 28)
            self.assertTrue(t["reject"])
        self.assertEqual(c["hypotheses"]["H4a"]["verdict"], "supported for 6 of 6 models")
        # control template never enters a contended denominator: flip only budget_control and nothing changes
        rows2 = _full_grid(self.M6, label_fn=lambda m, cfg, a, t, i, n, s: "stale_overwrite" if cfg == "none" or t == "budget_control" else "")
        c2 = self.conf(rows2)
        for h in analyze4.HYPOTHESES:
            self.assertEqual([t["p"] for t in c["hypotheses"][h]["tests"]], [t["p"] for t in c2["hypotheses"][h]["tests"]], h)

    def test_h1_fails_if_one_model_does_not_reject(self) -> None:
        rows = _full_grid(self.M6, label_fn=lambda m, cfg, a, t, i, n, s: "stale_overwrite" if cfg == "none" and (m != "m5" or s == 0) else "")
        h1 = self.conf(rows)["hypotheses"]["H1"]
        self.assertEqual(h1["verdict"], "not supported")
        self.assertEqual(h1["rejecting_models"], list(self.M6[:5]))
        m5 = h1["tests"][5]
        self.assertAlmostEqual(m5["estimate"], 0.5)
        self.assertEqual(m5["p"], 1.0)   # all instance values exactly 0.5 = theta0

    def test_h2_needs_four_of_six(self) -> None:
        lock_users = {"m0", "m1", "m2"}
        ch = lambda m, cfg, a, t, i, n, s: "a0:lock;a1:none" if m in lock_users else "a0:none;a1:none"  # noqa: E731
        h2 = self.conf(_full_grid(self.M6, choice_fn=ch))["hypotheses"]["H2"]
        self.assertEqual(h2["rejecting_models"], ["m3", "m4", "m5"])   # 3 models at 0 lock use; rate 0.5 does not reject
        self.assertEqual(h2["verdict"], "not supported")
        lock_users.discard("m2")
        h2 = self.conf(_full_grid(self.M6, choice_fn=ch))["hypotheses"]["H2"]
        self.assertEqual(h2["verdict"], "supported")

    def test_h3_pairs_and_option_by_config(self) -> None:
        def ch(m, cfg, a, t, i, n, s):
            if m == "m0" and a == 1 and cfg == "locks":
                return "a0:lock;a1:lock"
            if m == "m0" and a == 1 and cfg == "messages":
                return "a0:message;a1:lock"      # lock under messages is not the offered option
            if m == "m1" and a == 1 and cfg == "locks":
                return "a0:message;a1:none"      # message under locks is not the offered option
            return "a0:none;a1:none"
        h3 = self.conf(_full_grid(self.M6, choice_fn=ch))["hypotheses"]["H3"]
        t0, t1 = h3["tests"][0], h3["tests"][1]
        self.assertAlmostEqual(t0["estimate"], 6 / 8)  # per cluster, aware on: 4 of 4 lock (locks) + 2 of 4 message (messages); off: 0
        self.assertTrue(t0["reject"])
        self.assertEqual(t1["estimate"], 0.0)
        self.assertEqual(h3["rejecting_models"], ["m0"])
        self.assertEqual(h3["verdict"], "reported per model (no overall claim)")

    def test_h4a_uses_primary_label_on_single_record_templates(self) -> None:
        def lab(m, cfg, a, t, i, n, s):
            if t in analyze4.WRITE_SKEW_TEMPLATES or t == "transfer_shared_source":
                return "write_skew" if t != "transfer_shared_source" else "partial_action"
            return "stale_overwrite" if cfg == "none" and m == "m0" else ""
        h4a = self.conf(_full_grid(self.M6, label_fn=lab))["hypotheses"]["H4a"]
        self.assertEqual(h4a["rejecting_models"], ["m0"])
        self.assertAlmostEqual(h4a["tests"][0]["estimate"], 1.0)
        self.assertEqual(h4a["tests"][1]["estimate"], 0.0)   # write_skew / partial_action elsewhere are ignored

    def test_h4b_intersection_union_and_margin(self) -> None:
        def lab(m, cfg, a, t, i, n, s):
            if t not in analyze4.WRITE_SKEW_TEMPLATES or cfg not in ("none", "cas_available"):
                return ""
            if m == "m0":
                return "write_skew"                                      # 1.0 under both: (i) and (ii) hold
            if m == "m1":
                return "write_skew" if cfg == "none" else ""             # drop 1.0: (ii) fails
            if m == "m2":
                return "write_skew" if (cfg == "none" or s == 0) else "" # cas 0.5: (i) fails
            return "write_skew" if cfg == "none" or i < 2 or s == 0 else ""
        h4b = self.conf(_full_grid(self.M6, label_fn=lab))["hypotheses"]["H4b"]
        t = {x["model"]: x for x in h4b["tests"]}
        self.assertEqual(t["m0"]["n_complete_clusters"], 8)
        self.assertAlmostEqual(t["m0"]["component_i"]["p"], 0.5 ** 8)
        self.assertAlmostEqual(t["m0"]["component_ii"]["p"], 0.5 ** 8)
        self.assertAlmostEqual(t["m0"]["p"], 0.5 ** 8)
        self.assertEqual(t["m1"]["p"], 1.0)
        self.assertEqual(t["m2"]["p"], 1.0)
        self.assertEqual(t["m1"]["p"], max(t["m1"]["component_i"]["p"], t["m1"]["component_ii"]["p"]))
        self.assertIn("m0", h4b["rejecting_models"])
        self.assertNotIn("m1", h4b["rejecting_models"])
        self.assertNotIn("m2", h4b["rejecting_models"])

    def test_h6_slope_on_log2_n(self) -> None:
        def lab(m, cfg, a, t, i, n, s):
            return "write_skew" if m == "m0" and cfg == "cas_available" and n == 8 else ""
        h6 = self.conf(_full_grid(self.M6, label_fn=lab))["hypotheses"]["H6"]
        t0 = h6["tests"][0]
        self.assertEqual(t0["n_complete_clusters"], 14)
        self.assertAlmostEqual(t0["estimate"], 0.5)   # y = (0, 0, 1) on x = (1, 2, 3)
        self.assertTrue(t0["reject"])
        self.assertEqual(h6["tests"][1]["estimate"], 0.0)

    def test_holm_within_hypothesis_family(self) -> None:
        rows = _full_grid(self.M6, label_fn=lambda m, cfg, a, t, i, n, s: "stale_overwrite" if cfg == "none" else "")
        h1 = self.conf(rows)["hypotheses"]["H1"]
        ps = [t["p"] for t in h1["tests"]]
        self.assertEqual([t["p_holm"] for t in h1["tests"]], analyze4.holm(ps))

    def test_not_tested_when_budget_truncates_and_dropped_for_failures(self) -> None:
        rows = _full_grid(self.M6, label_fn=lambda m, cfg, a, t, i, n, s: "stale_overwrite" if cfg == "none" else "")
        # m5 never ran phase 3 (n = 8): H6 not tested for m5; other hypotheses unaffected
        cut = [r for r in rows if not (r["model"] == "m5" and r["n_agents"] == 8)]
        # m4: one H1 episode failed at the provider -> that cluster is dropped, H1 still tested
        lost = next(r for r in cut if r["model"] == "m4" and r["config"] == "none" and r["aware"] == 0 and r["n_agents"] == 2
                    and r["task"] == "seat_same" and r["instance"] == "1" and r["seed"] == 1)
        cut.remove(lost)
        failed = [run4.episode_id("m4", "none", False, "seat_same", 2, 1, 1)]
        c = self.conf(cut, failed_ids=failed)
        h6 = c["hypotheses"]["H6"]
        self.assertEqual(h6["not_tested_models"], ["m5"])
        self.assertEqual(h6["family_size"], 5)
        self.assertIsNone(h6["tests"][5]["p"])
        self.assertIsNone(h6["tests"][5]["reject"])
        self.assertEqual(h6["tests"][5]["status"], "not_tested")
        h1 = c["hypotheses"]["H1"]
        self.assertEqual(h1["tests"][4]["n_complete_clusters"], 27)
        self.assertEqual(h1["tests"][4]["dropped_clusters"], ["seat_same@i1"])
        self.assertEqual(h1["verdict"], "supported")
        # the same episode missing WITHOUT a failure record (never run) -> not tested, not a null result
        h1b = self.conf(cut)["hypotheses"]["H1"]
        self.assertEqual(h1b["not_tested_models"], ["m4"])
        self.assertEqual(h1b["verdict"], "not supported")   # counts as not supporting in "all six"
        self.assertEqual(h1b["family_size"], 5)

    def test_truncation_sensitivity_drops_clusters(self) -> None:
        rows = _full_grid(["m0"], label_fn=lambda m, cfg, a, t, i, n, s: "stale_overwrite" if cfg == "none" else "")
        trunc = next(r for r in rows if r["config"] == "none" and r["aware"] == 0 and r["n_agents"] == 2)
        trunc["truncated"] = True
        c = analyze4.confirmatory(rows, h5=[], models=["m0"], exclude_truncated=True, n_boot=200)
        self.assertGreaterEqual(c["meta"]["truncated_episodes_excluded"], 1)
        self.assertEqual(c["hypotheses"]["H1"]["tests"][0]["n_complete_clusters"], 27)
        self.assertEqual(c["hypotheses"]["H1"]["tests"][0]["status"], "tested")

    def test_h5_from_transcripts(self) -> None:
        from tests4 import manual
        task = I.build("transfer_shared_source", 0, 2)
        src = next(r for r in task.initial if task.intents["a0"].src == r)
        d0, d1 = task.intents["a0"].dst, task.intents["a1"].dst
        amt = task.intents["a0"].amount
        bal = task.initial[src]
        from decimal import Decimal
        new_src = str(Decimal(bal) - Decimal(amt))
        world, s = manual(task, "cas_available", [
            ("a0", "get_record", {"record_id": src}), ("a1", "get_record", {"record_id": src}),
            ("a0", "get_record", {"record_id": d0}), ("a1", "get_record", {"record_id": d1}),
            ("a1", "update_record", {"record_id": src, "value": new_src, "expected_version": 1}),
            ("a1", "update_record", {"record_id": d1, "value": str(Decimal(task.initial[d1]) + Decimal(amt)), "expected_version": 1}),
            ("a0", "update_record", {"record_id": src, "value": new_src, "expected_version": 1}),   # 409 version_conflict
            ("a0", "update_record", {"record_id": d0, "value": str(Decimal(task.initial[d0]) + Decimal(amt)), "expected_version": 1}),
        ])
        self.assertEqual(s.primary_label, "partial_action")
        tr = {"episode_id": "e1", "model": "m0", "n_agents": 2,
              "task": {"factory": "transfer_shared_source", "instance": 0},
              "ledger": {"calls": [c.to_dict() for c in world.store.ledger.calls]},
              "score": s.to_dict()}
        tr["score"]["agents"]["a0"]["end_reason"] = "returned"
        el = analyze4.h5_from_transcript(tr)
        self.assertEqual([(a["agent"], a["partial"]) for a in el], [("a0", True)])   # a1 saw no rejection
        c = analyze4.confirmatory([], h5=el, models=("m0", "m1"), n_boot=10)
        self.assertEqual((c["H5"]["per_model"]["m0"]["k"], c["H5"]["per_model"]["m0"]["n"]), (1, 1))
        self.assertEqual(c["H5"]["per_model"]["m1"]["n"], 0)
        lo, hi = analyze4.wilson(1.0, 1)
        self.assertAlmostEqual(c["H5"]["per_model"]["m0"]["ci_low"], lo)

    def test_analyze_cli_writes_confirmatory_and_labels_exploratory(self) -> None:
        d = tempfile.mkdtemp()
        try:
            rows = [_row(model=analyze4.REGISTERED_MODELS[0], instance=0, seed=0, primary_label="stale_overwrite", model_served="served-x")]
            p = _write_csv(os.path.join(d, "r.csv"), rows)
            out = os.path.join(d, "a")
            code, log = quiet(analyze4.main, [p, "--out", out])
            self.assertEqual(code, 0, log)
            with open(os.path.join(out, "confirmatory.json")) as f:
                c = json.load(f)
            self.assertEqual(c["registered"]["hypotheses"]["H1"]["not_tested_models"], list(analyze4.REGISTERED_MODELS))
            self.assertEqual(c["registered"]["meta"]["served_ids"][analyze4.REGISTERED_MODELS[0]], ["served-x"])
            with open(os.path.join(out, "confirmatory.md")) as f:
                md = f.read()
            self.assertIn("CONFIRMATORY", md)
            self.assertIn("not tested", md)
            with open(os.path.join(out, "tables.md")) as f:
                self.assertIn("EXPLORATORY", f.read())
            with open(os.path.join(out, "numbers.json")) as f:
                self.assertTrue(json.load(f)["status"].startswith("EXPLORATORY"))
        finally:
            shutil.rmtree(d)

    def test_registered_models_match_run_full(self) -> None:
        with open(os.path.join(HERE, "run_full.sh")) as f:
            sh = f.read()
        block = sh.split("MODELS_ORDERED=(", 1)[1].split(")", 1)[0]
        ids = [ln.strip().strip('"') for ln in block.splitlines() if ln.strip().startswith('"')]
        self.assertEqual(tuple(ids), analyze4.REGISTERED_MODELS)


class PriceMatchingTest(unittest.TestCase):
    def test_exact_or_dated_prefix_only(self) -> None:
        prices = M.PriceTable.load(os.path.join(HERE, "prices.json"))
        self.assertEqual(prices.lookup("claude-fable-5")["prefix"], "claude-fable-5")
        self.assertEqual(prices.lookup("claude-fable-5-20261101")["prefix"], "claude-fable-5")
        for other in ("claude-fable-5.1", "claude-fable-5.1-20261201", "claude-fable-5-1", "claude-fable-50"):
            self.assertIsNone(prices.lookup(other), other)
        self.assertEqual(prices.lookup("claude-haiku-4-5-20251001")["prefix"], "claude-haiku-4-5")
        self.assertEqual(prices.lookup("openrouter:qwen/qwen3.6-27b-20260422")["prefix"], "openrouter:qwen/qwen3.6-27b")
        for m in analyze4.REGISTERED_MODELS:
            self.assertIsNotNone(prices.lookup(m), m)
            self.assertIsNotNone(plan_full.cost_n2(m))
        with self.assertRaises(SystemExit):
            plan_full.cost_n2("claude-fable-5.1")
        t = M.PriceTable({"x": {"input": 1}, "x-20260101": {"input": 2}})
        self.assertEqual(t.lookup("x-20260101")["input"], 2)    # exact key wins


if __name__ == "__main__":
    unittest.main()
