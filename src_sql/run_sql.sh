#!/bin/bash
# EXPLORATORY raw-SQL slice (post hoc, NOT pre-registered): agents with raw SQL on one real SQLite file,
# truly concurrent. Claude Haiku 4.5 + Qwen3.6-27B, n = 2 and 4, 4 templates x 2 variants x 4 reps = 128 episodes.
#
# Run from your own Terminal:   bash ~/Desktop/idempotencybench/src_sql/run_sql.sh
#   Dry run (scripted fake agents, no keys, no money):   bash .../src_sql/run_sql.sh --dry-run
#   Only check whether the main run is still going:      bash .../src_sql/run_sql.sh --check-only
#
# - REFUSES TO START while the main study's full run is in progress: a running src4/run_full.sh or
#   src4/run4.py process, or a results4/full/run.log whose last session has no end line
#   ("=== FULL RUN DONE", a total-cost-cap stop, or "=== STOPPED before phase"). If that run crashed
#   and you have decided not to resume it, ALLOW_SQL_BEFORE_FULL_DONE=1 skips the log check only
#   (a running process always blocks). Dry runs only print the check.
# - Needs ANTHROPIC_API_KEY and OPENROUTER_API_KEY in ~/Desktop/idempotencybench/.env (not for --dry-run).
# - Resumable: if it stops (sleep, crash, Ctrl-C), run the same line again. Finished episodes are kept;
#   spend so far still counts toward the cap.
# - Money: hard cap $5 for results_sql/ (preflight calls included). Estimate printed before the run.
# - Writes ONLY to results_sql/ (dry run: results_sql/dry_run/). Never writes to src4/ or results4/.
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1   # no __pycache__ inside the frozen src4/

DRY=0; CHECK_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --check-only) CHECK_ONLY=1 ;;
    *) echo "unknown argument $1 (use --dry-run or --check-only)"; exit 1 ;;
  esac
  shift
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT" || exit 1

# --------------------------------------------------------------------------
# Guard: never compete with the main full run.
# --------------------------------------------------------------------------
full_run_guard() {
  if pgrep -f 'run_full[.]sh' >/dev/null 2>&1 || pgrep -f 'src4/run4[.]py' >/dev/null 2>&1; then
    echo "!! The main study's full run is RUNNING (src4/run_full.sh or src4/run4.py process found)."
    echo "   Not starting the SQL slice; run this again after it has finished."
    return 1
  fi
  local LOGF="results4/full/run.log"
  if [ ! -f "$LOGF" ]; then
    echo "   guard: no $LOGF (main full run not started). Do not start run_full.sh until this finishes."
    return 0
  fi
  # Text of the last session (from the last '=== start' line to the end of the log).
  local last
  last="$(awk '/^=== start /{buf=""} {buf = buf $0 "\n"} END {printf "%s", buf}' "$LOGF")"
  if printf '%s' "$last" | grep -qE '^=== FULL RUN DONE|total cost cap reached|^=== STOPPED before phase'; then
    echo "   guard: main full run has finished ($(printf '%s' "$last" | grep -E '^=== FULL RUN DONE|total cost cap reached|^=== STOPPED before phase' | tail -1))"
    return 0
  fi
  if [ "${ALLOW_SQL_BEFORE_FULL_DONE:-0}" = "1" ]; then
    echo "   guard: $LOGF has no end line, but ALLOW_SQL_BEFORE_FULL_DONE=1 is set - continuing (no run_full.sh process is running)."
    return 0
  fi
  echo "!! $LOGF: the last full-run session has no end line, so the main run is unfinished"
  echo "   (still running elsewhere, or stopped by a crash/sleep and waiting to be resumed)."
  echo "   Finish it first (bash src4/run_full.sh resumes it). If you have decided not to resume it:"
  echo "   ALLOW_SQL_BEFORE_FULL_DONE=1 bash src_sql/run_sql.sh"
  return 1
}

if [ $CHECK_ONLY = 1 ]; then
  full_run_guard; exit $?
fi

OUT="results_sql"
mkdir -p "$OUT"
LOG="$OUT/run.log"; [ $DRY = 1 ] && LOG="$OUT/run_dry.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== start $(date)  dry_run=$DRY  (EXPLORATORY raw-SQL slice, not pre-registered)"

if [ $DRY = 1 ]; then
  full_run_guard || echo "   (dry run: no API calls, continuing anyway)"
  PY=python3; DRYFLAG="--dry-run"; SUB="/dry_run"; RETRY_SLEEP=1
else
  full_run_guard || exit 1
  set -a; source .env; set +a
  for K in ANTHROPIC_API_KEY OPENROUTER_API_KEY; do
    if [ -z "${!K:-}" ]; then echo "$K missing in .env"; exit 1; fi
  done
  # Same private Python env as src4 (one dependency: anthropic SDK).
  if [ ! -x .venv/bin/python ]; then
    echo "Setting up .venv (one time)..."
    python3 -m venv .venv && .venv/bin/pip install -q anthropic || { echo "venv setup failed"; exit 1; }
  fi
  .venv/bin/python -c "import anthropic" 2>/dev/null || .venv/bin/pip install -q anthropic || { echo "pip install anthropic failed"; exit 1; }
  PY=.venv/bin/python; DRYFLAG=""; SUB=""; RETRY_SLEEP=60
  # Keep the Mac awake while this script runs (macOS).
  command -v caffeinate >/dev/null && caffeinate -dimsu -w $$ &
fi

MODELS="claude-haiku-4-5-20251001,openrouter:qwen/qwen3.6-27b-20260422"
MAX_USD=5
GRID=(--models "$MODELS" --tasks all --variants 0,1 --agents 2,4 --reps 0-3)

$PY src_sql/run_sql.py "${GRID[@]}" --out "$OUT" --estimate || { echo "!! estimate failed"; exit 1; }

echo "== preflight"
mkdir -p "$OUT$SUB"
if [ -f "$OUT$SUB/preflight_ok" ]; then
  echo "   already passed earlier ($(cat "$OUT$SUB/preflight_ok")); not repeated"
else
  $PY src4/preflight.py --models "$MODELS" --spend-log "$OUT$SUB/spend.jsonl" $DRYFLAG \
    || { echo "!! preflight failed - SQL slice not started (see above)"; exit 1; }
  date > "$OUT$SUB/preflight_ok"
fi

for attempt in 1 2 3 4 5; do
  echo "== SQL grid (attempt $attempt)  $(date)"
  $PY src_sql/run_sql.py "${GRID[@]}" --max-usd "$MAX_USD" --out "$OUT" $DRYFLAG
  status=$?
  case $status in
    0) echo "=== SQL SLICE DONE $(date). Results in $OUT$SUB/ (results.csv, agents.csv, transcripts/)."
       if [ $DRY = 1 ]; then
         $PY src_sql/analyze_sql.py "$OUT$SUB/results.csv" --out "$OUT$SUB/analysis" --include-dry-run
       else
         $PY src_sql/analyze_sql.py "$OUT/results.csv" --out "$OUT/analysis"
       fi
       exit 0 ;;
    2) echo "!! \$$MAX_USD cost cap reached - stopping. Completed episodes are in $OUT$SUB/."
       echo "   Analyse what finished with: $PY src_sql/analyze_sql.py $OUT$SUB/results.csv --out $OUT$SUB/analysis"
       exit 2 ;;
    4) echo "!! OpenRouter credit/key limit reached - stopping."; exit 4 ;;
    1) echo "!! run_sql.py refused to run (see message above)"; exit 1 ;;
    *) echo "   provider failures (exit $status); retrying in ${RETRY_SLEEP}s (completed episodes are kept)"; sleep "$RETRY_SLEEP" ;;
  esac
done
echo "!! still failing after 5 attempts - see $OUT$SUB/failures.jsonl; run this script again to retry"; exit 3
