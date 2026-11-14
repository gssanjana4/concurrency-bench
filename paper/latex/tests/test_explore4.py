"""Tests for explore4.py (EXPLORATORY analyses): exact coding rules on synthetic call logs, and consistency on the
dry-run analysis (ANALYSIS_DIR or ../analysis_dry). Also checks that confirmatory outputs are never written."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LATEX = os.path.dirname(HERE)
PAPER = os.path.dirname(LATEX)
sys.path.insert(0, LATEX)
sys.dont_write_bytecode = True
ANALYSIS = os.environ.get("ANALYSIS_DIR", os.path.join(PAPER, "analysis_dry"))
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")

import explore4 as E  # noqa: E402


def call(seq, agent, tool, rid=None, status=200, reason=None, committed=False, ev=None, read_version=None,
         effect_seq=None, step=None, lease=None):
    args = {"record_id": rid} if rid else {}
    if ev is not None:
        args["expected_version"] = ev
    return {"seq": seq, "agent_id": agent, "tool": tool, "record_id": rid, "status": status, "reason": reason,
            "committed": committed, "args": args, "read_version": read_version, "effect_seq": effect_seq,
            "step": seq if step is None else step, "lease_expires_at": lease}


R, S = "inventory:x", "account:y"
END = {"fulfilled": False, "end_reason": "returned", "valid_at_end": True}


class TestPostRejectionCodes(unittest.TestCase):
    def code(self, after, config="cas_available", end=END, writes=(R,), first_reason="version_conflict", first_tool="update_record"):
        calls = [call(1, "a0", "get_record", R, read_version=1),
                 call(2, "a1", "update_record", R, committed=True, ev=1, effect_seq=1),
                 call(3, "a0", first_tool, R, status=409, reason=first_reason, ev=1 if first_tool == "update_record" else None)]
        return E.code_post_rejection(calls + after, "a0", set(writes), config, end)

    def test_not_eligible(self):
        calls = [call(1, "a0", "get_record", R), call(2, "a0", "update_record", R, committed=True, ev=1)]
        self.assertIsNone(E.code_post_rejection(calls, "a0", {R}, "cas_available", END))
        # invalid_version is not a concurrency rejection
        calls = [call(1, "a0", "update_record", R, status=409, reason="invalid_version", ev=5)]
        self.assertIsNone(E.code_post_rejection(calls, "a0", {R}, "cas_available", END))
        # rejection on a record outside intent.writes
        self.assertIsNone(self.code([], writes=(S,)))

    def test_reread_retry(self):
        self.assertEqual(self.code([call(4, "a0", "get_record", R, read_version=2), call(5, "a0", "update_record", R, ev=2)]),
                         "reread_retry")

    def test_stale_retry_same_version(self):
        self.assertEqual(self.code([call(4, "a0", "update_record", R, status=409, reason="version_conflict", ev=1)]), "stale_retry")

    def test_stale_retry_reread_not_used(self):
        self.assertEqual(self.code([call(4, "a0", "get_record", R, read_version=3), call(5, "a0", "update_record", R, ev=2)]),
                         "stale_retry")

    def test_version_from_error(self):
        self.assertEqual(self.code([call(4, "a0", "update_record", R, ev=2, committed=True)]), "version_from_error")

    def test_bypass(self):
        self.assertEqual(self.code([call(4, "a0", "update_record", R, committed=True)]), "bypass")
        self.assertEqual(self.code([call(4, "a0", "update_record", R, status=428, reason="missing_expected_version")],
                                   config="cas_required"), "bypass")

    def test_locks_retry_without_version(self):
        # under locks there is no expected_version: re-read then write = reread_retry; write again at once = stale_retry
        self.assertEqual(self.code([call(4, "a0", "get_record", R, read_version=2), call(5, "a0", "update_record", R)],
                                   config="locks", first_reason="locked_by_other"), "reread_retry")
        self.assertEqual(self.code([call(4, "a0", "update_record", R)], config="locks", first_reason="locked_by_other"), "stale_retry")

    def test_claim_conflict_retry(self):
        self.assertEqual(self.code([call(4, "a0", "claim", R)], first_reason="claim_conflict", first_tool="claim"), "stale_retry")

    def test_other_record(self):
        self.assertEqual(self.code([call(4, "a0", "update_record", S, committed=True)], writes=(R, S)), "other_record")

    def test_end_codes(self):
        self.assertEqual(self.code([]), "giveup_valid")
        self.assertEqual(self.code([], end={"fulfilled": False, "end_reason": "returned", "valid_at_end": False}), "giveup_invalid")
        self.assertEqual(self.code([], end={"fulfilled": False, "end_reason": "turn_cap", "valid_at_end": True}), "cut_off")
        self.assertEqual(self.code([], end={"fulfilled": True, "end_reason": "returned", "valid_at_end": False}), "already_fulfilled")
        # reads and non-write calls after the rejection do not change an end code
        self.assertEqual(self.code([call(4, "a0", "get_record", R, read_version=2), call(5, "a0", "list_effects")]), "giveup_valid")

    def test_codes_are_the_declared_set(self):
        self.assertEqual(set(E.E4_CODES), {"reread_retry", "stale_retry", "version_from_error", "bypass", "other_record",
                                           "giveup_valid", "giveup_invalid", "cut_off", "already_fulfilled"})


class TestWriteSkewFlags(unittest.TestCase):
    CAP, A, B = "budget:cap", "budget:spend-a0", "budget:spend-a1"

    def flags(self, calls, effects):
        return E.ws_agent(calls, effects, "a0", (self.CAP, self.A, self.B), {self.A}, lambda v: str(v))

    def test_promotion(self):
        calls = [call(1, "a0", "get_record", self.B, read_version=1),
                 call(2, "a0", "update_record", self.B, ev=1, committed=True, effect_seq=1)]
        effects = [{"seq": 1, "old_value": "10", "new_value": "10"}]
        f = self.flags(calls, effects)
        self.assertTrue(f["promote"])
        self.assertFalse(f["committed"])
        # a rejected promotion counts; a blind write to another record does not
        self.assertTrue(self.flags([call(1, "a0", "update_record", self.CAP, status=409, reason="version_conflict", ev=1)], [])["promote"])
        self.assertFalse(self.flags([call(1, "a0", "update_record", self.B, committed=True, effect_seq=1)],
                                    [{"seq": 1, "old_value": "1", "new_value": "1"}])["promote"])

    def test_verify_and_compensate(self):
        calls = [call(1, "a0", "get_record", self.B, read_version=1),
                 call(2, "a0", "update_record", self.A, ev=1, committed=True, effect_seq=1),
                 call(3, "a0", "get_record", self.B, read_version=2),
                 call(4, "a0", "update_record", self.A, ev=2, committed=True, effect_seq=2)]
        effects = [{"seq": 1, "old_value": "0", "new_value": "40"}, {"seq": 2, "old_value": "40", "new_value": "0"}]
        f = self.flags(calls, effects)
        self.assertEqual(f, {"promote": False, "committed": True, "verify": True, "compensate": True})
        # read before the own commit is not verification; a second write that does not restore is not compensation
        calls2 = [calls[0], calls[1], call(4, "a0", "update_record", self.A, ev=2, committed=True, effect_seq=2)]
        effects2 = [effects[0], {"seq": 2, "old_value": "40", "new_value": "30"}]
        self.assertEqual(self.flags(calls2, effects2), {"promote": False, "committed": True, "verify": False, "compensate": False})


class TestLockAndCasFlags(unittest.TestCase):
    def test_lock_cover_release(self):
        acq = call(1, "a0", "acquire_lock", R, lease=10, step=1)
        w = call(2, "a0", "update_record", R, committed=True, step=2)
        rel = call(3, "a0", "release_lock", R)
        self.assertEqual(E.lock_agent([acq, w, rel], "a0", {R}), {"cover": True, "release": True})
        self.assertEqual(E.lock_agent([acq, w], "a0", {R}), {"cover": True, "release": False})
        # lock on one of two write records only; expired lease; no lock at all
        self.assertFalse(E.lock_agent([acq, w], "a0", {R, S})["cover"])
        self.assertFalse(E.lock_agent([call(1, "a0", "acquire_lock", R, lease=2, step=1), call(2, "a0", "update_record", R, step=5)],
                                      "a0", {R})["cover"])
        self.assertIsNone(E.lock_agent([w], "a0", {R}))
        self.assertIsNone(E.lock_agent([call(1, "a0", "acquire_lock", R, status=423, reason="lock_held")], "a0", {R}))

    def test_uncontended_writes(self):
        calls = [call(1, "a0", "get_record", R), call(2, "a0", "update_record", R, ev=1, committed=True),
                 call(3, "a1", "get_record", R), call(4, "a0", "update_record", R, committed=True),
                 call(5, "a1", "update_record", R, committed=True)]
        # a0@2: no foreign write since its read -> counted, carries ev; a0@4: same read (seq 1), a0's own write
        # in between is not foreign -> counted, no ev; a1@5: a0 wrote at 4 after a1's read -> excluded
        self.assertEqual(E.uncontended_writes(calls), [True, False])


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


class TestDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(os.path.join(ANALYSIS, "confirmatory.json")):
            subprocess.run([sys.executable, os.path.join(LATEX, "run_analysis.py"), "--dry-run", "--out", ANALYSIS],
                           check=True, cwd=LATEX, env=ENV)
        protected = [os.path.join(ANALYSIS, f) for f in E.PROTECTED if os.path.exists(os.path.join(ANALYSIS, f))]
        cls.before = {p: sha(p) for p in protected}
        subprocess.run([sys.executable, os.path.join(LATEX, "explore4.py"), "--analysis", ANALYSIS], check=True, cwd=LATEX, env=ENV,
                       capture_output=True)
        cls.after = {p: sha(p) for p in protected}
        cls.ex = json.load(open(os.path.join(ANALYSIS, E.OUT_NAME)))
        cls.numbers = json.load(open(os.path.join(ANALYSIS, "numbers.json")))

    def test_confirmatory_outputs_untouched(self):
        self.assertTrue(self.before)
        self.assertEqual(self.before, self.after)

    def test_refuses_protected_names(self):
        with tempfile.TemporaryDirectory() as d:
            for name in E.PROTECTED:
                with self.assertRaises(SystemExit):
                    E.write(d, {}, name)

    def test_labelled_exploratory(self):
        self.assertTrue(self.ex["label"].startswith("EXPLORATORY"))
        for k in ("E1", "E3", "E4", "E5", "E6", "E7", "E8", "E10"):
            self.assertIn("EXPLORATORY", self.ex[k]["label"], k)
        self.assertTrue(self.ex["dry_run"])
        self.assertEqual(self.ex["missing_transcripts"], 0)

    def test_e1_identity_and_giveup_matches_analyze4(self):
        idx = {(r["model"], r["config"], r["aware"], r["metric"]): r for r in self.numbers["rates"]
               if r["scope"] == "contended" and r["n_agents"] == 2}
        n = 0
        for r in self.ex["E1"]["rows"]:
            self.assertTrue(r["identity_ok"])
            if r["scope"] != "contended":
                continue
            ab = idx[(r["model"], r["config"], r["aware"], "abandoned")]
            gu = idx[(r["model"], r["config"], r["aware"], "unnecessary_give_up")]
            self.assertEqual((r["giveup"]["num"], r["giveup"]["den"]), (gu["numerator"], gu["denominator"]))
            if gu["estimate"] is not None:
                self.assertAlmostEqual(r["giveup"]["est"], gu["estimate"], places=12)
            self.assertAlmostEqual(r["fulfil"]["est"], 1 - ab["estimate"], places=12)
            n += 1
        self.assertGreater(n, 0)

    def test_e4_shares_sum_to_one_and_match_score4(self):
        for r in self.ex["E4"]["rows"]:
            if r["n_eligible"]:
                self.assertEqual(sum(c["num"] for c in r["codes"].values()), r["n_eligible"])
                self.assertAlmostEqual(sum(c["est"] for c in r["codes"].values() if c["est"] is not None), 1.0, places=9)
        # giveup_valid agents are a subset of score4's unnecessary_give_up agents (checked on transcripts)
        prov = json.load(open(os.path.join(ANALYSIS, "provenance.json")))
        rows = E.load(prov["analyzed_paths"])
        checked = 0
        for r in rows:
            if r["config"] != "cas_available" or r["n_agents"] != 2 or r["category"] == "control":
                continue
            tr = json.load(open(E.transcript_path(r)))
            for agent, intent in E.intents_of(tr).items():
                s = tr["score"]["agents"][agent]
                if E.code_post_rejection(tr["ledger"]["calls"], agent, set(intent.writes), r["config"], s) == "giveup_valid":
                    self.assertTrue(s["unnecessary_give_up"], r["episode_id"])
                    checked += 1
            if checked > 50:
                break
        self.assertGreater(checked, 0)

    def test_e6_loto_full_matches_analyze4_and_templates_average_to_cell(self):
        self.assertTrue(all(r["matches_analyze4"] in (True, None) for r in self.ex["E6"]["loto"]))
        self.assertTrue(any(r["matches_analyze4"] for r in self.ex["E6"]["loto"]))
        idx = {(r["model"], r["config"]): r for r in self.numbers["rates"] if r["scope"] == "contended" and r["n_agents"] == 2
               and r["aware"] == 0 and r["metric"] == "non_serializable"}
        per = {}
        for t in self.ex["E6"]["tpl"]:
            per.setdefault((t["model"], t["config"]), []).append(t["nonser"]["est"])
        for key, v in per.items():
            self.assertEqual(len(v), 7)
            self.assertAlmostEqual(sum(v) / len(v), idx[key]["estimate"], places=12)

    def test_e5_and_e7_shapes(self):
        cfgs = {r["config"] for r in self.ex["E5"]["rows"]}
        self.assertTrue({"none", "cas_available", "locks", "messages"} <= cfgs)
        for r in self.ex["E7"]["rows"]:
            for k in ("cover", "release", "leak"):
                self.assertLessEqual(r[k], r["n_lockers"])


@unittest.skipUnless(os.path.exists(os.path.join(PAPER, "make_anon_artifact.py")), "anonymizer not shipped (review artifact)")
class TestAnonArtifact(unittest.TestCase):
    def test_artifact_freeze_override_is_exact(self):
        """The artifact's pipeline accepts the redacted frozen files only through FREEZE_OVERRIDE.json, byte-exactly."""
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "artifact")
            r = subprocess.run([sys.executable, os.path.join(PAPER, "make_anon_artifact.py"), "--out", out,
                                "--registration-date", "2026-11-01"], capture_output=True, text=True, env=ENV)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            ov = json.load(open(os.path.join(out, "FREEZE_OVERRIDE.json")))["redacted_frozen_files"]
            self.assertEqual(sorted(e["file"] for e in ov),
                             ["providers.py", "run4.py", "run_full.sh", "run_pilot.sh", "tests_model4.py"])
            for f in ("paper/latex/explore4.py", "paper/latex/make_numbers4.py", "paper/latex/posthoc_review.py",
                      "paper/latex/deviations.csv", "paper/audit/H5_AUDIT.csv", "src4_batch/batch_driver.py",
                      "src_sql/analyze_sql.py", "ARTIFACT_README.md"):
                self.assertTrue(os.path.exists(os.path.join(out, f)), f)
            chk = ("import sys; sys.path.insert(0, '.'); import pipeline_common as P; "
                   "print('PROBLEMS', len(P.verify_freeze()[1]))")
            r = subprocess.run([sys.executable, "-c", chk], cwd=os.path.join(out, "paper", "latex"), capture_output=True,
                               text=True, env=dict(ENV, SRC4=os.path.join(out, "src4")))
            self.assertIn("PROBLEMS 0", r.stdout, r.stderr)
            with open(os.path.join(out, "src4", "run4.py"), "a") as f:
                f.write("\n# tampered\n")
            r = subprocess.run([sys.executable, "-c", chk], cwd=os.path.join(out, "paper", "latex"), capture_output=True,
                               text=True, env=dict(ENV, SRC4=os.path.join(out, "src4")))
            self.assertIn("PROBLEMS 1", r.stdout, r.stderr)

    def test_artifact_redacts_and_keeps_logic(self):
        sys.path.insert(0, PAPER)
        import make_anon_artifact as AA
        src4 = AA.SRC4
        before = {f: sha(os.path.join(d, f)) for d, _, fs in os.walk(src4) for f in fs if "__pycache__" not in d}
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "artifact")
            r = subprocess.run([sys.executable, os.path.join(PAPER, "make_anon_artifact.py"), "--out", out,
                                "--registration-date", "2026-11-01"], capture_output=True, text=True, env=ENV)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(AA.scan_paths([os.path.join(out, "src4"), os.path.join(out, "preregistration")]), [])
            changes = open(os.path.join(out, "ANON_CHANGES.md")).read()
            self.assertIn("2026-11-01", changes)
            for f in ("src4/providers.py", "src4/run_full.sh", "src4/run_pilot.sh", "src4/tests_model4.py",
                      "preregistration/PREREGISTRATION.md"):
                self.assertIn(f"### `{f}`", changes)
                self.assertIn(sha(os.path.join(out, f)), changes)
            # pattern assembled from pieces so that this test file itself carries no identity string
            self.assertNotRegex(changes.lower(), "sanj" + "ana|idempotency" + "bench|desk" + "top/")
            # every non-redacted frozen file is byte-identical, and redacted files differ only in listed lines
            for name, want, ok in AA.freeze_rows(os.path.join(out, "src4")):
                if f"### `src4/{name}`" not in changes:
                    self.assertTrue(ok, name)
            orig = open(os.path.join(src4, "providers.py")).read().split("\n")
            red = open(os.path.join(out, "src4", "providers.py")).read().split("\n")
            self.assertEqual(len(orig), len(red))
            diff = [i + 1 for i, (a, b) in enumerate(zip(orig, red)) if a != b]
            self.assertEqual(diff, [219, 220])
            # redacted code still compiles
            for d, _, fs in os.walk(os.path.join(out, "src4")):
                for f in fs:
                    if f.endswith(".py"):
                        compile(open(os.path.join(d, f)).read(), f, "exec")
        after = {f: sha(os.path.join(d, f)) for d, _, fs in os.walk(src4) for f in fs if "__pycache__" not in d}
        self.assertEqual(before, after, "src4 must never change")

    def test_refuses_output_inside_src4(self):
        sys.path.insert(0, PAPER)
        import make_anon_artifact as AA
        r = subprocess.run([sys.executable, os.path.join(PAPER, "make_anon_artifact.py"), "--out", os.path.join(AA.SRC4, "x")],
                           capture_output=True, text=True, env=ENV)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(AA.SRC4, "x")))


if __name__ == "__main__":
    unittest.main()
