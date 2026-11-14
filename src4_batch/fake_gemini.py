"""In-process fake of the Gemini API (generateContent + Batch Mode) for dry runs and tests (no network, no key).

Answers, through an httpx ``MockTransport``, the REST endpoints the Gemini batch backend uses:

    POST /v1beta/models/{m}:generateContent          sync completion (the sync-path comparator in tests)
    POST /v1beta/models/{m}:batchGenerateContent     create a batch (inline requests) -> Operation
    GET  /v1beta/batches/{id}                        Operation; ends after ``polls_to_end`` polls; inline results
    GET  /v1beta/batches                             list Operations
    GET  /v1beta/models/{m}                          model metadata

The "model" is the run4 --dry-run model (:func:`model_agent4.scripted_policy`, or ``policy``) applied to the
request converted back to the harness's neutral format, rendered as a GenerateContentResponse. Function-call ids
follow :class:`model_agent4.FakeProvider` (``fake_<n>``), so decisions equal a literal ``run4 --dry-run``.

Strict request checks (a violation is a 400 INVALID_ARGUMENT, as the real API would answer some of them, so
a translation slip cannot pass silently): allowed top-level fields only; every function declaration uses
``parametersJsonSchema``; ``generationConfig`` has only temperature / maxOutputTokens (no thinkingConfig);
roles alternate user/model starting with user; function responses answer the preceding calls in order with
matching ids and names; and **thought signatures**: each reply's first functionCall part carries
``sig_<sha256 of the request that produced it>``; every model turn sent back must carry exactly that signature
on its first functionCall part. Because the signature is recomputed from the request prefix, this also checks
that the whole earlier history is re-sent byte-identically (same system prompt, tools, config and turns).

``fault(key, request, seen) -> None | {"error": Status} | {"response": GenerateContentResponse}`` overrides one
batch request (``seen`` = earlier submissions of the same request); ``job_state(n)`` (n = batch number) can
end a whole job as FAILED / CANCELLED / EXPIRED. ``sync_fault(request) -> None | (http, error body)``.
``now()`` gives timestamps (RFC 3339 with nanoseconds, as the API).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import frozen  # noqa: F401
import model_agent4 as M
from fake_api import _httpx, canonical

TOP_KEYS = {"systemInstruction", "contents", "tools", "toolConfig", "generationConfig"}
GEN_KEYS = {"temperature", "maxOutputTokens"}
TERMINAL = {"BATCH_STATE_SUCCEEDED", "BATCH_STATE_FAILED", "BATCH_STATE_CANCELLED", "BATCH_STATE_EXPIRED"}


def signature_for(req: Dict[str, Any], n_contents: int) -> str:
    """The signature the fake puts on the reply to ``req`` truncated to its first ``n_contents`` contents."""
    prefix = dict(req, contents=req["contents"][:n_contents])
    return "sig_" + hashlib.sha256(canonical(prefix).encode()).hexdigest()[:24]


def invalid(msg: str) -> Dict[str, Any]:
    return {"code": 3, "message": msg, "status": "INVALID_ARGUMENT"}


def check_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """None if the request passes the fake's strict checks, else a google.rpc.Status (400)."""
    if set(req) - TOP_KEYS or "contents" not in req:
        return invalid(f"unknown or missing fields: {sorted(set(req) ^ TOP_KEYS)}")
    si = req.get("systemInstruction") or {}
    if set(si) != {"parts"} or len(si["parts"]) != 1 or set(si["parts"][0]) != {"text"}:
        return invalid("systemInstruction must be one text part")
    for t in req.get("tools", []):
        for d in t.get("functionDeclarations", []):
            if set(d) != {"name", "description", "parametersJsonSchema"}:
                return invalid(f"function declaration fields {sorted(d)}")
    gen = req.get("generationConfig") or {}
    if set(gen) - GEN_KEYS:
        return invalid(f"generationConfig fields {sorted(gen)}")
    contents = req["contents"]
    pending: List[Tuple[Optional[str], str]] = []
    for k, c in enumerate(contents):
        want = "user" if k % 2 == 0 else "model"
        if c.get("role") != want or not c.get("parts"):
            return invalid(f"contents[{k}] must be a non-empty {want} turn")
        if want == "model":
            fcs = [p for p in c["parts"] if "functionCall" in p]
            if fcs:
                exp = signature_for(req, k)
                if fcs[0].get("thoughtSignature") != exp:
                    return invalid(f"Function call `{fcs[0]['functionCall']['name']}` in the {k}. content block is "
                                   f"missing a `thought_signature`." if "thoughtSignature" not in fcs[0] else
                                   f"contents[{k}]: thought signature does not match the turn it was issued for")
            pending = [(p["functionCall"].get("id"), p["functionCall"]["name"]) for p in fcs]
        else:
            frs = [p["functionResponse"] for p in c["parts"] if "functionResponse" in p]
            if frs or pending:
                if [(f.get("id"), f["name"]) for f in frs] != pending:
                    return invalid(f"contents[{k}]: function responses do not answer the preceding calls in order")
                if any(set(f["response"]) != {"output"} or not isinstance(f["response"]["output"], str) for f in frs):
                    return invalid(f"contents[{k}]: function response must be {{'output': <string>}}")
            pending = []
    return None


def to_neutral(req: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(system text, Anthropic-style tools, neutral messages) for the scripted policies."""
    system = req["systemInstruction"]["parts"][0]["text"]
    tools = [{"name": d["name"], "description": d["description"], "input_schema": d["parametersJsonSchema"]}
             for t in req.get("tools", []) for d in t["functionDeclarations"]]
    msgs: List[Dict[str, Any]] = []
    for c in req["contents"]:
        if c["role"] == "model":
            blocks = []
            for p in c["parts"]:
                if "text" in p:
                    blocks.append({"type": "text", "text": p["text"]})
                elif "functionCall" in p:
                    fc = p["functionCall"]
                    blocks.append({"type": "tool_use", "id": fc.get("id"), "name": fc["name"], "input": fc.get("args", {})})
            msgs.append({"role": "assistant", "content": blocks})
        else:
            texts = [p["text"] for p in c["parts"] if "text" in p]
            frs = [p["functionResponse"] for p in c["parts"] if "functionResponse" in p]
            if frs:
                msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f.get("id"),
                                                          "content": f["response"]["output"]} for f in frs]})
            for t in texts:
                msgs.append({"role": "user", "content": t})
    return system, tools, msgs


def fake_response(req: Dict[str, Any], policy: Optional[Callable] = None, model_version: str = "gemini-4-argon") -> Dict[str, Any]:
    system, tools, msgs = to_neutral(req)
    blocks = copy.deepcopy((policy or M.scripted_policy)(system, tools, msgs))
    n_prior = sum(1 for c in req["contents"] if c["role"] == "model" for p in c["parts"] if "functionCall" in p)
    parts: List[Dict[str, Any]] = []
    sig = signature_for(req, len(req["contents"]))
    n_calls = 0
    for b in blocks:
        if b["type"] == "text":
            parts.append({"text": b["text"]})
        elif b["type"] == "tool_use":
            part: Dict[str, Any] = {"functionCall": {"id": f"fake_{n_prior + n_calls}", "name": b["name"], "args": b["input"]}}
            if n_calls == 0:
                part["thoughtSignature"] = sig
            parts.append(part)
            n_calls += 1
    if not n_calls and parts:
        parts[-1]["thoughtSignature"] = sig  # Gemini 3+/4: signature on the last part of a reply without calls
    first = not any(c["role"] == "model" for c in req["contents"])
    sys_tok = max(1, len(system) // 4)
    prompt = M._approx_tokens(system, tools, msgs)
    return {
        "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP", "index": 0}],
        "usageMetadata": {"promptTokenCount": prompt, "candidatesTokenCount": M._approx_tokens(blocks),
                          "thoughtsTokenCount": 5 + 3 * len(blocks), "cachedContentTokenCount": 0 if first else min(sys_tok, prompt),
                          "totalTokenCount": prompt + M._approx_tokens(blocks) + 5 + 3 * len(blocks)},
        "modelVersion": model_version,
        "responseId": "fake_" + hashlib.sha256(canonical(req).encode()).hexdigest()[:20],
    }


def _rfc3339(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond:06d}123Z"


class FakeGeminiAPI:
    def __init__(self, state_dir: Optional[str] = None, polls_to_end: int = 1, fault: Optional[Callable] = None,
                 sync_fault: Optional[Callable] = None, policy: Optional[Callable] = None,
                 job_state: Optional[Callable[[int], str]] = None, now: Optional[Callable[[], datetime]] = None,
                 model_version: str = "gemini-4-argon") -> None:
        self.state_dir = state_dir
        self.polls_to_end = polls_to_end
        self.fault = fault
        self.sync_fault = sync_fault
        self.policy = policy
        self.job_state = job_state
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.model_version = model_version
        self.sync_bodies: List[str] = []
        self.batch_params: List[Dict[str, Any]] = []
        self.batch_raw: List[bytes] = []
        self.batches: Dict[str, Dict[str, Any]] = {}
        self.seen: Dict[str, int] = {}
        self.counter = 0
        self.creates = 0
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)
            p = os.path.join(state_dir, "fake_gemini.json")
            if os.path.exists(p):
                with open(p) as f:
                    d = json.load(f)
                self.batches, self.seen, self.counter = d["batches"], d["seen"], d["counter"]

    def _save(self) -> None:
        if self.state_dir:
            p = os.path.join(self.state_dir, "fake_gemini.json")
            with open(p + ".tmp", "w") as f:
                json.dump({"batches": self.batches, "seen": self.seen, "counter": self.counter}, f)
            os.replace(p + ".tmp", p)

    # ------------------------------------------------------------- model
    def answer(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """{"response": ...} or {"error": Status} for one request (no faults)."""
        bad = check_request(req)
        if bad:
            return {"error": bad}
        return {"response": fake_response(req, self.policy, self.model_version)}

    # ------------------------------------------------------------- HTTP
    def handle(self, request: Any) -> Any:
        httpx = _httpx()
        path, method = request.url.path, request.method
        if request.headers.get("x-goog-api-key") in (None, ""):
            return httpx.Response(401, json={"error": {"code": 401, "message": "API key missing", "status": "UNAUTHENTICATED"}})
        m = re.fullmatch(r"/v1beta/models/([^/:]+):(generateContent|batchGenerateContent)", path)
        if method == "POST" and m:
            body = json.loads(request.read())
            if m.group(2) == "generateContent":
                self.sync_bodies.append(canonical(body))
                err = self.sync_fault(body) if self.sync_fault else None
                if err is not None:
                    return httpx.Response(err[0], json=err[1])
                a = self.answer(body)
                if "error" in a:
                    return httpx.Response(400, json={"error": a["error"]})
                return httpx.Response(200, json=a["response"])
            return self._create(m.group(1), body)
        m = re.fullmatch(r"/v1beta/models/([^/:]+)", path)
        if method == "GET" and m:
            return httpx.Response(200, json={"name": f"models/{m.group(1)}", "version": "fake-001",
                                             "displayName": "Gemini 4 Argon (fake)", "outputTokenLimit": 65536,
                                             "supportedGenerationMethods": ["generateContent", "batchGenerateContent"]})
        if method == "GET" and path == "/v1beta/batches":
            ops = [self._op(b) for b in sorted(self.batches.values(), key=lambda b: b["createTime"], reverse=True)]
            return httpx.Response(200, json={"operations": ops})
        m = re.fullmatch(r"/v1beta/(batches/[^/:]+)", path)
        if method == "GET" and m and m.group(1) in self.batches:
            b = self.batches[m.group(1)]
            if b["state"] not in TERMINAL:
                b["polls_left"] -= 1
                if b["polls_left"] <= 0:
                    self._finish(b)
                self._save()
            return httpx.Response(200, json=self._op(b))
        return httpx.Response(404, json={"error": {"code": 404, "message": f"{method} {path}", "status": "NOT_FOUND"}})

    def _create(self, model: str, body: Dict[str, Any]) -> Any:
        httpx = _httpx()
        b = body.get("batch") or {}
        reqs = ((b.get("inputConfig") or {}).get("requests") or {}).get("requests") or []
        keys = [(r.get("metadata") or {}).get("key") for r in reqs]
        if set(body) != {"batch"} or not b.get("displayName") or not reqs or len(set(keys)) != len(keys) \
                or any(not isinstance(k, str) for k in keys):
            return httpx.Response(400, json={"error": invalid("bad batch body")})
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        if len(raw) > 20 * 1024 * 1024:
            return httpx.Response(400, json={"error": invalid("inline batch over 20MB")})
        self.counter += 1
        self.creates += 1
        bid = "batches/fake" + hashlib.sha256(f"{self.counter}:{keys[0]}:{os.getpid()}".encode()).hexdigest()[:16]
        for r in reqs:
            self.batch_params.append(r["request"])
            self.batch_raw.append(json.dumps(r["request"], ensure_ascii=False, separators=(",", ":")).encode())
        self.batches[bid] = {"name": bid, "model": f"models/{model}", "displayName": b["displayName"],
                             "createTime": _rfc3339(self.now()), "state": "BATCH_STATE_PENDING", "requests": reqs,
                             "polls_left": self.polls_to_end, "n": self.creates}
        if self.polls_to_end <= 0:
            self._finish(self.batches[bid])
        self._save()
        return httpx.Response(200, json=self._op(self.batches[bid]))

    def _finish(self, b: Dict[str, Any]) -> None:
        state = self.job_state(b["n"]) if self.job_state else "BATCH_STATE_SUCCEEDED"
        out = []
        for r in b["requests"]:
            key = canonical(r["request"])
            seen = self.seen.get(key, 0)
            self.seen[key] = seen + 1
            res = self.fault(r["metadata"]["key"], r["request"], seen) if self.fault else None
            if res is None:
                res = self.answer(r["request"])
            out.append(dict(res, metadata=r["metadata"]))
        b["state"] = state
        b["endTime"] = _rfc3339(self.now())
        b["results"] = out if state in ("BATCH_STATE_SUCCEEDED", "BATCH_STATE_CANCELLED") else []
        if state == "BATCH_STATE_CANCELLED":
            b["results"] = out[: len(out) // 2]  # partial results, as a cancel stops processing new requests

    def _op(self, b: Dict[str, Any]) -> Dict[str, Any]:
        done = b["state"] in TERMINAL
        n = len(b["requests"])
        ok = sum(1 for r in b.get("results", []) if "response" in r)
        meta = {"@type": "type.googleapis.com/google.ai.generativelanguage.v1beta.GenerateContentBatch",
                "model": b["model"], "displayName": b["displayName"], "createTime": b["createTime"],
                "updateTime": b.get("endTime", b["createTime"]), "state": b["state"],
                "batchStats": {"requestCount": str(n), "successfulRequestCount": str(ok) if done else "0",
                               "failedRequestCount": str(len(b.get("results", [])) - ok) if done else "0",
                               "pendingRequestCount": "0" if done else str(n)}}
        if done:
            meta["endTime"] = b["endTime"]
        op: Dict[str, Any] = {"name": b["name"], "metadata": meta, "done": done}
        if done and b["state"] == "BATCH_STATE_FAILED":
            op["error"] = {"code": 13, "message": "fake: batch job failed", "status": "INTERNAL"}
        elif done and b.get("results"):
            op["response"] = {"@type": "type.googleapis.com/google.ai.generativelanguage.v1beta.GenerateContentBatchOutput",
                              "inlinedResponses": {"inlinedResponses": b["results"]}}
        return op


def http_client(handler: Callable, api_key: str = "fake-gemini-key") -> Any:
    httpx = _httpx()
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://generativelanguage.googleapis.com",
                        headers={"x-goog-api-key": api_key})
