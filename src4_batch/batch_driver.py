"""Batch execution driver for the frozen src4 grid: Anthropic Message Batches (claude-sonnet-5, claude-fable-5)
and the Gemini Batch API (openrouter:google/gemini-4-argon-20261013; see gemini_batch.py and README "Gemini").

    python3 src4_batch/batch_driver.py --models claude-sonnet-5 --configs all --aware both \\
        --tasks <8 templates> --instances 4 --seeds 0,1 --agents 2 --out results4/full/phase1 \\
        --max-usd 330 --extra-spend-logs <every spend.jsonl> [--dry-run]

Same grid arguments, outputs and exit codes as ``src4/run4.py``; the
episodes are the frozen ones (``run4.run_one``), advanced in lockstep:

    loop:
      collect every ended batch (succeeded responses -> responses.jsonl + spend.jsonl)
      replay each changed episode with the recorded responses (replay.py):
        finished          -> transcript + results.csv row (written as run4 writes them)
        provider failure  -> failures.jsonl (as run4), episode dropped for this run
        needs completions -> the requests of every agent that needs one in the
                             current scheduler round
      submit all new requests as one batch (split only for the cost gate / size limits)
      poll with backoff until a batch ends

Model input: identical to the sync path by construction (the request body is
captured from the real SDK under the frozen provider, see replay.py) and by
test (tests_batch.py).

Money: spend is priced at ``--price-factor`` (0.5, the Batch API discount,
which applies to input, output, cache-write and cache-read tokens alike) of
prices.json, logged per completion in OUT/spend.jsonl in the frozen schema
plus ``batch: true``, ``batch_id``, ``custom_id``, ``batch_gen`` and
``price_factor``. The cap is the same one total cap as run_full.sh: every
spend.jsonl named in --extra-spend-logs plus OUT/spend.jsonl. Episodes are
admitted in run4's grid order with run4's own estimate rule (1.5 x the most
expensive finished episode of the model in this grid, else the token prior),
at batch prices. Before each batch is submitted its worst case (input tokens
bounded by request bytes + 1000, priced at the dearest input rate, plus
max_tokens of output, x price factor) plus the worst case of every batch
still in flight must fit in the cap left, or the batch is not submitted.
Errored/expired/canceled requests are not billed (Anthropic docs) and are
resubmitted in the next batch, at most ``--max-tries`` (5) tries; then the
episode records a provider failure exactly as run4 does (the frozen provider
raises the same SDK exception a sync call would have).

State (OUT/batch_state/<model>/): batches.json (every batch id, its requests
and their outcome; a submission intent is written before each create call so
a crash between create and bookkeeping is recovered by matching custom ids),
responses.jsonl (every succeeded message), episodes.json (retry generation and
lockstep rounds per episode). A restart collects in-flight batches and never
resubmits a request that is in flight or answered.

Exit codes: 0 grid finished; 2 cost cap; 3 provider failures (rerun to retry);
1 refused (usage, unconfirmed prices, another driver running).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import frozen
import model_agent4 as M
import run4
import gemini_batch as GB
from fake_api import FakeAnthropicAPI, sdk_client
from replay import ReplayEngine, error_response

DEFAULT_PRICE_FACTOR = 0.5
MAX_BATCH_REQUESTS = 100_000          # Anthropic limit per batch
MAX_BATCH_BYTES = 200 * 1024 * 1024   # Anthropic limit 256 MB; keep a margin
WORST_CASE_EXTRA_INPUT_TOKENS = 1000  # tool-use system prompt and framing, on top of the body bytes


def log(msg: str) -> None:
    print(msg, flush=True)


def iso(x: Any) -> Optional[str]:
    """Normalise an API timestamp to run4's format (YYYY-MM-DDTHH:MM:SSZ)."""
    if x is None:
        return None
    if isinstance(x, datetime):
        dt = x
    else:
        dt = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class BatchPriceTable(M.PriceTable):
    """prices.json x factor for every token class (input, output, cache write, cache read)."""

    def __init__(self, base: M.PriceTable, factor: float) -> None:
        super().__init__(base.models)
        self.factor = factor

    def token_cost(self, model: str, usage: Dict[str, Any]) -> Optional[float]:
        c = super().token_cost(model, usage)
        return None if c is None else c * self.factor

    def worst_case(self, model: str, body_bytes: int, max_tokens: int) -> float:
        entry = self.lookup(model) or {}
        pin = float(entry.get("input", 0.0))
        dearest_in = max(pin, float(entry.get("cache_write", pin * 1.25)), float(entry.get("cache_read", pin * 0.1)))
        return self.factor * ((body_bytes + WORST_CASE_EXTRA_INPUT_TOKENS) * dearest_in
                              + max_tokens * float(entry.get("output", 0.0))) / 1e6


def usage_of(message: Dict[str, Any]) -> Dict[str, Any]:
    """The usage dict model_agent4.normalized_usage builds for this message."""
    u = message.get("usage") or {}

    def num(k: str) -> Optional[int]:
        v = u.get(k)
        return v if isinstance(v, int) else None

    return {"input": u.get("input_tokens"), "output": u.get("output_tokens"),
            "cache_read": num("cache_read_input_tokens") or 0, "cache_write": num("cache_creation_input_tokens") or 0}


class AnthropicAdapter:
    """Provider-specific parts of the driver for Anthropic Message Batches (the original behaviour)."""

    mode = "anthropic_message_batches"
    max_batch_bytes = MAX_BATCH_BYTES
    max_enqueued_tokens: Optional[int] = None

    def __init__(self, model: str, prices: "BatchPriceTable") -> None:
        self.model = model
        self.prices = prices

    def make_engine(self, run_kw: Dict[str, Any]) -> Any:
        return ReplayEngine(dict(run_kw, prices=self.prices))

    @staticmethod
    def tokens_est(nbytes: int) -> int:
        return 0

    def usage_cost(self, message: Dict[str, Any], at: str) -> Tuple[Dict[str, Any], Optional[float]]:
        usage = usage_of(message)
        return usage, self.prices.token_cost(self.model, usage)

    @staticmethod
    def replay_response(row: Dict[str, Any]) -> Any:
        return row["message"]

    @staticmethod
    def error_response(result: Dict[str, Any], batch_id: str, tries: int) -> Tuple[int, Dict[str, Any]]:
        return error_response(result, batch_id, tries)

    @staticmethod
    def sent_keys(params: Dict[str, Any]) -> List[str]:
        return sorted(k for k in params if k in ("temperature",))

    @staticmethod
    def temperature_rejection(rtype: str, err_obj: Dict[str, Any], sent: List[str]) -> Optional[Dict[str, Any]]:
        err = json.dumps(err_obj)
        if rtype == "errored" and "invalid_request_error" in err and "temperature" in err and "temperature" in sent:
            return err_obj if err_obj.get("type") == "error" else {"type": "error", "error": err_obj}
        return None

    @staticmethod
    def reject_for_replay(stored: Any) -> Any:
        return stored

    def execution_extra(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {}


# --------------------------------------------------------------------------
# Batch API backend (real SDK; the dry run gives it a mock transport)
# --------------------------------------------------------------------------


def _batch_dict(b: Any) -> Dict[str, Any]:
    d = b.model_dump(mode="json") if hasattr(b, "model_dump") else dict(b)
    return {"id": d["id"], "processing_status": d.get("processing_status"), "created_at": iso(d.get("created_at")),
            "ended_at": iso(d.get("ended_at")), "request_counts": d.get("request_counts")}


class Backend:
    def __init__(self, client: Any) -> None:
        self.client = client

    def create(self, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        # No SDK retries on create: a retried POST could create a second batch (no idempotency key).
        return _batch_dict(self.client.with_options(max_retries=0).messages.batches.create(requests=requests))

    def retrieve(self, batch_id: str) -> Dict[str, Any]:
        return _batch_dict(self.client.messages.batches.retrieve(batch_id))

    def results(self, batch_id: str) -> List[Dict[str, Any]]:
        """Result lines as raw JSON (the message object exactly as the API sent it)."""
        out = []
        with self.client.messages.batches.with_streaming_response.results(batch_id) as resp:
            for line in resp.iter_lines():
                if line.strip():
                    out.append(json.loads(line))
        return out

    def list_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [_batch_dict(b) for b in self.client.messages.batches.list(limit=limit).data]


# --------------------------------------------------------------------------
# Persistent state
# --------------------------------------------------------------------------


def _write_json_atomic(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _append_line(path: str, obj: Any) -> None:
    with open(path, "a") as f:
        f.write(json.dumps(obj, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


class Store:
    """batches.json + responses.jsonl + episodes.json for one (output dir, model)."""

    def __init__(self, sd: str, spend_path: str) -> None:
        self.sd = sd
        os.makedirs(sd, exist_ok=True)
        self.batches_path = os.path.join(sd, "batches.json")
        self.resp_path = os.path.join(sd, "responses.jsonl")
        self.ep_path = os.path.join(sd, "episodes.json")
        self.spend_path = spend_path
        st = self._load(self.batches_path, {"batches": {}, "intents": {}})
        self.batches: Dict[str, Dict[str, Any]] = st["batches"]
        self.intents: Dict[str, Dict[str, Any]] = st["intents"]
        self.episodes: Dict[str, Any] = self._load(self.ep_path, {"gen": {}, "rounds": {}, "meta": {}})
        self.responses: Dict[Tuple[str, int], Dict[str, Dict[str, Any]]] = {}
        self.resp_ids: Set[Tuple[str, str]] = set()
        if os.path.exists(self.resp_path):
            with open(self.resp_path) as f:
                for line in f:
                    if line.strip():
                        try:
                            r = json.loads(line)
                        except json.JSONDecodeError:
                            continue  # torn last line after a crash; the batch is re-collected
                        self._add_response(r)
        self.spend_ids: Set[Tuple[str, str]] = set()
        self.spend_by_resp: Dict[Tuple[str, str], Dict[str, Any]] = {}
        if os.path.exists(spend_path):
            with open(spend_path) as f:
                for line in f:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if e.get("batch") and e.get("batch_id"):
                        self.spend_ids.add((e["batch_id"], e["custom_id"]))
                        self.spend_by_resp[(e["batch_id"], e["custom_id"])] = e
        # (episode_id, gen) -> request key -> [(batch_id or "intent:<nonce>", custom_id), ...] in submission order
        self.index: Dict[Tuple[str, int], Dict[str, List[Tuple[str, str]]]] = {}
        for bid, b in self.batches.items():
            for cid, m in b["requests"].items():
                self.add_ref(m, (bid, cid))
        for nonce, it in self.intents.items():
            for cid, m in it["requests"].items():
                self.add_ref(m, ("intent:" + nonce, cid))

    def add_ref(self, m: Dict[str, Any], ref: Tuple[str, str]) -> None:
        self.index.setdefault((m["episode_id"], m["gen"]), {}).setdefault(m["key"], []).append(ref)

    def refs(self, ep: str, gen: int, key: str) -> List[Tuple[str, str]]:
        return self.index.get((ep, gen), {}).get(key, [])

    @staticmethod
    def _load(path: str, default: Any) -> Any:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return default

    def _add_response(self, r: Dict[str, Any]) -> None:
        d = self.responses.setdefault((r["episode_id"], r["gen"]), {})
        d.setdefault(r["key"], r)  # first answer wins
        self.resp_ids.add((r["batch_id"], r["custom_id"]))

    def save(self) -> None:
        _write_json_atomic(self.batches_path, {"batches": self.batches, "intents": self.intents})
        _write_json_atomic(self.ep_path, self.episodes)

    # -- queries
    def gen(self, ep: str) -> int:
        return int(self.episodes["gen"].get(ep, 0))

    def bump_gen(self, ep: str) -> None:
        self.episodes["gen"][ep] = self.gen(ep) + 1

    def meta(self, ref: Tuple[str, str]) -> Dict[str, Any]:
        bid, cid = ref
        if bid.startswith("intent:"):
            return self.intents[bid[7:]]["requests"][cid]
        return self.batches[bid]["requests"][cid]

    def ref_in_flight(self, ref: Tuple[str, str]) -> bool:
        bid = ref[0]
        return bid.startswith("intent:") or self.batches[bid]["status"] != "collected"

    def in_flight(self, ep: str, gen: int, key: str) -> bool:
        return any(self.ref_in_flight(r) for r in self.refs(ep, gen, key))

    def tries(self, ep: str, gen: int, key: str) -> int:
        return len(self.refs(ep, gen, key))

    def responses_for(self, ep: str, gen: int) -> Dict[str, Dict[str, Any]]:
        return self.responses.get((ep, gen), {})

    def failed_for(self, ep: str, gen: int, max_tries: int, error_fn: Any = error_response) -> Dict[str, Any]:
        out = {}
        answered = self.responses_for(ep, gen)
        for key, refs in self.index.get((ep, gen), {}).items():
            if key in answered or len(refs) < max_tries:
                continue
            if any(self.ref_in_flight(r) for r in refs):
                continue
            last = refs[-1]
            m = self.meta(last)
            out[key] = error_fn(m.get("result_obj") or {"type": m.get("result", "missing")}, last[0], len(refs))
        return out

    def inflight_worst(self) -> float:
        w = sum(b["worst_usd"] for b in self.batches.values() if b["status"] != "collected")
        return w + sum(it["worst_usd"] for it in self.intents.values())

    def inflight_tokens(self) -> int:
        """Estimated input tokens of batches still in flight (for the Gemini enqueued-token limit)."""
        t = sum(int(b.get("tokens_est", 0)) for b in self.batches.values() if b["status"] != "collected")
        return t + sum(int(it.get("tokens_est", 0)) for it in self.intents.values())

    def has_inflight(self) -> bool:
        return bool(self.intents) or any(b["status"] != "collected" for b in self.batches.values())

    def first_submit(self, ep: str, gen: int) -> Optional[str]:
        times = [self.batches[bid]["submitted_at"] for refs in self.index.get((ep, gen), {}).values()
                 for bid, _ in refs if not bid.startswith("intent:")]
        return min(times) if times else None


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


class Episode:
    def __init__(self, cell: Dict[str, Any], order: int) -> None:
        self.cell = cell
        self.id = cell["id"]
        self.order = order
        self.dirty = True
        self.needs: List[str] = []
        self.pending: List[Any] = []
        self.spent = 0.0


class Driver:
    def __init__(self, args: argparse.Namespace, backend: Any, out: str, sd: str, adapter: Any = None) -> None:
        self.a = args
        self.backend = backend
        self.out = out
        self.model = args.model
        self.tdir = os.path.join(out, "transcripts")
        self.csv_path = os.path.join(out, "results.csv")
        self.own_spend = os.path.abspath(os.path.join(out, "spend.jsonl"))
        self.extra_logs = [p for p in run4.parse_list(args.extra_spend_logs) if os.path.abspath(p) != self.own_spend]
        if adapter is None:
            base = M.PriceTable.load(args.prices) if os.path.exists(args.prices) else M.PriceTable({})
            adapter = AnthropicAdapter(self.model, BatchPriceTable(base, args.price_factor))
        self.ad = adapter
        self.prices = adapter.prices
        self.store = Store(sd, self.own_spend)
        self.engine = adapter.make_engine({
            "schedule_kw": {"read_write_gap": args.gap, "start_jitter": args.jitter, "stall_rounds": args.stall_rounds,
                            "max_rounds": args.max_rounds},
            "turn_cap": args.turn_cap, "max_tokens": args.max_tokens, "temperature": args.temperature,
            "dry_run": args.dry_run, "prompt_caching": not args.no_cache,
        })
        self.observed: List[float] = []
        self.stop_reason: Optional[str] = None
        self.failures = 0
        self.ran = 0
        self.outcomes: List[str] = []
        self.batches_submitted = 0
        self.rounds_done: List[int] = []
        self.active: Dict[str, Episode] = {}
        self._spent: Optional[float] = None

    # ---------------------------------------------------------------- money
    def spent(self) -> float:
        """Total spend in every log (re-read after each collection; other runners are not running)."""
        if self._spent is None:
            self._spent = sum(M.SpendTracker(p).total for p in self.extra_logs) + M.SpendTracker(self.own_spend).total
        return self._spent

    def estimate(self) -> float:
        if self.observed:
            return 1.5 * max(self.observed)
        return self.prices.episode_bound(self.model, self.a.agents, self.a.turn_cap, self.a.max_tokens,
                                         self.a.prior_input_tokens)

    # ---------------------------------------------------------------- collection
    def collect_ended(self) -> bool:
        progressed = False
        for bid, b in list(self.store.batches.items()):
            if b["status"] == "collected":
                continue
            info = self.backend.retrieve(bid)
            if info["processing_status"] == "ended":
                self.collect(bid, info.get("ended_at") or run4.now_utc())
                progressed = True
        if self.store.intents:
            progressed |= self.resolve_intents()
        return progressed

    def collect(self, bid: str, ended_at: str) -> None:
        b = self.store.batches[bid]
        lines = self.backend.results(bid)
        seen = set()
        counts: Dict[str, int] = {}
        star = next((x.get("result") or {} for x in lines if x.get("custom_id") == "*"), None)
        if star is not None:  # a job-level outcome (Gemini: FAILED / EXPIRED / CANCELLED) for requests without a line
            own = {x.get("custom_id") for x in lines}
            lines = [x for x in lines if x.get("custom_id") != "*"] + [
                {"custom_id": c, "result": star} for c in b["requests"] if c not in own]
        for line in lines:
            cid = line.get("custom_id")
            m = b["requests"].get(cid)
            if m is None:
                continue
            seen.add(cid)
            res = line.get("result") or {}
            rtype = res.get("type", "missing")
            counts[rtype] = counts.get(rtype, 0) + 1
            m["result"] = rtype
            if rtype == "succeeded":
                msg = res["message"]
                if (bid, cid) not in self.store.resp_ids:
                    r = {"episode_id": m["episode_id"], "gen": m["gen"], "key": m["key"], "batch_id": bid,
                         "custom_id": cid, "agent_id": m["agent_id"], "completion": m["completion"],
                         "ended_at": ended_at, "price_at": ended_at, "message": msg}
                    _append_line(self.store.resp_path, r)
                    self.store._add_response(r)
                if (bid, cid) not in self.store.spend_ids:
                    usage, cost = self.ad.usage_cost(msg, ended_at)
                    entry = {"episode_id": m["episode_id"], "agent_id": m["agent_id"], "model": self.model,
                             "completion": m["completion"] + 1, "usage": usage,  # 1-based, as model_agent4 logs it
                             "cost_usd": 0.0 if cost is None else cost,
                             "cost_source": "unpriced" if cost is None else "price_table", "at_utc": ended_at,
                             "batch": True, "batch_id": bid, "custom_id": cid, "batch_gen": m["gen"],
                             "price_factor": self.a.price_factor}
                    _append_line(self.own_spend, entry)
                    self.store.spend_ids.add((bid, cid))
                    self.store.spend_by_resp[(bid, cid)] = entry
            else:
                m["result_obj"] = res
                err_obj = res.get("error") or {}
                body = self.ad.temperature_rejection(rtype, err_obj, m.get("sent_keys", ["temperature"]))
                if body is not None:
                    meta = self.store.episodes.setdefault("meta", {})
                    if not meta.get("temperature_rejected"):
                        meta["temperature_rejected"] = body
                        log(f"!! the API rejected temperature for {self.model}: {json.dumps(err_obj)[:300]}. As on the "
                            f"sync path (the frozen provider), requests are resent without it; temperature_effective "
                            f"is logged as null.")
        for cid, m in b["requests"].items():
            if cid not in seen:
                m["result"] = "missing"
                m["result_obj"] = {"type": "missing"}
        b["status"] = "collected"
        b["ended_at"] = ended_at
        self.store.save()
        self._spent = None
        touched = {m["episode_id"] for m in b["requests"].values()}
        for ep in self.active.values():
            if ep.id in touched:
                ep.dirty = True
        log(f"   batch {bid} ended {ended_at}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            + f"; spend now ${self.spent():.4f}")

    def resolve_intents(self) -> bool:
        """Match submission intents left by a crash between create and bookkeeping to server-side batches."""
        progressed = False
        recent = None
        for nonce, it in list(self.store.intents.items()):
            if recent is None:
                recent = self.backend.list_recent()
            t0 = parse_iso(it["at"])
            cands = [x for x in recent if x["id"] not in self.store.batches and x.get("created_at")
                     and abs((parse_iso(x["created_at"]) - t0).total_seconds()) <= 900]
            adopted = False
            pending = False
            for c in cands:
                if c["processing_status"] != "ended":
                    c.update(self.backend.retrieve(c["id"]))
                if c["processing_status"] != "ended":
                    pending = True
                    continue
                lines = self.backend.results(c["id"])
                if any(str(x.get("custom_id", "")).startswith(nonce + "-") for x in lines):
                    self._adopt(nonce, c)
                    self.collect(c["id"], c.get("ended_at") or run4.now_utc())
                    adopted = progressed = True
                    break
            if not adopted and not pending:
                log(f"   submission {nonce} has no batch on the server: dropped (its requests will be resubmitted)")
                self._drop_intent(nonce)
                progressed = True
        self.store.save()
        return progressed

    def _adopt(self, nonce: str, c: Dict[str, Any]) -> None:
        it = self.store.intents.pop(nonce)
        bid = c["id"]
        self.store.batches[bid] = {"id": bid, "nonce": nonce, "submitted_at": it["at"], "status": "in_progress",
                                   "worst_usd": it["worst_usd"], "tokens_est": it.get("tokens_est", 0),
                                   "requests": it["requests"], "adopted": True}
        self._reindex_intent(nonce, bid)
        log(f"   adopted batch {bid} for submission {nonce} (created before a crash)")

    def _drop_intent(self, nonce: str) -> None:
        self.store.intents.pop(nonce, None)
        self._reindex_intent(nonce, None)

    def _reindex_intent(self, nonce: str, bid: Optional[str]) -> None:
        tag = "intent:" + nonce
        for per_ep in self.store.index.values():
            for k, refs in per_ep.items():
                per_ep[k] = [((bid, cid) if b == tag else (b, cid)) for b, cid in refs if b != tag or bid]

    # ---------------------------------------------------------------- submission
    def submit(self, needs: List[Tuple[Episode, Any]]) -> int:
        """Submit as many of ``needs`` as fit under the cap (worst case); returns how many were submitted."""
        cap = self.a.max_usd
        avail = float("inf") if cap is None else cap - self.spent() - self.store.inflight_worst()
        tok_limit = self.ad.max_enqueued_tokens
        tok_used = self.store.inflight_tokens()
        chunks: List[List[Tuple[Episode, Any, float]]] = [[]]
        size = total = 0.0
        refused = 0
        held_tokens = 0
        for i, (ep, need) in enumerate(needs):
            mt = need.params.get("max_tokens") or (need.params.get("generationConfig") or {}).get("maxOutputTokens")
            w = self.prices.worst_case(self.model, len(need.raw), int(mt or self.a.max_tokens))
            if total + w > avail:
                refused = len(needs) - sum(len(c) for c in chunks)
                break
            t = self.ad.tokens_est(len(need.raw))
            if tok_limit and tok_used + t > tok_limit and (tok_used > 0 or any(chunks)):
                held_tokens = len(needs) - i  # waits for batches in flight to end (provider's enqueued-token limit)
                break
            if len(chunks[-1]) >= self.a.max_requests_per_batch or size + len(need.raw) > self.ad.max_batch_bytes:
                chunks.append([])
                size = 0.0
            chunks[-1].append((ep, need, w))
            size += len(need.raw) + 200
            total += w
            tok_used += t
        n = 0
        for chunk in chunks:
            if chunk:
                self._create(chunk)
                n += len(chunk)
        if refused:
            log(f"   cost gate: {refused} requests held back (worst case would pass the cap: spend ${self.spent():.4f} "
                f"+ in flight worst ${self.store.inflight_worst():.4f}, cap ${cap})")
        if held_tokens:
            log(f"   enqueued-token limit: {held_tokens} requests wait for batches in flight to end "
                f"(about {self.store.inflight_tokens():,} tokens in flight, limit {tok_limit:,})")
        return n

    def _create(self, chunk: List[Tuple[Episode, Any, float]]) -> None:
        nonce = secrets.token_hex(6)
        reqs, metas = [], {}
        for i, (ep, need, w) in enumerate(chunk):
            cid = f"{nonce}-{i:05d}"
            gen = self.store.gen(ep.id)
            metas[cid] = {"episode_id": ep.id, "gen": gen, "key": need.key, "agent_id": need.agent_id,
                          "completion": need.completion, "round": need.round,
                          "try": self.store.tries(ep.id, gen, need.key) + 1, "worst_usd": w,
                          "sent_keys": self.ad.sent_keys(need.params)}
            reqs.append({"custom_id": cid, "params": need.params})
        worst = sum(m["worst_usd"] for m in metas.values())
        tokens = sum(self.ad.tokens_est(len(need.raw)) for _, need, _ in chunk)
        at = run4.now_utc()
        self.store.intents[nonce] = {"at": at, "worst_usd": worst, "tokens_est": tokens, "requests": metas}
        for cid, m in metas.items():
            self.store.add_ref(m, ("intent:" + nonce, cid))
        self.store.save()
        info = self.backend.create(reqs)  # an exception leaves the intent; resolve_intents() settles it
        if os.environ.get("SRC4_BATCH_TEST_CRASH_AFTER_CREATE"):
            raise SystemExit("test: simulated crash after create")
        bid = info["id"]
        self.store.intents.pop(nonce)
        self.store.batches[bid] = {"id": bid, "nonce": nonce, "submitted_at": at, "status": "in_progress",
                                   "worst_usd": worst, "tokens_est": tokens, "requests": metas}
        self._reindex_intent(nonce, bid)
        self.store.save()
        self.batches_submitted += 1
        retries = sum(1 for m in metas.values() if m["try"] > 1)
        log(f"   submitted batch {bid}: {len(reqs)} requests ({retries} retries), worst case ${worst:.4f}")

    # ---------------------------------------------------------------- episodes
    def finish(self, ep: Episode, r: Any) -> None:
        tr = r.transcript
        gen = self.store.gen(ep.id)
        resp = self.store.responses_for(ep.id, gen)
        # The frozen code's own spend entries for this episode must equal what was logged at collection.
        logged = {}
        for h in r.hits:
            row = resp[h.key]
            logged[(h.agent_id, h.completion + 1)] = self.store.spend_by_resp.get((row["batch_id"], row["custom_id"]))
        for e in r.spend_entries:
            got = logged.get((e["agent_id"], e["completion"]))
            same = got is not None and all(got[k] == e[k] for k in ("episode_id", "model", "usage", "cost_usd", "cost_source"))
            if not same:
                raise SystemExit(f"internal check failed: spend logged for {ep.id} {e['agent_id']}#{e['completion']} "
                                 f"differs from the frozen code's entry: {got} vs {e}")
        # Timing fields: the sync path stamps the time each response arrived; here, the batch's end.
        ends = []
        bids = set()
        for h in r.hits:
            row = resp[h.key]
            tr["agents"][h.agent_id]["turns"][h.completion]["at_utc"] = row["ended_at"]
            ends.append(row["ended_at"])
            bids.add(row["batch_id"])
        started = self.store.first_submit(ep.id, gen) or tr["run_info"]["started_utc"]
        finished = max(ends) if ends else tr["run_info"]["finished_utc"]
        tries = [self.store.tries(ep.id, gen, h.key) for h in r.hits]
        execution = {"mode": self.ad.mode, "driver": "src4_batch/batch_driver.py",
                     "price_factor": self.a.price_factor, "batch_ids": sorted(bids),
                     "lockstep_rounds": int(self.store.episodes["rounds"].get(ep.id, 0)),
                     "retried_requests": sum(1 for t in tries if t > 1), "retry_generation": gen}
        execution.update(self.ad.execution_extra([resp[h.key] for h in r.hits]))
        tr["run_info"] = {
            "started_utc": started, "finished_utc": finished,
            "wall_seconds": round((parse_iso(finished) - parse_iso(started)).total_seconds(), 3),
            "execution": execution,
        }
        run4.write_json_atomic(os.path.join(self.tdir, ep.id + ".json"), tr)
        run4.append_csv(self.csv_path, run4.csv_row(tr))
        self.observed.append(float(tr["totals"]["cost_usd"]))
        self.rounds_done.append(tr["run_info"]["execution"]["lockstep_rounds"])
        self.ran += 1
        self.outcomes.append("ok")
        sc = tr["score"]
        log(f"[done {self.ran}] {ep.id}: non_serializable={int(sc['non_serializable'])} "
            f"label={sc['primary_label'] or '-'} inv={int(sc['invariant_violation'])} "
            f"committed={len(sc['committed_agents'])} completions={tr['totals']['completions']} "
            f"rounds={tr['run_info']['execution']['lockstep_rounds']} cost=${tr['totals']['cost_usd']:.4f}")

    def fail(self, ep: Episode, msg: str) -> None:
        self.failures += 1
        self.outcomes.append("fail")
        log(f"FAILED {ep.id}: {msg[:300]}")
        with open(os.path.join(self.out, "failures.jsonl"), "a") as f:
            f.write(json.dumps({"episode_id": ep.id, "error": msg[:2000], "at_utc": run4.now_utc()}) + "\n")
        self.store.bump_gen(ep.id)  # a retry (next run) starts the episode afresh, as run4 would
        self.store.save()

    def run(self, todo: List[Dict[str, Any]]) -> int:
        self.active: Dict[str, Episode] = {}
        queue = list(todo)
        order = {c["id"]: i for i, c in enumerate(todo)}
        admitted = 0
        cap_logged = False
        backoff = self.a.poll_min
        create_errors = 0
        while True:
            progressed = self.collect_ended() if self.store.has_inflight() else False
            # admission: run4's estimate rule at batch prices, in grid order
            while queue and (not self.a.limit or admitted < self.a.limit):
                ok, why = self._admissible()
                if not ok:
                    if not cap_logged:
                        log(f"COST CAP: holding {queue[0]['id']} and later ({len(queue)} episodes): {why}; "
                            f"they start when finished episodes lower the estimate, else they are not run.")
                        cap_logged = True
                    break
                cell = queue.pop(0)
                self.active[cell["id"]] = Episode(cell, order[cell["id"]])
                admitted += 1
            # replay changed episodes
            for ep in sorted(self.active.values(), key=lambda e: e.order):
                if not ep.dirty:
                    continue
                gen = self.store.gen(ep.id)
                responses = {k: self.ad.replay_response(v) for k, v in self.store.responses_for(ep.id, gen).items()}
                ep.spent = sum(self.store.spend_by_resp.get((v["batch_id"], v["custom_id"]), {}).get("cost_usd", 0.0)
                               for v in self.store.responses_for(ep.id, gen).values())
                r = self.engine.replay(ep.cell, responses,
                                       self.store.failed_for(ep.id, gen, self.a.max_tries, self.ad.error_response),
                                       self.ad.reject_for_replay(
                                           self.store.episodes.get("meta", {}).get("temperature_rejected")))
                ep.dirty = False
                if r.kind == "done":
                    del self.active[ep.id]
                    self.finish(ep, r)
                elif r.kind == "failed":
                    del self.active[ep.id]
                    self.fail(ep, r.error)
                else:
                    new = [n for n in r.needs if not self.store.in_flight(ep.id, gen, n.key)]
                    if new and ep.needs != [n.key for n in r.needs]:
                        rk = self.store.episodes["rounds"]
                        rk[ep.id] = int(rk.get(ep.id, 0)) + 1
                    ep.needs = [n.key for n in r.needs]
                    ep.pending = r.needs
            k = self.a.max_consecutive_failures
            if k and len(self.outcomes) >= k and all(o == "fail" for o in self.outcomes[-k:]):
                log(f"{k} consecutive provider failures - stopping (rerun to retry; in-flight batches are kept).")
                self.store.save()
                return 3
            pending = [(ep, n) for ep in sorted(self.active.values(), key=lambda e: e.order)
                       for n in ep.pending if not self.store.in_flight(ep.id, self.store.gen(ep.id), n.key)]
            self.store.save()
            submitted = 0
            if pending:
                try:
                    submitted = self.submit(pending)
                    create_errors = 0
                except SystemExit:
                    raise
                except Exception as exc:  # noqa: BLE001 - API error on create; intent kept, settled on the next loop
                    create_errors += 1
                    log(f"!! batch create failed ({type(exc).__name__}: {str(exc)[:300]})")
                    if create_errors >= 3:
                        return 3
                    time.sleep(min(self.a.poll_max, self.a.poll_min * create_errors))
                    continue
            if not self.active and not self.store.has_inflight():
                if queue and (not self.a.limit or admitted < self.a.limit) and self._admissible()[0]:
                    continue
                break
            if self.store.has_inflight():
                if not progressed and not submitted:
                    time.sleep(backoff)
                    backoff = min(self.a.poll_max, max(backoff * 1.5, 0.0))
                elif progressed:
                    backoff = self.a.poll_min
                continue
            if pending and not submitted:
                log(f"COST CAP: {len(pending)} requests cannot be submitted within the cap and nothing is in flight; "
                    f"{len(self.active)} episodes left unfinished (resumable). Spend ${self.spent():.4f}.")
                self.store.save()
                return 2
        if queue and (not self.a.limit or admitted < self.a.limit):
            log(f"COST CAP: {len(queue)} episodes not run: {self._admissible()[1]}")
            return 2
        return 0

    def _admissible(self) -> Tuple[bool, str]:
        """run4's per-episode gate, for the next episode given the episodes already running."""
        if self.a.max_usd is None:
            return True, ""
        est = self.estimate()
        reserve = sum(max(est - e.spent, 0.0) for e in self.active.values())
        spent = self.spent()
        why = (f"spend ${spent:.4f} + reserved for running episodes ${reserve:.4f} + estimate ${est:.4f} "
               f"> cap ${self.a.max_usd:.2f}")
        return spent + reserve + est <= self.a.max_usd, why


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # run4's grid/run arguments (same names, same defaults)
    p.add_argument("--models", required=True, help="exactly one Anthropic model id")
    p.add_argument("--configs", default="all")
    p.add_argument("--tasks", default="pilot")
    p.add_argument("--instances", type=int, default=0)
    p.add_argument("--agents", type=int, default=2)
    p.add_argument("--seeds", default="0,1")
    p.add_argument("--aware", choices=("off", "on", "both"), default="off")
    p.add_argument("--out", required=True)
    p.add_argument("--max-usd", type=float, default=None)
    p.add_argument("--extra-spend-logs", default="")
    p.add_argument("--turn-cap", type=int, default=M.DEFAULT_TURN_CAP)
    p.add_argument("--max-tokens", type=int, default=int(os.environ.get("IBENCH_MAX_TOKENS", M.DEFAULT_MAX_TOKENS)))
    p.add_argument("--temperature", type=float, default=M.TEMPERATURE)
    p.add_argument("--gap", type=int, default=2)
    p.add_argument("--jitter", type=int, default=0)
    p.add_argument("--stall-rounds", type=int, default=6)
    p.add_argument("--max-rounds", type=int, default=2000)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--prices", default=run4.DEFAULT_PRICES)
    p.add_argument("--allow-unconfirmed-prices", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="fake Anthropic API (dry-run model), no network; output under OUT/dry_run")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--max-consecutive-failures", type=int, default=3)
    p.add_argument("--prior-input-tokens", type=int, default=4000)
    # batch-only
    p.add_argument("--price-factor", type=float, default=DEFAULT_PRICE_FACTOR, help="batch price / list price (0.5)")
    p.add_argument("--max-tries", type=int, default=5, help="tries per request before a provider failure")
    p.add_argument("--poll-min", type=float, default=None, help="seconds; default 30 (0 in --dry-run)")
    p.add_argument("--poll-max", type=float, default=None, help="seconds; default 300 (0 in --dry-run)")
    p.add_argument("--max-requests-per-batch", type=int, default=MAX_BATCH_REQUESTS)
    p.add_argument("--fake-polls", type=int, default=2, help="--dry-run: polls before a fake batch ends")
    # Gemini only
    p.add_argument("--batch-prices", default=GB.DEFAULT_BATCH_PRICES, help="Gemini: list prices per period (prices_batch.json)")
    p.add_argument("--max-enqueued-tokens", type=int,
                   default=int(os.environ.get("GEMINI_MAX_ENQUEUED_TOKENS", GB.DEFAULT_MAX_ENQUEUED_TOKENS)),
                   help="Gemini: estimated input tokens allowed in flight (Tier 1 limit 5M; env GEMINI_MAX_ENQUEUED_TOKENS)")
    return p


def main(argv: Optional[Sequence[str]] = None, fault=None, client=None) -> int:
    a = build_parser().parse_args(argv)
    models = run4.parse_list(a.models)
    if len(models) != 1 or models[0].startswith("fake") or (models[0].startswith("openrouter:") and not GB.is_gemini(models[0])):
        log("batch_driver.py takes exactly one model id: an Anthropic model, or "
            + ", ".join(GB.GEMINI_MODELS) + " (Gemini Batch API); other OpenRouter models run with src4/run4.py")
        return 1
    a.model = models[0]
    gemini = GB.is_gemini(a.model)
    if a.poll_min is None:
        a.poll_min = 0.0 if a.dry_run else 30.0
    if a.poll_max is None:
        a.poll_max = 0.0 if a.dry_run else 300.0
    configs = run4.resolve_configs(a.configs)
    tasks = run4.resolve_tasks(a.tasks)
    seeds = run4.resolve_seeds(a.seeds)
    awares = {"off": [False], "on": [True], "both": [False, True]}[a.aware]
    out = os.path.join(a.out, "dry_run") if a.dry_run else a.out
    tdir = os.path.join(out, "transcripts")
    os.makedirs(tdir, exist_ok=True)
    csv_path = os.path.join(out, "results.csv")
    header = run4.csv_header(csv_path)
    if header is not None and header != run4.CSV_FIELDS:
        log(f"Refusing to append: {csv_path} has a different header. Use a new --out directory.")
        return 1
    if gemini:
        prices: M.PriceTable = GB.PeriodBatchPriceTable.load_file(a.batch_prices, a.price_factor)
    else:
        prices = M.PriceTable.load(a.prices) if os.path.exists(a.prices) else M.PriceTable({})
    if not a.dry_run and not a.allow_unconfirmed_prices:
        problems = prices.problems([a.model])
        if problems:
            log("Refusing a real run: prices are not confirmed:\n  " + "\n  ".join(problems))
            return 1
    if gemini and not a.dry_run and client is None and not os.environ.get("GEMINI_API_KEY"):
        log("Refusing: GEMINI_API_KEY is not set")
        return 1
    bad = frozen.verify_freeze()
    if bad:
        log("Refusing: frozen src4 files differ from FREEZE.md:\n  " + "\n  ".join(bad))
        return 1
    sd = os.path.join(out, "batch_state", run4.safe_name(a.model))
    os.makedirs(sd, exist_ok=True)
    lock = open(os.path.join(sd, "lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log(f"Refusing: another batch driver holds {sd}/lock")
        return 1

    if gemini:
        if client is None:
            if a.dry_run:
                from fake_gemini import FakeGeminiAPI, http_client  # noqa: PLC0415

                api = FakeGeminiAPI(state_dir=os.path.join(sd, "fake_api"), polls_to_end=a.fake_polls, fault=fault)
                client = http_client(api.handle)
            else:
                client = GB.real_client(os.environ["GEMINI_API_KEY"])
        backend: Any = GB.GeminiBackend(client, GB.GEMINI_MODELS[a.model],
                                        sleep=(lambda s: None) if a.dry_run or a.poll_max == 0 else time.sleep)
        adapter: Any = GB.GeminiAdapter(a.model, a.batch_prices, a.price_factor, a.max_enqueued_tokens)
    else:
        if client is None:
            if a.dry_run:
                api = FakeAnthropicAPI(state_dir=os.path.join(sd, "fake_api"), polls_to_end=a.fake_polls, fault=fault)
                client = sdk_client(api.handle, max_retries=2)
            else:
                import anthropic  # noqa: PLC0415

                client = anthropic.Anthropic(max_retries=4)
        backend = Backend(client)
        adapter = None
    drv = Driver(a, backend, out, sd, adapter)
    import anthropic  # noqa: PLC0415

    meta = drv.store.episodes.setdefault("meta", {})
    meta.setdefault("first_start_utc", run4.now_utc())
    if meta.get("anthropic_sdk") not in (None, anthropic.__version__):
        log(f"WARNING: anthropic SDK changed since this state was created ({meta['anthropic_sdk']} -> "
            f"{anthropic.__version__}); recorded responses are still used where request bodies are unchanged")
    meta["anthropic_sdk"] = anthropic.__version__
    meta["driver_sha256"] = frozen.own_hashes()

    grid = run4.build_grid([a.model], configs, tasks, seeds, a.agents, awares, a.instances)
    mode = (f"Gemini Batch API (model {GB.GEMINI_MODELS[a.model]}, enqueued-token limit {a.max_enqueued_tokens:,})"
            if gemini else "message batches")
    log(f"grid: {len(grid)} episodes = 1 model x {len(configs)} configs x {len(awares)} prompts x {len(tasks)} tasks x "
        f"{max(a.instances, 1)} instances x {len(seeds)} seeds (n={a.agents}); out={out}; mode={mode} "
        f"(price factor {a.price_factor}); anthropic SDK {anthropic.__version__}")
    have_rows = run4.csv_ids(csv_path)
    todo = []
    for cell in grid:
        path = os.path.join(tdir, cell["id"] + ".json")
        if os.path.exists(path):
            with open(path) as f:
                tr = json.load(f)
            if gemini and "execution" not in tr.get("run_info", {}):
                log(f"Refusing: {path} was not written by the batch driver (sync/OpenRouter episode). The Gemini model "
                    f"switches to the Gemini Batch API as a whole; execution paths must not mix.")
                return 1
            drv.observed.append(float(tr["totals"]["cost_usd"]))
            if cell["id"] not in have_rows:
                run4.append_csv(csv_path, run4.csv_row(tr))
        else:
            todo.append(cell)
    cap_note = f" of cap ${a.max_usd:.2f}" if a.max_usd is not None else ""
    log(f"spend so far (all logs): ${drv.spent():.4f}{cap_note}; done already: {len(grid) - len(todo)}; to run: {len(todo)}; "
        f"in flight from an earlier run: {sum(1 for b in drv.store.batches.values() if b['status'] != 'collected')} batches")
    drv.store.save()
    code = drv.run(todo)
    if code == 0 and drv.failures:
        code = 3
    rd = drv.rounds_done
    log(f"finished: ran {drv.ran}, failed {drv.failures}, batches submitted {drv.batches_submitted}; "
        f"lockstep rounds per episode max {max(rd) if rd else 0} mean {sum(rd) / len(rd) if rd else 0:.2f}; "
        f"spend so far ${drv.spent():.4f}{cap_note}; exit {code}")
    drv.store.save()
    return code


if __name__ == "__main__":
    sys.exit(main())
