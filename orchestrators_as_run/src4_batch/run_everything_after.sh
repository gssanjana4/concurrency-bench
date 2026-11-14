#!/usr/bin/env bash
# Start ONCE in a spare Terminal tab:
#   bash ~/Desktop/idempotencybench/src4_batch/run_everything_after.sh
# It waits for the run that is going now, then starts everything left, one after another:
#   1. run_rest_next.sh  (Gemini via Google Batch, plus any cells of other models still missing)
#   2. src_sql/run_sql.sh (the small real-database test, ~$5 cap)
# Nothing runs twice: each step resumes and skips finished episodes. Safe to Ctrl+C and start again.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
LOG=results4/full/run_everything_after.log
mkdir -p results4/full
say() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

busy() { pgrep -f "src4_batch/run_rest.sh" >/dev/null || pgrep -f "src4/run4.py" >/dev/null \
         || pgrep -f "src4_batch/batch_driver.py" >/dev/null || pgrep -f "src4/run_full.sh" >/dev/null; }

say "waiting for the current concurrency run to finish (checks every 5 min)"
while busy; do sleep 300; done
say "current run finished; last lines of run_batch.log:"
tail -3 results4/full/run_batch.log 2>/dev/null | tee -a "$LOG"

say "step 1: run_rest_next.sh (Gemini + anything still missing)"
bash src4_batch/run_rest_next.sh 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
say "step 1 exit code $rc"
if [ "$rc" != "0" ]; then
  say "step 1 did not finish cleanly (credit, key or cap?) - stopping here. Tell Claude."
  exit "$rc"
fi

say "step 2: real-database SQL test"
ALLOW_SQL_BEFORE_FULL_DONE=1 bash src_sql/run_sql.sh 2>&1 | tee -a "$LOG"
say "step 2 exit code ${PIPESTATUS[0]}"
say "ALL DONE - tell Claude."
