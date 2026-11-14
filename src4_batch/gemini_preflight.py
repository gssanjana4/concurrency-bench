"""Gemini batch preflight: one tiny request through the Gemini Batch API before the first Gemini batch run.

    python3 src4_batch/gemini_preflight.py --base results4/full [--dry-run]

The request is the frozen ``src4/preflight.py`` request (its SYSTEM and PROMPT, the get_record tool,
max_tokens 512, temperature 0), built by the frozen ``providers.OpenRouterProvider`` and translated by
gemini_translate exactly as in the grid. It is submitted as a one-request batch; the script polls until the
batch ends (Gemini's target is 24 h; small batches usually end sooner), then prints the model metadata, the
served ``modelVersion``, finish reason, token usage (thinking tokens included) and cost at batch price, and
appends that cost to the preflight spend log (so it counts toward the one $330 cap).

It fails (exit 1) unless the reply parses through the frozen provider and the served model version is
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

import frozen  # noqa: F401
import model_agent4 as M
import preflight as P  # frozen src4/preflight.py (SYSTEM, PROMPT)
import gemini_batch as GB
import gemini_translate as G
from gemini_replay import make_provider, patched_urlopen, PLACEHOLDER, payload_of
from world4 import CoordinationConfig, tool_schemas

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

            client = http_client(FakeGeminiAPI(polls_to_end=1, policy=P._ping_policy).handle)
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
    messages = [{"role": "user", "content": P.PROMPT}]
    captured = {}

    def capture(req):
        captured["greq"] = G.to_gemini_request(payload_of(req))
        return __import__("io").BytesIO(json.dumps(PLACEHOLDER).encode())

    with patched_urlopen(capture):
        make_provider().complete(MODEL, P.SYSTEM, tools, messages, a.max_tokens, 0.0)
    greq = captured["greq"]

    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    if state.get("request") not in (None, greq):
        print("   note: the saved preflight batch was for a different request; submitting a new one")
        state = {}
    if not state.get("batch_id"):
        info_b = backend.create([{"custom_id": "preflight-00000", "params": greq}])
        state = {"batch_id": info_b["id"], "submitted_at": info_b.get("created_at"), "request": greq}
        with open(state_path, "w") as f:
            json.dump(state, f, indent=1)
        print(f"   submitted preflight batch {info_b['id']} (1 request); polling until it ends")
    t0, wait = time.time(), poll_min
    while True:
        st = backend.retrieve(state["batch_id"])
        if st["processing_status"] == "ended":
            break
        if time.time() - t0 > a.max_hours * 3600:
            print(f"   FAIL preflight batch {state['batch_id']} not ended after {a.max_hours} h (rerun to keep waiting)")
            return 1
        time.sleep(wait)
        wait = min(poll_max, max(wait * 1.5, poll_min))
    lines = backend.results(state["batch_id"])
    line = next((x for x in lines if x.get("custom_id") in ("preflight-00000", "*")), None)
    res = (line or {}).get("result") or {"type": "missing"}
    if res.get("type") != "succeeded":
        print(f"   FAIL preflight batch {state['batch_id']} ({st.get('state')}): {json.dumps(res)[:600]}")
        os.remove(state_path)  # an unanswered request is not billed; the next run submits a fresh one
        return 1
    resp = res["message"]

    def serve(req):
        return __import__("io").BytesIO(json.dumps(G.to_openrouter_response(resp, greq, gm)).encode())

    with patched_urlopen(serve):
        comp = make_provider().complete(MODEL, P.SYSTEM, tools, messages, a.max_tokens, 0.0)
    usage = M.normalized_usage(comp, None)
    at = st.get("ended_at")
    cost = prices.token_cost_at(MODEL, usage, at) or 0.0
    native = resp.get("usageMetadata") or {}
    called = [b["name"] for b in comp.tool_uses]
    print(f"   ok   served={comp.model_served}  stop={comp.stop_reason} (native {comp.provider_meta.get('native_finish_reason')})"
          f"  temperature_effective={comp.temperature_effective}")
    print(f"        usage={usage}  native usageMetadata={native}  cost=${cost:.6f} (batch price, period of {at})"
          f"  tool_calls={called or 'NONE'}")
    with open(spend_log, "a") as f:
        f.write(json.dumps({"episode_id": "preflight", "agent_id": None, "model": MODEL, "completion": 0,
                            "usage": usage, "cost_usd": cost, "cost_source": "price_table", "at_utc": at,
                            "batch": True, "batch_id": state["batch_id"], "custom_id": "preflight-00000",
                            "price_factor": a.price_factor}, sort_keys=True) + "\n")
    version = str(resp.get("modelVersion") or "")
    if not (version == gm or version.startswith(gm + "-")):
        print(f"   FAIL served model version {version!r} is not {gm} (or a version of it): not starting Gemini")
        return 1
    if not called:
        print("        WARNING: no tool call in the reply (raise --max-tokens if stop=length)")
    with open(ok_path, "w") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} served={version} batch={state['batch_id']}\n")
    print(f"   Gemini batch preflight ok: served model version {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
