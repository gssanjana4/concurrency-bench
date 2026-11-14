#!/bin/bash
# Study 2 (corrected harness, src5) runner for the author's Mac. Same autorun pattern as src4_batch/run_rest.sh:
# refuses to run twice, keeps the Mac awake, logs everything, retries until done, resumes where it stopped,
# and never spends past the caps -- here one cap PER PROVIDER (prepaid credit) plus a total:
#
#     Anthropic  $19   (Haiku, Sonnet, Fable: all through the Message Batches API)
#     OpenRouter $28   (Qwen, GPT-5.5: sync; the key is shared with Paper 1, so this leaves headroom)
#     Gemini     $22   (Gemini 4 Argon: Google Gemini Batch API)
#     total      $69
#   (override: STUDY2_CAP_ANTHROPIC=.. STUDY2_CAP_OPENROUTER=.. STUDY2_CAP_GEMINI=.. STUDY2_CAP_TOTAL=..)
#
# Run from your own Terminal, in the repo root (~/Desktop/idempotencybench):
#     bash run_conc_study2.sh                      # real run (needs .env with the three keys)
#     bash run_conc_study2.sh --dry-run            # fake models, no keys, no money (rehearsal of the whole grid)
#     bash run_conc_study2.sh --lane anthropic     # only one provider lane (anthropic | openrouter | gemini)
#     bash run_conc_study2.sh --sequential         # lanes one after another instead of in parallel
#   (macOS /bin/bash is 3.2: empty arrays are expanded as ${arr[@]+"${arr[@]}"} so `set -u` does not abort)
#
# What it does
#   1. Checks src5/FREEZE.md (every frozen file unchanged: src5/*.py|*.json, src5_batch/*.py|*.json|*.sh,
#      src5_verify/dry_check5.py and this script) and runs the reference-policy validity gate
#      (src5/validity5.py; scripted agents, no cost, ~30 s): it must pass, else nothing is spent.
#   2. Preflight (once): one tiny sync request per non-Gemini model, one tiny Gemini batch request.
#   3. Runs the grid in src5/plan_study2.json (src5/plan5.py chose it to fit the caps) in three provider lanes,
#      in parallel by default (each provider has its own cap, so lanes cannot overspend each other); the Gemini
#      lane starts first (and runs first with --sequential): its batch price doubles from 2026-11-30T00:00Z:
#        gemini    : batch driver, probes, core (aware off), then locks/all_available aware off+on
#        anthropic : batch driver, Haiku -> Sonnet -> Fable core blocks, then extensions
#        openrouter: run5.py sync, Qwen -> GPT-5.5 core, then extensions
#      Inside a block every contended episode is followed by its matched control and the two are admitted
#      together, so a cost-cap stop falls between pairs (never a contended cell without its control).
#      Priority inside a lane (V2 grid): 0 first-reply probes (one completion per agent, nothing executed),
#      1 core (n=2, 4 configs x contended+controls; Gemini aware on for locks/all_available interleaved with
#      aware off in the same batches), 4 extensions (bigger grids for GPT/Fable) -- each started only while money
#      is left.
#      A core block has a per-model sub-cap (1.3 x its estimate) so one model cannot eat another's core.
#   4. Sync models are re-run until every cell is done (rate limits are retried, never dropped); batch models
#      get 5 attempts per block (paid batch results are kept across attempts and reruns).
#   5. Writes results5/study2/summary.md (descriptive) at the end.
#   6. --dry-run only: a channel rehearsal with the labelled peer-informed config (all_peer_informed: CAS + locks +
#      messages; never in the paid grid) and src5_verify/dry_check5.py over every dry-run transcript (the fake
#      model locks and messages, so the control-disjointness check exercises the lock-token and message channels).
# Outputs: results5/study2/n<agents>-<provider>/ (transcripts/, results.csv, spend.jsonl, failures.jsonl,
# batch_state/), one directory per lane so parallel lanes never write the same file.
# Resumable: run the same line again. Logs: results5/study2/run_study2.log and lane_<provider>.log.
set -uo pipefail

DRY=0; BASE_ARG=""; ONLY_LANE=""; SEQUENTIAL=0; PLAN_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --base) shift; BASE_ARG="${1:-}" ;;
    --lane) shift; ONLY_LANE="${1:-}" ;;
    --sequential) SEQUENTIAL=1 ;;
    --plan) shift; PLAN_ARG="${1:-}" ;;
    *) echo "unknown argument $1 (use --dry-run, --base DIR, --lane NAME, --sequential, --plan FILE)"; exit 1 ;;
  esac
  shift
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
for f in src5/run5.py src5_batch/batch_driver.py src5/plan5.py; do
  [ -f "$f" ] || { echo "cannot find $f under $ROOT"; exit 1; }
done
PLAN="${PLAN_ARG:-src5/plan_study2.json}"
[ -f "$PLAN" ] || { echo "no plan file $PLAN (make one: python3 src5/plan5.py --plan $PLAN)"; exit 1; }

# Never run alongside another runner or driver (ancestors of this script excluded; see run_rest.sh).
ANCESTORS=" $$ "; p=$$
while [ -n "$p" ] && [ "$p" != "1" ] && [ "$p" != "0" ]; do
  p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"; ANCESTORS="$ANCESTORS$p "
done
PIDS_TMP="$(mktemp)"
for pat in 'run_conc_study2\.sh' 'src5/run5\.py' 'src5_batch/batch_driver\.py' 'src4_batch/run_rest\.sh' 'src4/run_full\.sh'; do
  pgrep -f "$pat" > "$PIDS_TMP" 2>/dev/null
  while read -r pid; do
    if [ -n "$pid" ] && [[ "$ANCESTORS" != *" $pid "* ]]; then
      echo "Refusing to start: a process matching $pat is running (pid $pid). Stop it first."; rm -f "$PIDS_TMP"; exit 1
    fi
  done < "$PIDS_TMP"
done
rm -f "$PIDS_TMP"

BASE="${BASE_ARG:-results5/study2}"
mkdir -p "$BASE"
LOCK="$BASE/.run_study2.lock"
mkdir "$LOCK" 2>/dev/null || { echo "Refusing to start: $LOCK exists (another run? remove it if not)"; exit 1; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
LOG="$BASE/run_study2.log"; [ $DRY = 1 ] && LOG="$BASE/run_study2_dry.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== start $(date)  dry_run=$DRY  lane=${ONLY_LANE:-all}  base=$BASE  plan=$PLAN"

CAP_ANTHROPIC="${STUDY2_CAP_ANTHROPIC:-19}"; CAP_OPENROUTER="${STUDY2_CAP_OPENROUTER:-28}"
CAP_GEMINI="${STUDY2_CAP_GEMINI:-22}"; CAP_TOTAL="${STUDY2_CAP_TOTAL:-69}"
CAPS=(--max-usd "$CAP_TOTAL" --family-cap "anthropic=$CAP_ANTHROPIC" --family-cap "openrouter=$CAP_OPENROUTER"
      --family-cap "gemini=$CAP_GEMINI")
echo "   caps: anthropic \$$CAP_ANTHROPIC, openrouter \$$CAP_OPENROUTER, gemini \$$CAP_GEMINI, total \$$CAP_TOTAL"

if [ $DRY = 1 ]; then
  PY="${PYTHON:-python3}"; SUB="/dry_run"; DRYFLAG="--dry-run"; RETRY_SLEEP=1
  SYNC_RETRY_MIN="${SYNC_RETRY_MIN:-1}"; SYNC_RETRY_JITTER="${SYNC_RETRY_JITTER:-0}"
else
  [ -f .env ] || { echo ".env missing (ANTHROPIC_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY)"; exit 1; }
  set -a; source .env; set +a
  for K in ANTHROPIC_API_KEY OPENROUTER_API_KEY GEMINI_API_KEY; do
    if [ -z "${!K:-}" ]; then echo "$K missing in .env"; exit 1; fi
  done
  if [ ! -x .venv/bin/python ]; then
    echo "Setting up .venv (one time)..."
    python3 -m venv .venv && .venv/bin/pip install -q anthropic || { echo "venv setup failed"; exit 1; }
  fi
  .venv/bin/python -c "import anthropic" 2>/dev/null || .venv/bin/pip install -q anthropic || { echo "pip install anthropic failed"; exit 1; }
  PY=.venv/bin/python; SUB=""; DRYFLAG=""; RETRY_SLEEP=60
  SYNC_RETRY_MIN=120; SYNC_RETRY_JITTER=60
  command -v caffeinate >/dev/null && caffeinate -dimsu -w $$ &
fi
export PYTHONDONTWRITEBYTECODE=1
$PY -c "import anthropic" 2>/dev/null || { echo "the batch driver needs the anthropic SDK in $PY"; exit 1; }

echo "== harness check (src5/FREEZE.md: src5, src5_batch, src5_verify/dry_check5.py, run_conc_study2.sh)"
$PY src5/freeze5.py --check || { echo "!! a frozen file differs from src5/FREEZE.md - not starting"; exit 1; }
echo "== reference-policy validity gate (scripted agents, no cost)"
if [ -f "$BASE/validity$SUB/ok" ]; then
  echo "   passed earlier ($(cat "$BASE/validity$SUB/ok"))"
else
  $PY src5/validity5.py --out "$BASE/validity$SUB" > "$BASE/validity_run.log" 2>&1 \
    || { echo "!! validity gate failed - see $BASE/validity_run.log; nothing was spent"; exit 1; }
  tail -1 "$BASE/validity_run.log"; date > "$BASE/validity$SUB/ok"
fi

PREF="$BASE/preflight$SUB"; mkdir -p "$PREF"
ALL_SPEND="$PREF/spend.jsonl"
for nn in 2 4; do for fm in anthropic openrouter gemini; do ALL_SPEND="$ALL_SPEND,$BASE/n$nn-$fm$SUB/spend.jsonl"; done; done
for fm in anthropic openrouter gemini; do ALL_SPEND="$ALL_SPEND,$BASE/probe-$fm$SUB/spend.jsonl"; done
GEMINI_MODEL="openrouter:google/gemini-4-argon-20261013"
echo "== preflight"
if [ -f "$PREF/ok" ]; then
  echo "   passed earlier ($(cat "$PREF/ok"))"
else
  $PY src5/preflight5.py --models "openrouter:qwen/qwen3.6-27b-20260422,claude-haiku-4-5-20251001,openrouter:openai/gpt-5.5-20260423,claude-sonnet-5,claude-fable-5" \
    --spend-log "$PREF/spend.jsonl" $DRYFLAG || { echo "!! preflight failed - not started"; exit 1; }
  $PY src5_batch/gemini_preflight.py --base "$BASE" --sub "$SUB" $DRYFLAG || { echo "!! Gemini batch preflight failed"; exit 1; }
  date > "$PREF/ok"
fi

is_batch_model() { case "$1" in claude-*|"$GEMINI_MODEL") return 0 ;; esac; return 1; }

# block runner: prio family model n configs tasks instances seeds aware model_cap mode
run_block() {
  local prio=$1 fam=$2 model=$3 n=$4 configs=$5 tasks=$6 inst=$7 seeds=$8 aware=$9 mcap=${10} mode=${11:-episodes}
  local out="$BASE/n$n-$fam" status attempt idle=0 before after total  # one directory per lane: no shared files
  local pf=(); [ "$mode" = "probe" ] && { pf=(--probe); out="$BASE/probe-$fam"; }
  local common=(--models "$model" --configs "$configs" --tasks "$tasks" --instances "$inst" --seeds "$seeds"
                --agents "$n" --aware "$aware" ${pf[@]+"${pf[@]}"})
  local mc=(); [ "$mcap" != "-" ] && mc=(--model-cap "$mcap")
  echo "== [$fam] prio $prio  $mode  $model  n=$n aware=$aware  $tasks  inst=$inst seeds=$seeds  model cap ${mcap}  $(date)"
  if is_batch_model "$model"; then
    for attempt in 1 2 3 4 5; do
      $PY src5_batch/batch_driver.py "${common[@]}" "${CAPS[@]}" ${mc[@]+"${mc[@]}"} --extra-spend-logs "$ALL_SPEND" --out "$out" $DRYFLAG
      status=$?
      case $status in
        0) return 0 ;;
        2) echo "   [$fam] cost cap reached for this block (family, total or model sub-cap); moving on"; return 2 ;;
        1) echo "!! [$fam] batch driver refused (see above)"; return 1 ;;
        *) echo "   [$fam] provider failures (exit $status), attempt $attempt; retrying in ${RETRY_SLEEP}s"; sleep "$RETRY_SLEEP" ;;
      esac
    done
    echo "!! [$fam] $model still failing after 5 attempts; rerun this script to retry"; return 3
  fi
  read -r before total < <($PY src5_batch/cells_done.py --model "$model" --out "$out$SUB" --configs "$configs" --aware "$aware" \
                             --tasks "$tasks" --instances "$inst" --seeds "$seeds" --agents "$n" ${pf[@]+"${pf[@]}"})
  attempt=0
  while :; do
    attempt=$((attempt + 1))
    $PY src5/run5.py "${common[@]}" "${CAPS[@]}" ${mc[@]+"${mc[@]}"} --extra-spend-logs "$ALL_SPEND" --out "$out" $DRYFLAG
    status=$?
    read -r after total < <($PY src5_batch/cells_done.py --model "$model" --out "$out$SUB" --configs "$configs" --aware "$aware" \
                              --tasks "$tasks" --instances "$inst" --seeds "$seeds" --agents "$n" ${pf[@]+"${pf[@]}"})
    echo "   [$fam] attempt $attempt: run5 exit $status; done $before -> $after of $total"
    case $status in
      2) echo "   [$fam] cost cap reached for this block; moving on"; return 2 ;;
      4) echo "!! [$fam] OpenRouter credit/key limit (402) - lane stops"; return 4 ;;
      1) echo "!! [$fam] run5 refused (see above)"; return 1 ;;
    esac
    [ "$after" -ge "$total" ] && return 0
    if [ "$after" -gt "$before" ]; then idle=0; else idle=$((idle + 1)); fi
    [ "$idle" -ge 10 ] && { echo "!! [$fam] 10 attempts without progress; rerun to continue"; return 3; }
    before=$after
    local wait=$SYNC_RETRY_MIN
    [ "$SYNC_RETRY_JITTER" -gt 0 ] && wait=$((SYNC_RETRY_MIN + RANDOM % (SYNC_RETRY_JITTER + 1)))
    echo "   [$fam] provider failures (rate limit?) - retrying in ${wait}s"; sleep "$wait"
  done
}

run_lane() {
  local lane=$1 st worst=0
  while IFS=$'\t' read -r prio fam model n configs tasks inst seeds aware mcap mode; do
    [ "$fam" = "$lane" ] || continue
    run_block "$prio" "$fam" "$model" "$n" "$configs" "$tasks" "$inst" "$seeds" "$aware" "$mcap" "$mode"
    st=$?
    case $st in
      0|2) ;;
      1|4) echo "!! lane $lane stops (exit $st)"; return $st ;;
      *) worst=$st ;;
    esac
  done < <($PY src5/plan5.py --blocks "$PLAN")
  echo "=== lane $lane finished $(date) (exit $worst)"
  return $worst
}

LANES=(gemini anthropic openrouter)  # Round 3: Gemini first (its batch price doubles from 2026-11-30T00:00Z)
[ -n "$ONLY_LANE" ] && LANES=("$ONLY_LANE")
declare_status=""
if [ $SEQUENTIAL = 1 ] || [ ${#LANES[@]} = 1 ]; then
  for l in "${LANES[@]}"; do run_lane "$l" > >(tee -a "$BASE/lane_$l.log") 2>&1; declare_status="$declare_status $l:$?"; done
else
  PIDS=()
  for l in "${LANES[@]}"; do
    ( run_lane "$l" ) >> "$BASE/lane_$l.log" 2>&1 &
    PIDS+=("$!")
    echo "   lane $l started (pid $!); follow it with: tail -f $BASE/lane_$l.log"
  done
  i=0
  for pid in "${PIDS[@]}"; do wait "$pid"; declare_status="$declare_status ${LANES[$i]}:$?"; i=$((i + 1)); done
fi
echo "=== lanes done:$declare_status  $(date)"
if [ $DRY = 1 ]; then
  echo "== dry run only: message/lock channel rehearsal (all_peer_informed, fake model; never in the paid grid)"
  $PY src5/run5.py --models claude-haiku-4-5-20251001 --configs locks,all_available,all_peer_informed --tasks study2 \
    --instances 2 --seeds 0,1 --agents 2 --aware off --out "$BASE/rehearsal" --dry-run > "$BASE/rehearsal.log" 2>&1 \
    || { echo "!! channel rehearsal failed - see $BASE/rehearsal.log"; declare_status="$declare_status rehearsal:3"; }
  tail -1 "$BASE/rehearsal.log"
  $PY src5_verify/dry_check5.py "$BASE" || declare_status="$declare_status dry_check:3"
fi
CSVS=$(ls "$BASE"/n*"$SUB"/results.csv "$BASE"/probe-*"$SUB"/results.csv 2>/dev/null | tr '\n' ' ')
if [ -n "$CSVS" ]; then
  $PY src5/summarize5.py $CSVS --out "$BASE/summary$([ $DRY = 1 ] && echo _dry).md" > /dev/null && echo "   summary: $BASE/summary$([ $DRY = 1 ] && echo _dry).md"
fi
$PY - "$ALL_SPEND" <<'EOF'
import sys
sys.path.insert(0, "src5")
import budget5
paths = sys.argv[1].split(",")
print("   spend by provider:", {k: round(v, 4) for k, v in budget5.spend_by_family(paths).items()})
EOF
case "$declare_status" in *:1*|*:3*|*:4*) exit 3 ;; esac
exit 0
