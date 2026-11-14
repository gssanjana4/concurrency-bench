#!/usr/bin/env bash
# Study 2, step between the probe block and the main analysis (registered at osf.io/zj3an):
# compute eligibility.json from the PROBE transcripts only, with the frozen analysis5/analyze5.py, and print its sha256.
# Reads no episode result. No API calls, no money. Not part of the frozen set.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
[ -f .study2_registered ] || { echo "not registered"; exit 3; }
python3 src5/freeze5.py --check || exit 4
OUT=analysis5/out_study2; mkdir -p "$OUT"
.venv/bin/python analysis5/analyze5.py eligibility --base results5/study2 --out "$OUT" || exit $?
echo "eligibility.json sha256:"; shasum -a 256 "$OUT/eligibility.json"
echo "analyze5.py sha256:"; shasum -a 256 analysis5/analyze5.py
