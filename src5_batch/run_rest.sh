#!/bin/bash
# Rest of the src4 FULL run: same grid, phases, model order and ONE $330 total cap as src4/run_full.sh,
# but claude-sonnet-5 and claude-fable-5 run through the Anthropic Message Batches API and
# openrouter:google/gemini-4-argon-20261013 through the Gemini Batch API (both 50% price) with
# src4_batch/batch_driver.py. Every other model runs with the FROZEN src4/run4.py exactly as run_full.sh
# runs it (same arguments; already-finished episodes are skipped, so a finished model is just verified).
# Gemini: GEMINI_API_KEY in the same .env (needed unless --skip-model openrouter:google/gemini-4-argon-20261013);
# before its first batch run, src4_batch/gemini_preflight.py sends ONE small batch request and stops unless the
# served model version is gemini-4-argon (printed; runs once, marker results4/full/preflight/gemini_batch_ok).
#
# Run from your own Terminal:    bash ~/Desktop/idempotencybench/src4_batch/run_rest.sh
#   Dry run (fake models, no keys, no money):  bash .../src4_batch/run_rest.sh --dry-run [--phase N] [--base DIR]
#
# - Stop run_full.sh first: this script refuses to start while run_full.sh / run4.py / batch_driver.py runs.
# - Same .env (ANTHROPIC_API_KEY, OPENROUTER_API_KEY, plus GEMINI_API_KEY) and .venv as run_full.sh.
# - Resumable: run the same line again. Batch ids are on disk (results4/full/phaseN/batch_state/); a
#   restart collects batches still in flight and never pays twice for a request.
# - Sync models are re-run until all their cells are done (provider failures such as OpenRouter 429 rate
#   limits are retried, never dropped), sleeping 120-180 s between attempts; see run_sync_model below.
# - Order: phase 1, 2, 3; within a phase the registered order
#   qwen, haiku, gpt-5.5 (run4.py), gemini, sonnet-5, fable-5 (batch driver); each model finishes the
#   phase before the next starts, as in run_full.sh. --skip-model ID (repeatable) leaves a model out of this
#   invocation in every phase; run again without it to run that model later.
# - Log: results4/full/run_batch.log (dry run: run_batch_dry.log).
set -uo pipefail

DRY=0; ONLY_PHASE=""; BASE_ARG=""; ALLOW_SYNC=""; SKIP_MODELS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --phase) shift; ONLY_PHASE="${1:-}" ;;
    --base) shift; BASE_ARG="${1:-}" ;;
    --allow-existing-sync) ALLOW_SYNC="--allow-existing-sync" ;;
    --skip-model) shift; SKIP_MODELS="$SKIP_MODELS ${1:-}" ;;
    *) echo "unknown argument $1 (use --dry-run, --phase N, --base DIR, --allow-existing-sync, --skip-model ID)"; exit 1 ;;
  esac
  shift
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
[ -f "$ROOT/src4/run4.py" ] || { echo "cannot find src4/run4.py next to src4_batch/"; exit 1; }
[ -f "$ROOT/src4_batch/batch_driver.py" ] || { echo "cannot find src4_batch/batch_driver.py"; exit 1; }
cd "$ROOT"

# Never run alongside the old runner (or a second copy of this one).
# (pgrep writes to a file: a $(...) subshell would carry this script's own command line and match itself;
#  this script's ancestors, e.g. caffeinate or a wrapper shell, are excluded too.)
ANCESTORS=" $$ "; p=$$
while [ -n "$p" ] && [ "$p" != "1" ] && [ "$p" != "0" ]; do
  p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"; ANCESTORS="$ANCESTORS$p "
done
PIDS_TMP="$(mktemp)"
for pat in 'src4/run_full\.sh' 'src4/run4\.py' 'src4_batch/batch_driver\.py' 'src4_batch/run_rest\.sh'; do
  pgrep -f "$pat" > "$PIDS_TMP" 2>/dev/null
  while read -r pid; do
    if [ -n "$pid" ] && [[ "$ANCESTORS" != *" $pid "* ]]; then
      echo "Refusing to start: a process matching $pat is running (pid $pid). Stop it first."; rm -f "$PIDS_TMP"; exit 1
    fi
  done < "$PIDS_TMP"
done
rm -f "$PIDS_TMP"

BASE="${BASE_ARG:-results4/full}"
mkdir -p "$BASE"
LOCK="$BASE/.run_rest.lock"
mkdir "$LOCK" 2>/dev/null || { echo "Refusing to start: $LOCK exists (another run_rest.sh? remove it if not)"; exit 1; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

LOG="$BASE/run_batch.log"; [ $DRY = 1 ] && LOG="$BASE/run_batch_dry.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== start $(date)  dry_run=$DRY  only_phase=${ONLY_PHASE:-all}  base=$BASE"

MAX_USD=330
MODELS_ORDERED=(
  "openrouter:qwen/qwen3.6-27b-20260422"
  "claude-haiku-4-5-20251001"
  "openrouter:openai/gpt-5.5-20260423"
  "openrouter:google/gemini-4-argon-20261013"
  "claude-sonnet-5"
  "claude-fable-5"
)
GEMINI_MODEL="openrouter:google/gemini-4-argon-20261013"
is_batch_model() { [ "$1" = "claude-sonnet-5" ] || [ "$1" = "claude-fable-5" ] || [ "$1" = "$GEMINI_MODEL" ]; }
is_skipped() { case " $SKIP_MODELS " in *" $1 "*) return 0 ;; esac; return 1; }
ALL_MODELS="$(IFS=,; echo "${MODELS_ORDERED[*]}")"
TASKS="inventory_last_unit,inventory_still_valid,seat_same,ticket_same,transfer_shared_source,budget_write_skew,joint_account_write_skew,budget_control"

PHASES=(1 2 3)
p_agents()  { case $1 in 1) echo 2 ;; 2) echo 4 ;; 3) echo 8 ;; esac; }
p_configs() { case $1 in 1) echo "none,reread_only,cas_available,cas_required,locks,messages" ;; *) echo "none,cas_available,locks" ;; esac; }
p_inst()    { case $1 in 1) echo 4 ;; *) echo 2 ;; esac; }
p_seeds()   { case $1 in 1) echo "0,1" ;; *) echo "0" ;; esac; }

if [ $DRY = 1 ]; then
  PY="${PYTHON:-python3}"; SUB="/dry_run"; DRYFLAG="--dry-run"; RETRY_SLEEP=1
  SYNC_RETRY_MIN="${SYNC_RETRY_MIN:-1}"; SYNC_RETRY_JITTER="${SYNC_RETRY_JITTER:-0}"
else
  set -a; source .env; set +a
  for K in ANTHROPIC_API_KEY OPENROUTER_API_KEY; do
    if [ -z "${!K:-}" ]; then echo "$K missing in .env"; exit 1; fi
  done
  if ! is_skipped "$GEMINI_MODEL" && [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "GEMINI_API_KEY missing in .env (Gemini runs on the Gemini Batch API; or pass --skip-model $GEMINI_MODEL)"; exit 1
  fi
  if [ ! -x .venv/bin/python ]; then
    echo "Setting up .venv (one time)..."
    python3 -m venv .venv && .venv/bin/pip install -q anthropic || { echo "venv setup failed"; exit 1; }
  fi
  .venv/bin/python -c "import anthropic" 2>/dev/null || .venv/bin/pip install -q anthropic || { echo "pip install anthropic failed"; exit 1; }
  PY=.venv/bin/python; SUB=""; DRYFLAG=""; RETRY_SLEEP=60
  SYNC_RETRY_MIN=120; SYNC_RETRY_JITTER=60   # 120-180 s between run4 attempts (OpenRouter 20 req/min limit)
  command -v caffeinate >/dev/null && caffeinate -dimsu -w $$ &
fi
export PYTHONDONTWRITEBYTECODE=1
$PY -c "import anthropic" 2>/dev/null || { echo "the batch driver needs the anthropic SDK in $PY"; exit 1; }

echo "== frozen harness check (src4/FREEZE.md)"
$PY src4_batch/frozen.py || { echo "!! src4 differs from FREEZE.md - not starting"; exit 1; }

echo "== switch facts (for the deviation note)"
$PY src4_batch/switch_facts.py --base "$BASE" --sub "$SUB" $ALLOW_SYNC || exit 1

PREFLIGHT_LOG="$BASE/preflight$SUB/spend.jsonl"
ALL_SPEND="$PREFLIGHT_LOG"
# Sync models (OpenRouter + Haiku): the FROZEN run4.py with run_full.sh's exact arguments, re-invoked until
# every cell of the model is done. run4 stops after 3 consecutive provider failures (e.g. OpenRouter 429 rate
# limits); those episodes are in failures.jsonl and are simply run again on the next attempt (resume skips
# finished ones), so rate-limited episodes are retried, never dropped. No low attempt cap: it stops on the
# cost cap (exit 2), a credit/key limit or HTTP 402 (run4 exit 4), a refusal (exit 1), or after
# SYNC_MAX_IDLE (10) attempts in a row that finish no episode (exit 3; rerun to continue).
SYNC_RUNNER="${SYNC_RUNNER:-src4/run4.py}"   # test hook only; the real run always uses the frozen run4.py
SYNC_MAX_IDLE="${SYNC_MAX_IDLE:-10}"
cells_done() {  # phase model -> "done total"
  $PY src4_batch/cells_done.py --model "$2" --out "$BASE/phase$1$SUB" "${COMMON[@]}"
}
n_failures() { [ -f "$1" ] && wc -l < "$1" | tr -d ' ' || echo 0; }
run_sync_model() {
  local ph=$1 model=$2 attempt=0 idle=0 status before after total fails
  read -r before total < <(cells_done "$ph" "$model")
  while :; do
    attempt=$((attempt + 1))
    fails=$(n_failures "$BASE/phase$ph$SUB/failures.jsonl")
    echo "== phase $ph  model $model  [sync run4]  attempt $attempt  done $before/$total  failures.jsonl lines $fails  $(date)"
    $PY "$SYNC_RUNNER" --models "$model" "${COMMON[@]}" --max-usd "$MAX_USD" \
      --extra-spend-logs "$ALL_SPEND" --out "$BASE/phase$ph" $DRYFLAG
    status=$?
    read -r after total < <(cells_done "$ph" "$model")
    echo "   attempt $attempt: run4 exit $status; episodes done $before -> $after of $total; failures.jsonl lines $(n_failures "$BASE/phase$ph$SUB/failures.jsonl")"
    case $status in
      2) echo "!! \$$MAX_USD total cost cap reached in phase $ph ($model) - stopping. Completed episodes are kept."
         skipped_from "$((ph + 1))"; exit 2 ;;
      4) echo "!! OpenRouter credit/key limit (402) reached - stopping (phase $ph, $model)."; exit 4 ;;
      1) echo "!! run4.py refused to run (see message above)"; exit 1 ;;
    esac
    if [ "$after" -ge "$total" ]; then echo "   phase $ph $model: all $total episodes done"; return 0; fi
    if [ "$status" = 0 ]; then echo "!! run4 exited 0 with $after/$total done - unexpected; stopping"; exit 1; fi
    if [ "$after" -gt "$before" ]; then idle=0; else idle=$((idle + 1)); fi
    if [ "$idle" -ge "$SYNC_MAX_IDLE" ]; then
      echo "!! phase $ph, $model: $idle attempts in a row finished no episode - stopping; rerun this script to continue"
      exit 3
    fi
    before=$after
    local wait=$SYNC_RETRY_MIN
    [ "$SYNC_RETRY_JITTER" -gt 0 ] && wait=$((SYNC_RETRY_MIN + RANDOM % (SYNC_RETRY_JITTER + 1)))
    echo "   provider failures (rate limit?) - retrying in ${wait}s (attempts without progress: $idle/$SYNC_MAX_IDLE)"
    sleep "$wait"
  done
}

# Batch models: the batch driver, with run_full.sh's 5-attempt retry handling.
run_batch_model() {
  local ph=$1 model=$2 attempt status
  if [ "$model" = "$GEMINI_MODEL" ]; then
    $PY src4_batch/switch_facts.py --base "$BASE" --sub "$SUB" --record-gemini $ALLOW_SYNC || exit 1
    echo "== Gemini batch preflight (one small batch request; once)"
    $PY src4_batch/gemini_preflight.py --base "$BASE" --sub "$SUB" $DRYFLAG \
      || { echo "!! Gemini batch preflight failed - Gemini not started (see above)"; exit 1; }
  else
    $PY src4_batch/switch_facts.py --base "$BASE" --sub "$SUB" --record $ALLOW_SYNC || exit 1
  fi
  for attempt in 1 2 3 4 5; do
    echo "== phase $ph  model $model  [batch]  (attempt $attempt)  $(date)"
    $PY src4_batch/batch_driver.py --models "$model" "${COMMON[@]}" --max-usd "$MAX_USD" \
      --extra-spend-logs "$ALL_SPEND" --out "$BASE/phase$ph" $DRYFLAG
    status=$?
    case $status in
      0) return 0 ;;
      2) echo "!! \$$MAX_USD total cost cap reached in phase $ph ($model) - stopping. Completed episodes are kept."
         skipped_from "$((ph + 1))"; exit 2 ;;
      1) echo "!! batch driver refused to run (see message above)"; exit 1 ;;
      *) echo "   provider failures (exit $status); retrying in ${RETRY_SLEEP}s (completed episodes and paid batch results are kept)"; sleep "$RETRY_SLEEP" ;;
    esac
  done
  echo "!! phase $ph, $model still failing after 5 attempts - see $BASE/phase$ph$SUB/failures.jsonl; rerun this script to retry"
  exit 3
}

for ph in "${PHASES[@]}"; do ALL_SPEND="$ALL_SPEND,$BASE/phase$ph$SUB/spend.jsonl"; done

echo "== preflight (all six models)"
mkdir -p "$(dirname "$PREFLIGHT_LOG")"
if [ -f "$BASE/preflight$SUB/ok" ]; then
  echo "   already passed earlier ($(cat "$BASE/preflight$SUB/ok")); not repeated"
else
  $PY src4/preflight.py --models "$ALL_MODELS" --spend-log "$PREFLIGHT_LOG" $DRYFLAG \
    || { echo "!! preflight failed - not started (see above)"; exit 1; }
  date > "$BASE/preflight$SUB/ok"
fi

skipped_from() {
  local start=$1 s="" q
  for q in "${PHASES[@]}"; do [ "$q" -ge "$start" ] && s="$s phase$q"; done
  echo "!! NOT RUN:$s"
}

for ph in "${PHASES[@]}"; do
  if [ -n "$ONLY_PHASE" ] && [ "$ph" != "$ONLY_PHASE" ]; then continue; fi
  OUT="$BASE/phase$ph"
  COMMON=(--configs "$(p_configs "$ph")" --aware both --tasks "$TASKS" --instances "$(p_inst "$ph")"
          --seeds "$(p_seeds "$ph")" --agents "$(p_agents "$ph")")
  $PY src4/plan_full.py --phase "$ph" --models "$ALL_MODELS" "${COMMON[@]}" --out "$OUT$SUB" \
    --max-usd "$MAX_USD" --spend-logs "$ALL_SPEND"
  case $? in
    0) ;;
    5) skipped_from "$ph"; echo "=== STOPPED before phase $ph (budget) $(date)"; exit 2 ;;
    *) echo "!! plan_full.py failed"; exit 1 ;;
  esac
  for model in "${MODELS_ORDERED[@]}"; do
    if is_skipped "$model"; then echo "   phase $ph $model: SKIPPED this invocation (--skip-model)"; continue; fi
    if is_batch_model "$model"; then
      run_batch_model "$ph" "$model"
    else
      run_sync_model "$ph" "$model"
    fi
  done
  echo "=== phase $ph done $(date). Results in $OUT$SUB/results.csv"
done
echo "=== FULL RUN DONE $(date). Analyse with:"
echo "    $PY src4/analyze4.py $BASE/phase1$SUB/results.csv $BASE/phase2$SUB/results.csv $BASE/phase3$SUB/results.csv --out $BASE/analysis$SUB"
exit 0
