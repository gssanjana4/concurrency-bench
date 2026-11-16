#!/usr/bin/env bash
# No-cost rehearsal of the Study 4 run on this Mac with the SAME interpreter the paid run uses (.venv/bin/python).
# Not part of the frozen set. Fake models only: no keys read, no API calls, no money. Then the frozen analysis on the
# dry-run transcripts, compared with the frozen dry-run outputs (analysis7/out).
set -uo pipefail
cd "$(dirname "$0")" || exit 1
[ -x .venv/bin/python ] || { echo "no .venv/bin/python here"; exit 2; }
PY="$(pwd)/.venv/bin/python"
"$PY" -c "import anthropic, sys; print('venv anthropic', anthropic.__version__, 'python', sys.version.split()[0])"
cd paper-concurrency/study4 || exit 1
PYTHON="$PY" bash run_conc_study4.sh --dry-run --base results7/study4_dry_mac; rc=$?
echo "run_conc_study4.sh --dry-run exit $rc"
"$PY" -B analysis7/analyze7.py analyze --base results7/study4_dry_mac --out results7/study4_dry_mac/analysis --allow-dry-run | head -1
"$PY" -c "
import json
a=json.load(open('analysis7/out/results.json')); b=json.load(open('results7/study4_dry_mac/analysis/results.json'))
ka=[(t['id'],t.get('estimate'),t.get('p'),t.get('reject'),t['status']) for t in a['tests']]
kb=[(t['id'],t.get('estimate'),t.get('p'),t.get('reject'),t['status']) for t in b['tests']]
print('tests identical to the frozen dry-run outputs:', ka==kb, '| inputs', a['inputs']['n_files'], b['inputs']['n_files'], '| lists equal', a['inputs']['list_sha256']==b['inputs']['list_sha256'])
print('descriptive identical:', a['descriptive']==b['descriptive'], '| checks ok:', b['checks']['lock_safety']['ok'], b['checks']['signals_only_where_offered']['ok'])
"
diff <(sed 1,4d analysis7/out/numbers.tex) <(sed 1,4d results7/study4_dry_mac/analysis/numbers.tex) > /dev/null && echo "numbers.tex macros identical" || echo "numbers.tex macros DIFFER"
exit $rc
