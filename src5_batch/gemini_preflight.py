"""Gemini batch preflight: one tiny request through the Gemini Batch API before the first Gemini batch run.

    python3 src5_batch/gemini_preflight.py --base results4/full [--dry-run]

The request is the ``src5/preflight5.py`` request (its SYSTEM and PROMPT, the get_record tool,
max_tokens 512, temperature 0), built by the harness ``providers.OpenRouterProvider`` and translated by
gemini_translate exactly as in the grid. It is submitted as a one-request batch; the script polls until the
batch ends (Gemini's target is 24 h; small batches usually end sooner), then prints the model metadata, the
served ``modelVersion``, finish reason, token usage (thinking tokens included) and cost at batch price, and
appends that cost to the preflight spend log (so it counts toward the Gemini provider cap, $22).

V2 (review V2 F8): a second, *two-turn parallel-call* check exercises the thought-signature round trip against
the live API: turn 1 asks for two parallel ``get_record`` calls; turn 2 sends both function responses back in one
user turn (signature on the first functionCall part, calls then responses in order: the layout the grid uses).
It fails unless turn 1 made at least two calls and turn 2 was answered without an error. Cost: two tiny
requests (well under $0.01).

It fails (exit 1) unless the reply parses through the harness provider and the served model version is
``gemini-4-argon`` or a version of it (``gemini-4-argon-...``): nothing else is spent before you have seen
the served name. Passing writes ``<base>/preflight<sub>/gemini_batch_ok``; later runs skip the preflight.
The batch id is saved before polling, so an interrupted preflight resumes the same batch (never pays twice).
``--dry-run`` uses the offline fake API (no key, no money).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional, Sequence

import harness  # noqa: F401
import model_agent5 as M
import preflight5 as P  # src5/preflight5.py (SYSTEM, PROMPT)
import gemini_batch as GB
import gemini_translate as G
from gemini_replay import make_provider, patched_urlopen, PLACEHOLDER, payload_of
from world5 import CoordinationConfig, tool_schemas

MODEL = next(iter(GB.GEMINI_MODELS))


def main(argv: Optional[Sequence[str]] = None, client=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", required=True)
    p.add_argument("--sub", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--batch-prices", default=GB.DEFAULT_BATCH_PRICES)
    p.add_argument("--price-factor", type=float, default=0.5)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--poll-min", type=float, default=None)
    p.add_argument("--poll-max", type=float, default=None)
    p.add_argument("--max-hours", type=float, default=48.0)
    a = p.parse_args(argv)
    sub = a.sub or ("/dry_run" if a.dry_run else "")
    d = os.path.join(a.base, "preflight" + sub)
    os.makedirs(d, exist_ok=True)
    ok_path, state_path = os.path.join(d, "gemini_batch_ok"), os.path.join(d, "gemini_batch_preflight.json")
    spend_log = os.path.join(d, "spend.jsonl")
    if os.path.exists(ok_path):
        print(f"   Gemini batch preflight already passed ({open(ok_path).read().strip()}); not repeated")
        return 0
    poll_min = a.poll_min if a.poll_min is not None else (0.0 if a.dry_run else 30.0)
    poll_max = a.poll_max if a.poll_max is not None else (0.0 if a.dry_run else 300.0)
    if client is None:
        if a.dry_run:
            from fake_gemini import FakeGeminiAPI, http_client  # noqa: PLC0415

            client = http_client(FakeGeminiAPI(polls_to_end=1, policy=_preflight_policy).handle)
        else:
            key = os.environ.get("GEMINI_API_KEY")
            if not key:
                print("   FAIL GEMINI_API_KEY is not set")
                return 1
            client = GB.real_client(key)
    gm = GB.GEMINI_MODELS[MODEL]
    backend = GB.GeminiBackend(client, gm, sleep=(lambda s: None) if poll_max == 0 else time.sleep)
    prices = GB.PeriodBatchPriceTable.load_file(a.batch_prices, a.price_factor)
    if prices.problems([MODEL]):
        print("   FAIL " + "; ".join(prices.problems([MODEL])))
        return 1
    try:
        info = backend.model_info()
    except Exception as exc:  # noqa: BLE001
        print(f"   FAIL model metadata for {gm}: {exc}")
        return 1
    print(f"-- {MODEL} via Gemini Batch API, model {info.get('name')} version={info.get('version')} "
          f"displayName={info.get('displayName')!r} outputTokenLimit={info.get('outputTokenLimit')}")

    tools = [tool_schemas(CoordinationConfig.from_names("none"))[0]]
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}

    def save() -> None:
        with open(state_path, "w") as f:
            json.dump(state, f, indent=1)

    def capture(system: str, messages):
        got = {}

        def cap(req):
            got["greq"] = G.to_gemini_request(payload_of(req))
            return __import__("io").BytesIO(json.dumps(PLACEHOLDER).encode())

        with patched_urlopen(cap):
            make_provider().complete(MODEL, system, tools, messages, a.max_tokens, 0.0)
        return got["greq"]

    def run_request(key: str, greq):
        """Submit ``greq`` as a one-request batch (resumable via the state file); (status, message) or None."""
        cid = f"preflight-{key}"
        st_k = state.get(key) or {}
        if st_k.get("request") not in (None, greq):
            print(f"   note: the saved preflight batch {key} was for a different request; submitting a new one")
            st_k = {}
        if not st_k.get("batch_id"):
            info_b = backend.create([{"custom_id": cid, "params": greq}])
            st_k = {"batch_id": info_b["id"], "submitted_at": info_b.get("created_at"), "request": greq}
            state[key] = st_k
            save()
            print(f"   submitted preflight batch {info_b['id']} ({key}); polling until it ends")
        t0, wait = time.time(), poll_min
        while True:
            st = backend.retrieve(st_k["batch_id"])
            if st["processing_status"] == "ended":
                break
            if time.time() - t0 > a.max_hours * 3600:
                print(f"   FAIL preflight batch {st_k['batch_id']} not ended after {a.max_hours} h (rerun to keep waiting)")
                return None
            time.sleep(wait)
            wait = min(poll_max, max(wait * 1.5, poll_min))
        lines = backend.results(st_k["batch_id"])
        line = next((x for x in lines if x.get("custom_id") in (cid, "*")), None)
        res = (line or {}).get("result") or {"type": "missing"}
        if res.get("type") != "succeeded":
            print(f"   FAIL preflight batch {st_k['batch_id']} ({key}, {st.get('state')}): {json.dumps(res)[:600]}")
            state.pop(key, None)  # an unanswered request is not billed; the next run submits a fresh one
            save()
            return None
        return st, res["message"]

    def parse(system: str, messages, greq, resp):
        def serve(req):
            return __import__("io").BytesIO(json.dumps(G.to_openrouter_response(resp, greq, gm)).encode())

        with patched_urlopen(serve):
            return make_provider().complete(MODEL, system, tools, messages, a.max_tokens, 0.0)

    def log_spend(comp, st, key: str) -> float:
        usage = M.normalized_usage(comp, None)
        at = st.get("ended_at")
        cost = prices.token_cost_at(MODEL, usage, at) or 0.0
        with open(spend_log, "a") as f:
            f.write(json.dumps({"episode_id": "preflight", "agent_id": None, "model": MODEL, "completion": 0,
                                "usage": usage, "cost_usd": cost, "cost_source": "price_table", "at_utc": at,
                                "batch": True, "batch_id": state[key]["batch_id"], "custom_id": f"preflight-{key}",
                                "price_factor": a.price_factor, "provider_family": "gemini"}, sort_keys=True) + "\n")
        return cost

    # ---- phase A: one single-turn request (served model, usage, cost)
    if "batch_id" in state and "ping" not in state:  # state written by the v1 preflight
        state = {"ping": state}
    messages = [{"role": "user", "content": P.PROMPT}]
    greq = capture(P.SYSTEM, messages)
    got = run_request("ping", greq)
    if got is None:
        return 1
    st, resp = got
    comp = parse(P.SYSTEM, messages, greq, resp)
    usage = M.normalized_usage(comp, None)
    native = resp.get("usageMetadata") or {}
    called = [b["name"] for b in comp.tool_uses]
    cost = log_spend(comp, st, "ping") if not state["ping"].get("logged") else 0.0
    state["ping"]["logged"] = True
    save()
    print(f"   ok   served={comp.model_served}  stop={comp.stop_reason} (native {comp.provider_meta.get('native_finish_reason')})"
          f"  temperature_effective={comp.temperature_effective}")
    print(f"        usage={usage}  native usageMetadata={native}  cost=${cost:.6f} (batch price, period of {st.get('ended_at')})"
          f"  tool_calls={called or 'NONE'}")
    version = str(resp.get("modelVersion") or "")
    if not (version == gm or version.startswith(gm + "-")):
        print(f"   FAIL served model version {version!r} is not {gm} (or a version of it): not starting Gemini")
        return 1
    if not called:
        print("        WARNING: no tool call in the reply (raise --max-tokens if stop=length)")

    # ---- phase B: two turns with parallel function calls (thought-signature round trip, review V2 F8)
    m1 = [{"role": "user", "content": PARALLEL_PROMPT}]
    g1 = capture(P.SYSTEM, m1)
    got = run_request("parallel_t1", g1)
    if got is None:
        return 1
    st1, r1 = got
    c1 = parse(P.SYSTEM, m1, g1, r1)
    if not state["parallel_t1"].get("logged"):
        log_spend(c1, st1, "parallel_t1")
        state["parallel_t1"]["logged"] = True
        save()
    if len(c1.tool_uses) < 2:
        print(f"   FAIL parallel-call check: turn 1 made {len(c1.tool_uses)} tool call(s), need 2 "
              f"(rerun to try again; the signature round trip with parallel calls was not exercised)")
        state.pop("parallel_t1", None)
        save()
        return 1
    prov = make_provider()
    results = [{"type": "tool_result", "tool_use_id": t["id"],
                "content": json.dumps({"ok": True, "status": 200, "record_id": t["input"].get("record_id"), "value": 5},
                                      sort_keys=True)} for t in c1.tool_uses]
    m2 = m1 + [prov.history_assistant(c1), prov.history_tool_results(results)]
    g2 = capture(P.SYSTEM, m2)
    first_model = next(c for c in g2["contents"] if c["role"] == "model")
    fcs = [q for q in first_model["parts"] if "functionCall" in q]
    if not fcs or "thoughtSignature" not in fcs[0]:
        print("   FAIL parallel-call check: the turn-2 request does not carry the thought signature on the first functionCall")
        return 1
    got = run_request("parallel_t2", g2)
    if got is None:
        print("   FAIL parallel-call check: turn 2 (two function responses after two parallel calls) was rejected")
        return 1
    st2, r2 = got
    c2 = parse(P.SYSTEM, m2, g2, r2)
    if not state["parallel_t2"].get("logged"):
        log_spend(c2, st2, "parallel_t2")
        state["parallel_t2"]["logged"] = True
        save()
    print(f"   ok   parallel-call check: turn 1 made {len(c1.tool_uses)} calls; turn 2 answered "
          f"(stop={c2.stop_reason}, {len(c2.tool_uses)} further calls)")
    with open(ok_path, "w") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} served={version} batch={state['ping']['batch_id']} "
                f"parallel={state['parallel_t1']['batch_id']},{state['parallel_t2']['batch_id']}\n")
    print(f"   Gemini batch preflight ok: served model version {version}")
    return 0


PARALLEL_PROMPT = ("In one reply, call get_record twice in parallel: record_id 'inventory:widget' and record_id "
                   "'inventory:gadget'. When you have both results, reply DONE with no tool call.")


def _preflight_policy(system, tools, messages):
    """Dry-run model for both preflight phases."""
    first = messages[0]["content"] if messages else ""
    turns = sum(1 for m in messages if m["role"] == "assistant")
    if first == PARALLEL_PROMPT:
        if turns == 0:
            return [{"type": "tool_use", "name": "get_record", "input": {"record_id": r}}
                    for r in ("inventory:widget", "inventory:gadget")]
        return [{"type": "text", "text": "DONE"}]
    return P._ping_policy(system, tools, messages)


if __name__ == "__main__":
    sys.exit(main())
