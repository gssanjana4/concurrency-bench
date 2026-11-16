#!/usr/bin/env bash
# Free check (no model call): OpenRouter account credits (total purchased, total used). Prints numbers only.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
.venv/bin/python - <<'PY'
import os, json, urllib.request
req = urllib.request.Request("https://openrouter.ai/api/v1/credits", headers={"Authorization": "Bearer " + os.environ.get("OPENROUTER_API_KEY", "")})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)["data"]; print("total_credits", d.get("total_credits"), "total_usage", d.get("total_usage"), "balance", round((d.get("total_credits") or 0) - (d.get("total_usage") or 0), 4))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read()[:300])
PY
