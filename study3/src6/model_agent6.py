"""LLM-backed agent for the concurrency benchmark (Study 2 copy of src4/model_agent4.py).

V2 fixes (pre-spend reviews V1, V2): the last queued call of every reply is marked ``ToolCall.ends_turn`` (the
scheduler's think gap comes before every completion, V1 B2); a reply without a tool call that was cut off ends the
agent with reason ``truncated`` (max_tokens / length) or ``provider_error`` (finish reason ``error``), never
``returned`` (V2 §5); ``first_reply`` codes the first completion's tool calls (the manipulation check, V2 F3);
``ModelRunConfig.probe`` makes a *first-reply probe* (one completion, nothing executed); Qwen is routed to Alibaba
with ``allow_fallbacks: false`` and a completion served by any other host aborts the episode (V2 F6); the dry-run
model locks and messages when those tools are offered (V1 B4).

Study 2 changes (review T2 sec. 3): every completion records ``temperature_effective``, ``reasoning_tokens``
(OpenRouter/Gemini), Anthropic ``thinking_blocks`` / ``thinking_chars`` (thinking text is kept in the
transcript), ``model_served`` and ``served_host`` (OpenRouter upstream, "anthropic", or the Gemini batch API)
and ``max_tokens_exceeded`` (a host that ignored ``max_tokens``, as two Study 1 Qwen hosts did). The turn cap
is set per cell (``design6.call_cap``). Settings are otherwise Study 1's: max_tokens 4096, temperature 0.0
requested, no reasoning/thinking parameter. Qwen on OpenRouter is sent a provider preference
(:data:`OPENROUTER_ROUTING`, override with ``STUDY2_QWEN_PROVIDER``; empty disables). Spend entries carry
``provider_family`` (anthropic / openrouter / gemini) for the per-provider caps.

A :class:`ModelAgent` plugs into :mod:`scheduler` exactly like the scripted
agents in :mod:`agents4`: it is a generator that yields one
:class:`~scheduler.ToolCall` per scheduler step and receives the world's
response. Each agent has its own conversation with the model.

Loop (per agent)
    system   = :func:`world4.build_system_prompt` (agent id, task text, peers
               when messaging exists, and the one-sentence concurrency notice
               when ``WorldConfig.concurrency_aware_prompt`` is set);
    user     = :data:`START_MESSAGE`;
    tools    = :func:`world4.tool_schemas` for the configuration.
    Each completion:
      * no tool call   -> the agent is done; its final text is recorded and
                          returned as the scheduler report (never scored);
      * k tool calls   -> queued and yielded one per step (other agents act in
                          between); all k results go back in one user turn.
                          ``multi_tool_turns`` counts how often k > 1.
    Malformed arguments (unparseable JSON, non-object) are sent to the world as
    a non-object, which rejects them with 400 and commits nothing; the call is
    logged in the ledger like any other and listed in ``invalid_calls``.

Turn cap
    ``turn_cap`` is the maximum number of executed tool calls per agent and
    must equal ``ScheduleConfig.turn_cap`` (``run4`` sets both; the cap
    counts tool calls, which equal steps, not model turns). The
    scheduler ends an agent that wants call ``turn_cap + 1`` with reason
    ``turn_cap``, so an agent makes at most ``turn_cap + 1`` completions; the
    extra one is what tells "wanted another call" (``turn_cap``) apart from
    "finished" (``returned``). A hard completion cap of ``turn_cap + 1`` is
    also enforced here as a safety net (it raises, ending the agent with
    reason ``error``; it cannot fire when the two caps are equal).

Provider failures and the spend cap
    Any exception from the provider is re-raised as :class:`ProviderFailure`,
    and exceeding the spend cap raises :class:`BudgetExceeded`. Both derive
    from ``BaseException`` on purpose: the scheduler converts ordinary
    exceptions into an agent ``error`` end and would otherwise score a broken
    episode; these abort the whole episode instead, so nothing is written and
    a resumed run repeats it.

Prompt caching
    For Anthropic the system prompt and the last tool schema carry
    ``cache_control: {"type": "ephemeral"}`` (tools -> system is the cache
    prefix order, so the tools breakpoint is shared by every agent and episode
    with the same configuration, the system breakpoint by one agent's turns).
    Note: Anthropic ignores breakpoints on prefixes shorter than the model's
    minimum cacheable length (4,096 tokens for Claude Haiku 4.5); these
    prompts are far shorter, so expect ``cache_*`` tokens of 0 on Haiku.
    OpenRouter requests are sent unchanged.

Temperature
    0.0 is requested; :mod:`providers` drops it at runtime for models that
    reject it and records the effective value per completion.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import providers6 as providers
from providers6 import Completion
from scheduler6 import AgentContext, AgentSpec, AgentStop, ToolCall
from world6 import WorldConfig, build_system_prompt, tool_schemas

DEFAULT_TURN_CAP = 12
# Reasoning tokens count against max_tokens on OpenRouter (see run_crossprovider.sh).
DEFAULT_MAX_TOKENS = 4096
TEMPERATURE = 0.0
# Stop reasons meaning "cut off" (Anthropic stop_reason / OpenRouter finish_reason).
TRUNCATED_STOPS = ("max_tokens", "length", "error")
# end reason of an agent whose last completion had no tool call and was cut off (V2 §5)
TRUNCATION_END = {"max_tokens": "truncated", "length": "truncated", "error": "provider_error"}
# Round 4: refusal and safety stops (Anthropic stop_reason "refusal"; OpenRouter finish_reason "content_filter",
# which is also what src6_batch/gemini_translate.py gives every Gemini SAFETY / RECITATION / PROHIBITED_CONTENT /
# BLOCKLIST / SPII finish and every blocked prompt). An agent whose completion stops this way with no tool call
# ends with this end reason, never "returned". A completion with a tool call runs its calls as before.
REFUSAL_END = {"refusal": "refusal", "content_filter": "content_filter"}
START_MESSAGE = "Begin. When you are finished, reply with a one-line summary and no tool call."
CACHE_CONTROL = {"type": "ephemeral"}
FINAL_TEXT_REPORT_CHARS = 500
QWEN_MODEL = "openrouter:qwen/qwen3.6-27b-20260422"
OPENROUTER_ROUTING: Dict[str, Dict[str, Any]] = {
    # V2 (review V2 F6): no fallbacks -- with fallbacks an Alibaba 429/outage silently re-created Study 1's host mix
    QWEN_MODEL: {"order": [os.environ.get("STUDY2_QWEN_PROVIDER", "alibaba")], "allow_fallbacks": False},
}


def required_host(model: str) -> Optional[str]:
    """The upstream host every completion of ``model`` must be served by (lower-case prefix), or None."""
    r = routing_for(model)
    return None if r is None else str(r["order"][0]).lower()


def host_ok(model: str, served_host: Any) -> bool:
    req = required_host(model)
    return req is None or str(served_host or "").lower().replace(" ", "").startswith(req)
GEMINI_MODEL = "openrouter:google/gemini-4-argon-20261013"  # Study 1 id; served by the Gemini Batch API only


def provider_family(model: str) -> str:
    """anthropic / openrouter / gemini (Gemini runs on Google's Batch API, never through OpenRouter)."""
    if model == GEMINI_MODEL or model.startswith("gemini"):
        return "gemini"
    if model.startswith("ollama:"):
        return "local"
    if model.startswith("openrouter:"):
        return "openrouter"
    if model.startswith("fake"):
        return "fake"
    return "anthropic"


def routing_for(model: str) -> Optional[Dict[str, Any]]:
    r = OPENROUTER_ROUTING.get(model)
    if r is None or not r.get("order") or not r["order"][0]:
        return None
    return r


class ProviderFailure(BaseException):
    """A model API call failed; the episode is aborted and not written."""


class BudgetExceeded(BaseException):
    """Recorded spend passed the cap; the episode is aborted and not written."""


# --------------------------------------------------------------------------
# Prices and spend
# --------------------------------------------------------------------------


_DATE_SUFFIX = re.compile(r"-\d{8}")


def model_key_matches(key: str, model: str) -> bool:
    """True iff ``model`` is exactly ``key`` or ``key`` plus a dated suffix ``-YYYYMMDD``.

    So ``claude-haiku-4-5`` matches ``claude-haiku-4-5-20251001``, but
    ``claude-fable-5`` matches neither ``claude-fable-5.1`` nor
    ``claude-fable-5.1-20261201`` nor ``claude-fable-5-1``.
    """
    return model == key or (model.startswith(key) and _DATE_SUFFIX.fullmatch(model[len(key):]) is not None)


class PriceTable:
    """USD per million tokens, keyed by exact model id or dated-prefix (:func:`model_key_matches`).

    Entry fields: ``input``, ``output``, ``cache_write`` (5-minute),
    ``cache_read``, ``confirmed`` (bool; real runs refuse unconfirmed entries).
    An exact key wins over a dated-prefix key.
    """

    def __init__(self, models: Dict[str, Dict[str, Any]]) -> None:
        self.models = dict(models)

    @classmethod
    def load(cls, path: str) -> "PriceTable":
        with open(path) as f:
            data = json.load(f)
        return cls(data.get("models", {}))

    def lookup(self, model: str) -> Optional[Dict[str, Any]]:
        if model in self.models:
            best: Optional[str] = model
        else:
            best = next((k for k in self.models if model_key_matches(k, model)), None)
        return None if best is None else dict(self.models[best], prefix=best)

    def problems(self, models: Sequence[str]) -> List[str]:
        """Models without a price entry, or whose entry is not confirmed."""
        out = []
        for m in models:
            entry = self.lookup(m)
            if entry is None:
                out.append(f"{m}: no entry in prices.json")
            elif entry.get("confirmed") is not True:
                out.append(f"{m}: price entry '{entry['prefix']}' is a placeholder (confirmed=false)")
        return out

    def token_cost(self, model: str, usage: Dict[str, Any]) -> Optional[float]:
        """Cost from token counts, or ``None`` if the model has no entry."""
        entry = self.lookup(model)
        if entry is None:
            return None
        price_in = float(entry.get("input", 0.0))
        total = (
            (usage.get("input") or 0) * price_in
            + (usage.get("output") or 0) * float(entry.get("output", 0.0))
            + (usage.get("cache_write") or 0) * float(entry.get("cache_write", price_in * 1.25))
            + (usage.get("cache_read") or 0) * float(entry.get("cache_read", price_in * 0.1))
        )
        return total / 1e6

    def episode_bound(self, model: str, n_agents: int, turn_cap: int, max_tokens: int, input_tokens_per_call: int = 4000) -> float:
        """Conservative prior for one episode's cost (no observed episodes yet)."""
        calls = n_agents * (turn_cap + 1)
        per_call = self.token_cost(model, {"input": input_tokens_per_call, "output": max_tokens}) or 0.0
        return calls * per_call


def completion_cost(model: str, comp: Completion, usage: Dict[str, Any], prices: Optional[PriceTable]) -> Tuple[float, str]:
    """``(usd, source)`` for one completion.

    OpenRouter's reported ``usage.cost`` wins (source ``reported``); otherwise
    token counts times the price table (source ``price_table``); with no price
    entry the cost is 0 (source ``unpriced``).
    """
    reported = (comp.provider_meta or {}).get("cost")
    if reported is not None:
        return float(reported), "reported"
    if prices is not None:
        cost = prices.token_cost(model, usage)
        if cost is not None:
            return cost, "price_table"
    return 0.0, "unpriced"


class SpendTracker:
    """Append-only spend log (one JSON line per completion) with an optional cap.

    The log lives in the output directory, so spend from earlier (resumed or
    aborted) runs counts toward the cap.
    """

    def __init__(self, path: Optional[str], max_usd: Optional[float] = None) -> None:
        self.path = path
        self.max_usd = max_usd
        self.total = 0.0
        if path and os.path.exists(path):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.total += float(json.loads(line).get("cost_usd") or 0.0)
                        except (ValueError, json.JSONDecodeError):
                            continue

    def record(self, entry: Dict[str, Any]) -> None:
        self.total += float(entry.get("cost_usd") or 0.0)
        if self.path:
            with open(self.path, "a") as f:
                f.write(json.dumps(entry, sort_keys=True) + "\n")
        if self.max_usd is not None and self.total > self.max_usd:
            raise BudgetExceeded(f"spend ${self.total:.4f} passed the cap ${self.max_usd:.2f}")


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------


class UsageProbeClient:
    """Wraps an ``anthropic.Anthropic`` client to keep the last response's usage.

    ``providers.AnthropicProvider`` (shared unchanged with the previous paper)
    keeps only input/output tokens; cache-read and cache-write tokens are read
    here instead.
    """

    def __init__(self, client: Any) -> None:
        self._client = client
        self.last_usage: Any = None
        self.messages = _ProbeMessages(self)


class _ProbeMessages:
    def __init__(self, outer: UsageProbeClient) -> None:
        self._outer = outer

    def create(self, **kwargs: Any) -> Any:
        resp = self._outer._client.messages.create(**kwargs)
        self._outer.last_usage = getattr(resp, "usage", None)
        return resp


def make_provider(model: str, dry_run: bool = False, fake_policy: Optional[Callable] = None) -> Tuple[Any, Optional[UsageProbeClient]]:
    """``(provider, usage_probe)`` for a model id. Dry runs never touch the network."""
    if dry_run or model.startswith("fake"):
        return FakeProvider(fake_policy), None
    if model.startswith(providers.OllamaProvider.PREFIX):
        return providers.OllamaProvider(), None
    if model.startswith(providers.OpenRouterProvider.PREFIX):
        providers.RECORD_COST = True  # log OpenRouter usage.cost (USD) per completion
        return providers.OpenRouterProvider(routing=routing_for(model)), None
    import anthropic  # noqa: PLC0415 - only needed for Anthropic models

    probe = UsageProbeClient(anthropic.Anthropic())
    return providers.AnthropicProvider(client=probe), probe


def _attr(obj: Any, name: str) -> Optional[int]:
    if obj is None:
        return None
    val = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return val if isinstance(val, int) else None


def normalized_usage(comp: Completion, probe: Optional[UsageProbeClient]) -> Dict[str, Any]:
    """``input`` (uncached), ``output``, ``cache_read``, ``cache_write`` (+ ``reasoning`` if known)."""
    usage = {"input": comp.usage.get("input"), "output": comp.usage.get("output"), "cache_read": 0, "cache_write": 0}
    if probe is not None and probe.last_usage is not None:
        usage["cache_read"] = _attr(probe.last_usage, "cache_read_input_tokens") or 0
        usage["cache_write"] = _attr(probe.last_usage, "cache_creation_input_tokens") or 0
    rtok = (comp.provider_meta or {}).get("reasoning_tokens")
    if rtok is not None:
        usage["reasoning"] = rtok
    return usage


# --------------------------------------------------------------------------
# Fake provider (dry runs and tests; deterministic, no network)
# --------------------------------------------------------------------------

FAKE_TIMESTAMP = "1970-01-01T00:00:00Z"
_RECORD_RE = re.compile(r"\b(?:inventory|seat|account|ticket|budget):[\w/.\-]*\w")


def _approx_tokens(*parts: Any) -> int:
    return max(1, len(json.dumps(parts, default=str, sort_keys=True)) // 4)


def _system_text(system: Any) -> str:
    if isinstance(system, str):
        return system
    return "".join(b.get("text", "") for b in system if isinstance(b, dict))


def _assistant_turns(messages: List[Dict[str, Any]]) -> int:
    return sum(1 for m in messages if m["role"] == "assistant")


def _last_results(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for m in reversed(messages):
        if m["role"] == "user" and isinstance(m["content"], list):
            out = []
            for b in m["content"]:
                if b.get("type") == "tool_result":
                    try:
                        out.append(json.loads(b["content"]))
                    except (TypeError, ValueError):
                        out.append({})
            return out
    return []


def _fmt_like(old: Any, new: Decimal) -> Any:
    return int(new) if isinstance(old, int) else f"{new:.2f}"


def _all_results(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], list):
            for b in m["content"]:
                if b.get("type") == "tool_result":
                    try:
                        out.append(json.loads(b["content"]))
                    except (TypeError, ValueError):
                        out.append({})
    return out


def scripted_policy(system: str, tools: List[Dict[str, Any]], messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dry-run 'model'. Without locks: read every record named in the task (one turn, several calls), write once
    from what it read (``expected_version`` when the schema offers it), stop. With locks (V2, review V1 B4): first
    lock every record of the task in sorted order (lease 10), then read, then write with the fencing tokens, then
    release. With messages: the first turn also messages every peer, and the turn after the write reads the
    mailbox. Exercises queueing, blocking lock waits, fencing, the message channel, writes and termination."""
    turn = _assistant_turns(messages)
    task_line = next((ln for ln in system.splitlines() if ln.startswith("Task:")), "")
    records = list(dict.fromkeys(_RECORD_RE.findall(task_line)))
    names = {t["name"] for t in tools}
    locks = "acquire_lock" in names
    msgs = "send_message" in names
    peers_line = next((ln for ln in system.splitlines() if ln.startswith("Agents you can message:")), "")
    peers = [p.strip(" .") for p in peers_line.split(":", 1)[1].split(",")] if peers_line else []
    me = (re.match(r"You are agent (\S+)\.", system) or [None, "?"])[1]
    hello = [{"type": "tool_use", "name": "send_message", "input": {"to_agent": p, "text": f"{me} starting"}}
             for p in peers] if msgs else []
    read_turn, write_turn = (1, 2) if locks else (0, 1)
    if locks and turn == 0 and records:
        return hello + [{"type": "tool_use", "name": "acquire_lock", "input": {"record_id": r, "lease_calls": 10}}
                        for r in sorted(records)]
    if turn == read_turn and records:
        return ([] if locks else hello) + [{"type": "tool_use", "name": "get_record", "input": {"record_id": r}} for r in records]
    if locks and turn == write_turn + 1:
        return [{"type": "tool_use", "name": "release_lock", "input": {"record_id": r}} for r in sorted(records)] + \
            ([{"type": "tool_use", "name": "read_messages", "input": {}}] if msgs else [])
    if not locks and msgs and turn == write_turn + 1:
        return [{"type": "tool_use", "name": "read_messages", "input": {}}]
    if turn == write_turn:
        seen = {r.get("record_id"): r for r in _last_results(messages) if r.get("ok") and "value" in r}
        tokens = {r.get("record_id"): r["fencing_token"] for r in _all_results(messages)
                  if r.get("ok") and r.get("fencing_token") is not None} if locks else {}
        out = _write_calls(task_line, tools, seen, tokens)
        if out is not None:
            return out
    return [{"type": "text", "text": "Done."}]


def _write_calls(task_line: str, tools: List[Dict[str, Any]], seen: Dict[str, Dict[str, Any]],
                 tokens: Dict[str, int]) -> Optional[List[Dict[str, Any]]]:
    """The write(s) of the dry-run 'model' for its task line, from the read results ``seen`` (``expected_version`` when
    the schema offers it and the read showed one; ``fencing_token`` for every record in ``tokens``); None if a record
    it needs was not read."""
    has_version = any(t["name"] == "update_record" and "expected_version" in t["input_schema"]["properties"] for t in tools)

    def fence(rid: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if has_version and seen.get(rid, {}).get("version") is not None:
            args["expected_version"] = seen[rid]["version"]
        if rid in tokens:
            args["fencing_token"] = tokens[rid]
        return args

    def upd(rid: str, value: Any) -> Dict[str, Any]:
        return {"type": "tool_use", "name": "update_record", "input": fence(rid, {"record_id": rid, "value": value})}

    def claim(rid: str, holder: str) -> Dict[str, Any]:
        return {"type": "tool_use", "name": "claim", "input": fence(rid, {"record_id": rid, "holder": holder})}

    def val(rid: str) -> Decimal:
        return Decimal(str(seen[rid]["value"]))

    try:
        if m := re.search(r"Assign (\S+) to (\S+), only", task_line):
            return [claim(m.group(1), m.group(2))]
        if m := re.search(r"(?:Sell|Withdraw) (\S+) from (\S+?),", task_line):
            rid = m.group(2)
            return [upd(rid, _fmt_like(seen[rid]["value"], val(rid) - Decimal(m.group(1))))]
        if m := re.search(r"Move (\S+) from (\S+) to (\S+?),", task_line):
            amt, src, dst = Decimal(m.group(1)), m.group(2), m.group(3)
            return [upd(src, f"{val(src) - amt:.2f}"), upd(dst, f"{val(dst) + amt:.2f}")]
        if m := re.search(r"Record a spend of (\S+) in (\S+?),", task_line):
            rid = m.group(2)
            return [upd(rid, f"{val(rid) + Decimal(m.group(1)):.2f}")]
        # paraphrased instructions (Intent.wording == 1)
        if m := re.search(r"Give (\S+) to (\S+), but only", task_line):
            return [claim(m.group(1), m.group(2))]
        if m := re.search(r"Reduce (\S+) by (\S+) to record", task_line):
            rid = m.group(1)
            return [upd(rid, _fmt_like(seen[rid]["value"], val(rid) - Decimal(m.group(2))))]
        if m := re.search(r"Transfer (\S+) out of (\S+) into (\S+?),", task_line):
            amt, src, dst = Decimal(m.group(1)), m.group(2), m.group(3)
            return [upd(src, f"{val(src) - amt:.2f}"), upd(dst, f"{val(dst) + amt:.2f}")]
        if m := re.search(r"Take (\S+) out of (\S+?),", task_line):
            rid = m.group(2)
            return [upd(rid, _fmt_like(seen[rid]["value"], val(rid) - Decimal(m.group(1))))]
        if m := re.search(r"Add (\S+) to (\S+?), provided", task_line):
            rid = m.group(2)
            return [upd(rid, f"{val(rid) + Decimal(m.group(1)):.2f}")]
    except KeyError:
        return None
    return None


FAKE_STYLES = ("lock_first", "read_then_lock", "plain")


def fake_style(system: str) -> str:
    """Study 3 dry runs: the protocol of the varied fake 'model', fixed per (agent, task line) by a hash."""
    return FAKE_STYLES[int(hashlib.sha256(system.encode()).hexdigest()[:8], 16) % len(FAKE_STYLES)]


def varied_policy(system: str, tools: List[Dict[str, Any]], messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Study 3 dry-run 'model' (deterministic; exercises every path the analysis reads). With locks offered, one of
    three protocols per (agent, task) (:func:`fake_style`): ``lock_first`` (the Study 2 fake: lock, read, write,
    release); ``read_then_lock`` (read, lock, write from the first read with the tokens: a stale-basis fenced write;
    release); ``plain`` (read, then write; but if a read showed ``locked: true`` or a write got 423 before it wrote,
    it locks, re-reads, writes and releases: a reactive lock). Without locks, or with messages offered (the channel
    rehearsal), the Study 2 fake (:func:`scripted_policy`)."""
    names = {t["name"] for t in tools}
    if "acquire_lock" not in names or "send_message" in names:
        return scripted_policy(system, tools, messages)
    style = fake_style(system)
    if style == "lock_first":
        return scripted_policy(system, tools, messages)
    task_line = next((ln for ln in system.splitlines() if ln.startswith("Task:")), "")
    records = sorted(dict.fromkeys(_RECORD_RE.findall(task_line)))
    done: List[str] = []
    for m in messages:
        if m["role"] != "assistant":
            continue
        used = {b.get("name") for b in m["content"] if b.get("type") == "tool_use"}
        done.append("write" if used & {"update_record", "claim"} else "lock" if "acquire_lock" in used
                    else "release" if "release_lock" in used else "read" if "get_record" in used else "other")
    results = _all_results(messages)
    tokens = {r.get("record_id"): r["fencing_token"] for r in results if r.get("ok") and r.get("fencing_token") is not None}
    lock = [{"type": "tool_use", "name": "acquire_lock", "input": {"record_id": r, "lease_calls": 10}} for r in records]
    read = [{"type": "tool_use", "name": "get_record", "input": {"record_id": r}} for r in records]
    release = [{"type": "tool_use", "name": "release_lock", "input": {"record_id": r}} for r in records]
    if style == "read_then_lock":
        if not done:
            return read
        if done == ["read"]:
            return lock
        if done == ["read", "lock"]:
            first = {}
            for m in messages:  # the first read's results (the stale basis on purpose)
                if m["role"] == "user" and isinstance(m["content"], list) and not first:
                    for b in m["content"]:
                        if b.get("type") == "tool_result":
                            try:
                                r = json.loads(b["content"])
                            except (TypeError, ValueError):
                                continue
                            if r.get("ok") and "value" in r:
                                first[r.get("record_id")] = r
            out = _write_calls(task_line, tools, first, tokens)
            return out if out is not None else release
        if done == ["read", "lock", "write"]:
            return release
        return [{"type": "text", "text": "Done."}]
    # plain, with a reactive lock after a perceivable sign of a lock
    signal = any(r.get("locked") is True or r.get("status") == 423 for r in results)
    if not done:
        return read
    if "write" in done and done[-1] == "write":
        last = _last_results(messages)
        if any(r.get("status") == 423 for r in last) and "lock" not in done:
            return lock
        return release if "lock" in done else [{"type": "text", "text": "Done."}]
    if "release" in done:
        return [{"type": "text", "text": "Done."}]
    if signal and "lock" not in done:
        return lock
    if done[-1] == "lock":
        return read
    seen = {r.get("record_id"): r for r in _last_results(messages) if r.get("ok") and "value" in r}
    out = _write_calls(task_line, tools, seen, tokens)
    return out if out is not None else [{"type": "text", "text": "Done."}]


class FakeProvider:
    """Deterministic stand-in for a provider: ``policy(system_text, tools, messages) -> blocks``.

    Tool-use ids are filled in deterministically; usage is approximated as
    characters / 4 so the price table and spend cap can be exercised.
    """

    name = "fake"

    def __init__(self, policy: Optional[Callable] = None) -> None:
        self.policy = policy or varied_policy  # Study 3: the varied fake (scripted_policy without locks)
        self.n_calls = 0

    def complete(self, model, system, tools, messages, max_tokens, temperature) -> Completion:
        self.n_calls += 1
        blocks = copy.deepcopy(self.policy(_system_text(system), tools, messages))
        n_prior = sum(1 for m in messages if m["role"] == "assistant" for b in m["content"] if b.get("type") == "tool_use")
        for i, b in enumerate(b for b in blocks if b["type"] == "tool_use"):
            b.setdefault("id", f"fake_{n_prior + i}")
        has_tool = any(b["type"] == "tool_use" for b in blocks)
        return Completion(
            blocks=blocks,
            provider=self.name,
            model_requested=model,
            model_served=f"fake/{model}",
            temperature_requested=temperature,
            temperature_effective=temperature,
            usage={"input": _approx_tokens(system, tools, messages), "output": _approx_tokens(blocks)},
            timestamp_utc=FAKE_TIMESTAMP,
            raw_assistant_message=None,
            stop_reason="tool_use" if has_tool else "end_turn",
        )

    @staticmethod
    def history_assistant(completion: Completion) -> Dict[str, Any]:
        return {"role": "assistant", "content": completion.blocks}

    @staticmethod
    def history_tool_results(results: list) -> Dict[str, Any]:
        return {"role": "user", "content": results}


# --------------------------------------------------------------------------
# The agent
# --------------------------------------------------------------------------


@dataclass
class ModelRunConfig:
    """Everything a :class:`ModelAgent` needs besides its :class:`AgentContext`."""

    model: str
    provider: Any
    world_config: WorldConfig
    turn_cap: int = DEFAULT_TURN_CAP
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: Optional[float] = TEMPERATURE
    prompt_caching: bool = True
    prices: Optional[PriceTable] = None
    spend: Optional[SpendTracker] = None
    usage_probe: Optional[UsageProbeClient] = None
    episode_id: str = ""
    probe: bool = False  # first-reply probe: one completion per agent, no tool call executed (V2 grid, block P)


def _is_malformed(args: Any) -> bool:
    return not isinstance(args, dict) or "_unparsed_arguments" in args


FIRST_REPLY_CODES = ("lock", "cas", "blind_write", "read", "message", "other", "no_call")


def first_reply_code(tool_uses: List[Dict[str, Any]]) -> str:
    """Code of one completion's tool calls (the first reply: the manipulation check, review V2 F3).

    ``lock`` any acquire_lock; ``cas`` any write with expected_version; ``blind_write`` any write without
    expected_version and without fencing_token; ``read`` get_record/list_effects only; ``message`` any messaging
    call; ``no_call`` a text-only reply. Several codes are joined with '+' in this order."""
    kinds = set()
    for t in tool_uses:
        name, args = t.get("name"), t.get("input") if isinstance(t.get("input"), dict) else {}
        if name in ("acquire_lock", "renew_lock"):
            kinds.add("lock")
        elif name in ("update_record", "claim"):
            kinds.add("cas" if args.get("expected_version") is not None
                      else "blind_write" if args.get("fencing_token") is None else "other")
        elif name in ("get_record", "list_effects"):
            kinds.add("read")
        elif name in ("send_message", "read_messages"):
            kinds.add("message")
        else:
            kinds.add("other")
    if not kinds:
        return "no_call"
    if kinds - {"read"}:
        kinds.discard("read")
    return "+".join(k for k in FIRST_REPLY_CODES if k in kinds)


class ModelAgent:
    """One model-driven agent; :meth:`run` is the scheduler generator.

    :attr:`record` is filled as the agent runs and stays readable after the
    scheduler closes the generator.
    """

    def __init__(self, ctx: AgentContext, rc: ModelRunConfig) -> None:
        if rc.world_config.coordination != ctx.coordination:
            raise ValueError("ModelRunConfig.world_config does not match the episode's coordination config")
        self.ctx = ctx
        self.rc = rc
        self.max_completions = rc.turn_cap + 1
        self.schemas = tool_schemas(ctx.coordination, rc.world_config)
        self.system_text = build_system_prompt(ctx.agent_id, ctx.peers, ctx.intent.describe(), rc.world_config)
        self.cached = rc.prompt_caching and getattr(rc.provider, "name", "") == "anthropic"
        if self.cached:
            self.tools_arg: List[Dict[str, Any]] = copy.deepcopy(self.schemas)
            self.tools_arg[-1]["cache_control"] = dict(CACHE_CONTROL)
            self.system_arg: Any = [{"type": "text", "text": self.system_text, "cache_control": dict(CACHE_CONTROL)}]
        else:
            self.tools_arg = self.schemas
            self.system_arg = self.system_text
        self.record: Dict[str, Any] = {
            "agent_id": ctx.agent_id,
            "intent": ctx.intent.describe(),
            "system": self.system_text,
            "prompt_caching": self.cached,
            "messages": [],          # neutral history (JSON), exactly what the model saw
            "turns": [],             # one entry per completion
            "executions": [],        # one entry per executed tool call
            "completions": 0,
            "multi_tool_turns": 0,
            "max_tool_calls_in_turn": 0,
            "invalid_calls": [],
            "unexecuted_tool_calls": [],  # queued calls never run because the scheduler ended the agent
            "final_text": None,
            "stop_reason": None,
            "truncated": False,
            "first_reply": None,         # first_reply_code of the first completion
            "probe_calls": None,         # probe mode: the tool calls the first completion asked for (not executed)
            "usage": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
            "cost_usd": 0.0,
        }

    def _complete(self, history: List[Dict[str, Any]]) -> Completion:
        rc = self.rc
        if rc.usage_probe is not None:
            rc.usage_probe.last_usage = None
        try:
            return rc.provider.complete(rc.model, self.system_arg, self.tools_arg, history, rc.max_tokens, rc.temperature)
        except Exception as exc:  # noqa: BLE001 - any API failure aborts the episode
            raise ProviderFailure(f"{rc.model}: {type(exc).__name__}: {exc}") from exc

    def _log_completion(self, comp: Completion) -> None:
        rc, rec = self.rc, self.record
        usage = normalized_usage(comp, rc.usage_probe)
        cost, source = completion_cost(rc.model, comp, usage, rc.prices)
        for k in ("input", "output", "cache_read", "cache_write"):
            rec["usage"][k] += usage.get(k) or 0
        rec["cost_usd"] += cost
        meta = comp.provider_meta or {}
        served = str(comp.model_served or "")
        turn = {
            "index": rec["completions"],
            "content": copy.deepcopy(comp.blocks),
            "stop_reason": comp.stop_reason,
            "model_served": comp.model_served,
            "served_host": served.split(" @", 1)[1] if " @" in served else getattr(comp, "provider", None),
            "temperature_requested": comp.temperature_requested,
            "temperature_effective": comp.temperature_effective,
            "reasoning_tokens": usage.get("reasoning"),
            "thinking_blocks": meta.get("thinking_blocks", 0),
            "thinking_chars": meta.get("thinking_chars", 0),
            "max_tokens_exceeded": (usage.get("output") or 0) > rc.max_tokens,
            "at_utc": comp.timestamp_utc,
            "usage": usage,
            "cost_usd": cost,
            "cost_source": source,
        }
        if comp.provider_meta:
            turn["provider_meta"] = copy.deepcopy(comp.provider_meta)
        rec["turns"].append(turn)
        host_bad = getattr(rc.provider, "name", "") not in ("fake",) and not host_ok(rc.model, turn["served_host"])
        if rc.spend is not None:
            rc.spend.record(
                {
                    "episode_id": rc.episode_id,
                    "agent_id": self.ctx.agent_id,
                    "model": rc.model,
                    "completion": rec["completions"],
                    "usage": usage,
                    "cost_usd": cost,
                    "cost_source": source,
                    "at_utc": comp.timestamp_utc,
                    "provider_family": provider_family(rc.model),
                }
            )
        if host_bad:  # counted in the spend, then the episode is aborted (re-run later), never scored (V2 F6)
            raise ProviderFailure(f"{rc.model}: served by {turn['served_host']!r}, required {required_host(rc.model)!r}")

    def run(self):
        rc, rec = self.rc, self.record
        history: List[Dict[str, Any]] = [{"role": "user", "content": START_MESSAGE}]
        rec["messages"].append({"role": "user", "content": START_MESSAGE})
        while True:
            if rec["completions"] >= self.max_completions:
                raise RuntimeError(f"model completion cap {self.max_completions} reached (turn_cap mismatch with scheduler)")
            comp = self._complete(history)
            rec["completions"] += 1
            self._log_completion(comp)
            rec["stop_reason"] = comp.stop_reason
            text = "".join(b.get("text", "") for b in comp.blocks if b["type"] == "text")
            tool_uses = comp.tool_uses
            if rec["completions"] == 1:
                rec["first_reply"] = first_reply_code(tool_uses)
            if rc.probe:
                rec["probe_calls"] = [{"tool": t["name"], "args": copy.deepcopy(t.get("input"))} for t in tool_uses]
                rec["final_text"] = text
                rec["truncated"] = not tool_uses and comp.stop_reason in TRUNCATED_STOPS
                rec["messages"].append({"role": "assistant", "content": copy.deepcopy(comp.blocks)})
                return AgentStop("probe", text[:FINAL_TEXT_REPORT_CHARS] if text else None)
            if not tool_uses:
                rec["final_text"] = text
                rec["truncated"] = comp.stop_reason in TRUNCATED_STOPS
                rec["messages"].append({"role": "assistant", "content": copy.deepcopy(comp.blocks)})
                report = text[:FINAL_TEXT_REPORT_CHARS] if text else None
                if rec["truncated"]:
                    return AgentStop(TRUNCATION_END.get(comp.stop_reason, "truncated"), report)
                if comp.stop_reason in REFUSAL_END:
                    return AgentStop(REFUSAL_END[comp.stop_reason], report)
                return report
            rec["max_tool_calls_in_turn"] = max(rec["max_tool_calls_in_turn"], len(tool_uses))
            if len(tool_uses) > 1:
                rec["multi_tool_turns"] += 1
            history.append(rc.provider.history_assistant(comp))
            rec["messages"].append({"role": "assistant", "content": copy.deepcopy(comp.blocks)})
            results = []
            for i, tu in enumerate(tool_uses):
                raw = tu.get("input")
                malformed = _is_malformed(raw)
                if malformed:
                    # Sent to the world as a raw string: 400, nothing commits, the call is logged.
                    unparsed = raw.get("_unparsed_arguments") if isinstance(raw, dict) else raw
                    call_args: Any = unparsed if isinstance(unparsed, str) else json.dumps(unparsed, default=str)
                else:
                    call_args = raw
                try:
                    response = yield ToolCall(tu["name"], call_args, i == len(tool_uses) - 1)
                except GeneratorExit:
                    # Stopped by the scheduler (turn cap, stall, max rounds) with calls still queued.
                    rec["unexecuted_tool_calls"] = [
                        {"tool_use_id": t["id"], "tool": t["name"], "args": copy.deepcopy(t.get("input"))} for t in tool_uses[i:]
                    ]
                    raise
                execution = {
                    "completion": rec["completions"] - 1,
                    "queue_index": i,
                    "queue_len": len(tool_uses),
                    "tool_use_id": tu["id"],
                    "tool": tu["name"],
                    "args": copy.deepcopy(raw),
                    "malformed_args": malformed,
                    "response": copy.deepcopy(response),
                }
                rec["executions"].append(execution)
                status = response.get("status") if isinstance(response, dict) else None
                if malformed or status == 400 or (status == 404 and response.get("error") == "tool_unavailable"):
                    rec["invalid_calls"].append(
                        {"tool_use_id": tu["id"], "tool": tu["name"], "args": copy.deepcopy(raw), "status": status, "error": response.get("message")}
                    )
                result = {"type": "tool_result", "tool_use_id": tu["id"], "content": json.dumps(response, sort_keys=True)}
                if not response.get("ok"):
                    result["is_error"] = True
                results.append(result)
            history.append(rc.provider.history_tool_results(results))
            rec["messages"].append({"role": "user", "content": copy.deepcopy(results)})


def model_agent_spec(rc: ModelRunConfig, records_out: Dict[str, Dict[str, Any]]) -> AgentSpec:
    """An :class:`AgentSpec` whose agents are :class:`ModelAgent` instances.

    Each agent's :attr:`ModelAgent.record` is stored in ``records_out`` under
    its agent id when the scheduler creates it.
    """

    def make(ctx: AgentContext):
        agent = ModelAgent(ctx, rc)
        records_out[ctx.agent_id] = agent.record
        return agent.run()

    return AgentSpec(f"model:{rc.model}", make)


def now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
