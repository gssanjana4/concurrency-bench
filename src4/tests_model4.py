"""Tests for the model loop (model_agent4), the grid runner (run4) and preflight.

All tests use the deterministic fake provider: no network, no API keys.

    cd src4 && python3 -m unittest tests_model4 -v
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import shutil
import tempfile
import types
import unittest
from typing import Any, Dict, List

import model_agent4 as M
import preflight
import providers
import run4
import tasks4 as T
from scheduler import ScheduleConfig, run_episode
from score4 import score_episode
from world4 import world_config

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_PROVIDERS = "/mnt/user-data/uploads/Desktop/idempotencybench/src/providers.py"

TEST_PRICES = M.PriceTable({
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.1, "confirmed": True},
    "fake-model": {"input": 1.0, "output": 5.0, "confirmed": True},
})


def tool(name: str, **inp: Any) -> Dict[str, Any]:
    return {"type": "tool_use", "name": name, "input": inp}


def text(s: str) -> Dict[str, Any]:
    return {"type": "text", "text": s}


def turn_policy(turns: List[List[Dict[str, Any]]]):
    """Fake policy replaying a fixed list of turns (then a final text)."""

    def policy(system, tools, messages):
        k = sum(1 for m in messages if m["role"] == "assistant")
        return turns[k] if k < len(turns) else [text("finished")]

    return policy


def run_with_policy(policy, task=None, config="none", turn_cap=12, provider=None, gap=0, seed=0, **rc_kw):
    task = task or T.inventory_last_unit(2)
    wc = world_config(config)
    provider = provider or M.FakeProvider(policy)
    rc = M.ModelRunConfig(model="fake-model", provider=provider, world_config=wc, turn_cap=turn_cap, **rc_kw)
    records: Dict[str, Dict[str, Any]] = {}
    ep = run_episode(task, M.model_agent_spec(rc, records), wc, ScheduleConfig(seed=seed, turn_cap=turn_cap, read_write_gap=gap))
    return ep, records


def quiet(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rv = fn(*a, **kw)
    return rv, buf.getvalue()


class TestModelAgentLoop(unittest.TestCase):
    def test_multi_tool_calls_are_queued_one_per_step(self):
        policy = turn_policy([
            [tool("get_record", record_id="inventory:widget"), tool("list_effects"), tool("get_record", record_id="inventory:widget")],
        ])
        ep, recs = run_with_policy(policy)
        # one call per agent per round: no agent has two calls in the same step
        steps = [(c.agent_id, c.step) for c in ep.ledger.calls]
        self.assertEqual(len(steps), len(set(steps)))
        self.assertEqual(len(ep.ledger.calls), 6)
        for a, rec in recs.items():
            self.assertEqual(rec["multi_tool_turns"], 1)
            self.assertEqual(rec["max_tool_calls_in_turn"], 3)
            self.assertEqual(rec["completions"], 2)
            self.assertEqual([e["queue_index"] for e in rec["executions"]], [0, 1, 2])
            # all three results go back to the model in a single user turn, in order
            results = rec["messages"][2]
            self.assertEqual(results["role"], "user")
            self.assertEqual([r["tool_use_id"] for r in results["content"]], ["fake_0", "fake_1", "fake_2"])
        # agents interleave: a0's queued calls are not executed back-to-back in the global log
        a0_seqs = [c.seq for c in ep.ledger.calls if c.agent_id == "a0"]
        self.assertNotEqual(a0_seqs, list(range(a0_seqs[0], a0_seqs[0] + 3)))

    def test_queued_calls_see_other_agents_writes(self):
        # a0 and a1 both queue [read, write 0] in one turn: the queued write is blind to the other agent
        policy = turn_policy([[tool("get_record", record_id="inventory:widget"), tool("update_record", record_id="inventory:widget", value=0)]])
        ep, _ = run_with_policy(policy)
        self.assertEqual(len(ep.ledger.effects), 2)
        self.assertTrue(score_episode(ep).invariant_violation)

    def test_no_tool_call_terminates_and_records_final_text(self):
        ep, recs = run_with_policy(turn_policy([[text("Nothing to do.")]]))
        self.assertEqual(len(ep.ledger.calls), 0)
        for a in ("a0", "a1"):
            end = ep.ledger.end_for(a)
            self.assertEqual(end.reason, "returned")
            self.assertEqual(end.report, "Nothing to do.")
            self.assertEqual(recs[a]["final_text"], "Nothing to do.")
            self.assertEqual(recs[a]["completions"], 1)
            self.assertFalse(recs[a]["truncated"])

    def test_truncated_reply_is_flagged(self):
        class Truncating(M.FakeProvider):
            def complete(self, *a, **kw):
                c = super().complete(*a, **kw)
                c.stop_reason = "length"
                return c

        _, recs = run_with_policy(None, provider=Truncating(turn_policy([[text("I will now")]])))
        self.assertTrue(recs["a0"]["truncated"])

    def test_malformed_args_are_tool_errors_and_commit_nothing(self):
        # what providers.blocks_from_openai_message produces for unparseable JSON arguments
        bad = providers.blocks_from_openai_message(
            {"content": None, "tool_calls": [{"id": "c1", "function": {"name": "update_record", "arguments": '{"record_id": "inventory:widget", "value": '}}]}
        )[0]
        self.assertIn("_unparsed_arguments", bad["input"])
        policy = turn_policy([
            [{"type": "tool_use", "name": "update_record", "input": bad["input"]}],
            [tool("update_record", record_id="inventory:widget")],          # missing 'value'
            [tool("claim", record_id="inventory:widget", holder="x", extra=1)],  # unsupported argument
            [tool("acquire_lock", record_id="inventory:widget", lease_steps=3)],  # tool not offered under 'none'
        ])
        ep, recs = run_with_policy(policy)
        self.assertEqual(ep.ledger.effects, [])
        self.assertEqual(ep.store.values()["inventory:widget"], 1)
        statuses = [c.status for c in ep.ledger.calls if c.agent_id == "a0"]
        self.assertEqual(statuses, [400, 400, 400, 404])
        self.assertTrue(all(not c.committed for c in ep.ledger.calls))
        rec = recs["a0"]
        self.assertEqual(len(rec["invalid_calls"]), 4)
        self.assertTrue(rec["executions"][0]["malformed_args"])
        self.assertEqual(rec["executions"][0]["args"], bad["input"])
        # the model is told about the error and the episode continues to a normal end
        first_result = rec["messages"][2]["content"][0]
        self.assertTrue(first_result["is_error"])
        self.assertIn("400", first_result["content"])
        self.assertEqual(ep.ledger.end_for("a0").reason, "returned")
        score_episode(ep)  # the ledger stays scoreable

    def test_turn_cap(self):
        always = lambda s, t, m: [tool("get_record", record_id="inventory:widget")]  # noqa: E731
        ep, recs = run_with_policy(always, turn_cap=5)
        for a in ("a0", "a1"):
            end = ep.ledger.end_for(a)
            self.assertEqual(end.reason, "turn_cap")
            self.assertEqual(end.turns, 5)
            self.assertEqual(len(ep.ledger.calls_for(a)), 5)
            # the (cap+1)-th completion is what reveals the agent wanted to continue
            self.assertEqual(recs[a]["completions"], 6)
            self.assertEqual(len(recs[a]["executions"]), 5)

    def test_turn_cap_counts_tool_calls_not_completions(self):
        burst = lambda s, t, m: [tool("get_record", record_id="inventory:widget")] * 4  # noqa: E731
        ep, recs = run_with_policy(burst, turn_cap=6)
        self.assertEqual(len(ep.ledger.calls_for("a0")), 6)
        self.assertEqual(ep.ledger.end_for("a0").reason, "turn_cap")
        self.assertEqual(recs["a0"]["completions"], 2)
        # the queued calls that never ran are recorded
        self.assertEqual(len(recs["a0"]["unexecuted_tool_calls"]), 2)

    def test_default_turn_cap_is_12(self):
        self.assertEqual(M.DEFAULT_TURN_CAP, 12)

    def test_provider_failure_aborts_episode(self):
        class Boom(M.FakeProvider):
            def complete(self, *a, **kw):
                raise RuntimeError("OpenRouter HTTP 500: upstream")

        with self.assertRaises(M.ProviderFailure):
            run_with_policy(None, provider=Boom())

    def test_system_prompt_and_aware_flag(self):
        task = T.seat_same(2)
        for aware in (False, True):
            wc = world_config("cas_available+messages", concurrency_aware_prompt=aware)
            rc = M.ModelRunConfig(model="fake", provider=M.FakeProvider(), world_config=wc)
            recs: Dict[str, Any] = {}
            run_episode(task, M.model_agent_spec(rc, recs), wc, ScheduleConfig(seed=0, turn_cap=12))
            sys_text = recs["a0"]["system"]
            self.assertIn("You are agent a0.", sys_text)
            self.assertIn(task.intents["a0"].describe(), sys_text)
            self.assertIn("Agents you can message: a1.", sys_text)
            self.assertEqual("Other agents may be reading" in sys_text, aware)
            self.assertLess(len(sys_text), 400)  # short system prompt (cost)

    def test_tools_match_world_schema(self):
        seen = {}

        def policy(system, tools, messages):
            seen["tools"] = tools
            return [text("done")]

        run_with_policy(policy, config="cas_required+locks")
        from world4 import CoordinationConfig, tool_schemas
        self.assertEqual(seen["tools"], tool_schemas(CoordinationConfig.from_names("cas_required+locks")))


class RecordingProvider(M.FakeProvider):
    def __init__(self, name, policy=None):
        super().__init__(policy)
        self.name = name
        self.calls = []

    def complete(self, model, system, tools, messages, max_tokens, temperature):
        self.calls.append({"system": system, "tools": tools, "temperature": temperature, "max_tokens": max_tokens})
        return super().complete(model, system, tools, messages, max_tokens, temperature)


class TestCachingAndCost(unittest.TestCase):
    def test_anthropic_gets_cache_control_on_system_and_last_tool(self):
        prov = RecordingProvider("anthropic", turn_policy([[tool("get_record", record_id="inventory:widget")]]))
        run_with_policy(None, provider=prov, config="locks")
        call = prov.calls[0]
        self.assertIsInstance(call["system"], list)
        self.assertEqual(call["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(call["tools"][-1]["cache_control"], {"type": "ephemeral"})
        self.assertTrue(all("cache_control" not in t for t in call["tools"][:-1]))
        self.assertEqual(call["temperature"], 0.0)
        # identical cached prefix across agents (tools) -> cache hits are possible
        self.assertEqual(prov.calls[0]["tools"], prov.calls[-1]["tools"])

    def test_openrouter_request_left_as_is(self):
        prov = RecordingProvider("openrouter")
        run_with_policy(None, provider=prov)
        self.assertIsInstance(prov.calls[0]["system"], str)
        self.assertTrue(all("cache_control" not in t for t in prov.calls[0]["tools"]))

    def test_no_cache_flag(self):
        prov = RecordingProvider("anthropic")
        run_with_policy(None, provider=prov, prompt_caching=False)
        self.assertIsInstance(prov.calls[0]["system"], str)

    def test_openrouter_reported_cost_wins(self):
        comp = providers.Completion(blocks=[], provider="openrouter", model_requested="openrouter:x", model_served="x",
                                    temperature_requested=0.0, temperature_effective="unverified",
                                    usage={"input": 1000, "output": 1000}, provider_meta={"cost": 0.0123})
        cost, src = M.completion_cost("claude-haiku-4-5", comp, {"input": 1000, "output": 1000}, TEST_PRICES)
        self.assertEqual((cost, src), (0.0123, "reported"))

    def test_anthropic_cache_tokens_priced_separately(self):
        usage = {"input": 1_000_000, "output": 1_000_000, "cache_write": 1_000_000, "cache_read": 1_000_000}
        self.assertAlmostEqual(TEST_PRICES.token_cost("claude-haiku-4-5-20251001", usage), 1.0 + 5.0 + 1.25 + 0.1)
        self.assertIsNone(TEST_PRICES.token_cost("unknown-model", usage))

    def test_usage_probe_reads_cache_tokens_through_shared_provider(self):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest("anthropic SDK not installed")

        class FakeMessages:
            def create(self, **kw):
                self.kw = kw
                return types.SimpleNamespace(
                    content=[types.SimpleNamespace(type="text", text="hi")], model="claude-haiku-4-5-20251001",
                    stop_reason="end_turn",
                    usage=types.SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=700, cache_creation_input_tokens=300))

        fake_client = types.SimpleNamespace(messages=FakeMessages())
        probe = M.UsageProbeClient(fake_client)
        prov = providers.AnthropicProvider(client=probe)
        comp = prov.complete("claude-haiku-4-5-20251001", [{"type": "text", "text": "s", "cache_control": {"type": "ephemeral"}}], [], [{"role": "user", "content": "x"}], 64, 0.0)
        usage = M.normalized_usage(comp, probe)
        self.assertEqual(usage, {"input": 10, "output": 5, "cache_read": 700, "cache_write": 300})
        cost, src = M.completion_cost(comp.model_requested, comp, usage, TEST_PRICES)
        self.assertEqual(src, "price_table")
        self.assertAlmostEqual(cost, (10 * 1.0 + 5 * 5.0 + 700 * 0.1 + 300 * 1.25) / 1e6)
        self.assertEqual(fake_client.messages.kw["temperature"], 0.0)

    def test_spend_tracker_persists_and_caps(self):
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "spend.jsonl")
            s = M.SpendTracker(path, max_usd=1.0)
            s.record({"cost_usd": 0.6})
            self.assertAlmostEqual(M.SpendTracker(path).total, 0.6)
            with self.assertRaises(M.BudgetExceeded):
                s.record({"cost_usd": 0.5})
            self.assertAlmostEqual(M.SpendTracker(path).total, 1.1)  # the overshooting call is still logged
        finally:
            shutil.rmtree(d)

    def test_prices_json_is_marked_placeholder(self):
        prices = M.PriceTable.load(os.path.join(HERE, "prices.json"))
        for m in ("claude-haiku-4-5-20251001", "openrouter:qwen/qwen3.6-27b-20260422"):
            self.assertIsNotNone(prices.lookup(m), m)
            entry = prices.lookup(m)
            for k in ("input", "output", "cache_write", "cache_read"):
                self.assertIsInstance(entry[k], (int, float))
            self.assertIn("confirmed", entry)


class GridTestBase(unittest.TestCase):
    MODELS = "claude-haiku-4-5-20251001,openrouter:qwen/qwen3.6-27b-20260422"

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.prices = os.path.join(self.dir, "prices.json")
        with open(self.prices, "w") as f:
            json.dump({"models": TEST_PRICES.models | {"openrouter:qwen/qwen3.6-27b": {"input": 0.5, "output": 2.5, "confirmed": True}}}, f)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def grid(self, *extra, out="out", policy=None, models=None):
        argv = ["--models", models or self.MODELS, "--configs", "none,cas_available", "--tasks",
                "inventory_last_unit,transfer_shared_source,budget_write_skew", "--agents", "2", "--seeds", "0,1",
                "--out", os.path.join(self.dir, out), "--prices", self.prices, "--dry-run", *extra]
        return quiet(run4.run_grid, argv, fake_policy=policy)

    def outdir(self, out="out"):
        return os.path.join(self.dir, out, "dry_run")

    def transcripts(self, out="out"):
        return sorted(os.listdir(os.path.join(self.outdir(out), "transcripts")))

    def rows(self, out="out"):
        with open(os.path.join(self.outdir(out), "results.csv"), newline="") as f:
            return list(csv.DictReader(f))


class TestRunner(GridTestBase):
    def test_grid_size_and_pilot_subset(self):
        (code, log) = self.grid()
        self.assertEqual(code, 0, log)
        self.assertEqual(len(self.transcripts()), 2 * 2 * 3 * 2)
        self.assertEqual(len(self.rows()), 24)
        # pilot covers every category, every intent type and every record kind
        tasks = [T.CATALOG[n](2) for n in run4.PILOT_TASKS]
        self.assertEqual({t.category for t in tasks}, set(T.CATEGORIES))
        self.assertEqual({t.kind for t in tasks}, {"inventory", "seat", "ticket", "account", "budget"})
        self.assertEqual({type(i).__name__ for t in tasks for i in t.intents.values()},
                         {"Decrement", "Claim", "Transfer", "GuardedSpend", "JointWithdraw"})
        self.assertEqual(run4.resolve_configs("all"), ["none", "reread_only", "cas_available", "cas_required", "locks", "messages"])

    def test_resume_skips_existing_episodes(self):
        calls = {"n": 0}

        def counting(system, tools, messages):
            calls["n"] += 1
            return M.scripted_policy(system, tools, messages)

        code, _ = self.grid(policy=counting)
        self.assertEqual(code, 0)
        first = calls["n"]
        self.assertGreater(first, 0)
        code, log = self.grid(policy=counting)
        self.assertEqual(code, 0)
        self.assertEqual(calls["n"], first)  # nothing re-run
        self.assertIn("done already: 24; to run: 0", log)
        # delete one transcript and its CSV row stays: only that episode reruns, no duplicate row
        victim = self.transcripts()[3]
        os.remove(os.path.join(self.outdir(), "transcripts", victim))
        rows_before = [r for r in self.rows() if r["episode_id"] + ".json" != victim]
        with open(os.path.join(self.outdir(), "results.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=run4.CSV_FIELDS)
            w.writeheader()
            w.writerows(rows_before)
        code, log = self.grid(policy=counting)
        self.assertIn("to run: 1", log)
        self.assertEqual(len(self.rows()), 24)
        self.assertEqual(len({r["episode_id"] for r in self.rows()}), 24)

    def test_resume_restores_missing_csv_row(self):
        self.grid()
        os.remove(os.path.join(self.outdir(), "results.csv"))
        code, log = self.grid()
        self.assertIn("to run: 0", log)
        self.assertEqual(len(self.rows()), 24)

    def test_cost_cap_stops_cleanly_before_an_episode(self):
        code, _ = self.grid()
        full_cost = sum(float(r["cost_usd"]) for r in self.rows())
        cap = full_cost / 3
        small_prior = ("--prior-input-tokens", "1", "--max-tokens", "1")
        code, log = self.grid("--max-usd", f"{cap:.6f}", *small_prior, out="capped")
        self.assertEqual(code, 2, log)
        self.assertIn("COST CAP: stopping before", log)
        self.assertIn("spend so far", log)
        spend = M.SpendTracker(os.path.join(self.outdir("capped"), "spend.jsonl")).total
        self.assertLessEqual(spend, cap)
        n = len(self.transcripts("capped"))
        self.assertGreater(n, 0)
        self.assertLess(n, 24)
        self.assertEqual(len(self.rows("capped")), n)
        # rerunning with the same cap does not run anything new
        code, log = self.grid("--max-usd", f"{cap:.6f}", *small_prior, out="capped")
        self.assertEqual(code, 2)
        self.assertEqual(len(self.transcripts("capped")), n)

    def test_hard_cap_aborts_episode_without_writing(self):
        # zero-estimate model: the pre-episode check passes, the in-episode guard must fire
        d = os.path.join(self.dir, "hard")
        os.makedirs(d)
        spend = M.SpendTracker(os.path.join(d, "spend.jsonl"), max_usd=1e-9)
        cell = run4.build_grid(["fake-model"], ["none"], ["inventory_last_unit"], [0], 2, [False])[0]
        with self.assertRaises(M.BudgetExceeded):
            run4.run_one(cell, M.FakeProvider(), None, {"read_write_gap": 0}, turn_cap=12, max_tokens=64,
                         temperature=0.0, prices=TEST_PRICES, spend=spend, dry_run=True)
        code, log = self.grid("--max-usd", "0.000001", models="fake-model", out="hard2")
        self.assertEqual(code, 2, log)
        self.assertEqual(self.transcripts("hard2"), [])

    def test_real_run_refuses_unconfirmed_prices(self):
        p = os.path.join(self.dir, "placeholder.json")
        with open(p, "w") as f:
            json.dump({"models": {"claude-haiku-4-5": {"input": 1, "output": 5, "confirmed": False}}}, f)
        code, log = quiet(run4.run_grid, ["--models", "claude-haiku-4-5-20251001", "--out", os.path.join(self.dir, "real"), "--prices", p])
        self.assertEqual(code, 1)
        self.assertIn("placeholder", log)
        code, log = quiet(preflight.main, ["--models", "claude-haiku-4-5-20251001", "--prices", p])
        self.assertEqual(code, 1)

    def test_dry_run_output_is_separate_from_real_output(self):
        self.grid()
        self.assertFalse(os.path.exists(os.path.join(self.dir, "out", "transcripts")))
        self.assertTrue(os.path.isdir(os.path.join(self.dir, "out", "dry_run", "transcripts")))

    def test_provider_failure_is_logged_and_episode_not_written(self):
        def flaky(system, tools, messages):
            if "Move" in system:
                raise RuntimeError("OpenRouter HTTP 503: try later")
            return M.scripted_policy(system, tools, messages)

        code, log = self.grid("--max-consecutive-failures", "100", policy=flaky)
        self.assertEqual(code, 3, log)
        self.assertEqual(len(self.transcripts()), 16)  # the 8 transfer episodes are missing
        with open(os.path.join(self.outdir(), "failures.jsonl")) as f:
            self.assertEqual(len(f.readlines()), 8)

    def test_credit_limit_stops(self):
        def broke(system, tools, messages):
            raise RuntimeError("OpenRouter HTTP 402: insufficient credits")

        code, log = self.grid(policy=broke)
        self.assertEqual(code, 4, log)

    def test_preflight_dry_run(self):
        code, log = quiet(preflight.main, ["--models", self.MODELS, "--prices", self.prices, "--dry-run",
                                           "--spend-log", os.path.join(self.dir, "pf", "spend.jsonl")])
        self.assertEqual(code, 0, log)
        self.assertIn("preflight ok", log)
        self.assertEqual(log.count("cost=$"), 2)
        self.assertGreater(M.SpendTracker(os.path.join(self.dir, "pf", "spend.jsonl")).total, 0)


class TestTranscripts(GridTestBase):
    def test_transcript_completeness(self):
        self.grid()
        tdir = os.path.join(self.outdir(), "transcripts")
        spend_total = M.SpendTracker(os.path.join(self.outdir(), "spend.jsonl")).total
        cost_sum = 0.0
        for fn in self.transcripts():
            with open(os.path.join(tdir, fn)) as f:
                tr = json.load(f)
            for key in ("episode_id", "model", "config", "task", "seed", "schedule", "generation", "agents",
                        "ledger", "final_store", "score", "totals", "concurrency_aware_prompt"):
                self.assertIn(key, tr, fn)
            self.assertEqual(set(tr["agents"]), {"a0", "a1"})
            self.assertEqual(tr["schedule"]["turn_cap"], M.DEFAULT_TURN_CAP)
            for a, rec in tr["agents"].items():
                # every executed call matches the ledger's call log for that agent, in order
                ledger_calls = [c for c in tr["ledger"]["calls"] if c["agent_id"] == a]
                self.assertEqual(len(rec["executions"]), len(ledger_calls))
                for ex, c in zip(rec["executions"], ledger_calls):
                    self.assertEqual(ex["tool"], c["tool"])
                    self.assertEqual(ex["response"], c["response"])
                # every tool_use in the history has exactly one tool_result
                uses = [b["id"] for m in rec["messages"] if m["role"] == "assistant" for b in m["content"] if b["type"] == "tool_use"]
                results = [b["tool_use_id"] for m in rec["messages"] if m["role"] == "user" and isinstance(m["content"], list) for b in m["content"]]
                self.assertEqual(uses, results)
                self.assertEqual(len(rec["turns"]), rec["completions"])
                for t in rec["turns"]:
                    self.assertIn("usage", t)
                    self.assertIn("cost_usd", t)
                    self.assertIn(t["cost_source"], ("reported", "price_table", "unpriced"))
                    self.assertIsNotNone(t["usage"]["input"])
                self.assertEqual(rec["final_text"], "Done.")
            self.assertEqual(len(tr["ledger"]["agent_ends"]), 2)
            self.assertEqual(set(tr["final_store"]), set(tr["task"]["initial"]))
            self.assertIn("non_serializable", tr["score"])
            cost_sum += tr["totals"]["cost_usd"]
        self.assertAlmostEqual(cost_sum, spend_total, places=9)

    def test_determinism_with_fake_provider(self):
        self.grid(out="r1")
        self.grid(out="r2")
        self.assertEqual(self.transcripts("r1"), self.transcripts("r2"))
        for fn in self.transcripts("r1"):
            trs = []
            for out in ("r1", "r2"):
                with open(os.path.join(self.outdir(out), "transcripts", fn)) as f:
                    tr = json.load(f)
                tr.pop("run_info")
                trs.append(json.dumps(tr, sort_keys=True))
            self.assertEqual(trs[0], trs[1], fn)
        self.assertEqual(self.rows("r1"), self.rows("r2"))

    def test_seed_changes_interleaving(self):
        policy = turn_policy([[tool("get_record", record_id="inventory:widget")], [tool("update_record", record_id="inventory:widget", value=0)]])
        orders = set()
        for seed in range(6):
            ep, _ = run_with_policy(policy, seed=seed)
            orders.add(tuple(c.agent_id for c in ep.ledger.calls))
        self.assertGreater(len(orders), 1)


class TestSharedProviderLayer(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(OLD_PROVIDERS), "previous benchmark's providers.py not present")
    def test_providers_py_identical_to_previous_benchmark(self):
        with open(OLD_PROVIDERS, "rb") as a, open(os.path.join(HERE, "providers.py"), "rb") as b:
            self.assertEqual(a.read(), b.read())


if __name__ == "__main__":
    unittest.main()
