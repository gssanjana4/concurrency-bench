"""Tests for the Gemini Batch API path (src4_batch). No network, no keys, no money.

Comparators:

* sync path  = frozen ``run4.run_grid`` (real-run mode) with ``run4.make_provider`` returning the frozen
  ``providers.OpenRouterProvider`` and its HTTP call answered by :class:`gemini_replay.SyncTransport`
  (same translation, one generateContent call per completion, fake Gemini model) -- the batch path must
  equal it except for timing fields;
* literal ``run4 --dry-run`` (FakeProvider) -- decisions, ledgers and scores must be identical;
* hand-written OpenRouter responses for the same cases -- the frozen provider must record the same thing.

    cd src4_batch && python3 -m unittest tests_gemini -v
"""

from __future__ import annotations

import collections
import contextlib
import copy
import io
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest import mock

import frozen
import model_agent4 as M
import providers
import run4
import world4
import batch_driver as BD
import gemini_batch as GB
import gemini_replay as GR
import gemini_translate as G
import gemini_preflight
from fake_api import canonical
from fake_gemini import FakeGeminiAPI, check_request, fake_response, http_client, signature_for, to_neutral
from tests_batch import (TEMPLATES, ALL_CONFIGS, SPEND_BATCH_ONLY, TmpCase, chaos_policy, diff_fields, quiet, rows,
                         spend, spend_multiset, strip, transcripts)
import unittest

MODEL = "openrouter:google/gemini-4-argon-20261013"
NOV = lambda: datetime(2026, 11, 15, 12, 0, 0, tzinfo=timezone.utc)  # noqa: E731
DEC = lambda: datetime(2026, 12, 2, 12, 0, 0, tzinfo=timezone.utc)  # noqa: E731
LIST_NOV = {"input": 2.0, "output": 10.0, "cache_write": 2.0, "cache_read": 0.1}


def grid_args(n: int, configs: str = ALL_CONFIGS, seeds: str = "0", instances: int = 1, tasks: str = TEMPLATES,
              aware: str = "both") -> List[str]:
    return ["--models", MODEL, "--configs", configs, "--aware", aware, "--tasks", tasks, "--instances", str(instances),
            "--seeds", seeds, "--agents", str(n)]


def sync_prices(path: str, entry: Dict[str, float] = LIST_NOV) -> str:
    with open(path, "w") as f:
        json.dump({"models": {"openrouter:google/gemini-4-argon": dict(entry, confirmed=True)}}, f)
    return path


def run_sync(case: TmpCase, out: str, args: List[str], api: FakeGeminiAPI, extra: Optional[List[str]] = None,
             generate=None) -> int:
    def default(greq):
        api.sync_bodies.append(canonical(greq))
        a = api.answer(greq)
        return (400, {"error": a["error"]}) if "error" in a else (200, a["response"])

    tr = GR.SyncTransport(generate or default, "gemini-4-argon")

    def make_provider(model, dry_run=False, fake_policy=None):
        return GR.make_provider(), None

    prices = sync_prices(os.path.join(case.tmp, "sync_prices.json"))
    with mock.patch.object(run4, "make_provider", make_provider), GR.patched_urlopen(tr), quiet():
        code = run4.run_grid(args + ["--out", out, "--max-usd", "330", "--prices", prices] + (extra or []))
    case.sync_requests = tr.requests
    return code


def run_batch(out: str, args: List[str], api: FakeGeminiAPI, extra: Optional[List[str]] = None, buf=None) -> int:
    with contextlib.redirect_stdout(buf if buf is not None else io.StringIO()):
        return BD.main(args + ["--out", out, "--max-usd", "330", "--poll-min", "0", "--poll-max", "0"] + (extra or []),
                       client=http_client(api.handle))


def complete_with(body: Dict[str, Any], messages=None, temperature=0.0):
    """Completion the frozen OpenRouterProvider builds from an OpenRouter response body."""
    def serve(req):
        return io.BytesIO(json.dumps(body).encode())

    with GR.patched_urlopen(serve):
        return GR.make_provider().complete(MODEL, "sys", world4.tool_schemas(world4.CoordinationConfig.from_names("none")),
                                          messages or [{"role": "user", "content": M.START_MESSAGE}], 4096, temperature)


def captured_payload(system, tools, messages, max_tokens=4096, temperature=0.0) -> Dict[str, Any]:
    """The payload the frozen OpenRouterProvider POSTs for this history."""
    got = {}

    def cap(req):
        got["p"] = GR.payload_of(req)
        return io.BytesIO(json.dumps(GR.PLACEHOLDER).encode())

    with GR.patched_urlopen(cap):
        GR.make_provider().complete(MODEL, system, tools, messages, max_tokens, temperature)
    return got["p"]


def usage_md(prompt=100, cand=20, thoughts=30, cached=0):
    return {"promptTokenCount": prompt, "candidatesTokenCount": cand, "thoughtsTokenCount": thoughts,
            "cachedContentTokenCount": cached, "totalTokenCount": prompt + cand + thoughts}


# --------------------------------------------------------------------------
# (2) Request translation: system prompt, tools, multi-turn history carried exactly
# --------------------------------------------------------------------------


class RequestTranslation(unittest.TestCase):
    SYSTEM = "You are agent a0.\nTask: Move 5.00 from account:x to account:y, only if...\nUnicode: é—中"

    def history(self):
        """A neutral history as ModelAgent keeps it: two tool turns (one parallel), results, signatures."""
        return [
            {"role": "user", "content": M.START_MESSAGE},
            {"role": "assistant", "content": [
                {"type": "text", "text": "Reading both."},
                {"type": "tool_use", "id": "call-A1", "name": "get_record", "input": {"record_id": "account:x"}},
                {"type": "tool_use", "id": "call-A2", "name": "get_record", "input": {"record_id": "account:y"}}],
             "reasoning_details": [
                 {"type": "reasoning.encrypted", "data": "SIG-TEXT", "id": None, "format": G.SIG_FORMAT, "index": 0},
                 {"type": "reasoning.encrypted", "data": "SIG-1", "id": "call-A1", "format": G.SIG_FORMAT, "index": 1}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "call-A1", "content": json.dumps({"ok": True, "value": "10.00", "version": 3}, sort_keys=True)},
                {"type": "tool_result", "tool_use_id": "call-A2", "content": json.dumps({"ok": False, "status": 404}, sort_keys=True), "is_error": True}]},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "gsyn_2_0", "name": "update_record",
                 "input": {"record_id": "account:x", "value": "5.00", "expected_version": 3, "nested": {"a": [1, 2.5, None]}}}],
             "reasoning_details": [
                 {"type": "reasoning.encrypted", "data": "SIG-2", "id": "gsyn_2_0", "format": G.SIG_FORMAT, "index": 0}]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "gsyn_2_0", "content": "{\"ok\": true, \"note\": \"café\"}"}]},
        ]

    def test_system_tools_history_carried_exactly(self):
        for preset in world4.PRESET_NAMES:
            tools = world4.tool_schemas(world4.CoordinationConfig.from_names(preset))
            payload = captured_payload(self.SYSTEM, tools, self.history())
            req = G.to_gemini_request(payload)
            with self.subTest(preset=preset):
                self.assertEqual(req["systemInstruction"], {"parts": [{"text": self.SYSTEM}]})
                decls = req["tools"][0]["functionDeclarations"]
                self.assertEqual(decls, [{"name": t["name"], "description": t["description"],
                                          "parametersJsonSchema": t["input_schema"]} for t in tools])
                self.assertEqual(json.dumps(decls[1]["parametersJsonSchema"], sort_keys=True),
                                 json.dumps(tools[1]["input_schema"], sort_keys=True))  # incl. typeless "value"
                self.assertEqual(req["toolConfig"], {"functionCallingConfig": {"mode": "AUTO"}})
                self.assertEqual(req["generationConfig"], {"maxOutputTokens": 4096, "temperature": 0.0})
                self.assertNotIn("thinkingConfig", req["generationConfig"])
                self.assertEqual(set(req), {"systemInstruction", "contents", "tools", "toolConfig", "generationConfig"})
        c = req["contents"]
        self.assertEqual([x["role"] for x in c], ["user", "model", "user", "model", "user"])
        self.assertEqual(c[0], {"role": "user", "parts": [{"text": M.START_MESSAGE}]})
        self.assertEqual(c[1]["parts"], [
            {"text": "Reading both.", "thoughtSignature": "SIG-TEXT"},
            {"functionCall": {"name": "get_record", "args": {"record_id": "account:x"}, "id": "call-A1"}, "thoughtSignature": "SIG-1"},
            {"functionCall": {"name": "get_record", "args": {"record_id": "account:y"}, "id": "call-A2"}}])
        h = self.history()
        self.assertEqual(c[2]["parts"], [
            {"functionResponse": {"name": "get_record", "response": {"output": h[2]["content"][0]["content"]}, "id": "call-A1"}},
            {"functionResponse": {"name": "get_record", "response": {"output": h[2]["content"][1]["content"]}, "id": "call-A2"}}])
        # synthetic ids are never sent to Gemini; signature still restored; args exact (nested, floats, null)
        self.assertEqual(c[3]["parts"], [{"functionCall": {"name": "update_record", "args": h[3]["content"][0]["input"]},
                                          "thoughtSignature": "SIG-2"}])
        self.assertEqual(c[4]["parts"], [{"functionResponse": {"name": "update_record",
                                                               "response": {"output": "{\"ok\": true, \"note\": \"café\"}"}}}])

    def test_round_trip_back_to_the_neutral_history(self):
        tools = world4.tool_schemas(world4.CoordinationConfig.from_names("locks"))
        h = self.history()
        system, tools_back, msgs = to_neutral(G.to_gemini_request(captured_payload(self.SYSTEM, tools, h)))
        self.assertEqual(system, self.SYSTEM)
        self.assertEqual(tools_back, tools)
        self.assertEqual(len(msgs), len(h))
        for got, want in zip(msgs, h):
            self.assertEqual(got["role"], want["role"])
            if isinstance(want["content"], str):
                self.assertEqual(got["content"], want["content"])
            elif want["role"] == "assistant":
                self.assertEqual([b.get("text") for b in got["content"] if b["type"] == "text"],
                                 [b.get("text") for b in want["content"] if b["type"] == "text"])
                self.assertEqual([(b["name"], b["input"]) for b in got["content"] if b["type"] == "tool_use"],
                                 [(b["name"], b["input"]) for b in want["content"] if b["type"] == "tool_use"])
            else:
                self.assertEqual([b["content"] for b in got["content"]], [b["content"] for b in want["content"]])

    def test_temperature_absent_when_not_sent_and_unknown_fields_refused(self):
        p = captured_payload("s", [], [{"role": "user", "content": "hi"}], temperature=None)
        self.assertEqual(G.to_gemini_request(p)["generationConfig"], {"maxOutputTokens": 4096})
        for bad in ({"reasoning": {"effort": "high"}}, {"top_p": 1}):
            with self.assertRaises(G.TranslationError):
                G.to_gemini_request(dict(p, **bad))
        with self.assertRaises(G.TranslationError):
            G.to_gemini_request(dict(p, messages=p["messages"] + [{"role": "assistant", "content": None}]))

    def test_fake_enforces_thought_signatures_and_prefix_identity(self):
        api = FakeGeminiAPI()
        tools = world4.tool_schemas(world4.CoordinationConfig.from_names("none"))
        system = "You are agent a0.\nTask: Sell 1 from inventory:w, only if it stays non-negative."
        req = G.to_gemini_request(captured_payload(system, tools, [{"role": "user", "content": M.START_MESSAGE}]))
        r1 = api.answer(req)["response"]
        fc = r1["candidates"][0]["content"]["parts"][0]
        self.assertEqual(fc["thoughtSignature"], signature_for(req, 1))
        req2 = copy.deepcopy(req)
        req2["contents"] += [r1["candidates"][0]["content"],
                             {"role": "user", "parts": [{"functionResponse": {"id": fc["functionCall"]["id"], "name": "get_record",
                                                                               "response": {"output": "{}"}}}]}]
        self.assertIsNone(check_request(req2))
        no_sig = copy.deepcopy(req2)
        del no_sig["contents"][1]["parts"][0]["thoughtSignature"]
        self.assertIn("missing a `thought_signature`", check_request(no_sig)["message"])
        changed = copy.deepcopy(req2)
        changed["systemInstruction"]["parts"][0]["text"] += " "
        self.assertIn("does not match", check_request(changed)["message"])


# --------------------------------------------------------------------------
# (3) Response parsing: same Completion as the OpenRouter path for the equivalent case
# --------------------------------------------------------------------------


def or_body(message, finish, native, usage=(100, 50, 30), model="gemini-4-argon"):
    p, c, r = usage
    return {"id": "x", "model": model, "provider": G.PROVIDER_LABEL,
            "choices": [{"index": 0, "message": message, "finish_reason": finish, "native_finish_reason": native}],
            "usage": {"prompt_tokens": p, "completion_tokens": c, "completion_tokens_details": {"reasoning_tokens": r}}}


class ResponseParsing(unittest.TestCase):
    REQ = {"contents": [{"role": "user", "parts": [{"text": "go"}]}]}

    def same(self, gemini_resp, openrouter_body):
        a = complete_with(G.to_openrouter_response(gemini_resp, self.REQ, "gemini-4-argon"))
        b = complete_with(openrouter_body)
        for k in ("blocks", "stop_reason", "usage", "model_served", "temperature_effective", "reasoning_details", "provider"):
            self.assertEqual(getattr(a, k), getattr(b, k), k)
        self.assertEqual(a.provider_meta, b.provider_meta)
        return a

    def test_multiple_function_calls(self):
        g = {"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"id": "c1", "name": "get_record", "args": {"record_id": "seat:1"}}, "thoughtSignature": "S1"},
            {"functionCall": {"id": "c2", "name": "claim", "args": {"record_id": "seat:1", "holder": "a0"}}}]},
            "finishReason": "STOP"}], "usageMetadata": usage_md(100, 20, 30), "modelVersion": "gemini-4-argon"}
        msg = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "get_record", "arguments": "{\"record_id\": \"seat:1\"}"}},
            {"id": "c2", "type": "function", "function": {"name": "claim", "arguments": "{\"record_id\": \"seat:1\", \"holder\": \"a0\"}"}}],
            "reasoning_details": [{"type": "reasoning.encrypted", "data": "S1", "id": "c1", "format": G.SIG_FORMAT, "index": 0}]}
        c = self.same(g, or_body(msg, "tool_calls", "STOP"))
        self.assertEqual([b["name"] for b in c.tool_uses], ["get_record", "claim"])
        self.assertEqual(c.usage, {"input": 100, "output": 50})  # thinking tokens billed as output
        self.assertEqual(c.provider_meta["reasoning_tokens"], 30)

    def test_text_and_call_and_missing_ids_get_stable_synthetic_ids(self):
        g = {"candidates": [{"content": {"parts": [{"text": "I will read."},
                                                   {"functionCall": {"name": "get_record", "args": {"record_id": "a"}}, "thoughtSignature": "S"}]},
                             "finishReason": "STOP"}], "usageMetadata": usage_md(100, 20, 30), "modelVersion": "gemini-4-argon"}
        msg = {"role": "assistant", "content": "I will read.", "tool_calls": [
            {"id": "gsyn_0_0", "type": "function", "function": {"name": "get_record", "arguments": "{\"record_id\": \"a\"}"}}],
            "reasoning_details": [{"type": "reasoning.encrypted", "data": "S", "id": "gsyn_0_0", "format": G.SIG_FORMAT, "index": 0}]}
        c = self.same(g, or_body(msg, "tool_calls", "STOP"))
        self.assertEqual(c.blocks[0], {"type": "text", "text": "I will read."})

    def test_empty_stop(self):
        g = {"candidates": [{"content": {"role": "model", "parts": []}, "finishReason": "STOP"}],
             "usageMetadata": usage_md(100, 0, 30), "modelVersion": "gemini-4-argon"}
        c = self.same(g, or_body({"role": "assistant", "content": None}, "stop", "STOP", (100, 30, 30)))
        self.assertEqual(c.blocks, [])

    def test_safety_finish_and_blocked_prompt_are_content_filter(self):
        g = {"candidates": [{"finishReason": "SAFETY", "safetyRatings": []}], "usageMetadata": usage_md(100, 0, 0),
             "modelVersion": "gemini-4-argon"}
        c = self.same(g, or_body({"role": "assistant", "content": None}, "content_filter", "SAFETY", (100, 0, 0)))
        self.assertEqual((c.blocks, c.stop_reason), ([], "content_filter"))
        blocked = {"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}, "usageMetadata": {"promptTokenCount": 100},
                   "modelVersion": "gemini-4-argon"}
        c = self.same(blocked, or_body({"role": "assistant", "content": None}, "content_filter", "PROHIBITED_CONTENT", (100, 0, 0)))
        self.assertEqual(c.blocks, [])
        self.assertNotIn(c.stop_reason, M.TRUNCATED_STOPS)  # the agent ends normally with empty final text

    def test_max_tokens_is_length_and_truncated(self):
        g = {"candidates": [{"content": {"parts": [{"text": "partial"}]}, "finishReason": "MAX_TOKENS"}],
             "usageMetadata": usage_md(100, 10, 4086), "modelVersion": "gemini-4-argon"}
        c = self.same(g, or_body({"role": "assistant", "content": "partial"}, "length", "MAX_TOKENS", (100, 4096, 4086)))
        self.assertIn(c.stop_reason, M.TRUNCATED_STOPS)

    def test_malformed_function_call_is_error_and_thought_parts_are_skipped(self):
        g = {"candidates": [{"content": {"parts": [{"text": "secret thought", "thought": True}]},
                             "finishReason": "MALFORMED_FUNCTION_CALL"}], "usageMetadata": usage_md(100, 0, 9),
             "modelVersion": "gemini-4-argon"}
        c = self.same(g, or_body({"role": "assistant", "content": None}, "error", "MALFORMED_FUNCTION_CALL", (100, 9, 9)))
        self.assertEqual(c.blocks, [])

    def test_no_candidate_and_no_block_is_an_error_result_not_a_reply(self):
        empty = {"usageMetadata": {"promptTokenCount": 10}}
        self.assertFalse(G.is_answer(empty))
        with self.assertRaises(G.TranslationError):
            G.to_openrouter_response(empty, self.REQ, "gemini-4-argon")

    def test_errors_use_openrouters_provider_error_envelope(self):
        for status, http in (({"code": 3, "message": "bad temperature", "status": "INVALID_ARGUMENT"}, 400),
                             ({"code": 8, "message": "quota"}, 429), ({"status": "UNAVAILABLE", "message": "x"}, 503),
                             ({"code": 13}, 500), ({}, 500)):
            code, body = G.error_http(status)
            self.assertEqual(code, http)
            b = json.loads(body)
            self.assertEqual(b["error"]["code"], http)
            self.assertEqual(json.loads(b["error"]["metadata"]["raw"]), status)


# --------------------------------------------------------------------------
# (1) The gate: equivalence with the sync path, and with literal run4 --dry-run
# --------------------------------------------------------------------------


class GeminiGate(TmpCase):
    def _gate(self, args: List[str], n_expected: int, policy=None) -> None:
        api_s = FakeGeminiAPI(policy=policy, now=NOV)
        api_b = FakeGeminiAPI(polls_to_end=2, policy=policy, now=NOV)
        self.assertEqual(run_sync(self, self.d("sync"), args, api_s), 0)
        buf = io.StringIO()
        self.assertEqual(run_batch(self.d("batch"), args, api_b, ["--price-factor", "1.0"], buf=buf), 0, buf.getvalue()[-2000:])
        # 1) request payloads: the batch submits exactly the Gemini requests the sync path sends (parsed and bytes)
        self.assertEqual(len(api_b.batch_params), len(self.sync_requests))
        self.assertEqual(collections.Counter(canonical(p) for p in api_b.batch_params),
                         collections.Counter(canonical(p) for p in self.sync_requests))
        self.assertEqual(collections.Counter(api_b.batch_raw), collections.Counter(G.compact(p) for p in self.sync_requests))
        for p in api_b.batch_params:
            self.assertEqual(p["generationConfig"], {"maxOutputTokens": M.DEFAULT_MAX_TOKENS, "temperature": 0.0})
            self.assertEqual(p["toolConfig"], {"functionCallingConfig": {"mode": "AUTO"}})
            self.assertEqual(p["contents"][0], {"role": "user", "parts": [{"text": M.START_MESSAGE}]})
            self.assertTrue(p["systemInstruction"]["parts"][0]["text"].startswith("You are agent "))
        # 2) results rows identical, every column
        rs, rb = rows(self.d("sync")), rows(self.d("batch"))
        self.assertEqual(len(rs), n_expected)
        self.assertEqual(rs, rb)
        # 3) transcripts identical except the timing fields
        ts, tb = transcripts(self.d("sync")), transcripts(self.d("batch"))
        differing = set()
        for eid in ts:
            differing |= set(diff_fields(ts[eid], tb[eid]))
            self.assertEqual(strip(ts[eid]), strip(tb[eid]), eid)
        allowed = {".run_info.started_utc", ".run_info.finished_utc", ".run_info.wall_seconds", ".run_info.execution"}
        allowed |= {f".agents.{a}.turns[].at_utc" for tr in ts.values() for a in tr["agents"]}
        self.assertTrue(differing <= allowed, differing - allowed)
        # 4) spend: same entries (frozen schema), batch-only keys aside
        self.assertEqual(spend_multiset(spend(self.d("sync"))), spend_multiset(spend(self.d("batch"))))
        tr0 = next(iter(tb.values()))
        self.assertEqual(tr0["provider"], "gemini_batch")
        self.assertEqual(tr0["run_info"]["execution"]["mode"], "gemini_batch_api")
        self.assertEqual(tr0["run_info"]["execution"]["served_model_versions"], ["gemini-4-argon"])

    def test_gate_n2_all_configs_aware_both(self):
        self._gate(grid_args(2, seeds="0,1"), 6 * 2 * 8 * 2)

    def test_gate_n4_all_configs_aware_both(self):
        self._gate(grid_args(4), 6 * 2 * 8)

    def test_gate_n8_all_configs_aware_both(self):
        self._gate(grid_args(8), 6 * 2 * 8)

    def test_gate_chaos_model_n2_n4_n8(self):
        base = self.tmp
        for n in (2, 4, 8):
            with self.subTest(n=n):
                self.tmp = os.path.join(base, f"chaos{n}")
                os.makedirs(self.tmp)
                self._gate(grid_args(n, tasks="inventory_last_unit,seat_same,transfer_shared_source,budget_write_skew,"
                                              "joint_account_write_skew"), 6 * 2 * 5, policy=chaos_policy)
                ts = transcripts(self.d("batch"))
                ends = collections.Counter(e["reason"] for tr in ts.values() for e in tr["ledger"]["agent_ends"])
                self.assertGreater(ends["turn_cap"], 0)
                self.assertGreater(max(a["max_tool_calls_in_turn"] for tr in ts.values() for a in tr["agents"].values()), 1)
        self.tmp = base

    def test_same_decisions_as_run4_dry_run(self):
        """(1) Against literal `run4 --dry-run` (FakeProvider): identical messages, executions, ledgers, stores,
        scores and CSV columns (provider-dependent token, cost, served-id, temperature columns aside)."""
        args = grid_args(4, configs="none,cas_available,locks,messages", tasks="transfer_shared_source,budget_write_skew,seat_same")
        with quiet():
            self.assertEqual(run4.run_grid(args + ["--out", self.d("r4"), "--dry-run"]), 0)
        self.assertEqual(run_batch(self.d("bd"), args + ["--dry-run"], FakeGeminiAPI()), 0)
        t4, tb = transcripts(self.d("r4/dry_run")), transcripts(self.d("bd/dry_run"))
        self.assertEqual(set(t4), set(tb))
        for eid in t4:
            for k in ("ledger", "final_store", "score", "task", "schedule", "world", "dry_run", "generation"):
                self.assertEqual(t4[eid][k], tb[eid][k], (eid, k))
            for a in t4[eid]["agents"]:
                for k in ("messages", "executions", "invalid_calls", "final_text", "completions", "system",
                          "multi_tool_turns", "unexecuted_tool_calls", "truncated"):
                    self.assertEqual(t4[eid]["agents"][a][k], tb[eid]["agents"][a][k], (eid, a, k))
        r4, rb = rows(self.d("r4/dry_run")), rows(self.d("bd/dry_run"))
        keep = [c for c in run4.CSV_FIELDS if c not in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
                                                         "cost_usd", "model_served", "temperature_effective")]
        self.assertEqual({k: {c: v[c] for c in keep} for k, v in r4.items()}, {k: {c: v[c] for c in keep} for k, v in rb.items()})


# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------


class Money(TmpCase):
    def test_price_file_is_half_of_list_and_matches_googles_batch_prices(self):
        data = json.load(open(GB.DEFAULT_BATCH_PRICES))["models"]["openrouter:google/gemini-4-argon"]
        self.assertTrue(data["confirmed"])
        for per in data["periods"]:
            for k, v in per["batch_published"].items():
                self.assertAlmostEqual(0.5 * per[k], v)
        t = GB.PeriodBatchPriceTable.load_file(GB.DEFAULT_BATCH_PRICES, 0.5)
        self.assertEqual(t.problems([MODEL]), [])
        mtok_in, mtok_out = {"input": 10**6, "output": 0}, {"input": 0, "output": 10**6}
        self.assertEqual(t.token_cost_at(MODEL, mtok_in, "2026-11-15T00:00:00Z"), 1.0)
        self.assertEqual(t.token_cost_at(MODEL, mtok_out, "2026-11-15T00:00:00Z"), 5.0)
        self.assertEqual(t.token_cost_at(MODEL, mtok_in, "2026-11-30T00:00:00Z"), 2.0)  # switch a day early
        self.assertEqual(t.token_cost_at(MODEL, mtok_out, "2026-12-02T00:00:00Z"), 10.0)
        self.assertEqual(t.token_cost(MODEL, mtok_out), 10.0)  # no time: dearest period (estimates, worst case)
        self.assertIsNone(t.lookup("openrouter:google/gemini-4-argon-pro"))
        self.assertIsNone(t.lookup("openrouter:google/gemini-4-argon-2026"))
        # thinking tokens are output tokens
        u = G.frozen_usage({"usageMetadata": usage_md(1000, 100, 900, cached=500)})
        self.assertEqual(u, {"input": 1000, "output": 1000, "cache_read": 0, "cache_write": 0, "reasoning": 900})
        self.assertAlmostEqual(t.token_cost_at(MODEL, u, "2026-11-15T00:00:00Z"), 0.5 * (1000 * 2 + 1000 * 10) / 1e6)

    def test_batch_end_time_picks_the_price_period(self):
        args = grid_args(2, configs="none", tasks="seat_same", aware="off")
        self.assertEqual(run_batch(self.d("nov"), args, FakeGeminiAPI(now=NOV)), 0)
        self.assertEqual(run_batch(self.d("dec"), args, FakeGeminiAPI(now=DEC)), 0)
        sn, sd = spend(self.d("nov")), spend(self.d("dec"))
        self.assertEqual([e["usage"] for e in sn], [e["usage"] for e in sd])
        for a, b in zip(sn, sd):
            self.assertAlmostEqual(b["cost_usd"], 2 * a["cost_usd"])
            self.assertAlmostEqual(a["cost_usd"], 0.5 * (a["usage"]["input"] * 2 + a["usage"]["output"] * 10) / 1e6)
        self.assertAlmostEqual(M.SpendTracker(os.path.join(self.d("nov"), "spend.jsonl")).total, sum(e["cost_usd"] for e in sn))

    def test_one_cap_over_all_spend_logs_gates_each_batch_on_worst_case(self):
        args = grid_args(2, configs="none,locks", tasks="inventory_last_unit,transfer_shared_source")
        other = self.d("other/spend.jsonl")
        os.makedirs(os.path.dirname(other))
        with open(other, "w") as f:
            f.write(json.dumps({"episode_id": "x", "cost_usd": 329.97, "cost_source": "reported"}) + "\n")
        submitted: List[float] = []
        orig = BD.Driver._create

        def spy(self_, chunk):
            left = 330 - self_.spent() - self_.store.inflight_worst()
            self.assertLessEqual(sum(x[2] for x in chunk), left + 1e-12)
            submitted.append(sum(x[2] for x in chunk))
            return orig(self_, chunk)

        buf = io.StringIO()
        with mock.patch.object(BD.Driver, "_create", spy):
            code = run_batch(self.d("b"), args, FakeGeminiAPI(), ["--extra-spend-logs", other, "--prior-input-tokens", "10"], buf=buf)
        self.assertEqual(code, 2, buf.getvalue()[-2000:])
        self.assertIn("COST CAP", buf.getvalue())
        self.assertLessEqual(329.97 + sum(e["cost_usd"] for e in spend(self.d("b"))), 330.0)

    def test_enqueued_token_limit_holds_requests_until_batches_end(self):
        args = grid_args(2, configs="none,locks", tasks="transfer_shared_source,budget_write_skew")
        api_s, api_b = FakeGeminiAPI(now=NOV), FakeGeminiAPI(polls_to_end=2, now=NOV)
        run_sync(self, self.d("sync"), args, api_s)
        seen: List[int] = []
        orig = BD.Driver._create

        def spy(self_, chunk):
            seen.append(self_.store.inflight_tokens() + sum(self_.ad.tokens_est(len(n.raw)) for _, n, _ in chunk))
            return orig(self_, chunk)

        buf = io.StringIO()
        with mock.patch.object(BD.Driver, "_create", spy):
            self.assertEqual(run_batch(self.d("b"), args, api_b, ["--price-factor", "1.0", "--max-enqueued-tokens", "3000"], buf=buf), 0)
        self.assertTrue(all(s <= 3000 for s in seen), seen)
        self.assertGreater(len(seen), 3)
        self.assertIn("enqueued-token limit", buf.getvalue())
        self.assertEqual(rows(self.d("sync")), rows(self.d("b")))


# --------------------------------------------------------------------------
# (4) Retries, failures, restart
# --------------------------------------------------------------------------


def target(req: Dict[str, Any]) -> bool:
    """Agent a0's second completion of transfer_shared_source, config locks, aware off."""
    s = req["systemInstruction"]["parts"][0]["text"]
    names = [d["name"] for t in req.get("tools", []) for d in t["functionDeclarations"]]
    return (s.startswith("You are agent a0.") and "Move" in s and "acquire_lock" in names
            and "at the same time" not in s and G.model_turns(req) == 1)


class Retries(TmpCase):
    ARGS = grid_args(2, configs="none,locks", tasks="transfer_shared_source,budget_write_skew", aware="both")

    def test_transient_errors_and_job_failures_are_retried_and_outputs_unchanged(self):
        def fault(key, req, seen):
            h = int(canonical(req)[-40:].encode().hex(), 16)
            if seen == 0 and h % 3 == 0:
                return {"error": {"code": 14, "message": "The model is overloaded.", "status": "UNAVAILABLE"}}
            if seen == 0 and h % 3 == 1:
                return {"response": {"usageMetadata": {"promptTokenCount": 5}}}  # no candidate, no block reason
            return None

        states = {2: "BATCH_STATE_EXPIRED", 4: "BATCH_STATE_FAILED", 5: "BATCH_STATE_CANCELLED"}
        api_s = FakeGeminiAPI(now=NOV)
        run_sync(self, self.d("sync"), self.ARGS, api_s)
        api_b = FakeGeminiAPI(fault=fault, job_state=lambda n: states.get(n, "BATCH_STATE_SUCCEEDED"), now=NOV)
        buf = io.StringIO()
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api_b, ["--price-factor", "1.0"], buf=buf), 0, buf.getvalue()[-3000:])
        log_text = buf.getvalue()
        for k in ("expired=", "errored=", "canceled="):
            self.assertIn(k, log_text)
        self.assertGreater(len(api_b.batch_params), len(self.sync_requests))
        self.assertEqual(rows(self.d("sync")), rows(self.d("b")))
        ts, tb = transcripts(self.d("sync")), transcripts(self.d("b"))
        for eid in ts:
            self.assertEqual(strip(ts[eid]), strip(tb[eid]))
        self.assertEqual(spend_multiset(spend(self.d("sync"))), spend_multiset(spend(self.d("b"))))  # failed tries unbilled

    def _five_failures(self, status: Dict[str, Any], http: int) -> None:
        def sync_gen(greq):
            if target(greq):
                return http, {"error": status}
            a = FakeGeminiAPI().answer(greq)
            return 200, a["response"]

        self.assertEqual(run_sync(self, self.d("sync"), self.ARGS, FakeGeminiAPI(), generate=sync_gen), 3)
        api_b = FakeGeminiAPI(fault=lambda k, r, seen: {"error": status} if target(r) else None)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api_b), 3)
        fs = [json.loads(x) for x in open(os.path.join(self.d("sync"), "failures.jsonl"))]
        fb = [json.loads(x) for x in open(os.path.join(self.d("b"), "failures.jsonl"))]
        self.assertEqual((len(fs), len(fb)), (1, 1))
        self.assertEqual(sorted(fb[0]), ["at_utc", "episode_id", "error"])  # run4's schema
        self.assertEqual(sorted(fb[0]), sorted(fs[0]))
        self.assertEqual(fb[0]["episode_id"], fs[0]["episode_id"])
        self.assertEqual(fb[0]["error"], fs[0]["error"])
        self.assertTrue(fb[0]["error"].startswith(f"{MODEL}: RuntimeError: OpenRouter HTTP {http}: "), fb[0]["error"])
        self.assertEqual(sum(1 for p in api_b.batch_params if target(p)), 5)
        self.assertEqual(set(rows(self.d("b"))), set(rows(self.d("sync"))))
        # rerun without the fault: the failed episode starts afresh and finishes
        self.assertEqual(run_batch(self.d("b"), self.ARGS, FakeGeminiAPI()), 0)
        got = transcripts(self.d("b"))[fs[0]["episode_id"]]
        self.assertEqual(got["run_info"]["execution"]["retry_generation"], 1)

    def test_five_failed_tries_400_record_a_failure_exactly_like_run4(self):
        self._five_failures({"code": 3, "message": "Request contains an invalid argument.", "status": "INVALID_ARGUMENT"}, 400)

    def test_five_failed_tries_503_record_a_failure_exactly_like_run4(self):
        self._five_failures({"code": 14, "message": "The model is overloaded.", "status": "UNAVAILABLE"}, 503)

    def test_blocked_and_safety_replies_inside_batches_equal_the_sync_path(self):
        blocked = {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {"promptTokenCount": 77}, "modelVersion": "gemini-4-argon"}

        def sync_gen(greq):
            if target(greq):
                return 200, blocked
            return 200, FakeGeminiAPI().answer(greq)["response"]

        run_sync(self, self.d("sync"), self.ARGS, FakeGeminiAPI(), generate=sync_gen)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, FakeGeminiAPI(now=NOV, fault=lambda k, r, s: {"response": blocked} if target(r) else None),
                                   ["--price-factor", "1.0"]), 0)
        ts, tb = transcripts(self.d("sync")), transcripts(self.d("b"))
        hit = [eid for eid in ts if any(t["stop_reason"] == "content_filter" for a in ts[eid]["agents"].values() for t in a["turns"])]
        self.assertEqual(len(hit), 1)
        for eid in ts:
            self.assertEqual(strip(ts[eid])["agents"], strip(tb[eid])["agents"])
            self.assertEqual(ts[eid]["score"], tb[eid]["score"])
        a0 = tb[hit[0]]["agents"]["a0"]
        self.assertEqual((a0["final_text"], a0["truncated"], a0["stop_reason"]), ("", False, "content_filter"))
        self.assertEqual(a0["turns"][-1]["provider_meta"]["native_finish_reason"], "SAFETY")

    def test_temperature_rejection_is_handled_like_the_sync_provider(self):
        err = {"code": 3, "message": "temperature is not supported for this model", "status": "INVALID_ARGUMENT"}

        def sync_gen(greq):
            if "temperature" in greq["generationConfig"]:
                return 400, {"error": err}
            return 200, FakeGeminiAPI().answer(greq)["response"]

        self.assertEqual(run_sync(self, self.d("sync"), self.ARGS, FakeGeminiAPI(), generate=sync_gen), 0)
        api_b = FakeGeminiAPI(now=NOV, fault=lambda k, r, s: {"error": err} if "temperature" in r["generationConfig"] else None)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api_b, ["--price-factor", "1.0"]), 0)
        self.assertEqual(rows(self.d("sync")), rows(self.d("b")))
        tb = transcripts(self.d("b"))
        for eid, tr in transcripts(self.d("sync")).items():
            self.assertEqual(strip(tr), strip(tb[eid]))
            self.assertTrue(all(t["temperature_effective"] is None for a in tb[eid]["agents"].values() for t in a["turns"]))
        self.assertEqual(collections.Counter(canonical(p) for p in api_b.batch_params if "temperature" not in p["generationConfig"]),
                         collections.Counter(canonical(p) for p in self.sync_requests if "temperature" not in p["generationConfig"]))

    def test_crash_after_create_is_adopted_without_resubmitting(self):
        st = self.d("api_state")
        base_api = FakeGeminiAPI()
        self.assertEqual(run_batch(self.d("ref"), self.ARGS, base_api), 0)
        api = FakeGeminiAPI(state_dir=st)
        with mock.patch.dict(os.environ, {"SRC4_BATCH_TEST_CRASH_AFTER_CREATE": "1"}), self.assertRaises(SystemExit):
            run_batch(self.d("b"), self.ARGS, api)
        state = json.load(open(os.path.join(self.d("b"), "batch_state", run4.safe_name(MODEL), "batches.json")))
        self.assertEqual((len(state["intents"]), len(state["batches"])), (1, 0))
        api2 = FakeGeminiAPI(state_dir=st)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api2), 0)
        self.assertEqual(len(api2.batch_params) + len(api.batch_params), len(base_api.batch_params))
        self.assertEqual(spend_multiset(spend(self.d("ref"))), spend_multiset(spend(self.d("b"))))

    def test_crash_while_in_flight_resumes_without_resubmitting(self):
        st = self.d("api_state")
        base_api = FakeGeminiAPI(now=NOV)
        run_batch(self.d("ref"), self.ARGS, base_api)
        api = FakeGeminiAPI(state_dir=st, polls_to_end=3, now=NOV)
        calls = {"n": 0}
        orig = GB.GeminiBackend.retrieve

        class Crash(BaseException):
            pass

        def crashing(self_, bid):
            calls["n"] += 1
            if calls["n"] == 4:
                raise Crash()
            return orig(self_, bid)

        with mock.patch.object(GB.GeminiBackend, "retrieve", crashing), self.assertRaises(Crash):
            run_batch(self.d("b"), self.ARGS, api)
        n_before = len(api.batch_params)
        api2 = FakeGeminiAPI(state_dir=st, polls_to_end=3, now=NOV)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api2), 0)
        self.assertEqual(n_before + len(api2.batch_params), len(base_api.batch_params))
        self.assertEqual(spend_multiset(spend(self.d("ref"))), spend_multiset(spend(self.d("b"))))
        for eid, tr in transcripts(self.d("ref")).items():
            self.assertEqual(strip(tr), strip(transcripts(self.d("b"))[eid]))

    def test_recollect_never_duplicates_and_resume_skips_finished(self):
        st = self.d("api_state")
        args = grid_args(2, configs="none", tasks="inventory_last_unit", aware="off")
        self.assertEqual(run_batch(self.d("b"), args, FakeGeminiAPI(state_dir=st)), 0)
        n_spend = len(spend(self.d("b")))
        sd = os.path.join(self.d("b"), "batch_state", run4.safe_name(MODEL))
        p = os.path.join(sd, "batches.json")
        state = json.load(open(p))
        for b in state["batches"].values():
            b["status"] = "in_progress"
        json.dump(state, open(p, "w"))
        n_resp = sum(1 for _ in open(os.path.join(sd, "responses.jsonl")))
        self.assertEqual(run_batch(self.d("b"), args, FakeGeminiAPI(state_dir=st)), 0)
        self.assertEqual(len(spend(self.d("b"))), n_spend)
        self.assertEqual(sum(1 for _ in open(os.path.join(sd, "responses.jsonl"))), n_resp)
        api = FakeGeminiAPI()
        buf = io.StringIO()
        self.assertEqual(run_batch(self.d("b"), args, api, buf=buf), 0)
        self.assertEqual(api.batch_params, [])
        self.assertIn("to run: 0", buf.getvalue())


# --------------------------------------------------------------------------
# Plumbing
# --------------------------------------------------------------------------


class Plumbing(TmpCase):
    def test_frozen_files_unchanged_and_urlopen_restored(self):
        self.assertEqual(frozen.verify_freeze(), [])
        import urllib.request

        orig, orig_time = urllib.request.urlopen, providers.time
        with self.assertRaises(ZeroDivisionError), GR.patched_urlopen(lambda r: 1 / 0):
            GR.make_provider().complete(MODEL, "s", [], [{"role": "user", "content": "x"}], 10, 0.0)
        self.assertIs(urllib.request.urlopen, orig)
        self.assertIs(providers.time, orig_time)

    def test_refusals(self):
        with quiet():
            self.assertEqual(BD.main(["--models", "openrouter:openai/gpt-5.5-20260423", "--out", self.d("x"), "--dry-run"]), 1)
            self.assertEqual(BD.main(["--models", "openrouter:google/gemini-4-argon", "--out", self.d("x"), "--dry-run"]), 1)
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
                self.assertEqual(BD.main(grid_args(2, configs="none", tasks="seat_same") + ["--out", self.d("k")]), 1)
        # a sync (OpenRouter) Gemini transcript in the output: never mix execution paths
        args = grid_args(2, configs="none", tasks="seat_same", aware="off")
        run_sync(self, self.d("mix"), args, FakeGeminiAPI())
        buf = io.StringIO()
        self.assertEqual(run_batch(self.d("mix"), args, FakeGeminiAPI(), buf=buf), 1)
        self.assertIn("must not mix", buf.getvalue())

    def test_backend_parsing_timestamps_results_file_and_list(self):
        self.assertEqual(GB.rfc3339("2026-11-01T12:34:56.123456789Z"), "2026-11-01T12:34:56Z")
        self.assertEqual(GB.rfc3339("2026-11-01T05:00:00-07:00"), "2026-11-01T12:00:00Z")
        from fake_api import _httpx

        httpx = _httpx()
        resp = fake_response(G.to_gemini_request(captured_payload("You are agent a0.\nTask: x", [], [{"role": "user", "content": "go"}])))

        def handler(request):
            if request.url.path == "/v1beta/batches/b1":
                return httpx.Response(200, json={"name": "batches/b1", "done": True, "metadata": {
                    "state": "BATCH_STATE_SUCCEEDED", "createTime": "2026-11-01T00:00:00.5Z", "endTime": "2026-11-01T01:00:00.000000001Z",
                    "output": {"responsesFile": "files/out1"}}})
            if request.url.path == "/download/v1beta/files/out1:download":
                lines = [json.dumps({"key": "n-00000", "response": resp}), json.dumps({"key": "n-00001", "error": {"code": 8}})]
                return httpx.Response(200, text="\n".join(lines))
            if request.url.path == "/v1beta/batches":
                return httpx.Response(200, json={"operations": [{"name": "batches/b1", "metadata": {"state": "BATCH_STATE_RUNNING",
                                                                                                   "createTime": "2026-11-01T00:00:00Z"}}]})
            return httpx.Response(404)

        be = GB.GeminiBackend(http_client(handler), "gemini-4-argon", sleep=lambda s: None)
        info = be.retrieve("batches/b1")
        self.assertEqual((info["processing_status"], info["created_at"], info["ended_at"]), ("ended", "2026-11-01T00:00:00Z", "2026-11-01T01:00:00Z"))
        res = be.results("batches/b1")
        self.assertEqual([(r["custom_id"], r["result"]["type"]) for r in res], [("n-00000", "succeeded"), ("n-00001", "errored")])
        self.assertEqual(be.list_recent()[0]["processing_status"], "in_progress")

    def test_create_is_never_retried(self):
        from fake_api import _httpx

        httpx = _httpx()
        n = {"posts": 0}

        def handler(request):
            n["posts"] += request.method == "POST"
            return httpx.Response(503, json={"error": {"code": 503}})

        be = GB.GeminiBackend(http_client(handler), "gemini-4-argon", sleep=lambda s: None)
        with self.assertRaises(GB.GeminiAPIError):
            be.create([{"custom_id": "n-00000", "params": {"contents": []}}])
        self.assertEqual(n["posts"], 1)

    def test_preflight_reports_served_model_and_refuses_another(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(gemini_preflight.main(["--base", self.d("p"), "--dry-run"]), 0)
        self.assertIn("served model version gemini-4-argon", buf.getvalue())
        self.assertIn("tool_calls=['get_record']", buf.getvalue())
        log_ = [json.loads(x) for x in open(self.d("p/preflight/dry_run/spend.jsonl"))]
        self.assertEqual(len(log_), 1)
        self.assertTrue(log_[0]["batch"] and log_[0]["model"] == MODEL and log_[0]["cost_usd"] > 0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gemini_preflight.main(["--base", self.d("p"), "--dry-run"]), 0)  # marker: not repeated
        self.assertEqual(len(open(self.d("p/preflight/dry_run/spend.jsonl")).readlines()), 1)
        import preflight as P

        other = FakeGeminiAPI(model_version="gemini-3-pro", policy=P._ping_policy)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(gemini_preflight.main(["--base", self.d("q"), "--sub", "/x"], client=http_client(other.handle)), 1)
        self.assertIn("is not gemini-4-argon", buf.getvalue())
        self.assertFalse(os.path.exists(self.d("q/preflight/x/gemini_batch_ok")))


if __name__ == "__main__":
    unittest.main()
