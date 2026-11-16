#!/usr/bin/env python3
"""Tests for the Study 4 analysis (synthetic samples; no transcripts needed)."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze7 as A  # noqa: E402

FAMS = A.FAMILIES


def rec(fs, basis=None):
    return {"fs": int(fs), "basis": int(fs if basis is None else basis), "mechanisms": [], "order": {}, "agents": {},
            "family": "x", "cap_truncated": False}


def sample(rates, n_inst=A.INSTANCES, seed=1, drop=()):
    """rates: model -> config -> failure probability."""
    rng = random.Random(seed)
    out = {}
    for m, by_c in rates.items():
        for f in FAMS:
            for i in range(n_inst):
                for c, p in by_c.items():
                    if (m, c, f, i) in drop:
                        continue
                    r = rec(rng.random() < p)
                    r["family"] = f
                    out[(m, c, f, i)] = r
    return out


def flat(p):
    return {c: p for c in A.CONFIGS}


class ClusterValues(unittest.TestCase):
    def test_contrasts(self):
        fs = {A.TWO: 1, A.INSTR: 0, A.SIGNALS: 1, A.BUNDLE: 0}  # instruction only
        self.assertEqual(A.cluster_value("H1", fs), 1)
        self.assertEqual(A.cluster_value("H2", fs), 1)
        self.assertEqual(A.cluster_value("H3", fs), 0)
        fs = {A.TWO: 1, A.INSTR: 1, A.SIGNALS: 0, A.BUNDLE: 0}  # signals only
        self.assertEqual(A.cluster_value("H2", fs), 0)
        self.assertEqual(A.cluster_value("H3", fs), 1)
        fs = {A.TWO: 1, A.INSTR: 0, A.SIGNALS: 0, A.BUNDLE: 0}  # either suffices
        self.assertEqual(A.cluster_value("H2", fs), 0.5)
        self.assertEqual(A.cluster_value("H3", fs), 0.5)
        self.assertEqual(A.cluster_value("H6", fs), 1)

    def test_constants(self):
        self.assertEqual(A.REGISTERED_CLUSTERS, 128)
        self.assertEqual(A.MIN_CLUSTERS, 96)
        self.assertEqual(len(A.MODELS), 4)
        self.assertEqual(A.CONFIGS, ("locks_s2text", "locks_instr", "locks_signals", "locks"))


class Suite(unittest.TestCase):
    def test_null_no_rejections(self):
        s = sample({m: flat(0.3) for m in A.MODELS}, seed=3)
        tests = A.run_suite(s, 500)
        self.assertEqual(len(tests), 30)
        self.assertFalse(any(t["reject"] for t in tests))

    def test_instruction_effect_found_signals_not(self):
        r = {A.TWO: 0.6, A.INSTR: 0.1, A.SIGNALS: 0.6, A.BUNDLE: 0.1}
        s = sample({m: r for m in A.MODELS}, seed=4)
        tests = {t["id"]: t for t in A.run_suite(s, 500)}
        for m in ("Qwen", "Haiku", "Sonnet", "Fable", "pooled"):
            self.assertTrue(tests[f"H1|{m}"]["reject"], m)
            self.assertTrue(tests[f"H2|{m}"]["reject"], m)
            self.assertFalse(tests[f"H3|{m}"]["reject"], m)
            self.assertTrue(tests[f"H4|{m}"]["reject"], m)
            self.assertFalse(tests[f"H5|{m}"]["reject"], m)
            self.assertFalse(tests[f"H6|{m}"]["reject"], m)  # additive: no interaction

    def test_either_part_suffices_shows_as_interaction(self):
        r = {A.TWO: 0.7, A.INSTR: 0.1, A.SIGNALS: 0.1, A.BUNDLE: 0.1}
        tests = {t["id"]: t for t in A.run_suite(sample({m: r for m in A.MODELS}, seed=9), 500)}
        for m in ("Haiku", "pooled"):
            for h in ("H1", "H2", "H3", "H4", "H5", "H6"):
                self.assertTrue(tests[f"{h}|{m}"]["reject"], (h, m))
            self.assertGreater(tests[f"H6|{m}"]["estimate"], 0)
            self.assertIn("smaller when the other part is present", tests[f"H6|{m}"]["claim"])

    def test_invalid_model_leaves_holm_and_pool(self):
        tests = {t["id"]: t for t in A.run_suite(sample({m: flat(0.3) for m in A.MODELS}, seed=10), 300,
                                                 invalid=[A.MODELS[1]])}
        self.assertEqual(tests["H1|Haiku"]["status"], "invalid")
        self.assertIsNone(tests["H1|Haiku"]["reject"])
        self.assertEqual(tests["H1|Qwen"]["holm_family_size"], 4)
        self.assertEqual(tests["H1|pooled"]["models_pooled"], ["Qwen", "Sonnet", "Fable"])

    def test_fable_floor_stop_pools_the_other_models(self):
        r = {m: {A.TWO: 0.5, A.INSTR: 0.1, A.SIGNALS: 0.5, A.BUNDLE: 0.1} for m in A.MODELS[:3]}
        s = sample(r, seed=11)
        fable = A.MODELS[3]
        for f in FAMS:  # stage 1 only, 3 failures
            for i in range(A.INSTANCES):
                x = rec(f == FAMS[0] and i < 3)
                x["family"] = f
                s[(fable, A.TWO, f, i)] = x
        tests = {t["id"]: t for t in A.run_suite(s, 300, stage={fable: "floor"})}
        self.assertEqual(tests["H1|Fable"]["status"], "not_run_floor")
        cap = {t["id"]: t for t in A.run_suite(s, 300, stage={fable: "stage1_incomplete"})}
        self.assertEqual(cap["H1|Fable"]["status"], "not_tested")  # a cap stop is not the floor
        self.assertIn("Not run: floor", tests["H1|Fable"]["claim"])
        self.assertEqual(tests["H1|pooled"]["status"], "tested")
        self.assertEqual(tests["H1|pooled"]["models_pooled"], ["Qwen", "Haiku", "Sonnet"])
        self.assertTrue(tests["H1|pooled"]["reject"])
        self.assertEqual(tests["H1|Qwen"]["holm_family_size"], 4)

    def test_direction_one_sided(self):
        r = {A.TWO: 0.1, A.INSTR: 0.6, A.SIGNALS: 0.1, A.BUNDLE: 0.6}  # the bundle raises failures
        s = sample({m: r for m in A.MODELS}, seed=5)
        self.assertFalse(any(t["reject"] for t in A.run_suite(s, 500)))

    def test_min_clusters_gate(self):
        m = A.MODELS[0]
        drop = {(m, A.BUNDLE, f, i) for f in FAMS for i in range(5)}  # 40 clusters lose the bundle: 88 < 96
        s = sample({x: flat(0.3) for x in A.MODELS}, drop=drop)
        tests = {t["id"]: t for t in A.run_suite(s, 300)}
        self.assertEqual(tests["H1|Qwen"]["status"], "not_tested")
        self.assertEqual(tests["H1|Qwen"]["n_clusters"], 88)
        self.assertEqual(tests["H1|Haiku"]["status"], "tested")
        self.assertEqual(tests["H1|pooled"]["models_pooled"], ["Haiku", "Sonnet", "Fable"])  # Qwen's test does not run
        self.assertEqual(tests["H1|pooled"]["status"], "tested")
        self.assertEqual(tests["H1|Haiku"]["holm_family_size"], 4)

    def test_holm_family_is_per_hypothesis(self):
        s = sample({m: flat(0.3) for m in A.MODELS}, seed=6)
        for t in A.run_suite(s, 300):
            self.assertEqual(t["holm_family_size"], 5)

    def test_pooled_is_equal_weight_mean(self):
        s = sample({m: {A.TWO: 0.5, A.INSTR: 0.2, A.SIGNALS: 0.4, A.BUNDLE: 0.1} for m in A.MODELS}, seed=7)
        per = {m: A.values_for(s, m, "H1") for m in A.MODELS}
        pooled = A.pooled_values(per)
        k = next(iter(pooled))
        self.assertAlmostEqual(pooled[k], sum(per[m][k] for m in A.MODELS) / 4)

    def test_floor(self):
        r = {m: {A.TWO: 0.5, A.INSTR: 0.1, A.SIGNALS: 0.5, A.BUNDLE: 0.1} for m in A.MODELS}
        r[A.MODELS[3]] = flat(0.0)
        tests = {t["id"]: t for t in A.run_suite(sample(r, seed=8), 300)}
        self.assertTrue(tests["H1|Fable"]["floor"])
        self.assertIn("floor", tests["H1|Fable"]["claim"])
        self.assertFalse(tests["H1|Haiku"]["floor"])
        self.assertTrue(tests["H1|pooled"]["reject"])

    def test_select_contended_study4_only(self):
        base = {"study": 4, "dry_run": False, "config": "locks", "start": "together", "model": A.MODELS[0], "n_agents": 2,
                "aware": 0, "probe": False, "arm": "contended", "family": FAMS[0], "instance": 0, "seed": 0,
                "host_bad": False, "exclusion_trigger": None, "order_key": ("a", "a"), "id": "e1", "fs": 0,
                "cap_truncated": False}
        recs = [dict(base), dict(base, id="e2", arm="control"), dict(base, id="e3", study=3),
                dict(base, id="e4", instance=1, exclusion_trigger="a0:truncated"), dict(base, id="e1", order_key=("b", "b"))]
        sel = A.select(recs, False)
        self.assertEqual(len(sel["main"]), 1)
        self.assertEqual(sel["log"]["never_data"], {"unregistered_cell": 1, "not_study4": 1})
        self.assertEqual(sel["log"]["counts"], {"duplicate_transcripts_ignored": 1, "agent_error_or_refusal": 1})


if __name__ == "__main__":
    unittest.main()
