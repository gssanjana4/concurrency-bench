#!/bin/bash
# Concurrency benchmark (src4) FULL runs: six models, three phases, ONE total cap.
# Run from your own Terminal:   bash ~/Desktop/idempotencybench/src4/run_full.sh
#   Dry run (fake provider, no keys, no money):   bash .../src4/run_full.sh --dry-run [--phase 1]
#
# - Needs ANTHROPIC_API_KEY and OPENROUTER_API_KEY in <repo>/.env (not for --dry-run).
# - Resumable: if it stops (sleep, crash, Ctrl-C, cap), run the same line again.
#   Finished episodes are kept; all spend so far still counts toward the cap.
# - Money: ONE hard cap of $MAX_USD over everything this script spends (preflight + all
#   phases; spend logs are per output dir and are summed). Total budget $350, pilot spent $1.60.
# - Before each phase it prints the grid size and the estimated cost, and stops BEFORE the
#   phase if the budget left is below that estimate.
# - Writes ONLY to results4/full/ (dry runs: results4/full/*/dry_run/).
#
# Phase 1: n=2, all 6 configs, aware off+on together, 8 templates x 4 instances, seeds 0,1
# Phase 2: n=4, configs none,cas_available,locks, aware off+on together, 8 templates x 2 instances
#          (14 contended + 2 budget_control), seed 0
# Phase 3: n=8, same as phase 2
# Within a phase, models run in the fixed registered order of MODELS_ORDERED (Fable 5 last);
# each model finishes the phase before the next starts.
set -uo pipefail

DRY=0; ONLY_PHASE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --phase) shift; ONLY_PHASE="${1:-}" ;;
    *) echo "unknown argument $1 (use --dry-run, --phase N)"; exit 1 ;;
  esac
  shift
done

# Repo root = the directory that contains src4/run4.py (this script lives in src4/).
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
[ -f "$ROOT/src4/run4.py" ] || { echo "cannot find src4/run4.py next to this script"; exit 1; }
cd "$ROOT"

BASE="results4/full"
mkdir -p "$BASE"
LOG="$BASE/run.log"; [ $DRY = 1 ] && LOG="$BASE/run_dry.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== start $(date)  dry_run=$DRY  only_phase=${ONLY_PHASE:-all}"

MAX_USD=330
# Requested ids in the registered run order (PREREGISTRATION.md; analyze4.REGISTERED_MODELS, tested).
# Haiku: the dated id the pilot used. claude-sonnet-5 / claude-fable-5 are undated aliases resolved
# server-side; the served id is recorded per completion (model_served).
MODELS_ORDERED=(
  "openrouter:qwen/qwen3.6-27b-20260422"
  "claude-haiku-4-5-20251001"
  "openrouter:openai/gpt-5.5-20260423"
  "openrouter:google/gemini-4-argon-20261013"
  "claude-sonnet-5"
  "claude-fable-5"
)
ALL_MODELS="$(IFS=,; echo "${MODELS_ORDERED[*]}")"
TASKS="inventory_last_unit,inventory_still_valid,seat_same,ticket_same,transfer_shared_source,budget_write_skew,joint_account_write_skew,budget_control"

PHASES=(1 2 3)
declare -A P_AGENTS=([1]=2 [2]=4 [3]=8)
declare -A P_CONFIGS=([1]="none,reread_only,cas_available,cas_required,locks,messages" [2]="none,cas_available,locks" [3]="none,cas_available,locks")
declare -A P_INST=([1]=4 [2]=2 [3]=2)
declare -A P_SEEDS=([1]="0,1" [2]="0" [3]="0")

if [ $DRY = 1 ]; then
  PY=python3; SUB="/dry_run"; DRYFLAG="--dry-run"; RETRY_SLEEP=1
else
  set -a; source .env; set +a
  for K in ANTHROPIC_API_KEY OPENROUTER_API_KEY; do
    if [ -z "${!K:-}" ]; then echo "$K missing in .env"; exit 1; fi
  done
  # Private Python env with the one dependency (anthropic SDK).
  if [ ! -x .venv/bin/python ]; then
    echo "Setting up .venv (one time)..."
    python3 -m venv .venv && .venv/bin/pip install -q anthropic || { echo "venv setup failed"; exit 1; }
  fi
  .venv/bin/python -c "import anthropic" 2>/dev/null || .venv/bin/pip install -q anthropic || { echo "pip install anthropic failed"; exit 1; }
  PY=.venv/bin/python; SUB=""; DRYFLAG=""; RETRY_SLEEP=60
  # Keep the Mac awake while this script runs (macOS).
  command -v caffeinate >/dev/null && caffeinate -dimsu -w $$ &
fi

PREFLIGHT_LOG="$BASE/preflight$SUB/spend.jsonl"
# Every spend log that counts toward the one cap.
ALL_SPEND="$PREFLIGHT_LOG"
for ph in "${PHASES[@]}"; do ALL_SPEND="$ALL_SPEND,$BASE/phase$ph$SUB/spend.jsonl"; done

echo "== preflight (all six models)"
mkdir -p "$(dirname "$PREFLIGHT_LOG")"
if [ -f "$BASE/preflight$SUB/ok" ]; then
  echo "   already passed earlier ($(cat "$BASE/preflight$SUB/ok")); not repeated"
else
  $PY src4/preflight.py --models "$ALL_MODELS" --spend-log "$PREFLIGHT_LOG" $DRYFLAG \
    || { echo "!! preflight failed - full run not started (see above)"; exit 1; }
  date > "$BASE/preflight$SUB/ok"
fi

skipped_from() {  # print the phases not run, starting at $1
  local start=$1 s="" q
  for q in "${PHASES[@]}"; do [ "$q" -ge "$start" ] && s="$s phase$q"; done
  echo "!! NOT RUN:$s"
}

for ph in "${PHASES[@]}"; do
  if [ -n "$ONLY_PHASE" ] && [ "$ph" != "$ONLY_PHASE" ]; then continue; fi
  OUT="$BASE/phase$ph"
  COMMON=(--configs "${P_CONFIGS[$ph]}" --aware both --tasks "$TASKS" --instances "${P_INST[$ph]}"
          --seeds "${P_SEEDS[$ph]}" --agents "${P_AGENTS[$ph]}")
  $PY src4/plan_full.py --phase "$ph" --models "$ALL_MODELS" "${COMMON[@]}" --out "$OUT$SUB" \
    --max-usd "$MAX_USD" --spend-logs "$ALL_SPEND"
  case $? in
    0) ;;
    5) skipped_from "$ph"; echo "=== STOPPED before phase $ph (budget) $(date)"; exit 2 ;;
    *) echo "!! plan_full.py failed"; exit 1 ;;
  esac
  for model in "${MODELS_ORDERED[@]}"; do
    done_model=0
    for attempt in 1 2 3 4 5; do
      echo "== phase $ph  model $model  (attempt $attempt)  $(date)"
      $PY src4/run4.py --models "$model" "${COMMON[@]}" --max-usd "$MAX_USD" \
        --extra-spend-logs "$ALL_SPEND" --out "$OUT" $DRYFLAG
      status=$?
      case $status in
        0) done_model=1; break ;;
        2) echo "!! \$$MAX_USD total cost cap reached in phase $ph ($model) - stopping. Completed episodes are kept."
           skipped_from "$((ph + 1))"; exit 2 ;;
        4) echo "!! OpenRouter credit/key limit reached - stopping (phase $ph, $model)."; exit 4 ;;
        1) echo "!! run4.py refused to run (see message above)"; exit 1 ;;
        *) echo "   provider failures (exit $status); retrying in ${RETRY_SLEEP}s (completed episodes are kept)"; sleep "$RETRY_SLEEP" ;;
      esac
    done
    if [ $done_model = 0 ]; then
      echo "!! phase $ph, $model still failing after 5 attempts - see $OUT$SUB/failures.jsonl; rerun this script to retry"
      exit 3
    fi
  done
  echo "=== phase $ph done $(date). Results in $OUT$SUB/results.csv"
done
echo "=== FULL RUN DONE $(date). Analyse with:"
echo "    $PY src4/analyze4.py $BASE/phase1$SUB/results.csv $BASE/phase2$SUB/results.csv $BASE/phase3$SUB/results.csv --out $BASE/analysis$SUB"
exit 0
