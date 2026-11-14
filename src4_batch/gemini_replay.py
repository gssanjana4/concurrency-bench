"""Deterministic replay of one frozen episode for the Gemini model, with recorded Gemini batch responses.

Seam: the HTTP call of the frozen ``providers.OpenRouterProvider`` (stdlib ``urllib.request.urlopen``). The
episode runs through the frozen chain unmodified -- ``run4.run_one`` -> ``scheduler.run_episode`` ->
``model_agent4.ModelAgent`` -> ``providers.OpenRouterProvider.complete`` -- exactly as ``run4.make_provider``
builds it for ``openrouter:google/gemini-4-argon-20261013``. The frozen provider builds the OpenAI-format
payload it would POST to OpenRouter (system prompt, tool specs, history, max_tokens 4096, temperature 0,
tool_choice auto; no reasoning parameter). During a replay ``urllib.request.urlopen`` is bound to a local
function that

* translates that payload into a Gemini GenerateContentRequest (:func:`gemini_translate.to_gemini_request`;
  this request, byte for byte, is what the batch submits),
* answers with the recorded Gemini response rendered as the OpenRouter JSON the frozen provider parses
  (:func:`gemini_translate.to_openrouter_response`), or with the recorded error as the HTTP error OpenRouter
  would relay, or -- when no response is recorded yet -- with a placeholder (an empty "stop" reply, which ends
  that agent), exactly as :mod:`replay` does for Anthropic.

Lockstep logic, the tick hook and the spend capture are those of :mod:`replay` (see its docstring for why
replay is exact). ``providers.time`` is bound to a shim whose ``sleep`` does nothing for the duration of a
replay, so the frozen provider's own retry loop on a served 429/5xx runs instantly; both are restored after.

The provider instance's ``name`` is set to ``"gemini_batch"`` (transcript ``provider`` and each Completion's
``provider``); it is not read by any frozen code path except a preflight warning. Prices: the replay's
price table is told the price period of each response it serves (Gemini batch prices change on a date).
"""

from __future__ import annotations

import contextlib
import io
import json
import time as _time
import types
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import frozen  # noqa: F401
import model_agent4 as M
import providers
import run4
import gemini_translate as G
from replay import Hit, Need, ReplayResult, _CaptureSpend, _hooked, _RoundBoundary, agents_by_system, request_key

PROVIDER_NAME = "gemini_batch"
PLACEHOLDER = {"id": "placeholder", "model": "placeholder",
               "choices": [{"index": 0, "message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 0, "completion_tokens": 0}}

_NO_SLEEP = types.SimpleNamespace(**{k: getattr(_time, k) for k in dir(_time) if not k.startswith("_")})
_NO_SLEEP.sleep = lambda s: None


@contextlib.contextmanager
def patched_urlopen(handler: Callable[[Any], Any]) -> Iterator[None]:
    orig_open, orig_time = urllib.request.urlopen, providers.time
    urllib.request.urlopen = lambda req, timeout=None: handler(req)
    providers.time = _NO_SLEEP
    try:
        yield
    finally:
        urllib.request.urlopen = orig_open
        providers.time = orig_time


def http_error(req: Any, status: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(req.full_url, status, "replay", {}, io.BytesIO(body))  # type: ignore[arg-type]


def make_provider() -> providers.OpenRouterProvider:
    p = providers.OpenRouterProvider(api_key="offline-replay")  # frozen class, frozen defaults (max_retries 4)
    p.name = PROVIDER_NAME
    return p


def payload_of(req: Any) -> Dict[str, Any]:
    if req.get_method() != "POST" or req.full_url != providers.OpenRouterProvider.BASE:
        raise RuntimeError(f"unexpected request in replay: {req.get_method()} {req.full_url}")
    return json.loads(req.data)


class _GCtx:
    def __init__(self, responses: Dict[str, Dict[str, Any]], failed: Dict[str, Tuple[int, bytes]],
                 agents: Dict[str, str], prices: Any, default_model: str,
                 reject_temperature: Optional[Tuple[int, bytes]] = None) -> None:
        self.responses = responses        # key -> {"response": GenerateContentResponse, "at": price time}
        self.failed = failed              # key -> (http status, body)
        self.agents = agents
        self.prices = prices
        self.default_model = default_model
        self.reject_temperature = reject_temperature
        self.needs: List[Need] = []
        self.hits: List[Hit] = []
        self.clock = 0
        self.last_was_placeholder = False

    def on_tick(self, clock: int) -> None:
        if self.needs:
            raise _RoundBoundary()
        self.clock = clock

    def handle(self, req: Any) -> Any:
        payload = payload_of(req)
        greq = G.to_gemini_request(payload)
        key = request_key(greq)
        agent = self.agents.get(payload["messages"][0]["content"], "?")
        completion = sum(1 for m in payload["messages"] if m["role"] == "assistant")
        self.last_was_placeholder = False
        if self.reject_temperature is not None and "temperature" in payload:
            raise http_error(req, *self.reject_temperature)
        if key in self.failed:
            raise http_error(req, *self.failed[key])
        if key in self.responses:
            rec = self.responses[key]
            self.hits.append(Hit(key, agent, completion))
            if self.prices is not None and hasattr(self.prices, "at"):
                self.prices.at = rec.get("at")
            return io.BytesIO(json.dumps(G.to_openrouter_response(rec["response"], greq, self.default_model)).encode())
        self.needs.append(Need(key, greq, G.compact(greq), agent, completion, self.clock))
        self.last_was_placeholder = True
        return io.BytesIO(json.dumps(PLACEHOLDER).encode())


class GeminiReplayEngine:
    """Replays episodes through the frozen code with the frozen OpenRouterProvider over the Gemini seam."""

    def __init__(self, run_kw: Dict[str, Any], default_model: str) -> None:
        self.run_kw = dict(run_kw)
        self.default_model = default_model

    def replay(self, cell: Dict[str, Any], responses: Dict[str, Dict[str, Any]],
               failed: Optional[Dict[str, Tuple[int, bytes]]] = None,
               reject_temperature: Optional[Tuple[int, bytes]] = None) -> ReplayResult:
        kw = self.run_kw
        ctx = _GCtx(responses, failed or {}, agents_by_system(cell), kw["prices"], self.default_model,
                    reject_temperature)
        spend = _CaptureSpend(ctx)  # type: ignore[arg-type]
        provider = make_provider()
        try:
            with _hooked(ctx), patched_urlopen(ctx.handle):  # type: ignore[arg-type]
                tr = run4.run_one(cell, provider, None, kw["schedule_kw"], turn_cap=kw["turn_cap"],
                                  max_tokens=kw["max_tokens"], temperature=kw["temperature"], prices=kw["prices"],
                                  spend=spend, dry_run=kw["dry_run"], prompt_caching=kw["prompt_caching"])
        except _RoundBoundary:
            return ReplayResult("need", needs=ctx.needs, hits=ctx.hits)
        except M.ProviderFailure as exc:
            return ReplayResult("failed", error=str(exc), hits=ctx.hits)
        except Exception:  # noqa: BLE001
            if ctx.needs:
                return ReplayResult("need", needs=ctx.needs, hits=ctx.hits)
            raise
        finally:
            if kw["prices"] is not None and hasattr(kw["prices"], "at"):
                kw["prices"].at = None
        if ctx.needs:
            return ReplayResult("need", needs=ctx.needs, hits=ctx.hits)
        return ReplayResult("done", transcript=tr, hits=ctx.hits, spend_entries=spend.entries)


# --------------------------------------------------------------------------
# Sync comparator (tests): the same frozen provider and translation, one generateContent call per completion
# --------------------------------------------------------------------------


class SyncTransport:
    """``urlopen`` replacement for a *sequential* run: translate, call ``generate(request) -> (http, json)``,
    render. With the fake Gemini API this is the sync path the batch path must equal (only the scheduling of
    calls differs)."""

    def __init__(self, generate: Callable[[Dict[str, Any]], Tuple[int, Dict[str, Any]]], default_model: str,
                 prices: Any = None, at: Optional[str] = None) -> None:
        self.generate = generate
        self.default_model = default_model
        self.prices = prices
        self.at = at
        self.requests: List[Dict[str, Any]] = []

    def __call__(self, req: Any) -> Any:
        payload = payload_of(req)
        greq = G.to_gemini_request(payload)
        self.requests.append(greq)
        status, body = self.generate(greq)
        if status != 200:
            raise http_error(req, *G.error_http(body.get("error") or {}))
        if self.prices is not None:
            self.prices.at = self.at
        return io.BytesIO(json.dumps(G.to_openrouter_response(body, greq, self.default_model)).encode())
