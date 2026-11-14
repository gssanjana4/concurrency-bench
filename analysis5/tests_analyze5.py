"""Tests of analyze5.py (stdlib unittest).

    PYTHONDONTWRITEBYTECODE=1 python3 analysis5/tests_analyze5.py            # all
    A5_DRY_BASE=/path/to/dry-run/base python3 analysis5/tests_analyze5.py    # other dry-run output

(a) end to end on the dry-run output: writes analysis5/out/results.json and numbers.tex;
(b) planted data with known effects: gatekeeping, TOST bounded / worse, H1 calibration gate, H2, H3, H4, eligibility
    (H4 only), leakage;
(c) determinism: two CLI runs (different PYTHONHASHSEED) give byte-identical outputs;
(d) exclusions (no re-runs) on planted truncated, refused and wrong-host rows; never-data rows; partners;
    sensitivity 9;
(e) size and power of the registered decision tests (small simulations, fixed seeds), the claim table and the
    Holm/gatekeeping logic on synthetic p-values.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, HERE)
import analyze5 as A  # noqa: E402
import balance5 as BAL  # noqa: E402

SCRATCH = "/tmp/claude-0/-home-claude/7bd43847-0fad-5af6-9555-aaafd42abf90/scratchpad"
# Round 4: the dry run of the final (frozen) harness, with the final plan it ran
DRY_BASE = os.environ.get("A5_DRY_BASE", os.path.join(SCRATCH, "r4", "dry_r4"))
DRY_PLAN = os.environ.get("A5_DRY_PLAN", os.path.join(os.path.dirname(HERE), "src5", "plan_study2.json"))
OUT = os.path.join(HERE, "out")
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

# ----------------------------------------------------------------------------------------------- planted data

FAMS = A.FAMILIES
K_INST, N_SEEDS, K_PROBE = 4, 2, 4


def plant_plan(models=A.CONFIRMATORY, gpt=True):
    blocks = []
    for m in models:
        blocks.append({"model": m, "mode": "probe", "priority": 0, "configs": list(A.CONFIGS), "aware": [False, True],
                       "families": list(FAMS), "instances": K_PROBE, "schedules": 1, "n": 2})
        blocks.append({"model": m, "mode": "episodes", "priority": 1, "configs": list(A.CONFIGS), "aware": [False],
                       "families": list(FAMS), "instances": K_INST, "schedules": N_SEEDS, "n": 2})
    if gpt:
        blocks.append({"model": A.GPT, "mode": "episodes", "priority": 1, "configs": list(A.CONFIGS), "aware": [False],
                       "families": list(FAMS[:3]), "instances": 2, "schedules": 2, "n": 2})
        blocks.append({"model": A.GPT, "mode": "episodes", "priority": 4, "configs": list(A.CONFIGS), "aware": [False],
                       "families": list(FAMS[:3]), "instances": 3, "schedules": 2, "n": 2})
    return {"blocks": blocks}


def agent(lock=False, cas=False, fp=None, fp_call=None, fc_call=None, end="returned", fulfilled=True, first_reply="read",
          stop="end_turn", host="anthropic", served=None, truncated=False):
    # score5._protection_timing's rules (Round 3): <= counts as before; lock_after_contention from the first lock call
    pbc = None if fp_call is None else (True if fc_call is None else fp_call <= fc_call)
    lock_call = fp_call if (lock and fp == "lock") else None
    lock_after = None if lock_call is None else (fc_call is not None and lock_call > fc_call)
    return {"score": {"lock": lock, "cas": cas, "first_protective": fp, "first_protective_call": fp_call,
                      "first_contention_call": fc_call, "protect_before_contention": pbc, "end_reason": end,
                      "contention_signals": 0 if fc_call is None else 1, "first_lock_call": lock_call,
                      "lock_after_contention": lock_after, "fulfilled": fulfilled},
            "raw": {"first_reply": first_reply, "truncated": truncated,
                    "turns": [{"stop_reason": "tool_use", "served_host": host, "model_served": served},
                              {"stop_reason": stop, "served_host": host, "model_served": served}]}}


def transcript(model, config, family, inst, seed, arm, agents, fs=0, basis=None, probe=False, aware=0, dry=False,
               outcome=None, cross=0, started="2026-11-10T00:00:00Z", mutex=()):
    ctrl = arm == "control"
    eid = "__".join([model.replace("/", "_").replace(":", "_"), config + ("+aware" if aware else ""),
                     f"{family}{'_ctrl' if ctrl else ''}@i{inst}", "n2", f"s{seed}"] + (["probe"] if probe else []))
    return {"episode_id": eid, "study": 2, "dry_run": dry, "model": model, "config": config,
            "concurrency_aware_prompt": bool(aware), "probe": probe, "n_agents": 2, "seed": seed,
            "task": {"factory": family + ("_ctrl" if ctrl else ""), "family": family,
                     "category": "control" if ctrl else "conflict", "instance": inst},
            "score": {"fs_nonserializable": bool(fs), "dsg_basis_cycle": bool(fs if basis is None else basis),
                      "outcome": outcome or ("failed" if fs else "clean"), "cross_agent_edges": cross,
                      "cap_truncated": False, "interleaving": {"reads_overlap": True},
                      "mutual_exclusion_violations": list(mutex),
                      "agents": {a: v["score"] for a, v in agents.items()}},
            "agents": {a: v["raw"] for a, v in agents.items()},
            "run_info": {"started_utc": started}}


def u(*key):
    """Deterministic uniform in [0, 1) for a planted cell."""
    return random.Random("plant|" + "|".join(map(str, key))).random()


# Planted truth (per model, config) of H1 (contended minus control failure):
#   'eq'      : Delta about 0 (two clusters at +0.5, two at -0.5);
#   'worse03' : 16 of 28 clusters at +0.5 (Delta = 0.29, above delta = 0.25), the rest 0;
#   'worse'   : contended fails with probability 0.7, control never (calibration under none).
H1_TRUTH = {(A.QWEN, "locks"): "worse03"}
CAL_TRUTH = {A.QWEN: "worse", A.HAIKU: "worse", A.SONNET: "eq", A.GPT: "worse"}


def plant_episodes(model, config):
    out = []
    host = "alibaba" if model == A.QWEN else "openai" if model == A.GPT else "anthropic"
    fams, ninst = (FAMS, K_INST) if model != A.GPT else (FAMS[:3], 2)
    for fi, fam in enumerate(fams):
        for i in range(ninst):
            for s in range(N_SEEDS):
                truth = CAL_TRUTH[model] if config == "none" else H1_TRUTH.get((model, config), "eq")
                base = u("fs", model, config, fam, i, s) < 0.1
                if truth == "worse":
                    fs_c, fs_k = u("w", model, config, fam, i, s) < 0.7, False
                elif truth == "worse03":
                    fs_c, fs_k = (s == 0 and (fi * 4 + i) % 7 < 4), False
                else:
                    fs_c = fs_k = base
                    if (fam, i, s) in (("seat_same", 0, 0), ("ticket_same", 1, 1)):
                        fs_c, fs_k = True, False  # a little noise: two clusters at +0.5 ...
                    if (fam, i, s) in (("seat_same", 2, 0), ("ticket_same", 3, 1)):
                        fs_c, fs_k = False, True  # ... and two at -0.5
                for arm, fs in (("contended", fs_c), ("control", fs_k)):
                    ags = {}
                    for a in ("a0", "a1"):
                        # H2a: Qwen locks more under all_available (0.8) than under locks (0.2); others 0.3 / 0.3
                        p_lock = {(A.QWEN, "all_available"): 0.8, (A.QWEN, "locks"): 0.2}.get((model, config), 0.3)
                        # H4: Haiku under locks: contended 0.6 vs control 0.1 (more uptake under contention)
                        if (model, config) == (A.HAIKU, "locks"):
                            p_lock = 0.6 if arm == "contended" else 0.1
                        lock = config in ("locks", "all_available") and u("lock", model, config, fam, i, s, a, arm) < p_lock
                        exposed = arm == "contended" and config == "locks"  # all_available: nobody exposed
                        ags[a] = agent(lock=lock, fp="lock" if lock else None, fp_call=3 if lock else None,
                                       fc_call=2 if exposed else None, host=host, served=model)
                    out.append(transcript(model, config, fam, i, s, arm, ags, fs=int(fs)))
    return out


def plant_probes(model):
    out = []
    host = "alibaba" if model == A.QWEN else "anthropic"
    for config in A.CONFIGS:
        for aware in (0, 1):
            for fam in FAMS:
                for i in range(K_PROBE):
                    def code(a, arm):
                        if config not in ("locks", "all_available"):
                            return "read"
                        if model == A.SONNET and config == "locks":
                            return "lock"  # Sonnet always locks first under locks: not eligible there (H4 only)
                        p = 0.05
                        if aware and a == "a0" and model in (A.QWEN, A.HAIKU):
                            p = 0.75  # H3: the aware notice raises a0 first-reply locking
                        if model == A.HAIKU and a == "a1" and arm == "contended" and config == "locks":
                            p = 0.6  # leakage: the tag leaks the arm for Haiku a1
                        return "lock" if u("fr", model, config, aware, fam, i, a, arm) < p else "read"
                    ags = {a: agent(end="probe", first_reply=code(a, "contended"), host=host, served=model) for a in ("a0", "a1")}
                    out.append(transcript(model, config, fam, i, 0, "contended", ags, probe=True, aware=aware))
                    out.append(transcript(model, config, fam, i, 0, "control",
                                          {"a1": agent(end="probe", first_reply=code("a1", "control"), host=host, served=model)},
                                          probe=True, aware=aware))
    return out


def planted_set(gpt=True):
    trs = []
    for m in A.CONFIRMATORY:
        for c in A.CONFIGS:
            trs += plant_episodes(m, c)
        trs += plant_probes(m)
    if gpt:
        for c in A.CONFIGS:
            trs += plant_episodes(A.GPT, c)
        # extension-only row (instance 2): never enters a statistic
        trs.append(transcript(A.GPT, "locks", FAMS[0], 2, 0, "contended", {"a0": agent(host="openai"), "a1": agent(host="openai")}, fs=1))
    return trs


def as_inputs(trs):
    return [(f"planted/{i:05d}.json", t) for i, t in enumerate(trs)]


_PLANTED = {}


def planted_result():
    if "r" not in _PLANTED:
        _PLANTED["r"] = A.run_analysis(as_inputs(planted_set()), plant_plan(), None, allow_dry_run=False,
                                       n_boot=A.N_BOOT, src5_dir=None, with_sensitivity=False)
    return _PLANTED["r"]


def by_id(res):
    return {t["id"]: t for t in res["tests"]}


# ----------------------------------------------------------------------------------------------- (e) decision tests


def beta_draw(rng, mu, icc=0.3):
    if mu <= 0:
        return 0.0
    s = 1 / icc - 1
    return rng.betavariate(mu * s, (1 - mu) * s)


def binom(rng, k, p):
    return sum(rng.random() < p for _ in range(k))


def cluster_d(rng, mu_c, shift, k=2, m=28):
    """One model's cluster values: arm probabilities Beta(mu, ICC 0.3), independent arms, k units per arm-cluster;
    the contended probability is the control-type draw plus ``shift``."""
    out = {}
    for j in range(m):
        pc, pt = beta_draw(rng, mu_c), min(1.0, beta_draw(rng, mu_c) + shift)
        out[(f"f{j % 7}", j)] = (binom(rng, k, pt) - binom(rng, k, pc)) / k
    return out


def tost_p(values, delta, key, B=999):
    bs = A.boot(values, key, B)
    lo, hi = A.tost_side(bs, -delta, "greater"), A.tost_side(bs, delta, "less")
    return max(lo["p"], hi["p"]), max(lo["p_percentile"], hi["p_percentile"])


class DecisionTests(unittest.TestCase):
    def test_signflip_exact_on_sparse_clusters(self):
        # T3b B1(b): k clusters at +0.5, the rest 0. The exact p is 2^-k; the old percentile bootstrap gave
        # about (1 - k/m)^m (0.040 at k = 3).
        for k in (3, 4, 5, 6):
            vals = {("f", i): (0.5 if i < k else 0.0) for i in range(28)}
            r = A.run_test("H1-diff", A.QWEN, "locks", vals, "greater", n_boot=2000)
            self.assertEqual(r["method"], "exact")
            self.assertAlmostEqual(r["p"], 0.5 ** k)
            if k == 3:
                self.assertLess(r["p_percentile"], 0.05)  # the Study 1 procedure would have rejected

    def test_signflip_two_sided_and_all_zero(self):
        vals = {("f", i): 0.0 for i in range(10)}
        r = A.run_test("H2a", A.QWEN, "c", vals, "two_sided", n_boot=200)
        self.assertEqual(r["p"], 1.0)
        vals = {("f", i): (0.25 if i < 6 else -0.25 if i < 8 else 0.0) for i in range(20)}
        g = A.signflip(list(vals.values()), "greater", "k")["p"]
        l_ = A.signflip(list(vals.values()), "less", "k")["p"]
        r = A.run_test("H2a", A.QWEN, "c", vals, "two_sided", n_boot=200)
        self.assertAlmostEqual(r["p"], min(1.0, 2 * min(g, l_)))

    def test_signflip_monte_carlo_fallback_and_key(self):
        vals = [0.1234567 + 0.001 * i for i in range(25)]  # no common denominator <= 10,000
        r1 = A.signflip(vals, "greater", "20261103|H3|qwen|x", n_mc=2000)
        r2 = A.signflip(vals, "greater", "20261103|H3|qwen|x", n_mc=2000)
        self.assertEqual(r1["method"], "monte_carlo")
        self.assertEqual(r1["p"], r2["p"])
        self.assertAlmostEqual(r1["p"], 1 / 2001)

    def test_signflip_size_under_sparse_symmetric_null(self):
        rng = random.Random("size-signflip")
        rej = {0.05: 0, 0.05 / 12: 0}
        n = 600
        for _ in range(n):
            v = [rng.choice([-0.5, 0.0, 0.0, 0.0, 0.5]) for _ in range(28)]
            p = A.signflip(v, "greater", "k")["p"]
            for a in rej:
                rej[a] += p < a
        self.assertLessEqual(rej[0.05] / n, 0.05)
        self.assertLessEqual(rej[0.05 / 12] / n, 0.05 / 12 + 0.003)

    def test_tost_se_zero_uses_sign_test(self):
        vals = {("f", i): 0.0 for i in range(28)}
        r = A.run_test("H1-eq", A.QWEN, "locks", vals, "tost", 0.25, n_boot=500)
        self.assertTrue(all(s["method"] == "sign_test_se0" for s in r["sides"]))
        self.assertAlmostEqual(r["p"], 0.5 ** 28)

    def test_tost_size_at_the_boundary_pooled(self):
        # T3b B1(a): pooled over 3 models, control 0, contended adds exactly delta = 0.15. The percentile bootstrap
        # was liberal (0.08 at alpha = 0.05 in the scratchpad simulation); bootstrap-t held 0.05.
        rng = random.Random("size-boundary")
        n, rej_t, rej_p = 400, 0, 0
        for i in range(n):
            per = [cluster_d(rng, 0.0, A.DELTA_POOLED) for _ in range(3)]
            pooled = A.intersect({f"m{j}": per[j] for j in range(3)})
            pt, pp = tost_p(pooled, A.DELTA_POOLED, f"sim|{i}")
            rej_t += pt < 0.05
            rej_p += pp < 0.05
        self.assertLessEqual(rej_t / n, 0.075)
        self.assertGreaterEqual(rej_p, rej_t)

    def test_tost_size_at_the_boundary_cell(self):
        rng = random.Random("size-boundary-cell")
        n, rej = 400, 0
        for i in range(n):
            pt, _ = tost_p(cluster_d(rng, 0.02, A.DELTA_CELL), A.DELTA_CELL, f"simc|{i}")
            rej += pt < 0.05
        self.assertLessEqual(rej / n, 0.075)

    def test_tost_power_when_failures_are_rare(self):
        # The SE* = 0 rule: a resample with no spread is studentized by the observed SE. With the +/-inf rule of
        # the T3b draft, power at a common rate of 0.01 to 0.03 was about 0.5 to 0.6 whatever delta.
        rng = random.Random("power-rare")
        n, rej = 200, 0
        for i in range(n):
            pt, _ = tost_p(cluster_d(rng, 0.02, 0.0), A.DELTA_CELL, f"simp|{i}")
            rej += pt < 0.05
        self.assertGreaterEqual(rej / n, 0.85)

    def test_tost_power_at_reference_rate(self):
        rng = random.Random("power-ref")
        n, rej = 200, 0
        for i in range(n):
            pt, _ = tost_p(cluster_d(rng, 0.05, 0.0), A.DELTA_CELL, f"simr|{i}")
            rej += pt < 0.05 / 9
        self.assertGreaterEqual(rej / n, 0.70)  # 0.82 in the scratchpad simulation (B = 1,000, 1,000 runs)

    def test_bootstrap_rng_key_and_draws(self):
        vals = {("f", i): float(i % 2) for i in range(5)}
        key = A.rng_key("H1-eq", A.QWEN, "locks")
        self.assertEqual(key, "20261103|H1eq|qwen|locks")
        self.assertEqual(A.rng_key("H1-eq", A.POOLED, "locks", 9), "20261103|H1eq|pooled|locks|sens9")
        bs = A.boot(vals, key, 50)
        draws = random.Random(key).choices(range(5), k=250)
        x = [vals[k] for k in sorted(vals, key=str)]
        self.assertIn(A.mean([x[j] for j in draws[:5]]), bs["means"])

    def test_pooled_uses_the_intersection(self):
        a = {("f", 0): 1.0, ("f", 1): 0.0, ("f", 2): 0.5}
        b = {("f", 1): 1.0, ("f", 2): 0.0}
        self.assertEqual(A.intersect({"a": a, "b": b}), {("f", 1): 0.5, ("f", 2): 0.25})

    def test_family_level(self):
        vals = {(f, i): 1.0 for f in FAMS for i in range(2)}
        self.assertAlmostEqual(A.family_level(vals, "greater", None), 1 / 128)
        vals = {(f, i): 0.01 * (j % 3) for j, f in enumerate(FAMS) for i in range(2)}
        p = A.family_level(vals, "tost", 0.25)
        self.assertLess(p, 0.001)
        self.assertAlmostEqual(A.t_sf(2.0, 6), 0.0462, places=4)


def _t(test, model, config, p, status="tested", **kw):
    d = {"id": f"{test}|{A.SHORT.get(model, model)}|{config}", "test": test, "model": model, "config": config,
         "status": status, "p": p, "kind": "tost" if test.endswith("-eq") else "greater", "mc": False}
    d.update(kw)
    return d


class HolmAndClaims(unittest.TestCase):
    def test_holm(self):
        self.assertEqual(A.holm([0.01, 0.04, None, 0.03]), [0.03, 0.06, None, 0.06])

    def test_gate_open_and_closed(self):
        cells = [_t("H1-eq", m, c, 0.001) for m in A.CONFIRMATORY for c in A.H1_CONFIGS]
        open_ = [_t("H1-eq", A.POOLED, c, p) for c, p in zip(A.H1_CONFIGS, (0.001, 0.02, 0.04))] + [dict(x) for x in cells]
        A.apply_holm(open_)
        self.assertTrue(all(t["gate_open"] for t in open_))
        self.assertTrue(all(t["reject"] for t in open_ if t["model"] != A.POOLED))
        self.assertEqual(open_[0]["holm_family_size"], 3)
        self.assertEqual(open_[5]["holm_family_size"], 9)
        closed = [_t("H1-eq", A.POOLED, c, p) for c, p in zip(A.H1_CONFIGS, (0.001, 0.02, 0.06))] + [dict(x) for x in cells]
        A.apply_holm(closed)
        self.assertFalse(closed[2]["reject"])
        self.assertTrue(all(t["status"] == "not_tested_gate_closed" and t["reject"] is None
                            for t in closed if t["model"] != A.POOLED))
        # a stage-1 test that is not tested closes the gate too
        nt = [_t("H1-eq", A.POOLED, c, 0.001) for c in A.H1_CONFIGS[:2]] + \
             [_t("H1-eq", A.POOLED, "all_available", None, status="not_tested")] + [dict(x) for x in cells]
        A.apply_holm(nt)
        self.assertFalse(nt[0]["gate_open"])

    def test_holm_levels_and_mc_recompute_flag(self):
        fam = [_t("H3", m, "x", p, kind="greater") for m, p in zip(A.CONFIRMATORY, (0.001, 0.02, 0.2))]
        A.apply_holm(fam)
        self.assertEqual([round(t["holm_level"], 4) for t in fam], [round(0.05 / 3, 4), 0.025, 0.05])
        t = _t("H3", A.QWEN, "x", 0.0167, kind="greater", mc=True)
        self.assertTrue(A._mc_near(t, 0.05 / 3))
        self.assertFalse(A._mc_near(dict(t, mc=False), 0.05 / 3))

    def _pair(self, base, model, eq_rej, diff_rej, **eq_kw):
        eq = _t(f"{base}-eq", model, "locks", 0.01, reject=eq_rej, delta=0.25, estimate=0.1, ci90_t=[0.0, 0.2], **eq_kw)
        diff = _t(f"{base}-diff", model, "locks", 0.01, reject=diff_rej, estimate=0.1, ci95=[0.01, 0.2])
        return eq, diff

    def test_claim_table(self):
        cal = [_t("H1cal-diff", A.QWEN, "none", 0.001, reject=True)]
        for (e, d), want in (((True, False), "bounded"), ((False, True), "worse"),
                             ((True, True), "worse_within_delta"), ((False, False), "inconclusive")):
            tests = list(self._pair("H1", A.QWEN, e, d)) + cal
            A.read_cells(tests)
            self.assertEqual(tests[0]["reading"], want)
        tests = list(self._pair("H1", A.QWEN, True, False)) + cal
        A.read_cells(tests)
        self.assertIn("did not add integrity failures beyond ±0.25", tests[0]["claim"])
        tests = list(self._pair("H1", A.QWEN, True, True)) + cal
        A.read_cells(tests)
        self.assertIn("by less than 0.25", tests[0]["claim"])

    def test_claim_needs_calibration_q_and_sensitivity_9(self):
        tests = list(self._pair("H1", A.QWEN, True, False)) + [_t("H1cal-diff", A.QWEN, "none", 0.2, reject=False)]
        A.read_cells(tests)
        self.assertEqual(tests[0]["reading"], "uninformative")
        tests = list(self._pair("H4", A.QWEN, True, False, q=0.2))
        A.read_cells(tests)
        self.assertEqual(tests[0]["reading"], "uninformative")
        tests = list(self._pair("H4", A.QWEN, True, False, q=0.5))
        A.read_cells(tests)
        self.assertEqual(tests[0]["reading"], "bounded")
        self.assertAlmostEqual(tests[0]["implied_bound_reacting_share"], 0.5)
        s9 = [dict(tests[0], reject=False)]
        tests = list(self._pair("H4", A.QWEN, True, False, q=0.5))
        A.read_cells(tests, s9_tests=s9)
        self.assertEqual(tests[0]["reading"], "inconclusive")
        self.assertIn("eq_not_robust_to_sensitivity_9", tests[0]["flags"])


# ----------------------------------------------------------------------------------------------- (b) planted effects


class PlantedEffects(unittest.TestCase):
    def setUp(self):
        self.r = planted_result()
        self.t = by_id(self.r)

    def test_eligibility_applies_to_h4_only(self):
        cells = self.r["eligibility"]["cells"]
        self.assertTrue(cells[f"{A.QWEN}|locks"]["eligible"])
        self.assertFalse(cells[f"{A.SONNET}|locks"]["eligible"])  # rate 1.0
        self.assertEqual(self.t["H1-eq|Sonnet|locks"]["status"], "tested")
        self.assertEqual(self.t["H4-eq|Sonnet|locks"]["status"], "not_eligible")
        self.assertIn("Sonnet", self.t["H1-eq|pooled|locks"]["models"])
        self.assertNotIn("Sonnet", self.t["H4-eq|pooled|locks"]["models"])

    def test_h1_gate_opens_and_cells_bounded(self):
        for c in A.H1_CONFIGS:
            self.assertTrue(self.t[f"H1-eq|pooled|{c}"]["reject"], c)
            self.assertTrue(self.t[f"H1-eq|pooled|{c}"]["gate_open"])
        fam = [t for t in self.r["tests"] if t.get("holm_family") == "H1-eq/stage2"]
        self.assertEqual(len(fam), 9)
        for cell in ("H1-eq|Qwen|cas_available", "H1-eq|Haiku|locks", "H1-eq|Qwen|all_available"):
            self.assertTrue(self.t[cell]["reject"], cell)
            self.assertEqual(self.t[cell]["reading"], "bounded", cell)

    def test_h1_worse_cell(self):
        self.assertFalse(self.t["H1-eq|Qwen|locks"]["reject"])
        self.assertTrue(self.t["H1-diff|Qwen|locks"]["reject"])
        self.assertEqual(self.t["H1-eq|Qwen|locks"]["reading"], "worse")
        self.assertAlmostEqual(self.t["H1-diff|Qwen|locks"]["estimate"], 16 * 0.5 / 28)
        self.assertEqual(self.t["H1-diff|Qwen|locks"]["holm_family_size"], 12)
        self.assertFalse(self.t["H1-diff|Qwen|cas_available"]["reject"])

    def test_h1_calibration_gate(self):
        self.assertTrue(self.t["H1cal-diff|Qwen|none"]["reject"])
        self.assertIsNone(self.t["H1cal-diff|Qwen|none"]["p_adj"])  # no Holm
        self.assertFalse(self.t["H1cal-diff|Sonnet|none"]["reject"])
        self.assertTrue(self.t["H1-eq|Sonnet|cas_available"]["reject"])
        self.assertEqual(self.t["H1-eq|Sonnet|cas_available"]["reading"], "uninformative")
        self.assertIn("uninformative_calibration", self.t["H1-eq|Sonnet|cas_available"]["flags"])
        self.assertTrue(self.t["H1cal-diff|pooled|none"]["reject"])

    def test_h4_gate_closed(self):
        # pooled H4 under locks over the eligible models (Qwen 0, Haiku 0.5) is 0.25 > 0.15: not equivalent, the gate
        # closes, and no per-cell H4 equivalence is tested; H4-diff still reads.
        self.assertFalse(self.t["H4-eq|pooled|locks"]["reject"])
        self.assertEqual(self.t["H4-eq|Qwen|locks"]["status"], "not_tested_gate_closed")
        self.assertEqual(self.t["H4-eq|Haiku|locks"]["reading"], "worse")
        self.assertIn("eq_not_tested_gate_closed", self.t["H4-eq|Haiku|locks"]["flags"])
        self.assertIn("leakage_total_effect_of_template", self.t["H4-eq|Haiku|locks"]["flags"])
        self.assertEqual(self.t["H4-eq|Qwen|locks"]["reading"], "inconclusive")
        self.assertAlmostEqual(self.t["H4-eq|Qwen|locks"]["q"], 1.0)
        self.assertAlmostEqual(self.t["H4-eq|Qwen|all_available"]["q"], 0.0)

    def test_h2_difference(self):
        self.assertTrue(self.t["H2a|Qwen|all_available-locks"]["reject"])
        self.assertGreater(self.t["H2a|Qwen|all_available-locks"]["estimate"], 0.4)
        self.assertFalse(self.t["H2a|Sonnet|all_available-locks"]["reject"])
        self.assertEqual(self.t["H2a|Qwen|all_available-locks"]["holm_family_size"], 12)

    def test_h3_aware_effect(self):
        self.assertTrue(self.t["H3|Qwen|locks+all_available"]["reject"])
        self.assertTrue(self.t["H3|Haiku|locks+all_available"]["reject"])
        self.assertFalse(self.t["H3|Sonnet|locks+all_available"]["reject"])
        self.assertEqual(self.t["H3|Qwen|locks+all_available"]["n_clusters"], 7 * K_PROBE)
        self.assertIn("raised first-reply lock use", self.t["H3|Qwen|locks+all_available"]["claim"])

    def test_leakage(self):
        lk = self.r["checks"]["leakage"]
        self.assertTrue(lk["Haiku"]["leaks"])
        self.assertFalse(lk["Qwen"]["leaks"])
        self.assertEqual(lk["Qwen"]["n_units"], 2 * 2 * 7 * K_PROBE)  # (config, aware, family, instance)
        self.assertEqual(lk["Gpt"]["status"], "not_run")  # no probes

    def test_descriptive_models_and_extension(self):
        g = self.t["H1-eq|Gpt|locks"]
        self.assertEqual(g["status"], "descriptive")
        self.assertIsNone(g["p"])
        self.assertEqual(g["n_clusters"], 6)  # the extension instance is not used
        self.assertEqual(self.r["selection"]["block"].get("priority_4"), 1)

    def test_checks_pass_on_clean_planted(self):
        ck = self.r["checks"]
        self.assertTrue(ck["exposure"]["ok"])
        self.assertTrue(ck["isolation"]["ok"])
        self.assertTrue(ck["lock_safety"]["ok"])
        self.assertEqual(self.r["reads_overlap"]["Qwen|locks|contended"]["share"], 1.0)

    def test_holm_consistent_interval(self):
        t = self.t["H1-eq|Qwen|cas_available"]
        lo, hi = t["ci_holm_t"]
        self.assertLessEqual(lo, t["ci90_t"][0] + 1e-12)
        self.assertGreaterEqual(hi, t["ci90_t"][1] - 1e-12)


# ----------------------------------------------------------------------------------------------- (d) exclusions


class Exclusions(unittest.TestCase):
    """A small planted grid (Qwen + Haiku, locks) with planted problem rows. The harness never re-runs."""

    @classmethod
    def setUpClass(cls):
        base = [t for m in (A.QWEN, A.HAIKU) for t in plant_episodes(m, "locks") + plant_probes(m)]
        extra = []
        cls.key = {}

        def mod(model, fam, i, s, arm, **ag):
            t = next(x for x in base if x["model"] == model and x["config"] == "locks" and not x["probe"]
                     and x["task"]["family"] == fam and x["task"]["instance"] == i and x["seed"] == s
                     and (x["task"]["factory"].endswith("_ctrl")) == (arm == "control"))
            t2 = json.loads(json.dumps(t))
            for a in t2["agents"]:
                if "end" in ag:
                    t2["score"]["agents"][a]["end_reason"] = ag["end"]
                if "stop" in ag:
                    t2["agents"][a]["turns"][-1]["stop_reason"] = ag["stop"]
                if "host" in ag:
                    for tu in t2["agents"][a]["turns"]:
                        tu["served_host"] = ag["host"]
                if "fs" in ag:
                    t2["score"]["fs_nonserializable"] = ag["fs"]
            if "started" in ag:
                t2["run_info"]["started_utc"] = ag["started"]
            return t, t2

        F = FAMS
        # 1. truncated agent -> episode and partner excluded
        t, t2 = mod(A.HAIKU, F[0], 0, 0, "contended", end="truncated")
        base.remove(t); extra.append(t2); cls.key["trunc"] = (A.HAIKU, "locks", 0, F[0], 0, 0, False)
        # 2. refusal in the control -> excluded with its partner
        t, t2 = mod(A.HAIKU, F[1], 0, 0, "control", stop="refusal")
        base.remove(t); extra.append(t2); cls.key["refusal"] = (A.HAIKU, "locks", 0, F[1], 0, 0, False)
        # 3. two transcripts for one episode id: the earliest is used
        t, t2 = mod(A.HAIKU, F[2], 1, 0, "contended", fs=True, started="2026-11-11T00:00:00Z")
        extra.append(t2); cls.key["dup"] = (A.HAIKU, "locks", 0, F[2], 1, 0, False)
        # 4. a written Qwen episode not served by Alibaba -> excluded with partner
        t, t2 = mod(A.QWEN, F[3], 0, 0, "contended", host="deepinfra")
        base.remove(t); extra.append(t2); cls.key["host"] = (A.QWEN, "locks", 0, F[3], 0, 0, False)
        # 5. content_filter on a probe -> probe and its other-arm partner excluded
        pr = next(x for x in base if x["model"] == A.QWEN and x["probe"] and x["config"] == "locks" and not x["concurrency_aware_prompt"]
                  and x["task"]["family"] == F[5] and x["task"]["instance"] == 0 and not x["task"]["factory"].endswith("_ctrl"))
        pr2 = json.loads(json.dumps(pr)); pr2["agents"]["a0"]["turns"][-1]["stop_reason"] = "content_filter"
        base.remove(pr); extra.append(pr2)
        # 6. never data: a dry-run row, an unregistered config, a different study
        never = [dict(base[0], episode_id="x1", dry_run=True), dict(base[1], episode_id="x2", config="all_peer_informed"),
                 dict(base[2], episode_id="x3", study=1)]
        # 7. cap_truncated (score5): failed and an agent ended turn_cap (fulfilled or not)
        t, t2 = mod(A.HAIKU, F[6], 1, 1, "contended", fs=True)
        t2["score"]["outcome"] = "failed"
        t2["score"]["cap_truncated"] = True
        t2["score"]["agents"]["a1"].update(end_reason="turn_cap", fulfilled=True)
        base.remove(t); extra.append(t2)
        # 8. a control agent coded as exposed (scorer bug) and a control with a cross-agent edge
        t, t2 = mod(A.QWEN, F[6], 3, 1, "control")
        t2["score"]["agents"]["a0"].update(first_contention_call=4, contention_signals=1)
        t2["score"]["cross_agent_edges"] = 1
        base.remove(t); extra.append(t2)
        # 9. Round 4: an agent that ended content_filter (score5.REFUSAL_ENDS; the last turn's stop says nothing)
        t, t2 = mod(A.HAIKU, F[4], 2, 1, "contended", end="content_filter")
        base.remove(t); extra.append(t2); cls.key["filter_end"] = (A.HAIKU, "locks", 0, F[4], 2, 1, False)
        cls.trs = base + extra + never
        plan = plant_plan(models=(A.QWEN, A.HAIKU), gpt=False)
        cls.res = A.run_analysis(as_inputs(cls.trs), plan, None, allow_dry_run=False, n_boot=500, src5_dir=None)
        cls.sel = A.select([A.normalize(t, f"p{i}", None, False, want_cap24=False) for i, t in enumerate(cls.trs)], plan, False)

    def excluded(self):
        return {tuple(e["key"]): e["reason"] for e in self.res["selection"]["excluded"]}

    def k(self, name, arm):
        m, c, aw, fam, i, s, probe = self.key[name]
        return tuple(map(str, (m, c, aw, fam, i, s, probe, arm)))

    def test_agent_error_excludes_pair(self):
        ex = self.excluded()
        self.assertEqual(ex[self.k("trunc", "contended")], "agent_error_or_refusal")
        self.assertEqual(ex[self.k("trunc", "control")], "partner_of:agent_error_or_refusal")
        self.assertEqual(ex[self.k("refusal", "control")], "agent_error_or_refusal")
        self.assertEqual(ex[self.k("refusal", "contended")], "partner_of:agent_error_or_refusal")
        self.assertEqual(ex[self.k("filter_end", "contended")], "agent_error_or_refusal")
        self.assertEqual(ex[self.k("filter_end", "control")], "partner_of:agent_error_or_refusal")

    def test_duplicate_transcripts_use_the_earliest(self):
        m, c, aw, fam, i, s, probe = self.key["dup"]
        self.assertEqual(self.sel["main"][(m, c, aw, fam, i, s, probe, "contended")]["fs"], 0)
        self.assertEqual(self.res["selection"]["counts"]["duplicate_transcripts_ignored"], 1)

    def test_wrong_host(self):
        ex = self.excluded()
        self.assertEqual(ex[self.k("host", "contended")], "wrong_host")
        self.assertEqual(ex[self.k("host", "control")], "partner_of:wrong_host")

    def test_probe_content_filter(self):
        ex = self.excluded()
        key = tuple(map(str, (A.QWEN, "locks", 0, FAMS[5], 0, 0, True, "contended")))
        self.assertEqual(ex[key], "agent_error_or_refusal")
        self.assertEqual(ex[key[:-1] + ("control",)], "partner_of:agent_error_or_refusal")

    def test_counts_per_arm_and_never_data(self):
        c = self.res["selection"]["counts"]
        self.assertEqual(c["agent_error_or_refusal"], 4)
        self.assertEqual(c["wrong_host"], 1)
        self.assertEqual(c["partner_excluded"], 5)
        by_arm = self.res["selection"]["excluded_by_cell_and_arm"]
        self.assertEqual(by_arm["Haiku|locks|aware0|episode|control|agent_error_or_refusal"], 1)
        self.assertEqual(by_arm["Haiku|locks|aware0|episode|contended|partner"], 1)
        nd = self.res["selection"]["never_data"]
        self.assertEqual(nd, {"dry_run": 1, "not_study2": 1, "unregistered_config:all_peer_informed": 1})

    def test_sensitivity_3_keeps_excluded(self):
        self.assertEqual(len(self.sel["as_is"]), len(self.sel["main"]) + 10)  # 5 excluded + 5 partners

    def test_sensitivity_9_scores_against_equivalence(self):
        s9, n = A.against_equivalence_sample(self.sel)
        self.assertEqual(n, 5)
        m, c, aw, fam, i, s, probe = self.key["trunc"]
        r = s9[(m, c, aw, fam, i, s, probe, "contended")]
        self.assertEqual(r["fs"], 1)
        self.assertTrue(all(a["lock"] and a["prim"] for a in r["agents"].values()))  # both agents errored
        m, c, aw, fam, i, s, probe = self.key["refusal"]
        self.assertEqual(s9[(m, c, aw, fam, i, s, probe, "contended")]["fs"], 1)
        self.assertEqual(self.res["sensitivity"]["s9_against_equivalence"]["pairs_scored_against"], 5)

    def test_cap_truncated_sensitivity(self):
        self.assertEqual(self.res["selection"]["flags"]["cap_truncated_episodes"], 1)
        self.assertEqual(self.res["sensitivity"]["s2_cap_truncated_excluded"]["dropped"], 2)  # with its partner

    def test_checks_fire(self):
        ck = self.res["checks"]
        self.assertEqual(ck["exposure"]["control_agents_exposed"], 1)
        self.assertFalse(ck["exposure"]["ok"])
        self.assertEqual(ck["isolation"]["control_episodes_with_cross_agent_edges"], 1)
        self.assertFalse(ck["isolation"]["ok"])

    def test_cap24_not_available_without_ledgers(self):
        self.assertEqual(self.res["sensitivity"]["s1_cap24"]["status"], "not_available")


class Round3Measures(unittest.TestCase):
    """H4 / reactive measures are score5's columns, read as stored (Round 3 / Round 4 reconciliation)."""

    def view(self, **kw):
        a = agent(**kw)
        return A.agent_view(a["score"], a["raw"])

    def test_own_reply_first_conflict_counts_as_protecting(self):
        # an acquire (or CAS) whose own response is the first signal: score5 counts it as before contention (<=)
        v = self.view(lock=True, fp="lock", fp_call=3, fc_call=3)
        self.assertTrue(v["exposed"])
        self.assertIs(v["pbc"], True)
        self.assertFalse(v["at_risk"] or v["reacting"] or v["lock_after"])

    def test_reacting_and_lock_after_contention(self):
        v = self.view(lock=True, fp="lock", fp_call=5, fc_call=2)
        self.assertTrue(v["at_risk"] and v["reacting"] and v["lock_after"])
        never = self.view(fc_call=2)  # exposed, never protected: at risk, not reacting
        self.assertTrue(never["at_risk"])
        self.assertFalse(never["reacting"] or never["lock_after"])
        # reacting is score5's protect_before_contention is False, as stored (not recomputed from the call indices)
        a = agent(lock=True, fp="lock", fp_call=5, fc_call=2)
        a["score"]["protect_before_contention"] = True
        self.assertFalse(A.agent_view(a["score"], a["raw"])["reacting"])

    def test_pre_round3_scores_are_refused(self):
        a = agent(fc_call=2)
        del a["score"]["lock_after_contention"]
        with self.assertRaises(A.ScorerVersionError):
            A.agent_view(a["score"], a["raw"])
        a = agent(fc_call=2)
        a["score"]["contention_signals"] = 0
        with self.assertRaises(A.ScorerVersionError):
            A.agent_view(a["score"], a["raw"])

    def test_field_names_are_score5s(self):
        import dataclasses
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src5"))
        try:
            import score5
        finally:
            sys.path.pop(0)
        names = {f.name for f in dataclasses.fields(score5.AgentScore)}
        self.assertTrue(set(A.ROUND3_AGENT_FIELDS) <= names, set(A.ROUND3_AGENT_FIELDS) - names)
        self.assertEqual(set(A.REFUSAL_ENDS), set(score5.REFUSAL_ENDS))
        self.assertEqual(set(A.AGENT_ERROR_ENDS), set(score5.ERROR_ENDS))


class Budget(unittest.TestCase):
    def test_balance_windows_and_external_stop(self):
        d = tempfile.mkdtemp(prefix="a5bal_", dir=SCRATCH if os.path.isdir(SCRATCH) else None)
        os.makedirs(os.path.join(d, "n2-openrouter"))
        with open(os.path.join(d, "n2-openrouter", "spend.jsonl"), "w") as f:
            for t, c in (("2026-11-10T01:00:00Z", 2.0), ("2026-11-10T02:00:00Z", 1.0), ("2026-11-12T01:00:00Z", 5.0)):
                f.write(json.dumps({"at_utc": t, "cost_usd": c, "provider_family": "openrouter"}) + "\n")
        rows = [BAL.entry("before", {"data": {"usage": 10.0, "limit_remaining": 30.0}}, "2026-11-10T00:00:00Z"),
                BAL.entry("after", {"data": {"usage": 17.5, "limit_remaining": 22.5}}, "2026-11-10T03:00:00Z", lane_exit=4)]
        with open(os.path.join(d, "openrouter_balance.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        rep = A.balance_report(d)
        w = rep["windows"][0]
        self.assertAlmostEqual(w["study2_spend_usd"], 3.0)
        self.assertAlmostEqual(w["others_spend_usd"], 4.5)
        self.assertTrue(w["stopped_by_external_cause"])
        self.assertEqual(A.balance_report(None)["status"], "no_base")


# ----------------------------------------------------------------------------------------------- (a), (c) dry run


def cli(*args, hashseed="0"):
    env = dict(ENV, PYTHONHASHSEED=hashseed)
    return subprocess.run([sys.executable, os.path.join(HERE, "analyze5.py"), *args], env=env, capture_output=True,
                          text=True, timeout=3600)


class DryRunEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # never skipped: the registered checks need the dry run of the final harness (set A5_DRY_BASE)
        assert os.path.isdir(DRY_BASE), f"no dry-run output at {DRY_BASE}"
        e = cli("eligibility", "--base", DRY_BASE, "--allow-dry-run", "--plan", DRY_PLAN, "--out", OUT)
        assert e.returncode == 0, e.stderr
        cls.run1 = cli("analyze", "--base", DRY_BASE, "--allow-dry-run", "--plan", DRY_PLAN, "--out", OUT,
                       "--eligibility", os.path.join(OUT, "eligibility.json"), hashseed="0")
        cls.tmp = tempfile.mkdtemp(prefix="a5det_", dir=SCRATCH if os.path.isdir(SCRATCH) else None)
        cls.run2 = cli("analyze", "--base", DRY_BASE, "--allow-dry-run", "--plan", DRY_PLAN, "--out", cls.tmp,
                       "--eligibility", os.path.join(OUT, "eligibility.json"), hashseed="12345")

    def test_a_end_to_end_outputs(self):
        self.assertEqual(self.run1.returncode, 0, self.run1.stderr)
        with open(os.path.join(OUT, "results.json")) as f:
            r = json.load(f)
        with open(os.path.join(OUT, "numbers.tex")) as f:
            tex = f.read()
        self.assertTrue(r["dry_run"])
        self.assertEqual(r["constants"]["B"], 10_000)
        self.assertEqual(r["constants"]["delta_cell"], 0.25)
        self.assertEqual(r["constants"]["delta_pooled"], 0.15)
        self.assertGreater(sum(t["status"] == "tested" for t in r["tests"]), 20)
        self.assertIn(r"\newcommand{\SiiDryRunFlag}{1}", tex)
        self.assertIn(r"\newcommand{\SiiHoneDiffQwenCasP}", tex)
        names = [ln.split("}")[0] for ln in tex.splitlines() if ln.startswith(r"\newcommand")]
        self.assertEqual(len(names), len(set(names)))  # no duplicate macro
        self.assertEqual(r["eligibility"]["source"], "file")
        self.assertTrue(r["checks"]["isolation"]["ok"])
        self.assertTrue(r["checks"]["lock_safety"]["ok"])
        self.assertEqual(r["checks"]["lock_safety"]["episodes_not_checked"], 0)
        self.assertEqual(r["sensitivity"]["s1_cap24"]["status"], "done")
        for key in ("s1_cap24", "s2_cap_truncated_excluded", "s3_exclusions_kept", "s9_against_equivalence"):
            self.assertEqual(r["sensitivity"][key]["changed_verdicts"], [], key)  # nothing changes on the dry run
        # Sensitivity 8 does change verdicts on the dry run, and should: the fake models lock and then write without
        # reading, so fs_nonserializable fails under locks / all_available while the basis DSG (read edges) has no
        # cycle. H1 now runs for every model (no eligibility rule), so these cells are tested.
        ch = r["sensitivity"]["s8_h1_dsg_basis_cycle"]["changed_verdicts"]
        self.assertTrue(ch)
        self.assertTrue(all(c["id"].split("|")[2] in ("locks", "all_available") for c in ch))
        self.assertEqual(r["selection"]["never_data"], {})
        self.assertTrue(all("_bs" not in t and "_values" not in t for t in r["tests"]))
        for t in r["tests"]:
            if t["test"] in ("H1-eq", "H4-eq") and t["status"] in ("tested", "not_tested_gate_closed"):
                self.assertIn("claim", t, t["id"])

    def test_c_deterministic(self):
        self.assertEqual(self.run2.returncode, 0, self.run2.stderr)
        for name in ("results.json", "numbers.tex"):
            with open(os.path.join(OUT, name), "rb") as f1, open(os.path.join(self.tmp, name), "rb") as f2:
                self.assertEqual(f1.read(), f2.read(), name)

    def test_a_eligibility_reads_probes_only(self):
        with open(os.path.join(OUT, "eligibility.json")) as f:
            e = json.load(f)
        self.assertEqual(e["selection"]["block"].get("priority_1"), None)
        # the final plan has no Fable probe block (K = 0): its cells are not computed; every probed cell is
        for c in e["cells"].values():
            self.assertEqual(c["computed"], c["registered_probes"] > 0, (c["model"], c["config"]))
            self.assertEqual(c["model"] == A.FABLE, c["registered_probes"] == 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
