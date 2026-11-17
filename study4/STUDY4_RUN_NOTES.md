# Study 4 run notes (manual interventions and anything else the paper must report)

- 2026-11-16 16:03Z: paid run started (job 009_s4go).
- 16:48Z: OpenRouter lane stopped after 80 of 512 Qwen episodes: HTTP 402 "in_flight_budget_exhausted" (OpenRouter's
  limit on credit reserved by in-flight requests; the key still had $9.92). The frozen script treats any 402 as a credit
  stop. One episode failed and was not written.
- 16:53Z: Anthropic lane stopped: the batch driver got HTTP 404 retrieving batch msgbatch_01KJXyyzxRCbrbcxSJv5GrdZ right
  after creating it (Haiku, 389 of 512 episodes written). A free GET at 18:10Z shows the batch exists and ended with
  123/123 succeeded: a transient API error.
- 18:10Z: both are a crash or a credit stop under the plan's manual-intervention rule; the run was restarted unchanged
  (job 011_s4go2; the script resumes from the written transcripts and the batch state).
- Seeing results (deviation): reading the Anthropic lane log for the error showed its last ~17 per-episode lines
  of Haiku, which print each episode's outcome and fs. Nothing was decided from them; the restart
  is required by the plan regardless. Reported as a deviation.
- 18:10Z: the restarted OpenRouter lane hit the same 402 after one episode. OpenRouter's documentation: the in-flight
  budget is a fraction of the balance (accounts with a low balance), counts running and recently completed requests,
  and clears after Retry-After (120 s). The frozen run7 stops the lane on any 402. Fix without touching frozen code:
  job 012 (run_conc_s4or.sh) reruns the frozen script with --lane openrouter, waiting 180 s after each such stop, and
  logs every restart (results7/study4/openrouter_restarts.log). It starts after job 011 (Anthropic lane) ends, since
  the Mac runner takes one job at a time. Episodes cut by a 402 are not written and are rerun (registered rule for
  provider failures). The OpenRouter lane will therefore finish after the Anthropic lane; visit order within the block
  is unchanged.
- 21:36Z: Fable stage rule (src7/floor_gate7.py): 128/128 stage-1 episodes, decision "floor": stage 2 not run
  (registered rule). Anthropic lane done 21:36Z (exit 0): Haiku 512, Sonnet 512, Fable 128.
- 21:36-21:47Z: job 012 (OpenRouter restarts): 4 passes, 1 more Qwen episode (82 of 512). The last 402 was
  "openrouter_credits": the OpenRouter account balance was exhausted (GET /api/v1/credits: total credits $190, usage
  $190.15, balance -$0.15). The "$9.92 remaining" logged by balance7 was the key's limit, not the account balance; the
  cost plan assumed $9.50 of OpenRouter credit that did not exist (planning error). The earlier "in-flight budget"
  402s were the same low balance.
- 2026-11-16 ~22:50Z: the author chose not to add credit. The Qwen block stops at 82 episodes (a cap-like stop before
  any analysis): Qwen's tests have fewer than 96 clusters and are "not tested" under the registered rule; the pooled
  tests use the models whose own tests run. Decided before any analysis was run or any summary opened.
- Python for the analysis: Python 3.10.12 in a Linux VM on the run machine (version recorded in the analysis log).
- After the analysis (exploratory, not registered): `paper7/qwen_exploratory7.py` computes the plan's contrasts on
  the 20 Qwen clusters that have all four configs (instances 0 and 1 of every family, and four families of instance 2),
  with exact sign-flip p values and no adjustment. The paper labels it exploratory.
