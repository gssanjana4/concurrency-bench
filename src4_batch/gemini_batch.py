"""Gemini Batch API backend, batch price table and driver adapter for the registered Gemini model.

Used by batch_driver.py for ``openrouter:google/gemini-4-argon-20261013`` (see README, "Gemini"). The registered
model id is kept everywhere (grid, transcripts, results.csv, spend.jsonl), so analysis cells are unchanged;
the batch is created for Google's model name ``gemini-4-argon`` (:data:`GEMINI_MODELS`).

HTTP: plain REST over the httpx module the installed ``anthropic`` SDK uses (no google-genai SDK). What is
submitted is exactly the JSON :mod:`gemini_translate` produced (no SDK object round trip that could rename or
drop fields such as ``thoughtSignature`` or ``parametersJsonSchema``); the create call is never retried
(batch creation is not idempotent); GETs are retried on 429/5xx/transport errors.

Endpoints (ai.google.dev/api/batch-mode): POST v1beta/models/{m}:batchGenerateContent (inline requests,
``metadata.key`` = our custom id), GET v1beta/batches/{id} (Operation: metadata.state, done, response.
inlinedResponses.inlinedResponses[] {metadata, response | error}, same order as the requests), GET v1beta/batches.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import frozen  # noqa: F401
import model_agent4 as M
import gemini_translate as G

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BATCH_PRICES = os.path.join(HERE, "prices_batch.json")
API_BASE = "https://generativelanguage.googleapis.com"
# registered model id -> Gemini API model name used for the batch (Google lists one version, stable "gemini-4-argon")
GEMINI_MODELS = {"openrouter:google/gemini-4-argon-20261013": "gemini-4-argon"}
TERMINAL = {"BATCH_STATE_SUCCEEDED", "BATCH_STATE_FAILED", "BATCH_STATE_CANCELLED", "BATCH_STATE_EXPIRED",
            "JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
MAX_INLINE_BYTES = 16 * 1024 * 1024        # Google: inline batches under 20 MB total; keep a margin
DEFAULT_MAX_ENQUEUED_TOKENS = 4_000_000    # Google Tier 1 "batch enqueued tokens" for Gemini 4 Argon is 5,000,000
BYTES_PER_TOKEN_EST = 3                    # conservative token estimate for the enqueued-token gate (JSON ~4 B/token)


def is_gemini(model: str) -> bool:
    return model in GEMINI_MODELS


def rfc3339(x: Any) -> Optional[str]:
    """Google RFC 3339 timestamp (nanoseconds allowed) -> run4's YYYY-MM-DDTHH:MM:SSZ (any Python 3)."""
    if not x:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})?$", str(x))
    if not m:
        raise ValueError(f"unparseable timestamp {x!r}")
    dt = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
    tz = m.group(2) or "Z"
    if tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        hh, mm = int(tz[1:3]), int(tz[4:6])
        dt = datetime.fromtimestamp(dt.replace(tzinfo=timezone.utc).timestamp() - sign * (hh * 3600 + mm * 60), timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# Prices: list prices per date period x price factor (0.5)
# --------------------------------------------------------------------------


class PeriodBatchPriceTable(M.PriceTable):
    """prices_batch.json: an entry may hold ``periods`` [{from_utc?, until_utc?, input, output, cache_write,
    cache_read}]. ``at`` (run4 timestamp) picks the period; ``at=None`` picks the dearest (estimates, worst case).
    Cost = list price x ``factor`` for every token class, as BatchPriceTable."""

    def __init__(self, models: Dict[str, Dict[str, Any]], factor: float) -> None:
        super().__init__(models)
        self.factor = factor
        self.at: Optional[str] = None

    @classmethod
    def load_file(cls, path: str, factor: float) -> "PeriodBatchPriceTable":
        with open(path) as f:
            return cls(json.load(f).get("models", {}), factor)

    def copy(self) -> "PeriodBatchPriceTable":
        return PeriodBatchPriceTable(self.models, self.factor)

    def lookup(self, model: str) -> Optional[Dict[str, Any]]:
        entry = super().lookup(model)
        if entry is None or "periods" not in entry:
            return entry
        periods = entry["periods"]
        if self.at is None:
            per = max(periods, key=lambda p: (float(p["output"]), float(p["input"])))
        else:
            per = next((p for p in periods if p.get("from_utc", "") <= self.at < p.get("until_utc", "9999")), None)
            if per is None:
                raise ValueError(f"{model}: no price period covers {self.at}")
        out = {k: v for k, v in entry.items() if k != "periods"}
        out.update({k: per[k] for k in ("input", "output", "cache_write", "cache_read") if k in per})
        out["period"] = {k: per[k] for k in ("from_utc", "until_utc") if k in per}
        return out

    def token_cost(self, model: str, usage: Dict[str, Any]) -> Optional[float]:
        c = super().token_cost(model, usage)
        return None if c is None else c * self.factor

    def token_cost_at(self, model: str, usage: Dict[str, Any], at: Optional[str]) -> Optional[float]:
        old, self.at = self.at, at
        try:
            return self.token_cost(model, usage)
        finally:
            self.at = old

    def worst_case(self, model: str, body_bytes: int, max_tokens: int) -> float:
        entry = self.lookup(model) or {}
        pin = float(entry.get("input", 0.0))
        dearest_in = max(pin, float(entry.get("cache_write", pin)), float(entry.get("cache_read", pin)))
        return self.factor * ((body_bytes + 1000) * dearest_in + max_tokens * float(entry.get("output", 0.0))) / 1e6


# --------------------------------------------------------------------------
# Backend
# --------------------------------------------------------------------------


class GeminiAPIError(RuntimeError):
    pass


class GeminiBackend:
    def __init__(self, client: Any, model_name: str, sleep: Callable[[float], None] = time.sleep, retries: int = 4) -> None:
        self.client = client
        self.model_name = model_name
        self.sleep = sleep
        self.retries = retries
        self._ops: Dict[str, Dict[str, Any]] = {}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        delay = 2.0
        for attempt in range(self.retries + 1):
            try:
                r = self.client.get(path, params=params, timeout=120)
            except Exception as exc:  # noqa: BLE001 - transport errors
                if attempt < self.retries:
                    self.sleep(delay)
                    delay *= 2
                    continue
                raise GeminiAPIError(f"GET {path}: {type(exc).__name__}: {exc}") from exc
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                self.sleep(delay)
                delay *= 2
                continue
            raise GeminiAPIError(f"GET {path}: HTTP {r.status_code}: {r.text[:500]}")
        raise GeminiAPIError("unreachable")

    @staticmethod
    def _norm(op: Dict[str, Any]) -> Dict[str, Any]:
        meta = op.get("metadata") or {}
        state = meta.get("state")
        done = bool(op.get("done")) or state in TERMINAL
        return {"id": op["name"], "processing_status": "ended" if done else "in_progress",
                "created_at": rfc3339(meta.get("createTime")),
                "ended_at": rfc3339(meta.get("endTime") or meta.get("updateTime")) if done else None,
                "request_counts": meta.get("batchStats"), "state": state, "display_name": meta.get("displayName")}

    def create(self, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        display = requests[0]["custom_id"].split("-", 1)[0]
        body = {"batch": {"displayName": f"src4-{display}",
                          "inputConfig": {"requests": {"requests": [
                              {"request": r["params"], "metadata": {"key": r["custom_id"]}} for r in requests]}}}}
        raw = G.compact(body)
        r = self.client.post(f"/v1beta/models/{self.model_name}:batchGenerateContent", content=raw,
                             headers={"content-type": "application/json"}, timeout=300)
        if r.status_code != 200:
            raise GeminiAPIError(f"batch create: HTTP {r.status_code}: {r.text[:500]}")
        op = r.json()
        self._ops[op["name"]] = op
        return self._norm(op)

    def retrieve(self, batch_id: str) -> Dict[str, Any]:
        op = self._get(f"/v1beta/{batch_id}")
        self._ops[batch_id] = op
        return self._norm(op)

    def _inlined(self, op: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        for holder in (op.get("response") or {}, (op.get("metadata") or {}).get("output") or {}):
            inl = holder.get("inlinedResponses")
            if isinstance(inl, dict):
                inl = inl.get("inlinedResponses")
            if isinstance(inl, list):
                return inl
            fname = holder.get("responsesFile")
            if fname:
                r = self.client.get(f"/download/v1beta/{fname}:download", params={"alt": "media"}, timeout=300)
                if r.status_code != 200:
                    raise GeminiAPIError(f"download {fname}: HTTP {r.status_code}: {r.text[:300]}")
                out = []
                for line in r.text.splitlines():
                    if line.strip():
                        d = json.loads(line)
                        if "key" in d and "metadata" not in d:
                            d["metadata"] = {"key": d["key"]}
                        out.append(d)
                return out
        return None

    def results(self, batch_id: str) -> List[Dict[str, Any]]:
        """Result lines in the driver's shape: {"custom_id", "result": {"type": succeeded|errored|expired|canceled,
        "message" | "error"}}. A line with custom_id "*" applies to every request without its own line."""
        op = self._ops.get(batch_id)
        if op is None or not (op.get("done") or (op.get("metadata") or {}).get("state") in TERMINAL):
            op = self._get(f"/v1beta/{batch_id}")
            self._ops[batch_id] = op
        state = (op.get("metadata") or {}).get("state", "")
        out: List[Dict[str, Any]] = []
        for item in self._inlined(op) or []:
            key = (item.get("metadata") or {}).get("key")
            if key is None:
                continue
            if "response" in item:
                resp = item["response"]
                if G.is_answer(resp):
                    out.append({"custom_id": key, "result": {"type": "succeeded", "message": resp}})
                else:
                    out.append({"custom_id": key, "result": {"type": "errored", "error": {
                        "code": 13, "status": "INTERNAL", "message": "empty response: no candidate and no block reason",
                        "response": resp}}})
            else:
                out.append({"custom_id": key, "result": {"type": "errored", "error": item.get("error") or {}}})
        if state.endswith("FAILED"):
            out.append({"custom_id": "*", "result": {"type": "errored", "error": op.get("error") or
                                                    {"code": 13, "status": "INTERNAL", "message": f"batch {state}"}}})
        elif state.endswith("EXPIRED"):
            out.append({"custom_id": "*", "result": {"type": "expired"}})
        elif state.endswith("CANCELLED"):
            out.append({"custom_id": "*", "result": {"type": "canceled"}})
        self._ops.pop(batch_id, None)
        return out

    def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        d = self._get("/v1beta/batches", params={"pageSize": min(limit, 100)})
        return [self._norm(op) for op in d.get("operations", [])]

    def model_info(self) -> Dict[str, Any]:
        return self._get(f"/v1beta/models/{self.model_name}")


def real_client(api_key: str) -> Any:
    from fake_api import _httpx  # noqa: PLC0415 - the httpx module of the installed anthropic SDK

    httpx = _httpx()
    return httpx.Client(base_url=API_BASE, headers={"x-goog-api-key": api_key}, timeout=300)


# --------------------------------------------------------------------------
# Driver adapter
# --------------------------------------------------------------------------


class GeminiAdapter:
    mode = "gemini_batch_api"
    max_batch_bytes = MAX_INLINE_BYTES

    def __init__(self, model: str, price_path: str, price_factor: float, max_enqueued_tokens: int) -> None:
        self.model = model
        self.gemini_model = GEMINI_MODELS[model]
        self.prices = PeriodBatchPriceTable.load_file(price_path, price_factor)
        self.engine_prices = self.prices.copy()
        self.max_enqueued_tokens = max_enqueued_tokens

    def make_engine(self, run_kw: Dict[str, Any]) -> Any:
        from gemini_replay import GeminiReplayEngine  # noqa: PLC0415

        return GeminiReplayEngine(dict(run_kw, prices=self.engine_prices), self.gemini_model)

    @staticmethod
    def tokens_est(nbytes: int) -> int:
        return int(math.ceil(nbytes / BYTES_PER_TOKEN_EST))

    def usage_cost(self, message: Dict[str, Any], at: str) -> Tuple[Dict[str, Any], Optional[float]]:
        usage = G.frozen_usage(message)
        return usage, self.prices.token_cost_at(self.model, usage, at)

    @staticmethod
    def replay_response(row: Dict[str, Any]) -> Dict[str, Any]:
        return {"response": row["message"], "at": row.get("price_at") or row["ended_at"]}

    @staticmethod
    def error_response(result: Dict[str, Any], batch_id: str, tries: int) -> Tuple[int, bytes]:
        rtype = result.get("type")
        if rtype == "errored":
            return G.error_http(result.get("error") or {})
        return G.error_http({"code": 13, "status": "INTERNAL",
                             "message": f"request {rtype} in Gemini batch {batch_id} (try {tries})"})

    @staticmethod
    def sent_keys(params: Dict[str, Any]) -> List[str]:
        return ["temperature"] if "temperature" in (params.get("generationConfig") or {}) else []

    @staticmethod
    def temperature_rejection(rtype: str, err_obj: Dict[str, Any], sent: List[str]) -> Optional[List[Any]]:
        msg = json.dumps(err_obj)
        if rtype == "errored" and "temperature" in sent and "temperature" in msg.lower() and \
                (err_obj.get("code") == 3 or err_obj.get("status") == "INVALID_ARGUMENT"):
            status, body = G.error_http(err_obj)
            return [status, body.decode()]
        return None

    @staticmethod
    def reject_for_replay(stored: Optional[List[Any]]) -> Optional[Tuple[int, bytes]]:
        return None if not stored else (int(stored[0]), stored[1].encode())

    def execution_extra(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        native = {"promptTokenCount": 0, "cachedContentTokenCount": 0, "candidatesTokenCount": 0, "thoughtsTokenCount": 0}
        versions = set()
        for r in rows:
            u = r["message"].get("usageMetadata") or {}
            for k in native:
                native[k] += int(u.get(k) or 0)
            versions.add(str(r["message"].get("modelVersion")))
        return {"gemini_model": self.gemini_model, "served_model_versions": sorted(versions),
                "request_translation": "src4_batch/gemini_translate.py", "native_usage": native}
