#!/usr/bin/env bash
# No-cost rehearsal of the Study 2 run on this Mac with the SAME interpreter the paid run uses (.venv/bin/python).
# Not part of the frozen set. Fake models only: no keys read, no API calls, no money.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "no .venv/bin/python here"; exit 2; }
.venv/bin/python -c "import anthropic, sys; print('venv anthropic', anthropic.__version__, 'python', sys.version.split()[0])"
PYTHON=.venv/bin/python bash run_conc_study2.sh --dry-run --base results5/study2_dry_mac
