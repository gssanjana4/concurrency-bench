"""Tests of analysis6/analyze6.py (Study 3): the statistical core equals the frozen Study 2 code, the cluster values,
the gates and readings on planted data, the exclusion rule, determinism, and an end-to-end run on a dry run.

    PYTHONDONTWRITEBYTECODE=1 python3 analysis6/tests_analyze6.py                  # unit tests
    A6_DRY_BASE=/path/to/results6/study3_dry PYTHONDONTWRITEBYTECODE=1 python3 analysis6/tests_analyze6.py
        # also the end-to-end tests on that dry run (writes to a temporary directory)
    A5_DIR=/path/to/analysis5   # the frozen Study 2 analysis, for the core-equality test (else ../../analysis5, ../analysis5)
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import random
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze6 as A  # noqa: E402

DRY = os.environ.get("A6_DRY_BASE")


def _find_a5():
    for d in (os.environ.get("A5_DIR"), os.path.join(HERE, "..", "..", "..", "analysis5"),
              os.path.join(HERE, "..", "..", "analysis5"), os.path.join(HERE, "..", "analysis5"),
              "/home/claude/concurrency-bench/analysis5"):
        if d and os.path.exists(os.path.join(d, "analyze5.py")):
            return os.path.join(d, "analyze5.py")
    return None


def agent(**kw):
    base = {"lock": False, "cas": False, "prim": False, "perceivable": 0, "pbp": None, "at_risk": False,
            "reacting": False, "exposed_s2": False, "at_risk_s2": False, "reacting_s2": False, "read_before_lock": None,
            "lock_scope": "none", "missing_leg": False, "fulfilled": True, "committed_writes": 1, "end": "returned",
            "first_reply": "read", "fr_lock": False, "success_reported": False, "last_stop": "end_turn", "truncated": False}
    base.update(kw)
    return base


def rec(model, config, start, fam, inst, arm, fs=0, a0=None, a1=None, **kw):
    r = {"id": f"{model}|{config}|{start}|{fam}|{inst}|{arm}", "path": "", "model": model, "config": config,
         "start": start, "aware": 0, "probe": False, "study": 3, "dry_run": False, "n_agents": 2, "family": fam,
         "arm": arm, "instance": inst, "seed": 0, "fs": fs, "basis": fs, "outcome": "failed" if fs else "clean",
         "cap_truncated": False, "cross_agent_edges": 0, "agents": {"a0": a0 or agent(), "a1": a1 or agent()},
         "order": {"a0": "no_lock", "a1": "no_lock"}, "mechanisms": [], "stagger_ok": None if start == "together" else True,
         "order_key": ("", ""), "exclusion_trigger": None, "errored_agents": [], "hosts": ["alibaba"], "served": [],
         "host_bad": False, "me_violations": []}
    r.update(kw)
    return r


def grid(fill, models=A.MODELS, conditions=A.CONDITIONS, instances=A.INSTANCES):
    """Every registered (model, condition, family, instance, arm) episode; ``fill(r)`` edits each record."""
    out = {}
    for m in models:
        for c, st in conditions:
            for f in A.FAMILIES:
                for i in range(instances):
                    for arm in ("contended", "control"):
                        r = rec(m, c, st, f, i, arm)
                        fill(r)
                        out[A.pair_key(r)] = r
    return out


NB = 300  # bootstrap draws in unit tests (registered: 10,000)


class Core(unittest.TestCase):
    def test_statistical_core_equals_the_frozen_study2_code(self):
        p = _find_a5()
        if p is None:
            self.skipTest("analysis5/analyze5.py not found (set A5_DIR)")
        spec = importlib.util.spec_from_file_location("analyze5_ref", p)
        A5 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(A5)
        rng = random.Random(7)
        for trial in range(6):
            m = rng.choice([20, 48, 64])
            vals = {(f"f{j % 8}", j): rng.choice([-1, 0, 0, 1, 0.5, -0.5]) for j in range(m)}
            x = list(vals.values())
            for alt in ("greater", "less"):
                self.assertEqual(A.signflip(x, alt, "k"), A5.signflip(x, alt, "k"))
            b6, b5 = A.boot(vals, "key", 500), A5.boot(vals, "key", 500)
            self.assertEqual(b6, b5)
            for th, alt in ((0.25, "less"), (-0.25, "greater")):
                self.assertEqual(A.tost_side(b6, th, alt), A5.tost_side(b5, th, alt))
            self.assertEqual(A.t_interval(b6, 0.05), A5.t_interval(b5, 0.05))
            self.assertEqual(A.family_level(vals, "greater", None), A5.family_level(vals, "greater", None))
            self.assertEqual(A.family_level(vals, "tost", 0.25), A5.family_level(vals, "tost", 0.25))
            self.assertEqual(A.holm([0.01, 0.04, 0.03, None]), A5.holm([0.01, 0.04, 0.03, None]))
        self.assertNotEqual(A.SEED, A5.SEED)  # a new RNG seed string, so no Study 2 resample is reused


class Values(unittest.TestCase):
    def test_h1_cluster_values_and_planted_effect(self):
        def fill(r):
            r["fs"] = int(r["arm"] == "contended" and r["config"] in ("locks", "locks_s2text") and r["instance"] < 6)
        D = A.Data(grid(fill))
        v = A.h1_values(D, A.HAIKU, "locks")
        self.assertEqual(len(v), 64)
        self.assertAlmostEqual(A.mean(list(v.values())), 0.75)
        self.assertEqual(A.h1_values(D, A.HAIKU, "cas_available"), {k: 0.0 for k in v})
        tests = A.suite(D, NB, only=("H1",))["tests"]
        by = {t["id"]: t for t in tests}
        self.assertTrue(by["H1-diff|Haiku|locks"]["reject"] and by["H1-diff|pooled|locks"]["reject"])
        self.assertFalse(by["H1-diff|Haiku|cas_available"]["reject"])
        self.assertEqual({t["holm_family_size"] for t in tests if t["test"] == "H1-diff"}, {16})
        self.assertEqual(by["H1cal-diff|Haiku|none"]["holm_level"], A.ALPHA)

    def test_h2_values(self):
        def fill(r):
            if r["config"] == "locks_s2text" and r["arm"] == "contended" and r["instance"] < 4:
                r["fs"] = 1
            if r["config"] in ("locks_s2text", "locks"):
                rbl = r["config"] == "locks_s2text"
                r["agents"] = {"a0": agent(lock=True, read_before_lock=rbl), "a1": agent(lock=True, read_before_lock=False)}
        D = A.Data(grid(fill))
        a = A.h2a_values(D, A.QWEN)
        self.assertAlmostEqual(A.mean(list(a.values())), 0.5)
        b = A.h2b_values(D, A.QWEN)
        self.assertEqual(len(b), 64)
        self.assertAlmostEqual(A.mean(list(b.values())), 0.5)
        tests = {t["id"]: t for t in A.suite(D, NB, only=("H2a", "H2b"))["tests"]}
        self.assertTrue(tests["H2a|pooled|locks_s2text-locks"]["reject"])
        self.assertTrue(tests["H2b|Sonnet|locks_s2text-locks"]["reject"])
        self.assertEqual(tests["H2b|Sonnet|locks_s2text-locks"]["holm_family_size"], 4)

    def test_h2b_needs_an_eligible_agent_in_both_configs(self):
        def fill(r):
            if r["config"] == "locks" and r["family"] in A.FAMILIES[:3]:
                return  # no eligible agent in these clusters under locks
            if r["config"] in ("locks_s2text", "locks"):
                r["agents"]["a0"] = agent(lock=True, read_before_lock=True)
        D = A.Data(grid(fill))
        self.assertEqual(len(A.h2b_values(D, A.HAIKU)), 64 - 3 * 8)


class H3(unittest.TestCase):
    def _data(self, contended_uptake, control_uptake, at_risk):
        rng = random.Random(3)

        def fill(r):
            if r["start"] != "staggered":
                return
            p = contended_uptake if r["arm"] == "contended" else control_uptake
            up = rng.random() < p
            risk = r["arm"] == "contended" and rng.random() < at_risk
            r["agents"]["a1"] = agent(lock=up, prim=up, perceivable=int(risk), at_risk=risk, reacting=risk and up,
                                      pbp=(False if up else None) if risk else (True if up else None))
        return A.Data(grid(fill))

    def test_bounded_when_informative_and_gate_open(self):
        D = self._data(0.70, 0.70, 0.6)
        tests = A.suite(D, 2000, only=("H3",))["tests"]
        A.read_cells(tests, s5_tests=[dict(t, reject=True) for t in tests])
        by = {t["id"]: t for t in tests}
        p = by["H3-eq|pooled|locks"]
        self.assertGreater(p["q"], A.DELTA_POOLED)
        self.assertTrue(p["reject"], p)
        self.assertEqual(p["reading"], "bounded")
        self.assertIn("implied_bound_reacting_share", p)
        self.assertTrue(p["gate_open"])
        self.assertEqual({t["holm_family_size"] for t in tests if t["test"] == "H3-diff"}, {8})

    def test_uninformative_when_q_is_low(self):
        D = self._data(0.97, 0.97, 0.05)
        tests = A.suite(D, 2000, only=("H3",))["tests"]
        A.read_cells(tests, s5_tests=[dict(t, reject=True) for t in tests])
        p = {t["id"]: t for t in tests}["H3-eq|pooled|locks"]
        self.assertLessEqual(p["q"], A.DELTA_POOLED)
        if p["reject"]:
            self.assertEqual(p["reading"], "uninformative")
        self.assertNotEqual(p["reading"], "bounded")

    def test_ceiling_makes_an_equivalence_uninformative(self):
        D = self._data(0.97, 0.97, 0.6)  # q is high but control uptake leaves less than delta of room
        tests = A.suite(D, 2000, only=("H3",))["tests"]
        A.read_cells(tests, s5_tests=[dict(t, reject=True) for t in tests])
        p = {t["id"]: t for t in tests}["H3-eq|pooled|locks"]
        self.assertGreater(p["q"], A.DELTA_POOLED)
        self.assertGreater(p["u_ctrl"], 1 - A.DELTA_POOLED)
        self.assertTrue(p["reject"])
        self.assertEqual(p["reading"], "uninformative")
        self.assertIn("uninformative_ceiling", p["flags"])

    def test_gate_closes_stage2_and_s5_guards_the_claim(self):
        D = self._data(0.9, 0.4, 0.6)  # a large reactive effect: pooled TOST cannot reject
        tests = A.suite(D, 1000, only=("H3",))["tests"]
        A.read_cells(tests, s5_tests=[dict(t, reject=False) for t in tests])
        st2 = [t for t in tests if t["test"] == "H3-eq" and t["model"] != A.POOLED]
        self.assertTrue(all(t["status"] == "not_tested_gate_closed" for t in st2))
        pd = {t["id"]: t for t in tests}["H3-diff|pooled|locks"]
        self.assertTrue(pd["reject"])
        self.assertEqual(pd["reading"], "worse")

    def test_late_agent_only_and_s7_both_agents(self):
        def fill(r):
            if r["start"] == "staggered":
                r["agents"]["a0"] = agent(lock=r["arm"] == "contended")  # a0 differs, a1 does not
        D = A.Data(grid(fill))
        self.assertEqual(set(A.h3_values(D, A.SONNET, "locks").values()), {0.0})
        self.assertEqual(set(A.uctrl_values(D, A.SONNET, "locks").values()), {0.0})
        self.assertEqual(set(A.h3_values(D, A.SONNET, "locks", ("a0", "a1")).values()), {0.5})


class Selection(unittest.TestCase):
    def test_exclusion_takes_the_partner_and_unregistered_rows_are_never_data(self):
        s = grid(lambda r: None, models=(A.QWEN,))
        recs = list(copy.deepcopy(list(s.values())))
        bad = recs[0]
        bad["exclusion_trigger"] = "a1:truncated"
        bad["errored_agents"] = ["a1"]
        recs.append(rec(A.QWEN, "cas_available", "staggered", A.FAMILIES[0], 0, "contended"))  # unregistered condition
        recs.append(rec(A.QWEN, "locks", "together", A.FAMILIES[0], 8, "contended"))  # unregistered instance
        sel = A.select(recs, allow_dry_run=False)
        self.assertNotIn(A.pair_key(bad), sel["main"])
        self.assertNotIn(A.pair_key(bad, A.other_arm(bad["arm"])), sel["main"])
        self.assertEqual(sel["log"]["counts"].get("partner_excluded"), 1)
        self.assertEqual(sum(sel["log"]["never_data"].values()), 2)
        s5, n5 = A.against_equivalence_sample(sel)
        self.assertEqual(n5, 2)
        k = A.pair_key(bad)
        if bad["arm"] == "contended":
            self.assertEqual(s5[k]["fs"], 1)
            self.assertTrue(s5[k]["agents"]["a1"]["lock"])

    def test_wrong_host_qwen_is_excluded(self):
        r = rec(A.QWEN, "none", "together", A.FAMILIES[0], 0, "contended", host_bad=True)
        k = rec(A.QWEN, "none", "together", A.FAMILIES[0], 0, "control")
        sel = A.select([r, k], allow_dry_run=False)
        self.assertEqual(sel["main"], {})

    def test_75_percent_rule(self):
        s = grid(lambda r: r.update(fs=int(r["arm"] == "contended")))
        cut = {k: r for k, r in s.items() if not (r["model"] == A.HAIKU and r["instance"] >= 6 and r["family"] in A.FAMILIES[:2])}
        # Haiku loses 2 families x 2 instances = 4 clusters: 60 >= 48, still tested
        t = {x["id"]: x for x in A.suite(A.Data(cut), NB, only=("H1",))["tests"]}
        self.assertEqual(t["H1-diff|Haiku|locks"]["status"], "tested")
        cut2 = {k: r for k, r in s.items() if not (r["model"] == A.HAIKU and r["instance"] >= 5)}
        t2 = {x["id"]: x for x in A.suite(A.Data(cut2), NB, only=("H1",))["tests"]}
        self.assertEqual(t2["H1-diff|Haiku|locks"]["status"], "not_tested")  # 40 of 64 clusters
        self.assertEqual(t2["H1-diff|Haiku|locks"]["n_clusters"], 40)
        self.assertEqual(set(t2["H1-diff|pooled|locks"]["models"]), {"Qwen", "Sonnet"})

    def test_h2b_75_percent_rule(self):
        def fill(r):
            if r["config"] == "locks" and r["family"] in A.FAMILIES[:3]:
                return
            if r["config"] in ("locks_s2text", "locks"):
                r["agents"]["a0"] = agent(lock=True, read_before_lock=True)
        t = {x["id"]: x for x in A.suite(A.Data(grid(fill)), NB, only=("H2b",))["tests"]}
        self.assertEqual(t["H2b|Haiku|locks_s2text-locks"]["status"], "not_tested")  # 40 < 48


class Determinism(unittest.TestCase):
    def test_same_input_same_output(self):
        rng = random.Random(11)
        s = grid(lambda r: r.update(fs=int(r["arm"] == "contended" and rng.random() < 0.4)))
        r1 = A.suite(A.Data(copy.deepcopy(s)), NB)["tests"]
        r2 = A.suite(A.Data(copy.deepcopy(s)), NB)["tests"]
        self.assertEqual(json.dumps(A._jsonable(r1), sort_keys=True, default=str),
                         json.dumps(A._jsonable(r2), sort_keys=True, default=str))


@unittest.skipUnless(DRY and os.path.isdir(DRY), "set A6_DRY_BASE to a Study 3 dry run")
class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dirs = A.discover(DRY, allow_dry_run=True)
        cls.res = A.run_analysis(A.read_transcripts(dirs), allow_dry_run=True, n_boot=500, root=DRY,
                                 failures=A.failure_counts(dirs))
        cls.out = tempfile.mkdtemp(prefix="a6out_")  # never overwrites the registered dry-run outputs in analysis6/out
        cls.paths = A.write_outputs(cls.res, cls.out)

    def test_grid_complete_and_checks_pass(self):
        self.assertEqual(self.res["inputs"]["n_files"], 2688)
        self.assertEqual(self.res["selection"]["never_data"], {})
        ck = self.res["checks"]
        self.assertTrue(ck["exposure"]["ok"] and ck["isolation"]["ok"] and ck["lock_safety"]["ok"] and ck["stagger"]["ok"], ck)
        self.assertEqual(ck["stagger"]["staggered_episodes"], 3 * 2 * 8 * 8 * 2)

    def test_every_registered_test_runs(self):
        ids = {t["id"]: t for t in self.res["tests"]}
        for m in ("Qwen", "Haiku", "Sonnet", "pooled"):
            for c in A.H1_CONFIGS:
                self.assertEqual(ids[f"H1-diff|{m}|{c}"]["status"], "tested")
            for h in ("H2a", "H2b"):
                self.assertEqual(ids[f"{h}|{m}|locks_s2text-locks"]["status"], "tested", (h, m))
            for c in A.H3_CONFIGS:
                self.assertIn(ids[f"H3-eq|{m}|{c}"]["status"], ("tested", "not_tested_gate_closed"))
                self.assertEqual(ids[f"H3-diff|{m}|{c}"]["status"], "tested")
                self.assertIsNotNone(ids[f"H3-eq|{m}|{c}"]["q"])
        self.assertEqual(len(self.res["tests"]), 16 + 4 + 4 + 4 + 8 + 8)

    def test_outputs_written_and_deterministic(self):
        jp, tp = self.paths
        self.assertTrue(os.path.getsize(jp) > 1000 and os.path.getsize(tp) > 1000)
        tex = open(tp).read()
        self.assertIn(r"\newcommand{\SiiiDryRunFlag}{1}", tex)
        dirs = A.discover(DRY, allow_dry_run=True)
        again = A.run_analysis(A.read_transcripts(dirs), allow_dry_run=True, n_boot=500, root=DRY,
                               failures=A.failure_counts(dirs))
        with tempfile.TemporaryDirectory() as d:
            jp2, tp2 = A.write_outputs(again, d)
            self.assertEqual(open(tp2).read(), tex)
            self.assertEqual(open(jp2).read(), open(jp).read())

    def test_descriptives_and_sensitivities_present(self):
        d = self.res["descriptive"]
        self.assertTrue(d["D1_amounts"] and d["D2_lock_mechanisms"] and d["D3_protocol"] and d["D4_reacting_share"])
        s = self.res["sensitivity"]
        self.assertTrue(d["D4b_conditional_reaction"] and d["D6_reactive_reread"])
        for k in ("S1_cap_truncated_excluded", "S2_exclusions_kept", "S3_holm_within_model", "S4_family_level",
                  "S5_against_equivalence", "S6_h1_dsg_basis_cycle", "S7_h3_both_agents", "S8_q_study2_signals",
                  "S9_h2b_every_agent"):
            self.assertIn(k, s)


if __name__ == "__main__":
    unittest.main()
