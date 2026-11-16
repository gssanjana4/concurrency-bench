"""In-process fake of the Anthropic HTTP API for dry runs and tests (no network, no keys).

It answers, through an ``httpx`` ``MockTransport`` handed to a real
``anthropic.Anthropic`` client, the endpoints the harness and the batch
driver use:

    POST /v1/messages                          sync completion (the sync-path comparator)
    POST /v1/messages/batches                  create a batch
    GET  /v1/messages/batches                  list batches
    GET  /v1/messages/batches/{id}             retrieve (status); ends after ``polls_to_end`` polls
    GET  /v1/messages/batches/{id}/results     JSONL results

The "model" is the harness dry-run model of run7 --dry-run
(:func:`model_agent7.varied_policy`, Study 3: the FakeProvider default), rendered as an Anthropic Message: a
pure function of the request body, so the sync and batch paths get identical
responses for identical requests. Tool-use ids and approximate token usage
follow :class:`model_agent7.FakeProvider`; cache tokens are filled
deterministically (creation on an agent's first completion, reads after) so
that all four price buckets are exercised.

``fault(custom_id, params, seen)`` (optional) returns ``None`` (succeed) or a
result object (``{"type": "errored", "error": {...}}``, ``{"type": "expired"}``,
``{"type": "canceled"}``) for one batch request; ``seen`` is how many times
the same request body was submitted in a batch before (0 on the first try).

With ``state_dir`` the batch store survives a new instance (crash/restart tests).
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import harness  # noqa: F401  (puts src6 on sys.path)
import model_agent7 as M

CUSTOM_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fake_message(params: Dict[str, Any], policy: Optional[Callable] = None) -> Dict[str, Any]:
    """The dry-run model's reply to one Messages API request body, as Anthropic Message JSON.

    ``policy(system_text, tools, messages) -> blocks`` defaults to the run7 --dry-run model."""
    system_text = M._system_text(params.get("system", ""))
    tools = params.get("tools") or []
    messages = params["messages"]
    blocks = copy.deepcopy((policy or M.varied_policy)(system_text, tools, messages))  # Study 3: = FakeProvider default
    n_prior = sum(1 for m in messages if m["role"] == "assistant" and isinstance(m["content"], list)
                  for b in m["content"] if b.get("type") == "tool_use")
    for i, b in enumerate(b for b in blocks if b["type"] == "tool_use"):
        b.setdefault("id", f"fake_{n_prior + i}")
    has_tool = any(b["type"] == "tool_use" for b in blocks)
    first = not any(m["role"] == "assistant" for m in messages)
    sys_tok = max(1, len(system_text) // 4)
    usage = {
        "input_tokens": M._approx_tokens(params.get("system"), tools, messages),
        "output_tokens": M._approx_tokens(blocks),
        "cache_creation_input_tokens": sys_tok if first else 0,
        "cache_read_input_tokens": 0 if first else sys_tok,
    }
    return {
        "id": "msg_fake_" + hashlib.sha256(canonical(params).encode()).hexdigest()[:24],
        "type": "message",
        "role": "assistant",
        "model": params["model"],
        "content": blocks,
        "stop_reason": "tool_use" if has_tool else "end_turn",
        "stop_sequence": None,
        "usage": usage,
    }


class FakeAnthropicAPI:
    """Fake Messages + Message Batches API (see module docstring)."""

    def __init__(self, state_dir: Optional[str] = None, polls_to_end: int = 1,
                 fault: Optional[Callable[[str, Dict[str, Any], int], Optional[Dict[str, Any]]]] = None,
                 sync_fault: Optional[Callable[[Dict[str, Any]], Optional[tuple]]] = None,
                 policy: Optional[Callable] = None) -> None:
        self.policy = policy
        self.state_dir = state_dir
        self.polls_to_end = polls_to_end
        self.fault = fault
        self.sync_fault = sync_fault  # params -> None | (http_status, error_body) for POST /v1/messages
        self.sync_bodies: List[str] = []           # canonical JSON of every POST /v1/messages body
        self.sync_raw: List[bytes] = []            # raw bytes as the SDK sent them
        self.batch_params: List[Dict[str, Any]] = []  # every batch request's params, in submission order
        self.batches: Dict[str, Dict[str, Any]] = {}
        self.seen: Dict[str, int] = {}
        self.counter = 0
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)
            p = os.path.join(state_dir, "fake_api.json")
            if os.path.exists(p):
                with open(p) as f:
                    d = json.load(f)
                self.batches, self.seen, self.counter = d["batches"], d["seen"], d["counter"]

    # ---------------------------------------------------------------- state
    def _save(self) -> None:
        if not self.state_dir:
            return
        p = os.path.join(self.state_dir, "fake_api.json")
        with open(p + ".tmp", "w") as f:
            json.dump({"batches": self.batches, "seen": self.seen, "counter": self.counter}, f)
        os.replace(p + ".tmp", p)

    def _now(self) -> str:
        self.counter += 1
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _batch_json(self, b: Dict[str, Any]) -> Dict[str, Any]:
        counts = {"processing": 0, "succeeded": 0, "errored": 0, "canceled": 0, "expired": 0}
        if b["status"] == "ended":
            for r in b["results"]:
                counts[r["result"]["type"]] += 1
        else:
            counts["processing"] = len(b["requests"])
        return {
            "id": b["id"], "type": "message_batch", "processing_status": b["status"], "request_counts": counts,
            "created_at": b["created_at"], "ended_at": b.get("ended_at"), "expires_at": b["expires_at"],
            "archived_at": None, "cancel_initiated_at": None,
            "results_url": (f"https://api.anthropic.com/v1/messages/batches/{b['id']}/results"
                            if b["status"] == "ended" else None),
        }

    # ---------------------------------------------------------------- HTTP
    def handle(self, request: Any) -> Any:
        httpx = _httpx()
        path, method = request.url.path, request.method
        if method == "POST" and path == "/v1/messages":
            body = request.read()
            self.sync_raw.append(body)
            params = json.loads(body)
            self.sync_bodies.append(canonical(params))
            err = self.sync_fault(params) if self.sync_fault else None
            if err is not None:
                return httpx.Response(err[0], json=err[1])
            return httpx.Response(200, json=fake_message(params, self.policy))
        if method == "POST" and path == "/v1/messages/batches":
            return self._create(json.loads(request.read()))
        if method == "GET" and path == "/v1/messages/batches":
            data = [self._batch_json(b) for b in sorted(self.batches.values(), key=lambda b: b["created_at"], reverse=True)]
            return httpx.Response(200, json={"data": data, "has_more": False,
                                             "first_id": data[0]["id"] if data else None,
                                             "last_id": data[-1]["id"] if data else None})
        m = re.fullmatch(r"/v1/messages/batches/([^/]+)(/results)?", path)
        if method == "GET" and m and m.group(1) in self.batches:
            b = self.batches[m.group(1)]
            if m.group(2):
                if b["status"] != "ended":
                    return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "not ended"}})
                text = "".join(json.dumps(r) + "\n" for r in b["results"])
                return httpx.Response(200, content=text.encode(), headers={"content-type": "application/binary"})
            if b["status"] != "ended":
                b["polls_left"] -= 1
                if b["polls_left"] <= 0:
                    self._finish(b)
                self._save()
            return httpx.Response(200, json=self._batch_json(b))
        return httpx.Response(404, json={"type": "error", "error": {"type": "not_found_error", "message": f"{method} {path}"}})

    def _create(self, body: Dict[str, Any]) -> Any:
        httpx = _httpx()
        reqs = body.get("requests") or []
        ids = [r.get("custom_id") for r in reqs]
        bad = [i for i in ids if not isinstance(i, str) or not CUSTOM_ID_RE.match(i)]
        if not reqs or bad or len(set(ids)) != len(ids) or len(reqs) > 100_000:
            return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
                                                                         "message": f"bad batch: {bad[:3]} n={len(reqs)}"}})
        now = self._now()
        bid = "msgbatch_fake_" + hashlib.sha256(f"{self.counter}:{now}:{ids[0]}:{os.getpid()}".encode()).hexdigest()[:20]
        for r in reqs:
            self.batch_params.append(r["params"])
        self.batches[bid] = {"id": bid, "status": "in_progress", "created_at": now,
                             "expires_at": now, "requests": reqs, "polls_left": self.polls_to_end}
        if self.polls_to_end <= 0:
            self._finish(self.batches[bid])
        self._save()
        return httpx.Response(200, json=self._batch_json(self.batches[bid]))

    def _finish(self, b: Dict[str, Any]) -> None:
        results = []
        for r in b["requests"]:
            key = canonical(r["params"])
            seen = self.seen.get(key, 0)
            self.seen[key] = seen + 1
            res = self.fault(r["custom_id"], r["params"], seen) if self.fault else None
            if res is None:
                res = {"type": "succeeded", "message": fake_message(r["params"], self.policy)}
            results.append({"custom_id": r["custom_id"], "result": res})
        b["results"] = results
        b["status"] = "ended"
        b["ended_at"] = self._now()


def _httpx():
    """The httpx module the installed anthropic SDK uses (httpx2 in SDK 2.x, httpx before)."""
    import anthropic._base_client as bc  # noqa: PLC0415

    return getattr(bc, "httpx2", None) or getattr(bc, "httpx")


def sdk_client(handler: Callable, max_retries: int = 0) -> Any:
    """A real ``anthropic.Anthropic`` client whose HTTP traffic goes to ``handler`` (no network)."""
    import anthropic  # noqa: PLC0415

    httpx = _httpx()
    return anthropic.Anthropic(api_key="sk-ant-offline", base_url="https://api.anthropic.com", max_retries=max_retries,
                               http_client=httpx.Client(transport=httpx.MockTransport(handler)))
