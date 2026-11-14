# Orchestrator scripts exactly as run on the author's Mac (Study 1)

Copied from ~/Desktop/idempotencybench on 2026-11-03 after the run. SHA256SUMS lists their hashes.
These scripts were not part of the frozen src4 set (see deviations.csv: the frozen run_full.sh could not run on the
Mac's bash, so phases ran through these). run_rest.sh and run_rest_v2.sh are byte-identical (the --skip-model
version); run_rest_next.sh added Gemini batch support; run_everything_after.sh chained run_rest_next.sh and the SQL slice.
The deviations table's orchestrator-hash rows must use these hashes, and make_anon_artifact.py must ship this folder.
