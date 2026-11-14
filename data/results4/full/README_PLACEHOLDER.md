# PLACEHOLDER: Study 1 data (results4/full) are added from the author's Mac at packaging time

This directory is empty on purpose. The Study 1 run outputs live on the author's Mac
(the repository's `results4/full` folder); the builder copies them here when it is run with
`--results <path to results4/full>` (see tools/make_artifact_v2.py). Until then the Study 1 number pipeline
(`paper/latex/`) cannot be run from this artifact, and `reference_outputs/study1_analysis/` holds the author's
outputs for comparison.

Expected content, exactly as written by the registered Study 1 run (`src4/run_full.sh` through the orchestrators in
`orchestrators_as_run/`; dry-run rehearsal subfolders are optional and only used by the pipeline tests):

```
data/results4/full/
  phase1/results.csv  phase1/spend.jsonl  phase1/failures.jsonl  phase1/transcripts/*.json   (4,608 transcripts)
  phase2/results.csv  phase2/spend.jsonl  phase2/failures.jsonl  phase2/transcripts/*.json   (576 transcripts)
  phase3/results.csv  phase3/spend.jsonl  phase3/failures.jsonl  phase3/transcripts/*.json   (576 transcripts)
  preflight/ok  preflight/spend.jsonl  preflight/gemini_batch_preflight.json  preflight/gemini_batch_ok
  analysis/confirmatory.json  analysis/confirmatory.md  analysis/numbers.json  analysis/tables.md
  run.log  run_batch.log  run_dry.log  run_everything_after.log
  batch_switch_facts.json  batch_switch_facts_gemini.json  batch_switch_facts_latest.json
  phase{1,2,3}/dry_run/  preflight/dry_run/                 (optional: fake-model rehearsal, used by paper/latex/tests)
```

Transcripts include the ledgers; `batch_state/` directories (provider request/response state) are not shipped.
Licence: CC BY 4.0 (see ../../LICENSE.txt), model outputs subject to the providers' terms.
