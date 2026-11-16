"""Deterministic replay of one harness episode with recorded model responses.

Seam: the HTTP transport under the real ``anthropic`` SDK client. The episode
runs through the harness code end to end and unmodified --
``run6.run_one`` -> ``scheduler.run_episode`` -> ``model_agent6.ModelAgent``
-> ``providers.AnthropicProvider`` -> ``model_agent6.UsageProbeClient`` ->
``anthropic.Anthropic().messages.create`` -- exactly as ``run6`` builds it
for a real Anthropic run (``make_provider``). Only the network is replaced:
the SDK hands the serialized ``POST /v1/messages`` body to an
``httpx.MockTransport``, so the captured body is byte for byte what the sync
path would send; the transport answers with a recorded Message (the
``message`` object of a batch result) and the SDK parses it as it would a
sync response.

Why replay is exact: the scheduler is simulated (seeded round order, no
wall clock), so every completion request depends only on the responses
before it. A request an agent makes in scheduler round r depends only on the
results of its own tool calls, all executed in rounds < r. So in one replay
we can collect, for round r, the request of *every* agent that needs a
completion in round r (the first one whose response is not recorded fixes r):

* a missing response is recorded as a :class:`Need` and answered with a
  placeholder (an empty end_turn message, which ends that agent);
* the episode is abandoned at the next world tick (start of round r+1),
  before anything that depends on a placeholder can produce a request.

Placeholders never reach a written transcript: an episode is only written
from a replay with no missing response. The tick is observed by running the
episode with :class:`_TickWorld` (a subclass of the frozen
``world6.ConcurrentWorld`` that calls ``super().tick()`` and then the hook)
bound as ``scheduler.ConcurrentWorld`` for the duration of the replay; the
module attribute is restored afterwards. The equivalence test shows the
episodes are identical to the unhooked sync path.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

import harness  # noqa: F401
import model_agent6 as M
import providers6 as providers
import run6
import scheduler6 as scheduler
import world6 as world6
from fake_api import _httpx, canonical, sdk_client

PLACEHOLDER_TEXT = ""

# Anthropic error type -> HTTP status, so a request that failed in every batch
# try raises in the harness provider the same SDK exception a sync call would.
ERROR_STATUS = {
    "invalid_request_error": 400, "authentication_error": 401, "billing_error": 402, "permission_error": 403,
    "not_found_error": 404, "request_too_large": 413, "rate_limit_error": 429, "api_error": 500,
    "timeout_error": 504, "overloaded_error": 529,
}


class _RoundBoundary(BaseException):
    """Raised from the tick hook to abandon a replay at the start of the next round."""


_ACTIVE_HOOK: Optional["_Ctx"] = None


class _TickWorld(world6.ConcurrentWorld):
    """The harness world, plus a notification after each tick (behaviour unchanged)."""

    def tick(self) -> int:
        clock = super().tick()
        if _ACTIVE_HOOK is not None:
            _ACTIVE_HOOK.on_tick(clock)
        return clock


@contextlib.contextmanager
def _hooked(ctx: "_Ctx") -> Iterator[None]:
    global _ACTIVE_HOOK
    orig = scheduler.ConcurrentWorld
    scheduler.ConcurrentWorld = _TickWorld
    _ACTIVE_HOOK = ctx
    try:
        yield
    finally:
        scheduler.ConcurrentWorld = orig
        _ACTIVE_HOOK = None


def request_key(params: Dict[str, Any]) -> str:
    """Identity of one request body within an episode (sha256 of canonical JSON)."""
    return hashlib.sha256(canonical(params).encode()).hexdigest()


@dataclass
class Need:
    key: str
    params: Dict[str, Any]      # the exact POST /v1/messages body (key order preserved)
    raw: bytes                  # the body bytes as the SDK serialized them
    agent_id: str
    completion: int
    round: int


@dataclass
class Hit:
    key: str
    agent_id: str
    completion: int


@dataclass
class ReplayResult:
    kind: str                                   # "done" | "need" | "failed"
    transcript: Optional[Dict[str, Any]] = None
    needs: List[Need] = field(default_factory=list)
    hits: List[Hit] = field(default_factory=list)
    error: str = ""
    spend_entries: List[Dict[str, Any]] = field(default_factory=list)  # what the harness code would have logged


class _CaptureSpend(M.SpendTracker):
    """In-memory harness SpendTracker (no file, no cap) that keeps the entries of real (non-placeholder) completions."""

    def __init__(self, ctx: "_Ctx") -> None:
        super().__init__(None, None)
        self.ctx = ctx
        self.entries: List[Dict[str, Any]] = []

    def record(self, entry: Dict[str, Any]) -> None:
        if not self.ctx.last_was_placeholder:
            self.entries.append(json.loads(json.dumps(entry, sort_keys=True)))
        super().record(entry)


class _Ctx:
    def __init__(self, responses: Dict[str, Dict[str, Any]], failed: Dict[str, Tuple[int, Dict[str, Any]]],
                 agents_by_system: Dict[str, str], reject_temperature: Optional[Dict[str, Any]] = None) -> None:
        self.reject_temperature = reject_temperature
        self.responses = responses
        self.failed = failed
        self.agents_by_system = agents_by_system
        self.needs: List[Need] = []
        self.hits: List[Hit] = []
        self.clock = 0
        self.last_was_placeholder = False

    def on_tick(self, clock: int) -> None:
        if self.needs:
            raise _RoundBoundary()
        self.clock = clock

    def handle(self, request: Any) -> Any:
        httpx = _httpx()
        if request.method != "POST" or request.url.path != "/v1/messages":
            return httpx.Response(404, json={"type": "error", "error": {"type": "not_found_error", "message": "replay"}})
        raw = request.read()
        params = json.loads(raw)
        key = request_key(params)
        system = M._system_text(params.get("system", ""))
        agent = self.agents_by_system.get(system, "?")
        completion = sum(1 for m in params["messages"] if m["role"] == "assistant")
        self.last_was_placeholder = False
        if self.reject_temperature is not None and "temperature" in params:
            # The API rejected temperature for this model (a batch result said so). Serve that 400 locally, so
            # the harness provider drops temperature exactly as on the sync path (and remembers it for the
            # rest of this provider instance, i.e. this episode).
            return httpx.Response(400, json=self.reject_temperature)
        if key in self.failed:
            status, body = self.failed[key]
            return httpx.Response(status, json=body)
        if key in self.responses:
            self.hits.append(Hit(key, agent, completion))
            return httpx.Response(200, json=self.responses[key])
        self.needs.append(Need(key, params, raw, agent, completion, self.clock))
        self.last_was_placeholder = True
        return httpx.Response(200, json={
            "id": "msg_placeholder", "type": "message", "role": "assistant", "model": params.get("model"),
            "content": [{"type": "text", "text": PLACEHOLDER_TEXT}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        })


def agents_by_system(cell: Dict[str, Any]) -> Dict[str, str]:
    """System prompt text -> agent id, computed with the harness prompt builder."""
    task = run6.cell_task(cell)
    wc = world6.world_config(cell["config"], concurrency_aware_prompt=cell["aware"])
    ids = task.agent_ids
    out = {}
    for a in ids:
        peers = tuple(x for x in ids if x != a)
        out[world6.build_system_prompt(a, peers, task.intents[a].describe(), wc)] = a
    return out


class ReplayEngine:
    """Replays episodes through the harness code; one SDK client reused across replays."""

    def __init__(self, run_kw: Dict[str, Any]) -> None:
        self.run_kw = dict(run_kw)  # schedule_kw, turn_cap, max_tokens, temperature, prices, dry_run, prompt_caching
        self._ctx: Optional[_Ctx] = None
        self.client = sdk_client(self._handle, max_retries=0)

    def _handle(self, request: Any) -> Any:
        assert self._ctx is not None
        return self._ctx.handle(request)

    def replay(self, cell: Dict[str, Any], responses: Dict[str, Dict[str, Any]],
               failed: Optional[Dict[str, Tuple[int, Dict[str, Any]]]] = None,
               reject_temperature: Optional[Dict[str, Any]] = None) -> ReplayResult:
        ctx = _Ctx(responses, failed or {}, agents_by_system(cell), reject_temperature)
        self._ctx = ctx
        probe = M.UsageProbeClient(self.client)
        provider = providers.AnthropicProvider(client=probe)
        spend = _CaptureSpend(ctx)
        kw = dict(self.run_kw)
        try:
            with _hooked(ctx):
                tr = run6.run_one(cell, provider, probe, kw["schedule_kw"], turn_cap=kw["turn_cap"],
                                  max_tokens=kw["max_tokens"], temperature=kw["temperature"], prices=kw["prices"],
                                  spend=spend, dry_run=kw["dry_run"], prompt_caching=kw["prompt_caching"])
        except _RoundBoundary:
            return ReplayResult("need", needs=ctx.needs, hits=ctx.hits)
        except M.ProviderFailure as exc:
            return ReplayResult("failed", error=str(exc), hits=ctx.hits)
        except Exception:  # noqa: BLE001
            if ctx.needs:  # a placeholder-ended episode is discarded anyway
                return ReplayResult("need", needs=ctx.needs, hits=ctx.hits)
            raise
        finally:
            self._ctx = None
        if ctx.needs:
            return ReplayResult("need", needs=ctx.needs, hits=ctx.hits)
        return ReplayResult("done", transcript=tr, hits=ctx.hits, spend_entries=spend.entries)


def error_response(result: Dict[str, Any], batch_id: str, tries: int) -> Tuple[int, Dict[str, Any]]:
    """HTTP status + body to serve for a request that failed in every try (last result decides)."""
    rtype = result.get("type")
    if rtype == "errored":
        err = result.get("error") or {}
        inner = err.get("error") if isinstance(err.get("error"), dict) else err
        etype = (inner or {}).get("type", "api_error")
        body = err if err.get("type") == "error" else {"type": "error", "error": inner}
        return ERROR_STATUS.get(etype, 500), body
    return 500, {"type": "error", "error": {"type": f"batch_{rtype}",
                                            "message": f"request {rtype} in message batch {batch_id} (try {tries})"}}
