#!/bin/bash
# Concurrency-paper runner. Start it ONCE in a spare Terminal tab and leave it open:
#     bash ~/Desktop/idempotencybench/tools/autorun_conc.sh
# Claude drops job files into .autorun_conc/queue/; this runs them one at a time, and only if the job is
# exactly "bash run_conc_<name>.sh [--flag ...]" for a script in the repo root. Anything else is rejected.
# Separate from tools/autorun.sh (paper 1), so the two papers never block each other.
# Keys stay in .env and are read by the scripts as usual; this runner never prints them.
# Stop it with Ctrl-C or by closing the tab. Nothing keeps running after that.
cd "$(dirname "$0")/.." || exit 1
ROOT=$(pwd)
B=.autorun_conc; Q=$B/queue; RUN=$B/running; DONE=$B/done; LOGS=$B/logs
mkdir -p "$Q" "$RUN" "$DONE" "$LOGS"
ALLOWED='^bash (run_conc_[a-z0-9_]+\.sh)( --[a-z][a-z0-9-]*)*$'
echo "autorun_conc: watching $ROOT/$Q (Ctrl-C to stop)"
while true; do
  date -u +%Y-%m-%dT%H:%M:%SZ > $B/heartbeat
  for f in "$Q"/*.job; do
    [ -e "$f" ] || continue
    id=$(basename "$f" .job)
    cmd=$(head -n 1 "$f" | tr -d '\r')
    if [[ ! "$cmd" =~ $ALLOWED ]] || [ ! -f "${BASH_REMATCH[1]}" ]; then
      echo "rejected: $cmd" > "$DONE/$id.rejected"; mv "$f" "$DONE/$id.job.rejected"
      echo "$(date '+%H:%M:%S') rejected job $id: $cmd"; continue
    fi
    mv "$f" "$RUN/$id.job"
    echo "$(date '+%H:%M:%S') running job $id: $cmd"
    $cmd > "$LOGS/$id.log" 2>&1; rc=$?
    echo "$rc" > "$DONE/$id.exit"; mv "$RUN/$id.job" "$DONE/$id.job"
    echo "$(date '+%H:%M:%S') job $id finished, exit $rc"
  done
  sleep 10
done
