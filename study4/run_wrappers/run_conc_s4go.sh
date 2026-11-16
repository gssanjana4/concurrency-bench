#!/usr/bin/env bash
# Study 4 paid run, started by the autorun_conc queue. Not part of the frozen set: it only wraps the frozen
# paper-concurrency/study4/run_conc_study4.sh, which refuses unless src7/gate7.py confirms the archived registration.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"
[ -x .venv/bin/python ] || { echo "no .venv/bin/python here"; exit 2; }
export PATH="$ROOT/.venv/bin:$PATH"
"$ROOT/.venv/bin/python" -B paper-concurrency/study4/src7/gate7.py || { echo "Study 4 registration not confirmed: refusing to spend."; exit 3; }
set -a; [ -f .env ] && . ./.env; set +a
cd paper-concurrency/study4 || exit 1
PYTHON="$ROOT/.venv/bin/python" bash run_conc_study4.sh
rc=$?
echo "run_conc_study4.sh exit $rc"
exit "$rc"
