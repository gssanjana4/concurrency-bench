#!/usr/bin/env bash
# Study 2 paid run, started by the autorun_conc queue. Not part of the frozen set: it only wraps the frozen
# run_conc_study2.sh with the registered OpenRouter balance log (balance5.py before/after).
# Refuses to start unless .study2_registered exists (written only after the OSF registration is confirmed).
set -uo pipefail
cd "$(dirname "$0")" || exit 1
[ -f .study2_registered ] || { echo "Study 2 is not registered yet: refusing to spend."; exit 3; }
set -a; [ -f .env ] && . ./.env; set +a
mkdir -p results5/study2
python3 src5/freeze5.py --check || { echo "freeze check failed: refusing to spend"; exit 4; }
python3 analysis5/balance5.py --base results5/study2 --phase before
bash run_conc_study2.sh
rc=$?
python3 analysis5/balance5.py --base results5/study2 --phase after --lane-exit "$rc"
echo "run_conc_study2.sh exit $rc"
exit "$rc"
