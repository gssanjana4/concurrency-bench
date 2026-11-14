# PLACEHOLDER: the exploratory SQL-slice results (results_sql) are added from the author's Mac at packaging time

This directory is empty on purpose. The SQL slice (post hoc, not pre-registered; code in `src_sql/`) wrote its
outputs on the author's Mac (the repository's `results_sql` folder); the builder copies them here when it is run with
`--results-sql <path to results_sql>` (see tools/make_artifact_v2.py).

Expected content:

```
data/results_sql/
  results.csv  agents.csv  spend.jsonl  run.log  preflight_ok
  transcripts/*.json                     (128 transcripts)
  dbs/*.sqlite                           (one SQLite database per episode)
  analysis/numbers.json  analysis/tables.md  analysis/tables_appendix.tex
  dry_run/                               (optional: fake-model rehearsal)
```

The Study 1 pipeline reads it through `RESULTS_SQL=<artifact>/data/results_sql` (paper/latex/posthoc_review.py,
make_numbers4.py). Licence: CC BY 4.0 (see ../LICENSE.txt), model outputs subject to the providers' terms.
