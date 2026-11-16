#!/usr/bin/env bash
# Study 4, OpenRouter lane only, restarted after each OpenRouter 402 "in_flight_budget_exhausted" stop (a transient
# limit on credit reserved by recent requests; its Retry-After is 120 s). Not part of the frozen set: each pass runs the
# frozen run_conc_study4.sh --lane openrouter unchanged, which resumes from the written transcripts. Every restart is
# logged with its time (manual-intervention rule; reported as a deviation). Stops when the block is done, on any
# other failure, or after 3 passes in a row without progress.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
export PATH="$ROOT/.venv/bin:$PATH"
"$ROOT/.venv/bin/python" -B paper-concurrency/study4/src7/gate7.py || exit 3
set -a; [ -f .env ] && . ./.env; set +a
cd paper-concurrency/study4 || exit 1
LOG=results7/study4/openrouter_restarts.log
done_count() { ls results7/study4/n2-openrouter/transcripts 2>/dev/null | wc -l | tr -d ' '; }
stall=0
for pass in $(seq 1 80); do
  before=$(done_count)
  echo "$(date -u +%FT%TZ) pass $pass start: $before transcripts" | tee -a "$LOG"
  PYTHON="$ROOT/.venv/bin/python" bash run_conc_study4.sh --lane openrouter; rc=$?
  after=$(done_count)
  echo "$(date -u +%FT%TZ) pass $pass end: exit $rc, $after transcripts" | tee -a "$LOG"
  [ "$after" -ge 512 ] && { echo "OpenRouter block complete"; exit 0; }
  if ! tail -40 results7/study4/lane_openrouter.log | grep -q 'in_flight_budget_exhausted'; then
    echo "stopped for another reason (exit $rc): not restarting" | tee -a "$LOG"; exit "$rc"
  fi
  if [ "$after" -le "$before" ]; then stall=$((stall + 1)); else stall=0; fi
  [ $stall -ge 3 ] && { echo "no progress in 3 passes: stopping" | tee -a "$LOG"; exit 4; }
  sleep 180
done
exit 4
