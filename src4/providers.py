"""Provider layer: one tool-use loop, several model APIs.

The harness speaks a neutral message format (Anthropic-style content
blocks) and each provider translates. Model ids select the provider:

    claude-sonnet-5                   -> Anthropic Messages API
    openrouter:openai/gpt-5.5         -> OpenRouter (OpenAI-compatible)
    openrouter:qwen/qwen3.6-27b       -> OpenRouter

Every completion returns a `Completion` carrying the content blocks plus the
reproducibility fields reviewers asked for: served model id, requested vs.
effective temperature, token usage, UTC timestamp.

Stdlib only for OpenRouter (urllib); `anthropic` SDK only when used.
"""
from __future__ import annotations

import json
import os
import time
import http.client
import urllib.error
import urllib.request
from dataclasses import dataclass, field


# Log OpenRouter's per-response usage.cost (USD) in provider_meta["cost"].
# Off by default so runs already in flight write unchanged transcripts;
# src/tier1.py turns it on for its spend guard.
RECORD_COST = False


@dataclass
class Completion:
    blocks: list                      # [{"type":"text",...}|{"type":"tool_use",...}]
    provider: str
    model_requested: str
    model_served: str
    temperature_requested: float | None
    # float = confirmed applied; None = not sent / rejected; "unverified" =
    # sent, but the provider gives no confirmation it was applied (OpenRouter
    # silently drops unsupported parameters and does not echo them).
    temperature_effective: float | str | None
    usage: dict = field(default_factory=dict)   # {"input": int, "output": int}
    timestamp_utc: str = ""
    raw_assistant_message: object = None  # provider-native, for message history
    # Why generation stopped: Anthropic stop_reason ("end_turn", "tool_use",
    # "max_tokens", ...) / OpenRouter finish_reason ("stop", "tool_calls",
    # "length", ...). None if the provider did not say.
    stop_reason: str | None = None
    provider_meta: dict = field(default_factory=dict)  # per-turn extras for transcripts
    # OpenRouter reasoning_details of this assistant message; must be sent
    # back unchanged on the next request (tool calling with reasoning models).
    reasoning_details: list | None = None

    @property
    def tool_uses(self):
        return [b for b in self.blocks if b["type"] == "tool_use"]


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _blocks_from_anthropic(content) -> list:
    out = []
    for b in content:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name,
                        "input": dict(b.input)})
        else:
            out.append({"type": b.type})
    return out


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client=None):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client
        self._temperature_unsupported: set = set()

    def complete(self, model, system, tools, messages, max_tokens,
                 temperature) -> Completion:
        import anthropic
        kwargs = dict(model=model, max_tokens=max_tokens, system=system,
                      tools=tools, messages=messages)
        eff = None
        if temperature is not None and model not in self._temperature_unsupported:
            kwargs["temperature"] = temperature
            eff = temperature
        try:
            try:
                resp = self.client.messages.create(**kwargs)
            except TypeError as e:
                # Newer anthropic SDKs drop `temperature` from the signature.
                # Send it in the raw body so the API request is identical to
                # runs made with older SDKs (the API decides, as before).
                if "temperature" in kwargs and "temperature" in str(e):
                    kwargs["extra_body"] = {"temperature": kwargs.pop("temperature")}
                    resp = self.client.messages.create(**kwargs)
                else:
                    raise
        except anthropic.BadRequestError as e:
            if ("temperature" in kwargs or "extra_body" in kwargs) \
                    and "temperature" in str(e):
                self._temperature_unsupported.add(model)
                kwargs.pop("temperature", None)
                kwargs.pop("extra_body", None)
                eff = None
                resp = self.client.messages.create(**kwargs)
            else:
                raise
        usage = {"input": getattr(resp.usage, "input_tokens", None),
                 "output": getattr(resp.usage, "output_tokens", None)}
        return Completion(blocks=_blocks_from_anthropic(resp.content),
                          provider=self.name, model_requested=model,
                          model_served=getattr(resp, "model", model),
                          temperature_requested=temperature,
                          temperature_effective=eff, usage=usage,
                          timestamp_utc=_now(), raw_assistant_message=resp.content,
                          stop_reason=getattr(resp, "stop_reason", None))

    @staticmethod
    def history_assistant(completion: Completion):
        return {"role": "assistant", "content": completion.raw_assistant_message}

    @staticmethod
    def history_tool_results(results: list):
        return {"role": "user", "content": results}


# ---------------------------------------------------------------------------
# OpenAI-compatible chat completions (OpenRouter)
# ---------------------------------------------------------------------------

def tools_to_openai(tools: list) -> list:
    return [{"type": "function",
             "function": {"name": t["name"],
                          "description": t.get("description", ""),
                          "parameters": t["input_schema"]}} for t in tools]


def messages_to_openai(system: str, messages: list) -> list:
    """Neutral (Anthropic-style) history -> OpenAI chat messages."""
    out = [{"role": "system", "content": system}]
    for m in messages:
        role, content = m["role"], m["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if role == "assistant":
            text = "".join(b.get("text", "") for b in content if b["type"] == "text")
            calls = [{"id": b["id"], "type": "function",
                      "function": {"name": b["name"],
                                   "arguments": json.dumps(b["input"])}}
                     for b in content if b["type"] == "tool_use"]
            msg = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            if m.get("reasoning_details"):
                # passed back unmodified, in order (OpenRouter reasoning docs)
                msg["reasoning_details"] = m["reasoning_details"]
            out.append(msg)
        else:  # user turn carrying tool results
            for r in content:
                if r.get("type") == "tool_result":
                    out.append({"role": "tool", "tool_call_id": r["tool_use_id"],
                                "content": str(r["content"])})
                elif r.get("type") == "text":
                    out.append({"role": "user", "content": r["text"]})
    return out


def blocks_from_openai_message(msg: dict) -> list:
    blocks = []
    if msg.get("content"):
        blocks.append({"type": "text", "text": msg["content"]})
    for tc in msg.get("tool_calls") or []:
        fn = tc["function"]
        raw = fn.get("arguments")
        if isinstance(raw, dict):      # some providers return parsed objects
            args = dict(raw)
        else:
            try:
                args = json.loads(raw or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {"_unparsed_arguments": raw}
        if not isinstance(args, dict):
            args = {"_unparsed_arguments": args}
        blocks.append({"type": "tool_use", "id": tc["id"], "name": fn["name"],
                       "input": args})
    return blocks


class OpenRouterProvider:
    name = "openrouter"
    BASE = "https://openrouter.ai/api/v1/chat/completions"
    PREFIX = "openrouter:"

    def __init__(self, api_key=None, max_retries=4):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        self.max_retries = max_retries
        self._temperature_unsupported: set = set()

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.BASE, data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": os.environ.get("IBENCH_HTTP_REFERER", "https://example.org/idempotencybench"),
                     "X-Title": "IdempotencyBench"})
        delay = 2.0
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")
                if e.code in (429, 500, 502, 503) and attempt < self.max_retries:
                    time.sleep(delay); delay *= 2
                    continue
                raise RuntimeError(f"OpenRouter HTTP {e.code}: {text[:500]}")
            except (urllib.error.URLError, TimeoutError,
                    http.client.HTTPException, ConnectionError) as e:
                if attempt < self.max_retries:
                    time.sleep(delay); delay *= 2
                    continue
                raise
        raise RuntimeError("unreachable")

    def complete(self, model, system, tools, messages, max_tokens,
                 temperature) -> Completion:
        slug = model[len(self.PREFIX):] if model.startswith(self.PREFIX) else model
        payload = {"model": slug, "max_tokens": max_tokens,
                   "messages": messages_to_openai(system, messages),
                   "tools": tools_to_openai(tools), "tool_choice": "auto"}
        eff = None
        if temperature is not None and slug not in self._temperature_unsupported:
            payload["temperature"] = temperature
            # OpenRouter ignores unsupported params silently and does not echo
            # sampling params, so sending T is not evidence it was applied.
            eff = "unverified"
        try:
            data = self._post(payload)
        except RuntimeError as e:
            if "temperature" in payload and "temperature" in str(e).lower():
                self._temperature_unsupported.add(slug)
                payload.pop("temperature"); eff = None
                data = self._post(payload)
            else:
                raise
        if "choices" not in data:
            raise RuntimeError(f"OpenRouter response without choices: "
                               f"{json.dumps(data)[:500]}")
        choice = data["choices"][0]
        msg = choice["message"]
        usage = data.get("usage") or {}
        meta = {"temperature_sent": payload.get("temperature")}
        if choice.get("native_finish_reason") is not None:
            meta["native_finish_reason"] = choice["native_finish_reason"]
        if data.get("provider"):
            meta["upstream_provider"] = data["provider"]
        if data.get("system_fingerprint"):
            meta["system_fingerprint"] = data["system_fingerprint"]
        if RECORD_COST and usage.get("cost") is not None:
            meta["cost"] = usage["cost"]   # USD charged (OpenRouter usage accounting)
        rtok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if rtok is not None:
            meta["reasoning_tokens"] = rtok
        rd = msg.get("reasoning_details") or None
        if rd:
            meta["reasoning_details_n"] = len(rd)
        return Completion(
            blocks=blocks_from_openai_message(msg), provider=self.name,
            model_requested=model,
            model_served=f'{data.get("model", slug)}'
                         + (f' @{data["provider"]}' if data.get("provider") else ""),
            temperature_requested=temperature, temperature_effective=eff,
            usage={"input": usage.get("prompt_tokens"),
                   "output": usage.get("completion_tokens")},
            timestamp_utc=_now(), raw_assistant_message=None,
            stop_reason=choice.get("finish_reason"), provider_meta=meta,
            reasoning_details=rd)

    @staticmethod
    def history_assistant(completion: Completion):
        # Neutral blocks are the history; messages_to_openai converts on send.
        # reasoning_details ride along so reasoning models keep their state.
        msg = {"role": "assistant", "content": completion.blocks}
        if completion.reasoning_details:
            msg["reasoning_details"] = completion.reasoning_details
        return msg

    @staticmethod
    def history_tool_results(results: list):
        return {"role": "user", "content": results}


_PROVIDERS: dict = {}


def provider_for(model: str, anthropic_client=None):
    """Return (cached) provider instance for a model id."""
    if model.startswith(OpenRouterProvider.PREFIX):
        key = "openrouter"
        if key not in _PROVIDERS:
            _PROVIDERS[key] = OpenRouterProvider()
    else:
        key = "anthropic"
        if key not in _PROVIDERS:
            _PROVIDERS[key] = AnthropicProvider(anthropic_client)
    return _PROVIDERS[key]
