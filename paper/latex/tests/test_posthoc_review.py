"""Unit tests for the POST HOC review helpers (posthoc_review.py) and the reference-policy runner.

    python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LATEX = os.path.dirname(HERE)
sys.path.insert(0, LATEX)
sys.dont_write_bytecode = True

import posthoc_review as PR  # noqa: E402
import reference_policies as RP  # noqa: E402


def call(seq, agent, tool, rid, step=None, status=200, committed=False, effect_seq=None, read_version=None, args=None,
         lease=None):
    return {"seq": seq, "agent_id": agent, "tool": tool, "record_id": rid, "step": step if step is not None else seq,
            "status": status, "committed": committed, "effect_seq": effect_seq, "read_version": read_version,
            "args": args or {}, "lease_expires_at": lease}


def eff(seq, agent, rid, old_v, new_v):
    return {"seq": seq, "agent_id": agent, "record_id": rid, "old_version": old_v, "new_version": new_v,
            "old_value": 0, "new_value": 1}


class TestHelpers(unittest.TestCase):
    def test_cp_lower_all(self):
        self.assertAlmostEqual(PR.cp_lower_all(28), 0.05 ** (1 / 28))
        self.assertAlmostEqual(round(PR.cp_lower_all(28), 2), 0.90)
        self.assertAlmostEqual(round(PR.cp_lower_all(16), 2), 0.83)
        self.assertAlmostEqual(round(PR.cp_lower_all(8), 2), 0.69)
        self.assertIsNone(PR.cp_lower_all(0))

    def test_icc1(self):
        self.assertAlmostEqual(PR.icc1([[1, 1], [0, 0]]), 1.0)
        self.assertIsNone(PR.icc1([[1, 1], [1, 1]]))
        self.assertLess(PR.icc1([[1, 0], [1, 0], [0, 1]]), 0.0)
        self.assertIsNone(PR.icc1([[1]]))

    def test_lost_update_detected(self):
        # a0 and a1 both read v1; a0 writes v1->v2; a1 writes blind on basis v1 (v2->v3): a0's effect is lost
        calls = [call(1, "a0", "get_record", "r", read_version=1), call(2, "a1", "get_record", "r", read_version=1),
                 call(3, "a0", "update_record", "r", committed=True, effect_seq=1),
                 call(4, "a1", "update_record", "r", committed=True, effect_seq=2)]
        effects = [eff(1, "a0", "r", 1, 2), eff(2, "a1", "r", 2, 3)]
        self.assertEqual(PR.lost_agents(calls, effects), {"a0"})

    def test_fresh_later_write_does_not_lose(self):
        calls = [call(1, "a0", "get_record", "r", read_version=1), call(2, "a0", "update_record", "r", committed=True, effect_seq=1),
                 call(3, "a1", "get_record", "r", read_version=2), call(4, "a1", "update_record", "r", committed=True, effect_seq=2)]
        effects = [eff(1, "a0", "r", 1, 2), eff(2, "a1", "r", 2, 3)]
        self.assertEqual(PR.lost_agents(calls, effects), set())

    def test_lease_class(self):
        held = [call(1, "a0", "acquire_lock", "r", step=1, lease=10), call(2, "a0", "update_record", "r", step=5)]
        self.assertEqual(PR.lease_class(held, "a0", ["r"])[0], "held")
        expired = [call(1, "a0", "acquire_lock", "r", step=1, lease=3), call(2, "a0", "update_record", "r", step=5)]
        self.assertEqual(PR.lease_class(expired, "a0", ["r"])[0], "expired")
        self.assertIsNone(PR.lease_class([call(1, "a0", "update_record", "r")], "a0", ["r"]))
        released = [call(1, "a0", "acquire_lock", "r", step=1, lease=30), call(2, "a0", "release_lock", "r", step=2),
                    call(3, "a0", "update_record", "r", step=5)]
        self.assertEqual(PR.lease_class(released, "a0", ["r"])[0], "other")

    def test_same_reply(self):
        tu = lambda rid: {"type": "tool_use", "name": "update_record", "input": {"record_id": rid}}  # noqa: E731
        self.assertTrue(PR.same_reply_both_legs({"turns": [{"content": [tu("a"), tu("b")]}]}, ["a", "b"]))
        self.assertFalse(PR.same_reply_both_legs({"turns": [{"content": [tu("a")]}, {"content": [tu("b")]}]}, ["a", "b"]))


class TestReferencePolicies(unittest.TestCase):
    def test_registered_schedule_and_h1_floor(self):
        sched = RP.registered_schedule()
        self.assertEqual(sched["start_jitter"], 0)
        self.assertGreater(sched["read_write_gap"], 0)
        data = RP.run()
        rows = {(r["policy"], r["config"], r["scope"]): r for r in data["rows"]}
        for p in ("naive", "rereader"):
            r = rows[(p, "none", "all")]
            self.assertEqual(r["non_serializable"], r["episodes"])  # H1 cannot fail for these policies
        # H4a can fail in principle: the naive writer still overwrites stale data under cas_available
        r = rows[("naive", "cas_available", "single_record")]
        self.assertEqual(r["stale_overwrite"], r["episodes"])
        self.assertEqual(rows[("careful_cas", "cas_available", "single_record")]["stale_overwrite"], 0)
        for r in data["rows"]:
            self.assertEqual(r["non_serializable"], r["stale_overwrite"] + r["partial_action"] + r["write_skew"])


if __name__ == "__main__":
    unittest.main()


class TestReview2Helpers(unittest.TestCase):
    """Pure helpers added after the 2026-11-03 reviews."""

    def test_signflip_exact(self):
        import posthoc_review as PR
        self.assertAlmostEqual(PR.signflip_exact([0.1] * 7, 0.0, "greater"), 1 / 128)
        self.assertEqual(PR.signflip_exact([0.0] * 7, 0.0, "greater"), 1.0)
        self.assertAlmostEqual(PR.signflip_exact([0.2, -0.1], 0.0, "greater"), 0.5)
        self.assertAlmostEqual(PR.signflip_exact([0.1] * 3, 0.25, "less"), 1 / 8)

    def test_floor_rounding_of_bounds(self):
        import make_numbers4 as MN
        self.assertEqual(MN.ffloor(0.05 ** (1 / 28)), "0.89")
        self.assertEqual(MN.ffloor(0.05 ** (1 / 7)), "0.65")
        self.assertEqual(MN.ffloor(0.05 ** (1 / 14)), "0.80")
