#!/bin/bash
# Starts the concurrency-paper job runner (tools/autorun_conc.sh) in the background and returns at once,
# so it never blocks paper 1's runner. Safe to run twice: does nothing if it is already running.
cd "$(dirname "$0")" || exit 1
mkdir -p .autorun_conc
if pgrep -f "tools/autorun_conc.sh" >/dev/null; then echo "autorun_conc already running"; exit 0; fi
nohup bash tools/autorun_conc.sh >> .autorun_conc/runner.log 2>&1 < /dev/null &
disown
echo "autorun_conc started, pid $!"
