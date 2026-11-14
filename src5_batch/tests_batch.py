"""Tests for the Message Batches driver (src5_batch). No network, no keys, no money.

Both paths run the harness src4 code with a real ``anthropic`` SDK client whose
HTTP goes to :class:`fake_api.FakeAnthropicAPI` (the run5 --dry-run model,
:func:`model_agent5.scripted_policy`, served as Anthropic Messages):

* sync path  = harness ``run5.run_grid`` (real-run mode) with ``run5.make_provider``
  returning ``providers.AnthropicProvider(UsageProbeClient(<that client>))`` --
  what run5 builds for a real Anthropic run, network replaced;
* batch path = ``batch_driver.main`` with the same client.

    cd src5_batch && python3 -m unittest tests_batch -v     (needs the anthropic SDK)
"""

from __future__ import annotations

import collections
import contextlib
import copy
import csv
import io
import json
import os
import shutil
import tempfile
import unittest
from typing import Any, Dict, List, Optional
from unittest import mock

import harness
import model_agent5 as M
import providers5 as providers
import run5
import scheduler5 as scheduler
import batch_driver as BD
import budget5 as B
import replay as R
from fake_api import FakeAnthropicAPI, canonical, fake_message, sdk_client

MODEL = "claude-sonnet-5"
import instances5 as I

TEMPLATES = ",".join(I.TEMPLATES)  # the 14 Study 2 templates (7 contended + 7 matched controls)
ALL_CONFIGS = "none,cas_available,locks,all_available"
N_T = len(I.TEMPLATES)

# The only transcript fields allowed to differ between the sync and the batch path.
TIMING_FIELDS_RUN_INFO = ("started_utc", "finished_utc", "wall_seconds", "execution")
TIMING_FIELDS_TURN = ("at_utc",)
SPEND_BATCH_ONLY = ("at_utc", "batch", "batch_id", "custom_id", "batch_gen", "price_factor")


def grid_args(n: int, configs: str = ALL_CONFIGS, seeds: str = "0", instances: int = 1, tasks: str = TEMPLATES,
              aware: str = "both") -> List[str]:
    return ["--models", MODEL, "--configs", configs, "--aware", aware, "--tasks", tasks, "--instances", str(instances),
            "--seeds", seeds, "--agents", str(n)]


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def run_sync(out: str, args: List[str], api: FakeAnthropicAPI, extra: Optional[List[str]] = None) -> int:
    def make_provider(model, dry_run=False, fake_policy=None):
        probe = M.UsageProbeClient(sdk_client(api.handle, max_retries=0))
        return providers.AnthropicProvider(client=probe), probe

    with mock.patch.object(run5, "make_provider", make_provider), quiet():
        return run5.run_grid(args + ["--out", out, "--max-usd", "330"] + (extra or []))


def run_batch(out: str, args: List[str], api: FakeAnthropicAPI, extra: Optional[List[str]] = None, buf=None) -> int:
    with contextlib.redirect_stdout(buf if buf is not None else io.StringIO()):
        return BD.main(args + ["--out", out, "--max-usd", "330", "--poll-min", "0", "--poll-max", "0"] + (extra or []),
                       client=sdk_client(api.handle, max_retries=0))


def rows(path: str) -> Dict[str, Dict[str, str]]:
    with open(os.path.join(path, "results.csv"), newline="") as f:
        return {r["episode_id"]: r for r in csv.DictReader(f)}


def transcripts(path: str) -> Dict[str, Dict[str, Any]]:
    d = os.path.join(path, "transcripts")
    out = {}
    for fn in sorted(os.listdir(d)):
        with open(os.path.join(d, fn)) as f:
            out[fn[:-5]] = json.load(f)
    return out


def strip(tr: Dict[str, Any]) -> Dict[str, Any]:
    tr = copy.deepcopy(tr)
    for k in TIMING_FIELDS_RUN_INFO:
        tr["run_info"].pop(k, None)
    for a in tr["agents"].values():
        for t in a["turns"]:
            for k in TIMING_FIELDS_TURN:
                t.pop(k, None)
    return tr


def spend(path: str) -> List[Dict[str, Any]]:
    p = os.path.join(path, "spend.jsonl")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(line) for line in f if line.strip()]


def spend_multiset(entries: List[Dict[str, Any]]) -> collections.Counter:
    return collections.Counter(canonical({k: v for k, v in e.items() if k not in SPEND_BATCH_ONLY}) for e in entries)


def diff_fields(a: Any, b: Any, path: str = "") -> List[str]:
    """Paths where two JSON values differ (for exact reporting)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            out += diff_fields(a.get(k, "<missing>"), b.get(k, "<missing>"), f"{path}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += diff_fields(x, y, f"{path}[]")
        return out
    return [] if a == b else [path]


def chaos_policy(system: str, tools: List[Dict[str, Any]], messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A harder deterministic fake model for the gate: a pseudo-random function of the conversation that issues
    1-3 calls per turn over every offered tool (reads, blind/CAS writes, claims, locks, messages, invalid
    arguments), so agents desynchronise, wait on locks, stall and hit the turn cap."""
    import hashlib
    import random
    import re

    rng = random.Random(hashlib.sha256((system + canonical(messages)).encode()).hexdigest())
    turn = sum(1 for m in messages if m["role"] == "assistant")
    task = next((ln for ln in system.splitlines() if ln.startswith("Task:")), "")
    recs = list(dict.fromkeys(re.findall(r"\b(?:inventory|seat|account|ticket|budget):[\w/.\-]*\w", task))) or ["inventory:x"]
    me = re.match(r"You are agent (\S+)\.", system).group(1)
    peers_line = next((ln for ln in system.splitlines() if ln.startswith("Agents you can message:")), "")
    peers = [p.strip(" .") for p in peers_line.split(":", 1)[1].split(",")] if peers_line else []
    names = [t["name"] for t in tools]
    if turn >= 2 and rng.random() < 0.15:
        return [{"type": "text", "text": f"done after {turn} turns"}]
    out = []
    for _ in range(rng.choice((1, 1, 2, 3))):
        name = rng.choice(names)
        r = rng.choice(recs)
        if name == "get_record":
            args: Dict[str, Any] = {"record_id": r}
        elif name == "update_record":
            args = {"record_id": r, "value": rng.choice([0, 1, 2, "5.00", "10.00", "-1", "abc"])}
            if rng.random() < 0.5:
                args["expected_version"] = rng.randint(0, 3)
            if rng.random() < 0.3:
                args["fencing_token"] = rng.randint(1, 4)
        elif name == "claim":
            args = {"record_id": r, "holder": rng.choice([me] + peers)}
        elif name in ("acquire_lock", "renew_lock"):
            args = {"record_id": r, "lease_calls": rng.randint(1, 4)}
        elif name == "release_lock":
            args = {"record_id": r}
        elif name == "send_message":
            args = {"to_agent": rng.choice(peers or [me]), "text": f"hi from {me} t{turn}"}
        elif name == "read_messages":
            args = {}
        else:
            args = {}
        if rng.random() < 0.05:
            args = {"bogus": True}
        out.append({"type": "tool_use", "name": name, "input": args})
    return out


class TmpCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="src5batch_")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def d(self, name: str) -> str:
        return os.path.join(self.tmp, name)


# --------------------------------------------------------------------------
# The gate: equivalence with the sync path
# --------------------------------------------------------------------------


class EquivalenceGate(TmpCase):
    def _gate(self, args: List[str], n_expected: int, policy=None) -> None:
        api_s, api_b = FakeAnthropicAPI(policy=policy), FakeAnthropicAPI(polls_to_end=2, policy=policy)
        self.assertEqual(run_sync(self.d("sync"), args, api_s), 0)
        # price factor 1.0 here so costs are comparable; the 0.5 factor is checked in its own test
        self.assertEqual(run_batch(self.d("batch"), args, api_b, ["--price-factor", "1.0"]), 0)

        # 1) request payloads: every request body the batch path submits equals, byte for byte, one the sync path sent
        self.assertEqual(len(api_b.batch_params), len(api_s.sync_bodies))
        self.assertEqual(collections.Counter(canonical(p) for p in api_b.batch_params),
                         collections.Counter(api_s.sync_bodies))
        sdk_bytes = collections.Counter(json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode()
                                        for p in api_b.batch_params)
        self.assertEqual(sdk_bytes, collections.Counter(api_s.sync_raw))
        for p in api_b.batch_params:
            self.assertEqual(p["model"], MODEL)
            self.assertEqual(p["max_tokens"], M.DEFAULT_MAX_TOKENS)
            self.assertEqual(p["temperature"], 0.0)
            self.assertEqual(p["system"][0]["cache_control"], {"type": "ephemeral"})
            self.assertEqual(p["tools"][-1]["cache_control"], {"type": "ephemeral"})
            self.assertTrue(all("cache_control" not in t for t in p["tools"][:-1]))
            self.assertEqual(p["messages"][0], {"role": "user", "content": M.START_MESSAGE})

        # 2) results rows: identical, every column
        rs, rb = rows(self.d("sync")), rows(self.d("batch"))
        self.assertEqual(len(rs), n_expected)
        self.assertEqual(rs, rb)

        # 3) transcripts: identical except the listed timing fields
        ts, tb = transcripts(self.d("sync")), transcripts(self.d("batch"))
        self.assertEqual(set(ts), set(tb))
        differing = set()
        for eid in ts:
            differing |= set(diff_fields(ts[eid], tb[eid]))
            self.assertEqual(strip(ts[eid]), strip(tb[eid]), eid)
            self.assertEqual(ts[eid]["score"], tb[eid]["score"], eid)
        allowed = {".run_info.started_utc", ".run_info.finished_utc", ".run_info.wall_seconds", ".run_info.execution"}
        allowed |= {f".agents.{a}.turns[].at_utc" for tr in ts.values() for a in tr["agents"]}
        self.assertTrue(differing <= allowed, differing - allowed)

        # 4) spend log: same entries (frozen schema), batch-only keys aside
        ss, sb = spend(self.d("sync")), spend(self.d("batch"))
        self.assertEqual(spend_multiset(ss), spend_multiset(sb))
        self.assertTrue(all(e["batch"] is True and e["cost_source"] == "price_table" for e in sb))

    def test_gate_n2_all_configs_aware_both(self):
        self._gate(grid_args(2, seeds="0,1"), 4 * 2 * N_T * 2)

    def test_gate_n4_all_configs_aware_both(self):
        self._gate(grid_args(4), 4 * 2 * N_T)

    def test_gate_probe_mode_n2(self):
        """First-reply probes: same request bodies, rows and transcripts on both paths."""
        self._gate(grid_args(2, seeds="0") + ["--probe"], 4 * 2 * (N_T // 2) * 2)

    def test_gate_n8_all_configs_aware_both(self):
        self._gate(grid_args(8, tasks="inventory_last_unit,transfer_shared_source_ctrl,budget_write_skew"), 4 * 2 * 3)

    def test_gate_chaos_model_n2_n4_n8(self):
        """Same gate with a model that desynchronises agents (multi-call turns, locks, messages, stalls, turn cap).
        V2: the peer-informed configuration is added so the message tools are exercised (no grid config has them)."""
        base = self.tmp
        for n in (2, 4, 8):
            with self.subTest(n=n):
                self.tmp = os.path.join(base, f"chaos{n}")
                self._gate(grid_args(n, configs=ALL_CONFIGS + ",all_peer_informed",
                                     tasks="inventory_last_unit,seat_same,transfer_shared_source,budget_write_skew,"
                                           "joint_account_write_skew,seat_same_ctrl"), 5 * 2 * 6, policy=chaos_policy)
                ts = transcripts(self.d("batch"))
                ends = collections.Counter(r for tr in ts.values() for r in
                                           (e["reason"] for e in tr["ledger"]["agent_ends"]))
                rounds = [tr["run_info"]["execution"]["lockstep_rounds"] for tr in ts.values()]
                comps = [max(a["completions"] for a in tr["agents"].values()) for tr in ts.values()]
                if n < 8:  # at n = 8 the Study 2 cap (72 calls) is out of the chaos model's reach
                    self.assertGreater(ends["turn_cap"], 0)
                self.assertGreater(ends["returned"], 0)
                self.assertTrue(all(r >= c for r, c in zip(rounds, comps)))
                print(f"\n   chaos n={n}: agent ends {dict(ends)}; lockstep rounds max {max(rounds)} "
                      f"mean {sum(rounds) / len(rounds):.1f}; completions/episode max "
                      f"{max(tr['totals']['completions'] for tr in ts.values())}")
        self.tmp = base

    def test_same_decisions_as_run4_dry_run(self):
        """Against the literal `run5 --dry-run` (FakeProvider): same tool calls, ledger, store and score.
        (Provider-dependent fields differ by design there: provider, prompt_caching, model_served, usage, cost.)"""
        args = grid_args(4, configs=ALL_CONFIGS, tasks="transfer_shared_source,budget_write_skew,seat_same,seat_same_ctrl")
        with quiet():
            self.assertEqual(run5.run_grid(args + ["--out", self.d("r4"), "--dry-run"]), 0)
        self.assertEqual(run_batch(self.d("bd"), args + ["--dry-run"], FakeAnthropicAPI()), 0)
        t4, tb = transcripts(self.d("r4/dry_run")), transcripts(self.d("bd/dry_run"))
        self.assertEqual(set(t4), set(tb))
        for eid in t4:
            for k in ("ledger", "final_store", "score", "task", "schedule", "world", "dry_run"):
                self.assertEqual(t4[eid][k], tb[eid][k], (eid, k))
            for a in t4[eid]["agents"]:
                for k in ("messages", "executions", "invalid_calls", "final_text", "completions"):
                    self.assertEqual(t4[eid]["agents"][a][k], tb[eid]["agents"][a][k], (eid, a, k))
        r4, rb = rows(self.d("r4/dry_run")), rows(self.d("bd/dry_run"))
        keep = [c for c in run5.CSV_FIELDS if c not in ("input_tokens", "output_tokens", "cache_read_tokens",
                                                         "cache_write_tokens", "cost_usd", "model_served", "served_hosts")]
        self.assertEqual({k: {c: v[c] for c in keep} for k, v in r4.items()},
                         {k: {c: v[c] for c in keep} for k, v in rb.items()})


# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------


class Money(TmpCase):
    def test_batch_price_is_half_of_every_token_class(self):
        base = M.PriceTable.load(run5.DEFAULT_PRICES)
        bt = BD.BatchPriceTable(base, 0.5)
        for model in ("claude-sonnet-5", "claude-fable-5"):
            for k in ("input", "output", "cache_read", "cache_write"):
                u = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, k: 1_000_000}
                self.assertEqual(bt.token_cost(model, u), 0.5 * base.token_cost(model, u))
        # documented batch prices: Sonnet 5 $1/$5, Fable 5 $5/$25 per MTok
        self.assertEqual(bt.token_cost("claude-sonnet-5", {"input": 10**6, "output": 0}), 1.0)
        self.assertEqual(bt.token_cost("claude-sonnet-5", {"input": 0, "output": 10**6}), 5.0)
        self.assertEqual(bt.token_cost("claude-fable-5", {"input": 10**6, "output": 0}), 5.0)
        self.assertEqual(bt.token_cost("claude-fable-5", {"input": 0, "output": 10**6}), 25.0)
        # worst case: (bytes + 1000) at the dearest input rate (cache write) + max_tokens output, halved
        self.assertAlmostEqual(bt.worst_case("claude-fable-5", 9000, 4096), 0.5 * (10000 * 12.5 + 4096 * 50) / 1e6)

    def test_costs_are_exactly_half_of_sync_and_logged_with_batch_flag(self):
        args = grid_args(2, configs="none,locks", tasks="inventory_last_unit,transfer_shared_source")
        run_sync(self.d("sync"), args, FakeAnthropicAPI())
        self.assertEqual(run_batch(self.d("batch"), args, FakeAnthropicAPI()), 0)
        ts, tb = transcripts(self.d("sync")), transcripts(self.d("batch"))
        for eid in ts:
            self.assertEqual(tb[eid]["totals"]["cost_usd"], 0.5 * ts[eid]["totals"]["cost_usd"])
            for a in ts[eid]["agents"]:
                for x, y in zip(ts[eid]["agents"][a]["turns"], tb[eid]["agents"][a]["turns"]):
                    self.assertEqual(y["cost_usd"], 0.5 * x["cost_usd"])
                    self.assertEqual(y["usage"], x["usage"])
        sb = spend(self.d("batch"))
        self.assertTrue(all(e["batch"] is True and e["price_factor"] == 0.5 and e["cost_source"] == "price_table" for e in sb))
        self.assertAlmostEqual(sum(e["cost_usd"] for e in sb), 0.5 * sum(e["cost_usd"] for e in spend(self.d("sync"))), places=12)
        # the harness SpendTracker (used by run5/plan_full for the shared cap) reads the batch log unchanged
        self.assertAlmostEqual(M.SpendTracker(os.path.join(self.d("batch"), "spend.jsonl")).total,
                               sum(e["cost_usd"] for e in sb), places=12)

    def test_cap_counts_all_spend_logs_and_gates_each_batch_on_worst_case(self):
        args = grid_args(2, configs="none,locks", tasks="inventory_last_unit,transfer_shared_source")
        other = self.d("other/spend.jsonl")
        os.makedirs(os.path.dirname(other))
        with open(other, "w") as f:  # earlier sync / OpenRouter spend
            f.write(json.dumps({"episode_id": "x", "model": "openrouter:x/y", "cost_usd": 329.95, "cost_source": "reported"}) + "\n")
        api = FakeAnthropicAPI()
        submitted: List[float] = []
        orig = BD.Driver._create

        def spy(self_, chunk):
            left = 330 - self_.spent() - self_.store.inflight_worst()
            w = sum(x[2] for x in chunk)
            self.assertLessEqual(w, left + 1e-12)
            submitted.append(w)
            return orig(self_, chunk)

        buf = io.StringIO()
        with mock.patch.object(BD.Driver, "_create", spy):
            code = run_batch(self.d("b"), args, api, ["--extra-spend-logs", other, "--prior-input-tokens", "10"], buf=buf)
        self.assertEqual(code, 2, buf.getvalue()[-2000:])
        self.assertIn("COST CAP", buf.getvalue())
        total = 329.95 + sum(e["cost_usd"] for e in spend(self.d("b")))
        self.assertLessEqual(total, 330.0)

    def test_family_cap_binds_separately_from_the_total(self):
        args = grid_args(2, configs="none,locks", tasks="inventory_last_unit,transfer_shared_source")
        other = self.d("other/spend.jsonl")
        os.makedirs(os.path.dirname(other))
        with open(other, "w") as f:  # Anthropic spend already near its own cap; the total cap is far away
            f.write(json.dumps({"episode_id": "x", "model": "claude-haiku-4-5-20251001", "cost_usd": 18.99}) + "\n")
        buf = io.StringIO()
        code = run_batch(self.d("b"), args, FakeAnthropicAPI(), ["--extra-spend-logs", other, "--family-cap", "anthropic=19"],
                         buf=buf)
        self.assertEqual(code, 2, buf.getvalue()[-2000:])
        fam = B.spend_by_family([other, os.path.join(self.d("b"), "spend.jsonl")])
        self.assertLessEqual(fam["anthropic"], 19.0)
        # a Gemini or OpenRouter entry does not use up the Anthropic cap
        with open(other, "w") as f:
            f.write(json.dumps({"episode_id": "x", "model": "openrouter:openai/gpt-5.5-20260423", "cost_usd": 27.0}) + "\n")
        self.assertEqual(run_batch(self.d("c"), args, FakeAnthropicAPI(), ["--extra-spend-logs", other]), 0)

    def test_cost_cap_never_strands_a_contended_episode_without_its_control(self):
        # Round 3 (task item 5): pairs are admitted and advanced together, and written only together
        tasks = "inventory_last_unit,inventory_last_unit_ctrl,seat_same,seat_same_ctrl"
        args = grid_args(2, configs="none,locks", tasks=tasks, instances=2, aware="off")
        self.assertEqual(run_batch(self.d("full"), args, FakeAnthropicAPI()), 0)
        n = len(rows(self.d("full")))
        self.assertEqual(n, 16)
        per_ep = sum(e["cost_usd"] for e in spend(self.d("full"))) / n
        stops = 0
        for k, left in enumerate((2.5, 4.2, 6.6, 9.1)):
            other = self.d(f"other{k}/spend.jsonl")
            os.makedirs(os.path.dirname(other))
            with open(other, "w") as f:
                f.write(json.dumps({"episode_id": "x", "model": MODEL, "cost_usd": 330 - left * per_ep}) + "\n")
            out = self.d(f"cap{k}")
            code = run_batch(out, args, FakeAnthropicAPI(), ["--extra-spend-logs", other])
            got = list(rows(out).values()) if os.path.exists(os.path.join(out, "results.csv")) else []
            self.assertEqual(run5.unpaired(got), [], (left, sorted(got_r["episode_id"] for got_r in got)))
            stops += code == 2 and len(got) < n
            if code == 2:  # resume with money: the held arm is completed, nothing is re-run twice
                with open(other, "w") as f:
                    f.write("")
                self.assertEqual(run_batch(out, args, FakeAnthropicAPI()), 0)
                self.assertEqual(len(rows(out)), n)
                self.assertFalse(os.listdir(os.path.join(out, run5.HELD_DIR)) if os.path.isdir(os.path.join(out, run5.HELD_DIR)) else [])
        self.assertGreater(stops, 0)

    def test_admission_uses_run5_estimate_rule(self):
        args = grid_args(2, configs="none", tasks="inventory_last_unit,seat_same", aware="off", seeds="0,1")
        cells = run5.build_grid([MODEL], ["none"], ["inventory_last_unit", "seat_same"], [0, 1], 2, [False], 1)
        prior = run5.prior_estimate(cells[0]) + run5.prior_estimate(cells[1])
        buf = io.StringIO()
        # room for exactly two prior-bound episodes: two run, then the estimate falls to 1.5 x observed and the rest run
        code = run_batch(self.d("b"), args, FakeAnthropicAPI(), ["--max-usd", str(1.05 * prior)], buf=buf)
        self.assertEqual(code, 0, buf.getvalue()[-1500:])
        self.assertEqual(len(rows(self.d("b"))), 4)
        log_text = buf.getvalue()
        self.assertIn("COST CAP: holding claude-sonnet-5__none__inventory_last_unit@i0__n2__s1", log_text)
        self.assertLess(log_text.index("[done 1]"), log_text.rindex("submitted batch"))  # second wave after the first finished


# --------------------------------------------------------------------------
# Retries, failures, crash / restart
# --------------------------------------------------------------------------


def target_key(params: Dict[str, Any]) -> bool:
    """One request of one episode: agent a0's second completion of transfer_shared_source, config locks, aware off."""
    sys0 = params["system"][0]["text"]
    return (sys0.startswith("You are agent a0.") and "Move" in sys0 and "acquire_lock" in json.dumps(params["tools"])
            and "at the same time" not in sys0 and sum(m["role"] == "assistant" for m in params["messages"]) == 1)


class Retries(TmpCase):
    ARGS = grid_args(2, configs="none,locks", tasks="transfer_shared_source,budget_write_skew", aware="both")

    def test_transient_errors_are_retried_and_outputs_unchanged(self):
        def fault(cid, params, seen):
            h = int(canonical(params)[-40:].encode().hex(), 16)
            if seen == 0 and h % 3 == 0:
                return {"type": "errored", "error": {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}}
            if seen == 0 and h % 3 == 1:
                return {"type": "expired"}
            if seen == 1 and h % 5 == 0:
                return {"type": "canceled"}
            return None

        api_s = FakeAnthropicAPI()
        run_sync(self.d("sync"), self.ARGS, api_s)
        api_b = FakeAnthropicAPI(fault=fault)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api_b, ["--price-factor", "1.0"]), 0)
        self.assertGreater(len(api_b.batch_params), len(api_s.sync_bodies))  # retries happened
        self.assertEqual(rows(self.d("sync")), rows(self.d("b")))
        ts, tb = transcripts(self.d("sync")), transcripts(self.d("b"))
        for eid in ts:
            self.assertEqual(strip(ts[eid]), strip(tb[eid]))
        self.assertEqual(spend_multiset(spend(self.d("sync"))), spend_multiset(spend(self.d("b"))))  # failed tries unbilled

    def test_five_failed_tries_record_a_provider_failure_like_run4_then_rerun_completes(self):
        err = {"type": "error", "error": {"type": "invalid_request_error", "message": "messages: something is wrong"}}
        # sync reference: the same request rejected by the sync API -> run5's failure line
        api_s = FakeAnthropicAPI(sync_fault=lambda p: (400, err) if target_key(p) else None)
        self.assertEqual(run_sync(self.d("sync"), self.ARGS, api_s), 3)
        api_b = FakeAnthropicAPI(fault=lambda cid, p, seen: {"type": "errored", "error": err} if target_key(p) else None)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api_b), 3)
        fs = [json.loads(x) for x in open(os.path.join(self.d("sync"), "failures.jsonl"))]
        fb = [json.loads(x) for x in open(os.path.join(self.d("b"), "failures.jsonl"))]
        self.assertEqual(len(fs), 1)
        self.assertEqual(len(fb), 1)
        self.assertEqual(sorted(fb[0]), sorted(fs[0]))           # same schema
        self.assertEqual(fb[0]["episode_id"], fs[0]["episode_id"])
        self.assertEqual(fb[0]["error"], fs[0]["error"])         # same message, formatted by the harness code
        self.assertTrue(fb[0]["error"].startswith(f"{MODEL}: BadRequestError: Error code: 400"))
        self.assertEqual(sum(1 for p in api_b.batch_params if target_key(p)), 5)
        self.assertEqual(set(rows(self.d("b"))), set(rows(self.d("sync"))))  # every other episode written
        # rerun without the fault: the failed episode starts afresh and finishes; outputs equal a clean sync run
        api_b2 = FakeAnthropicAPI()
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api_b2), 0)
        run_sync(self.d("sync_clean"), self.ARGS, FakeAnthropicAPI())
        clean = transcripts(self.d("sync_clean"))
        got = transcripts(self.d("b"))
        self.assertEqual(set(clean), set(got))
        failed_id = fs[0]["episode_id"]
        self.assertEqual(strip(clean[failed_id])["score"], strip(got[failed_id])["score"])
        self.assertEqual(got[failed_id]["run_info"]["execution"]["retry_generation"], 1)

    def test_temperature_rejection_is_handled_like_the_sync_provider(self):
        err = {"type": "error", "error": {"type": "invalid_request_error", "message": "temperature: not supported for this model"}}
        api_s = FakeAnthropicAPI(sync_fault=lambda p: (400, err) if "temperature" in p else None)
        self.assertEqual(run_sync(self.d("sync"), self.ARGS, api_s), 0)
        api_b = FakeAnthropicAPI(fault=lambda cid, p, seen: {"type": "errored", "error": err} if "temperature" in p else None)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api_b, ["--price-factor", "1.0"]), 0)
        self.assertEqual(rows(self.d("sync")), rows(self.d("b")))
        ts, tb = transcripts(self.d("sync")), transcripts(self.d("b"))
        for eid in ts:
            self.assertEqual(strip(ts[eid]), strip(tb[eid]))
            self.assertTrue(all(t["temperature_effective"] is None for a in tb[eid]["agents"].values() for t in a["turns"]))
        ok_b = collections.Counter(canonical(p) for p in api_b.batch_params if "temperature" not in p)
        ok_s = collections.Counter(x for x in api_s.sync_bodies if '"temperature"' not in x)
        self.assertEqual(ok_b, ok_s)

    def test_refusal_stop_inside_batches_equals_the_sync_path_and_ends_refusal(self):
        """Round 4: Anthropic ``stop_reason == "refusal"`` ends the agent ``refusal`` (V2 code: ``returned``), on the
        sync path and the batch path alike; everything else equal to the sync path."""
        def refusal(params):
            return {"id": "msg_refusal_" + canonical(params)[-24:].encode().hex()[:24], "type": "message", "role": "assistant",
                    "model": params["model"], "content": [{"type": "text", "text": "I can't help with that."}],
                    "stop_reason": "refusal", "stop_sequence": None,
                    "usage": {"input_tokens": 60, "output_tokens": 7, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 40}}

        api_s = FakeAnthropicAPI(sync_fault=lambda p: (200, refusal(p)) if target_key(p) else None)
        self.assertEqual(run_sync(self.d("sync"), self.ARGS, api_s), 0)
        api_b = FakeAnthropicAPI(fault=lambda cid, p, seen: {"type": "succeeded", "message": refusal(p)} if target_key(p) else None)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api_b, ["--price-factor", "1.0"]), 0)
        self.assertEqual(rows(self.d("sync")), rows(self.d("b")))
        ts, tb = transcripts(self.d("sync")), transcripts(self.d("b"))
        self.assertEqual(set(ts), set(tb))
        for eid in ts:
            self.assertEqual(strip(ts[eid]), strip(tb[eid]))
        self.assertEqual(spend_multiset(spend(self.d("sync"))), spend_multiset(spend(self.d("b"))))
        hit = {eid: tr for eid, tr in tb.items()
               if any(t["stop_reason"] == "refusal" for a in tr["agents"].values() for t in a["turns"])}
        self.assertGreaterEqual(len(hit), 1)
        for eid, tr in hit.items():
            a0 = tr["score"]["agents"]["a0"]
            self.assertEqual((a0["end_reason"], a0["abandoned"]), ("refusal", False))
            self.assertEqual(tr["agents"]["a0"]["stop_reason"], "refusal")
            self.assertIn("a0:refusal", rows(self.d("b"))[eid]["end_reasons"])
        self.assertFalse(any(a["end_reason"] == "refusal" for eid, tr in tb.items() if eid not in hit
                             for a in tr["score"]["agents"].values()))

    def test_crash_after_create_is_adopted_without_resubmitting(self):
        st = self.d("api_state")
        base_api = FakeAnthropicAPI()
        self.assertEqual(run_batch(self.d("ref"), self.ARGS, base_api), 0)
        api = FakeAnthropicAPI(state_dir=st)
        with mock.patch.dict(os.environ, {"SRC4_BATCH_TEST_CRASH_AFTER_CREATE": "1"}):
            with self.assertRaises(SystemExit):
                run_batch(self.d("b"), self.ARGS, api)
        state = json.load(open(os.path.join(self.d("b"), "batch_state", MODEL, "batches.json")))
        self.assertEqual(len(state["intents"]), 1)
        self.assertEqual(len(state["batches"]), 0)
        api2 = FakeAnthropicAPI(state_dir=st)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api2), 0)
        self.assertEqual(len(api2.batch_params) + len(api.batch_params), len(base_api.batch_params))  # nothing paid twice
        self.assertEqual(rows(self.d("ref")).keys(), rows(self.d("b")).keys())
        self.assertEqual(spend_multiset(spend(self.d("ref"))), spend_multiset(spend(self.d("b"))))

    def test_crash_while_in_flight_resumes_without_resubmitting(self):
        st = self.d("api_state")
        base_api = FakeAnthropicAPI()
        run_batch(self.d("ref"), self.ARGS, base_api)
        api = FakeAnthropicAPI(state_dir=st, polls_to_end=3)
        calls = {"n": 0}
        orig = BD.Backend.retrieve

        class Crash(BaseException):
            pass

        def crashing(self_, bid):
            calls["n"] += 1
            if calls["n"] == 4:  # second batch is in flight
                raise Crash()
            return orig(self_, bid)

        with mock.patch.object(BD.Backend, "retrieve", crashing), self.assertRaises(Crash):
            run_batch(self.d("b"), self.ARGS, api)
        n_before = len(api.batch_params)
        api2 = FakeAnthropicAPI(state_dir=st, polls_to_end=3)
        self.assertEqual(run_batch(self.d("b"), self.ARGS, api2), 0)
        self.assertEqual(n_before + len(api2.batch_params), len(base_api.batch_params))
        self.assertEqual(spend_multiset(spend(self.d("ref"))), spend_multiset(spend(self.d("b"))))
        for eid, tr in transcripts(self.d("ref")).items():
            self.assertEqual(strip(tr), strip(transcripts(self.d("b"))[eid]))

    def test_recollecting_a_batch_never_duplicates_spend_or_responses(self):
        st = self.d("api_state")
        api = FakeAnthropicAPI(state_dir=st)
        args = grid_args(2, configs="none", tasks="inventory_last_unit", aware="off")
        self.assertEqual(run_batch(self.d("b"), args, api), 0)
        n_spend = len(spend(self.d("b")))
        sd = os.path.join(self.d("b"), "batch_state", MODEL)
        p = os.path.join(sd, "batches.json")
        state = json.load(open(p))
        for b in state["batches"].values():
            b["status"] = "in_progress"  # as if the process died after writing results but before marking collected
        json.dump(state, open(p, "w"))
        n_resp = sum(1 for _ in open(os.path.join(sd, "responses.jsonl")))
        self.assertEqual(run_batch(self.d("b"), args, FakeAnthropicAPI(state_dir=st)), 0)
        self.assertEqual(len(spend(self.d("b"))), n_spend)
        self.assertEqual(sum(1 for _ in open(os.path.join(sd, "responses.jsonl"))), n_resp)

    def test_resume_skips_finished_episodes(self):
        args = grid_args(2, configs="none", tasks="seat_same", aware="both")
        run_batch(self.d("b"), args, FakeAnthropicAPI())
        api = FakeAnthropicAPI()
        buf = io.StringIO()
        self.assertEqual(run_batch(self.d("b"), args, api, buf=buf), 0)
        self.assertEqual(api.batch_params, [])
        self.assertIn("to run: 0", buf.getvalue())


# --------------------------------------------------------------------------
# Plumbing
# --------------------------------------------------------------------------


class Plumbing(TmpCase):
    def test_frozen_files_unchanged(self):
        self.assertEqual(harness.verify_freeze(), [])

    def test_tick_hook_is_removed_after_replay_even_on_exceptions(self):
        orig = scheduler.ConcurrentWorld
        eng = R.ReplayEngine({"schedule_kw": {}, "turn_cap": 0, "max_tokens": 4096, "temperature": 0.0, "prices": None, "dry_run": True,
                              "prompt_caching": True})
        cell = run5.build_grid([MODEL], ["locks"], ["transfer_shared_source"], [0], 4, [True], 1)[0]
        resp: Dict[str, Any] = {}
        rounds = 0
        while True:
            r = eng.replay(cell, resp)
            self.assertIs(scheduler.ConcurrentWorld, orig)
            if r.kind == "done":
                break
            rounds += 1
            self.assertEqual(len({(n.agent_id) for n in r.needs}), len(r.needs))
            self.assertEqual(len({n.round for n in r.needs}), 1)  # all needs of one replay are in one scheduler round
            for n in r.needs:
                resp[n.key] = fake_message(n.params)
        self.assertGreaterEqual(rounds, 3)  # randomized schedule: agents need completions in different rounds
        # V2 dry-run model under locks: lock, read, write, release, final text = 5 completions per agent
        self.assertEqual(r.transcript["totals"]["completions"], 4 * 5)

    def test_refusals(self):
        with quiet():
            self.assertEqual(BD.main(["--models", "openrouter:openai/gpt-5.5-20260423", "--out", self.d("x"), "--dry-run"]), 1)
            self.assertEqual(BD.main(["--models", "claude-sonnet-5,claude-fable-5", "--out", self.d("x"), "--dry-run"]), 1)
            os.makedirs(self.d("h"))
            with open(self.d("h/results.csv"), "w") as f:
                f.write("episode_id,lost_update\n")
            self.assertEqual(run_batch(self.d("h"), grid_args(2, configs="none", tasks="seat_same"), FakeAnthropicAPI()), 1)
            prices = self.d("p.json")
            json.dump({"models": {MODEL: {"input": 2, "output": 10, "confirmed": False}}}, open(prices, "w"))
            self.assertEqual(run_batch(self.d("u"), grid_args(2, configs="none", tasks="seat_same") + ["--prices", prices],
                                       FakeAnthropicAPI()), 1)

    def test_custom_ids_are_valid_and_unique(self):
        api = FakeAnthropicAPI()
        run_batch(self.d("b"), grid_args(2, configs="none,locks", tasks="seat_same"), api)
        st = json.load(open(os.path.join(self.d("b"), "batch_state", MODEL, "batches.json")))
        cids = [c for b in st["batches"].values() for c in b["requests"]]
        self.assertEqual(len(cids), len(set(cids)))
        self.assertTrue(all(len(c) <= 64 and c.replace("-", "").isalnum() for c in cids))


if __name__ == "__main__":
    unittest.main()
