#!/usr/bin/env bash
# Free check (no model call): does the Anthropic API know the Study 4 batch that returned 404? Prints status only.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
.venv/bin/python - <<'PY'
import os, json, urllib.request
for b in ("msgbatch_01KJXyyzxRCbrbcxSJv5GrdZ",):
    req = urllib.request.Request(f"https://api.anthropic.com/v1/messages/batches/{b}",
        headers={"x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r); print(b, "OK", d.get("processing_status"), d.get("request_counts"), d.get("created_at"))
    except urllib.error.HTTPError as e:
        print(b, "HTTP", e.code, e.read()[:200])
PY
