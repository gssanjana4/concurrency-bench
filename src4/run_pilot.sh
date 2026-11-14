#!/bin/bash
# Concurrency benchmark (src4) pilot: Claude Haiku 4.5 + Qwen3.6-27B, 2 agents.
# Run from your own Terminal:   bash ~/Desktop/idempotencybench/src4/run_pilot.sh
# - Before the first run: check the prices in src4/prices.json and set
#   "confirmed": true for both models (the run refuses placeholder prices).
# - Needs ANTHROPIC_API_KEY and OPENROUTER_API_KEY in ~/Desktop/idempotencybench/.env
# - Resumable: if it stops (sleep, crash, Ctrl-C), run the same line again.
#   Finished episodes are kept; spend so far still counts toward the cap.
# - Money: hard cap $15 for results4/pilot/ (preflight calls included).
# - Writes ONLY to results4/pilot/.
set -uo pipefail
cd "$(dirname "$0")/.."            # repo root (~/Desktop/idempotencybench)
OUT="results4/pilot"
mkdir -p "$OUT"
exec > >(tee -a "$OUT/run.log") 2>&1
echo "=== start $(date)"

set -a; source .env; set +a
for K in ANTHROPIC_API_KEY OPENROUTER_API_KEY; do
  if [ -z "${!K:-}" ]; then echo "$K missing in .env"; exit 1; fi
done

# Private Python env with the one dependency (anthropic SDK).
if [ ! -x .venv/bin/python ]; then
  echo "Setting up .venv (one time)..."
  python3 -m venv .venv && .venv/bin/pip install -q anthropic || { echo "venv setup failed"; exit 1; }
fi
.venv/bin/python -c "import anthropic" 2>/dev/null || .venv/bin/pip install -q anthropic || { echo "pip install anthropic failed"; exit 1; }
PY=.venv/bin/python

# Keep the Mac awake while this script runs (macOS).
command -v caffeinate >/dev/null && caffeinate -dimsu -w $$ &

# Exact ids. Haiku: the dated id the previous paper's code used (src2/sweep2.py).
MODELS="claude-haiku-4-5-20251001,openrouter:qwen/qwen3.6-27b-20260422"
CONFIGS="none,reread_only,cas_available,cas_required,locks,messages"
MAX_USD=15

echo "== preflight"
$PY src4/preflight.py --models "$MODELS" --spend-log "$OUT/spend.jsonl" \
  || { echo "!! preflight failed - pilot not started (see above)"; exit 1; }

for attempt in 1 2 3 4 5; do
  echo "== pilot grid (attempt $attempt)  $(date)"
  $PY src4/run4.py --models "$MODELS" --configs "$CONFIGS" --tasks pilot \
    --agents 2 --seeds 0,1 --max-usd "$MAX_USD" --out "$OUT"
  status=$?
  case $status in
    0) echo "=== PILOT DONE $(date). Results in $OUT/ (results.csv, transcripts/) - tell Claude it finished."; exit 0 ;;
    2) echo "!! \$$MAX_USD cost cap reached - stopping. Completed episodes are in $OUT/."; exit 2 ;;
    4) echo "!! OpenRouter credit/key limit reached - stopping."; exit 4 ;;
    1) echo "!! run4.py refused to run (see message above)"; exit 1 ;;
    *) echo "   provider failures (exit $status); retrying in 60s (completed episodes are kept)"; sleep 60 ;;
  esac
done
echo "!! pilot still failing after 5 attempts - see $OUT/failures.jsonl"; exit 3
