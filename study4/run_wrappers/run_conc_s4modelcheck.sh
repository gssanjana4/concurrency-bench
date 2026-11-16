#!/usr/bin/env bash
# Free check (no model call, no cost): does the Anthropic API list the Study 4 model ids? Prints status and id only.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
PY="$(pwd)/.venv/bin/python"
"$PY" - <<'PYEOF'
import os, json, urllib.request
for m in ("claude-fable-5", "claude-sonnet-5", "claude-haiku-4-5-20251001"):
    req = urllib.request.Request(f"https://api.anthropic.com/v1/models/{m}",
        headers={"x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r); print(m, "OK", d.get("id"), d.get("display_name"), d.get("created_at"))
    except urllib.error.HTTPError as e:
        print(m, "HTTP", e.code, e.read()[:200])
    except Exception as e:
        print(m, "ERR", type(e).__name__, str(e)[:200])
PYEOF
