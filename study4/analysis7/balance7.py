"""Log the shared OpenRouter key's usage before and after the Study 4 OpenRouter lane (registration, Data collection).
Copied from Study 3's analysis6/balance6.py; run by run_conc_study4.sh:

    python3 analysis7/balance7.py --base results7/study4 --phase before
    python3 analysis7/balance7.py --base results7/study4 --phase after --lane-exit <the lane's exit code>

Reads ``GET https://openrouter.ai/api/v1/key`` with ``$OPENROUTER_API_KEY`` (no model call, no cost) and appends
one line to ``<base>/openrouter_balance.jsonl``: time, phase, the key's ``usage`` and ``limit_remaining`` in USD, and
the raw response. ``core7.balance_report`` (Study 3's) subtracts the OpenRouter spend logged in the window; the rest
is spend by other projects on the same key.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from typing import Any, Dict, Mapping, Optional

URL = "https://openrouter.ai/api/v1/key"


def entry(phase: str, resp: Mapping[str, Any], at_utc: str, lane_exit: Optional[int] = None) -> Dict[str, Any]:
    data = resp.get("data") or {}
    usage = data.get("usage")
    rem = data.get("limit_remaining")
    return {"at_utc": at_utc, "phase": phase, "lane": "openrouter", "usage_usd": None if usage is None else float(usage),
            "limit_remaining_usd": None if rem is None else float(rem), "lane_exit": lane_exit, "raw": dict(resp)}


def fetch(key: str) -> Dict[str, Any]:  # pragma: no cover - network
    req = urllib.request.Request(URL, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main(argv=None) -> int:  # pragma: no cover - network
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--phase", choices=("before", "after"), required=True)
    ap.add_argument("--lane-exit", type=int)
    a = ap.parse_args(argv)
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    e = entry(a.phase, fetch(key), now, a.lane_exit)
    os.makedirs(a.base, exist_ok=True)
    with open(os.path.join(a.base, "openrouter_balance.jsonl"), "a") as f:
        f.write(json.dumps(e, sort_keys=True) + "\n")
    print(f"{a.phase}: usage ${e['usage_usd']}, remaining ${e['limit_remaining_usd']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
