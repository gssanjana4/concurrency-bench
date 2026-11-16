"""Preflight (Study 2 copy of src4/preflight.py): one tiny request per model before a paid run.

For each model: checks that its prices.json entry exists and is confirmed,
sends one small request (one tool offered, small max_tokens) through the same
provider code the run uses, and prints the served model id, token usage and
the cost of that call. Exits non-zero if any model fails, so run_pilot.sh
aborts before the grid starts.

    python3 preflight6.py --models claude-haiku-4-5-20251001,openrouter:qwen/qwen3.6-27b-20260422 \\
        --spend-log results4/pilot/spend.jsonl

``--spend-log`` appends the preflight calls to the run's spend log so they
count toward the caps of run6.py / the batch driver. ``--dry-run`` uses the fake provider.

V2 (review V2 F6): a model with a required upstream host (Qwen: ``alibaba``, ``allow_fallbacks: false``) fails
the preflight unless the completion was served by that host. Anthropic models print ``thinking_chars`` (the API
may return thinking blocks with an empty text and only a signature; the transcripts record what arrives).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence

from model_agent6 import (
    host_ok,
    required_host,
    provider_family,
    PriceTable,
    completion_cost,
    make_provider,
    normalized_usage,
    now_utc,
)
from world6 import CoordinationConfig, tool_schemas

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = "You are a test agent. Use the tool once."
PROMPT = "Call get_record with record_id 'inventory:widget'."


def _ping_policy(system, tools, messages):
    return [{"type": "tool_use", "name": "get_record", "input": {"record_id": "inventory:widget"}}]


def preflight(models: Sequence[str], prices: PriceTable, max_tokens: int, dry_run: bool = False,
              allow_unconfirmed: bool = False, spend_log: Optional[str] = None) -> List[str]:
    """Return a list of failure messages (empty: all models passed)."""
    import json

    failures: List[str] = []
    tools = [tool_schemas(CoordinationConfig.from_names("none"))[0]]  # get_record only
    for model in models:
        print(f"-- {model}")
        if not dry_run and not allow_unconfirmed:
            problems = prices.problems([model])
            if problems:
                failures.append(problems[0] + " -- edit prices.json, check the numbers, set confirmed: true")
                print(f"   FAIL {failures[-1]}")
                continue
        try:
            provider, probe = make_provider(model, dry_run=dry_run, fake_policy=_ping_policy)
            comp = provider.complete(model, SYSTEM, tools, [{"role": "user", "content": PROMPT}], max_tokens, 0.0)
        except Exception as exc:  # noqa: BLE001 - report every failure, then abort the pilot
            failures.append(f"{model}: {type(exc).__name__}: {str(exc)[:400]}")
            print(f"   FAIL {failures[-1]}")
            continue
        usage = normalized_usage(comp, probe)
        cost, source = completion_cost(model, comp, usage, prices)
        called = [b["name"] for b in comp.tool_uses]
        served = str(comp.model_served or "")
        host = served.split(" @", 1)[1] if " @" in served else getattr(comp, "provider", None)
        if not dry_run and not host_ok(model, host):
            failures.append(f"{model}: served by {host!r}, required {required_host(model)!r} (allow_fallbacks is false)")
            print(f"   FAIL {failures[-1]}")
        print(f"   ok   served={comp.model_served}  stop={comp.stop_reason}  temperature_effective={comp.temperature_effective}")
        if (comp.provider_meta or {}).get("thinking_blocks"):
            print(f"        thinking_blocks={comp.provider_meta['thinking_blocks']} thinking_chars={comp.provider_meta.get('thinking_chars', 0)}")
        print(f"        usage={usage}  cost=${cost:.6f} ({source})  tool_calls={called or 'NONE'}")
        if comp.provider == "openrouter" and source != "reported":
            print("        WARNING: OpenRouter returned no usage.cost; the cap will fall back to prices.json for this model")
        if not called:
            print("        WARNING: no tool call in the reply (raise --max-tokens if stop=length)")
        if spend_log:
            os.makedirs(os.path.dirname(os.path.abspath(spend_log)), exist_ok=True)
            with open(spend_log, "a") as f:
                f.write(json.dumps({"episode_id": "preflight", "agent_id": None, "model": model, "completion": 0,
                                    "usage": usage, "cost_usd": cost, "cost_source": source,
                                    "provider_family": provider_family(model), "model_served": comp.model_served,
                                    "at_utc": comp.timestamp_utc or now_utc()}, sort_keys=True) + "\n")
    return failures


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", required=True)
    p.add_argument("--prices", default=os.path.join(HERE, "prices.json"))
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--spend-log", default=None)
    p.add_argument("--allow-unconfirmed-prices", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    prices = PriceTable.load(args.prices) if os.path.exists(args.prices) else PriceTable({})
    failures = preflight(models, prices, args.max_tokens, args.dry_run, args.allow_unconfirmed_prices, args.spend_log)
    if failures:
        print("PREFLIGHT FAILED:\n  " + "\n  ".join(failures))
        return 1
    print("preflight ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
