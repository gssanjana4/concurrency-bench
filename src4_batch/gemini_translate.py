"""OpenAI-format request (what the frozen OpenRouterProvider sends) <-> Gemini API (generateContent) objects.

On the frozen path, ``providers.OpenRouterProvider`` POSTs an OpenAI chat-completions payload to OpenRouter,
and OpenRouter translates it into a Gemini request. On the batch path the same frozen provider builds the same
payload; :func:`to_gemini_request` replaces OpenRouter's translation, and :func:`to_openrouter_response`
renders the Gemini reply as the OpenRouter chat-completions JSON the frozen provider parses. Pure functions,
no I/O. Anything not listed below is refused (TranslationError) rather than guessed.

Request (payload keys model, max_tokens, messages, tools, tool_choice, temperature; nothing else accepted):

    messages[0] system (str)            -> systemInstruction.parts[0].text (exact text)
    user (str)                          -> contents[] {role: user, parts: [{text}]}
    assistant {content, tool_calls,     -> contents[] {role: model, parts: [{text}?, {functionCall{id?, name, args}}...]}
               reasoning_details}          args = json.loads(arguments); id sent back when Gemini issued it;
                                           thoughtSignature put back on the part it came from (via reasoning_details)
    tool {tool_call_id, content}        -> {functionResponse{id?, name, response: {"output": <content string, exact>}}}
                                           consecutive tool messages -> one user content, in call order
    tools[] {function{name,             -> tools[0].functionDeclarations[] {name, description,
             description, parameters}}     parametersJsonSchema: <parameters, unchanged JSON Schema>}
    tool_choice auto                    -> toolConfig.functionCallingConfig.mode AUTO
    max_tokens                          -> generationConfig.maxOutputTokens
    temperature (if sent)               -> generationConfig.temperature
    (no thinkingConfig, safetySettings, cachedContent: provider defaults, as on the frozen path)

Response (first candidate; thought-summary parts are never requested and are skipped if present):

    text parts (joined)                 -> message.content (None if empty)
    functionCall parts                  -> message.tool_calls[] {id: Gemini id or "gsyn_<turn>_<i>",
                                           function{name, arguments: json.dumps(args)}}
    thoughtSignature on a part          -> message.reasoning_details[] {type: reasoning.encrypted, data, id, format:
                                           google-gemini-v1, index} (passed back unchanged by the frozen provider)
    finishReason                        -> finish_reason (tool_calls|stop|length|content_filter|error, OpenRouter's
                                           normalized set) and native_finish_reason (verbatim)
    promptFeedback.blockReason          -> empty message, finish_reason content_filter, native = blockReason
    usageMetadata                       -> usage {prompt_tokens: promptTokenCount, completion_tokens:
                                           candidatesTokenCount + thoughtsTokenCount (both billed as output),
                                           completion_tokens_details.reasoning_tokens: thoughtsTokenCount,
                                           prompt_tokens_details.cached_tokens: cachedContentTokenCount}
    modelVersion                        -> model (so model_served = "<modelVersion> @Google Gemini Batch API")
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

PROVIDER_LABEL = "Google Gemini Batch API"
SIG_FORMAT = "google-gemini-v1"
SYN_PREFIX = "gsyn_"  # tool-call ids made up here when Gemini sent none; never sent back to Gemini

PAYLOAD_KEYS = {"model", "max_tokens", "messages", "tools", "tool_choice", "temperature"}
TOOL_CHOICE = {"auto": "AUTO", "none": "NONE", "required": "ANY"}
CONTENT_FILTER = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "IMAGE_SAFETY",
                  "IMAGE_PROHIBITED_CONTENT", "IMAGE_RECITATION"}
# google.rpc.Code -> HTTP status (Google's standard mapping)
GRPC_HTTP = {0: 200, 1: 499, 2: 500, 3: 400, 4: 504, 5: 404, 6: 409, 7: 403, 8: 429, 9: 400, 10: 409, 11: 400,
             12: 501, 13: 500, 14: 503, 15: 500, 16: 401}
GRPC_NAME_HTTP = {"CANCELLED": 499, "UNKNOWN": 500, "INVALID_ARGUMENT": 400, "DEADLINE_EXCEEDED": 504,
                  "NOT_FOUND": 404, "ALREADY_EXISTS": 409, "PERMISSION_DENIED": 403, "RESOURCE_EXHAUSTED": 429,
                  "FAILED_PRECONDITION": 400, "ABORTED": 409, "OUT_OF_RANGE": 400, "UNIMPLEMENTED": 501,
                  "INTERNAL": 500, "UNAVAILABLE": 503, "DATA_LOSS": 500, "UNAUTHENTICATED": 401}


class TranslationError(ValueError):
    """The payload or response has something this translation does not handle (refused, never guessed)."""


def compact(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()


# --------------------------------------------------------------------------
# Request: OpenAI chat payload -> GenerateContentRequest
# --------------------------------------------------------------------------


def signatures(reasoning_details: Optional[List[Dict[str, Any]]]) -> Tuple[Optional[str], Dict[str, str]]:
    """(signature of the text part, {tool call id: signature}) from reasoning_details written by this module."""
    text_sig: Optional[str] = None
    calls: Dict[str, str] = {}
    for d in reasoning_details or []:
        if d.get("type") != "reasoning.encrypted" or d.get("format") != SIG_FORMAT:
            raise TranslationError(f"unexpected reasoning_details entry: {json.dumps(d)[:200]}")
        if d.get("id") is None:
            text_sig = text_sig or d["data"]
        else:
            calls[d["id"]] = d["data"]
    return text_sig, calls


def to_gemini_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    extra = set(payload) - PAYLOAD_KEYS
    if extra:
        raise TranslationError(f"payload keys not translated: {sorted(extra)}")
    msgs = payload["messages"]
    if not msgs or msgs[0].get("role") != "system" or not isinstance(msgs[0].get("content"), str):
        raise TranslationError("first message must be the system prompt (str)")
    contents: List[Dict[str, Any]] = []
    name_by_id: Dict[str, str] = {}

    def add(role: str, parts: List[Dict[str, Any]]) -> None:
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})

    for m in msgs[1:]:
        role = m.get("role")
        if role == "user":
            if set(m) != {"role", "content"} or not isinstance(m["content"], str):
                raise TranslationError(f"user message not translated: {json.dumps(m)[:200]}")
            add("user", [{"text": m["content"]}])
        elif role == "assistant":
            if set(m) - {"role", "content", "tool_calls", "reasoning_details"}:
                raise TranslationError(f"assistant message keys not translated: {sorted(m)}")
            text_sig, call_sigs = signatures(m.get("reasoning_details"))
            parts: List[Dict[str, Any]] = []
            if m.get("content"):
                if not isinstance(m["content"], str):
                    raise TranslationError("assistant content must be a string or null")
                part: Dict[str, Any] = {"text": m["content"]}
                if text_sig:
                    part["thoughtSignature"] = text_sig
                parts.append(part)
            for tc in m.get("tool_calls") or []:
                if tc.get("type") != "function":
                    raise TranslationError(f"tool call type {tc.get('type')!r}")
                args = json.loads(tc["function"]["arguments"])
                if not isinstance(args, dict):
                    raise TranslationError("tool call arguments must be a JSON object")
                fc: Dict[str, Any] = {"name": tc["function"]["name"], "args": args}
                if not tc["id"].startswith(SYN_PREFIX):
                    fc["id"] = tc["id"]
                part = {"functionCall": fc}
                if tc["id"] in call_sigs:
                    part["thoughtSignature"] = call_sigs[tc["id"]]
                parts.append(part)
                name_by_id[tc["id"]] = fc["name"]
            if not parts:
                raise TranslationError("assistant message with neither text nor tool calls")
            add("model", parts)
        elif role == "tool":
            if set(m) != {"role", "tool_call_id", "content"} or not isinstance(m["content"], str):
                raise TranslationError(f"tool message not translated: {json.dumps(m)[:200]}")
            tid = m["tool_call_id"]
            if tid not in name_by_id:
                raise TranslationError(f"tool result for unknown call id {tid!r}")
            fr: Dict[str, Any] = {"name": name_by_id[tid], "response": {"output": m["content"]}}
            if not tid.startswith(SYN_PREFIX):
                fr["id"] = tid
            add("user", [{"functionResponse": fr}])
        else:
            raise TranslationError(f"message role {role!r} not translated")

    req: Dict[str, Any] = {"systemInstruction": {"parts": [{"text": msgs[0]["content"]}]}, "contents": contents}
    tools = payload.get("tools") or []
    if tools:
        decls = []
        for t in tools:
            if t.get("type") != "function" or set(t["function"]) - {"name", "description", "parameters"}:
                raise TranslationError(f"tool not translated: {json.dumps(t)[:200]}")
            f = t["function"]
            decls.append({"name": f["name"], "description": f.get("description", ""),
                          "parametersJsonSchema": f["parameters"]})
        req["tools"] = [{"functionDeclarations": decls}]
    if "tool_choice" in payload:
        if payload["tool_choice"] not in TOOL_CHOICE:
            raise TranslationError(f"tool_choice {payload['tool_choice']!r}")
        req["toolConfig"] = {"functionCallingConfig": {"mode": TOOL_CHOICE[payload["tool_choice"]]}}
    gen: Dict[str, Any] = {"maxOutputTokens": int(payload["max_tokens"])}
    if "temperature" in payload:
        gen["temperature"] = payload["temperature"]
    req["generationConfig"] = gen
    return req


def model_turns(req: Dict[str, Any]) -> int:
    return sum(1 for c in req.get("contents", []) if c.get("role") == "model")


# --------------------------------------------------------------------------
# Response: GenerateContentResponse -> OpenRouter chat completion JSON
# --------------------------------------------------------------------------


def is_answer(resp: Dict[str, Any]) -> bool:
    """A usable reply: a candidate, or a prompt block (rendered as content_filter). Otherwise it is an error."""
    return bool(resp.get("candidates")) or bool((resp.get("promptFeedback") or {}).get("blockReason"))


def openrouter_usage(resp: Dict[str, Any]) -> Dict[str, Any]:
    u = resp.get("usageMetadata") or {}
    cand = int(u.get("candidatesTokenCount") or 0)
    thoughts = int(u.get("thoughtsTokenCount") or 0)
    prompt = u.get("promptTokenCount")
    out = {"prompt_tokens": prompt, "completion_tokens": cand + thoughts,
           "total_tokens": (prompt or 0) + cand + thoughts,
           "completion_tokens_details": {"reasoning_tokens": thoughts},
           "prompt_tokens_details": {"cached_tokens": int(u.get("cachedContentTokenCount") or 0)}}
    return out


def frozen_usage(resp: Dict[str, Any]) -> Dict[str, Any]:
    """The usage dict model_agent4.normalized_usage builds for the rendered reply (OpenRouter path, no probe)."""
    u = openrouter_usage(resp)
    return {"input": u["prompt_tokens"], "output": u["completion_tokens"], "cache_read": 0, "cache_write": 0,
            "reasoning": u["completion_tokens_details"]["reasoning_tokens"]}


def finish_reason(native: Optional[str], has_calls: bool) -> str:
    if native in (None, "STOP"):
        return "tool_calls" if has_calls else "stop"
    if native == "MAX_TOKENS":
        return "length"
    if native in CONTENT_FILTER:
        return "content_filter"
    return "error"  # MALFORMED_FUNCTION_CALL, UNEXPECTED_TOOL_CALL, TOO_MANY_TOOL_CALLS, LANGUAGE, OTHER, ...


def to_openrouter_response(resp: Dict[str, Any], req: Dict[str, Any], default_model: str) -> Dict[str, Any]:
    turn = model_turns(req)
    cands = resp.get("candidates") or []
    message: Dict[str, Any] = {"role": "assistant", "content": None}
    if cands:
        c = cands[0]
        texts: List[str] = []
        calls: List[Dict[str, Any]] = []
        rd: List[Dict[str, Any]] = []
        for p in (c.get("content") or {}).get("parts") or []:
            if p.get("thought"):
                continue
            sig = p.get("thoughtSignature")
            if "functionCall" in p:
                fc = p["functionCall"]
                cid = fc.get("id") or f"{SYN_PREFIX}{turn}_{len(calls)}"
                calls.append({"id": cid, "type": "function",
                              "function": {"name": fc["name"], "arguments": json.dumps(fc.get("args") or {})}})
                if sig:
                    rd.append({"type": "reasoning.encrypted", "data": sig, "id": cid, "format": SIG_FORMAT,
                               "index": len(rd)})
            elif "text" in p:
                texts.append(p["text"])
                if sig:
                    rd.append({"type": "reasoning.encrypted", "data": sig, "id": None, "format": SIG_FORMAT,
                               "index": len(rd)})
        message["content"] = "".join(texts) or None
        if calls:
            message["tool_calls"] = calls
        if rd:
            message["reasoning_details"] = rd
        native = c.get("finishReason")
        finish = finish_reason(native, bool(calls))
    else:
        native = (resp.get("promptFeedback") or {}).get("blockReason")
        if not native:
            raise TranslationError("response has no candidate and no block reason")
        finish = "content_filter"
    choice: Dict[str, Any] = {"index": 0, "message": message, "finish_reason": finish}
    if native is not None:
        choice["native_finish_reason"] = native
    return {"id": resp.get("responseId"), "object": "chat.completion",
            "model": resp.get("modelVersion") or default_model, "provider": PROVIDER_LABEL,
            "choices": [choice], "usage": openrouter_usage(resp)}


# --------------------------------------------------------------------------
# Errors: google.rpc.Status -> the HTTP error OpenRouter would relay
# --------------------------------------------------------------------------


def error_http(status: Dict[str, Any]) -> Tuple[int, bytes]:
    """HTTP status and body (OpenRouter's provider-error envelope) for a Gemini per-request error."""
    code = status.get("code")
    http = GRPC_HTTP.get(code) if isinstance(code, int) else None
    if http is None:
        http = GRPC_NAME_HTTP.get(str(status.get("status")), 500)
    body = {"error": {"code": http, "message": "Provider returned error",
                      "metadata": {"provider_name": PROVIDER_LABEL, "raw": json.dumps(status, sort_keys=True)}}}
    return http, json.dumps(body).encode()
