#!/bin/bash
# Study 3 runner (harness src6) for the author's Mac. Derived from run_conc_study2.sh (Study 2): same autorun pattern
# (refuses to run twice, keeps the Mac awake, logs everything, retries until done, resumes where it stopped) and the
# same cap mechanism (budget6: one cap per provider plus a total, checked before every pair or batch wave):
#
#     Anthropic  $29.50  (Claude Haiku 4.5, Claude Sonnet 5: Message Batches)
#     OpenRouter $15.50  (Qwen3.6-27B: sync, routed to Alibaba without fallbacks)
#     total      $45   (Study 3 budget approved by the author: $50; at least $5 stays unspent)
#   (override: STUDY3_CAP_ANTHROPIC=.. STUDY3_CAP_OPENROUTER=.. STUDY3_CAP_TOTAL=..; never above the registered caps
#    without a registered deviation)
#
# Run from your own Terminal, in this folder (paper-concurrency/study3):
#     bash run_conc_study3.sh --dry-run            # fake models, no keys, no money (rehearsal of the whole grid)
#     bash run_conc_study3.sh                      # paid run: refuses unless .study3_registered exists
#     bash run_conc_study3.sh --lane anthropic     # only one provider lane (anthropic | openrouter)
#     bash run_conc_study3.sh --sequential         # lanes one after another instead of in parallel
#   (macOS /bin/bash is 3.2: empty arrays are expanded as ${arr[@]+"${arr[@]}"} so `set -u` does not abort)
#
# What it does
#   0. Paid run only: refuses unless .study3_registered exists in this folder (written only after the author has
#      filed the OSF registration), reads .env (ANTHROPIC_API_KEY, OPENROUTER_API_KEY) from this folder or from the
#      project root two levels up, and uses the project's .venv/bin/python.
#   1. Checks src6/FREEZE.md (src6/*.py|*.json, src6_batch/*.py|*.json|*.sh, src6_verify/dry_check6.py, this script)
#      and runs the reference-policy validity gate (src6/validity6.py; scripted agents, no cost): it must pass.
#   2. Preflight (once): one tiny sync request per model.
#   3. Runs the grid of src6/plan_study3.json in two provider lanes, in parallel by default:
#        anthropic : batch driver, Haiku then Sonnet (each 896 episodes, own sub-cap)
#        openrouter: run6.py sync, Qwen (896 episodes); the OpenRouter key's usage is logged before and after
#                    (analysis6/balance6.py, no model call)
#      Inside a block every contended episode is followed by its matched control and the two are admitted together,
#      so a cost-cap stop falls between pairs; the grid is visited instance-major, so a stop drops whole later
#      instances evenly over families and conditions.
#   4. Sync models are re-run until every cell is done (rate limits are retried, never dropped); batch models get
#      5 attempts per block (paid batch results are kept across attempts and reruns).
#   5. Writes results6/study3/summary.md (descriptive) at the end; --dry-run also runs src6_verify/dry_check6.py.
# Outputs: results6/study3/n2-<provider>/ (transcripts/, results.csv, spend.jsonl, failures.jsonl, batch_state/).
# Resumable: run the same line again. Logs: results6/study3/run_study3.log and lane_<provider>.log.
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
for f in src6/run6.py src6_batch/batch_driver.py src6/plan6.py; do
  [ -f "$f" ] || { echo "cannot find $f under $ROOT"; exit 1; }
done
PLAN="${PLAN_ARG:-src6/plan_study3.json}"
[ -f "$PLAN" ] || { echo "no plan file $PLAN (make one: python3 src6/plan6.py --plan $PLAN)"; exit 1; }
if [ $DRY = 0 ] && [ ! -f .study3_registered ]; then
  echo "Study 3 is not registered yet (.study3_registered is missing): refusing to spend."; exit 3
fi

# Never run alongside another runner or driver (ancestors of this script excluded).
ANCESTORS=" $$ "; p=$$
while [ -n "$p" ] && [ "$p" != "1" ] && [ "$p" != "0" ]; do
  p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"; ANCESTORS="$ANCESTORS$p "
done
PIDS_TMP="$(mktemp)"
for pat in 'run_conc_study3\.sh' 'src6/run6\.py' 'src6_batch/batch_driver\.py' 'run_conc_study2\.sh' 'src5/run5\.py' 'src5_batch/batch_driver\.py'; do
  pgrep -f "$pat" > "$PIDS_TMP" 2>/dev/null
  while read -r pid; do
    if [ -n "$pid" ] && [[ "$ANCESTORS" != *" $pid "* ]]; then
      echo "Refusing to start: a process matching $pat is running (pid $pid). Stop it first."; rm -f "$PIDS_TMP"; exit 1
    fi
  done < "$PIDS_TMP"
done
rm -f "$PIDS_TMP"

BASE="${BASE_ARG:-results6/study3}"
mkdir -p "$BASE"
LOCK="$BASE/.run_study3.lock"
mkdir "$LOCK" 2>/dev/null || { echo "Refusing to start: $LOCK exists (another run? remove it if not)"; exit 1; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
LOG="$BASE/run_study3.log"; [ $DRY = 1 ] && LOG="$BASE/run_study3_dry.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== start $(date)  dry_run=$DRY  lane=${ONLY_LANE:-all}  base=$BASE  plan=$PLAN"

CAP_ANTHROPIC="${STUDY3_CAP_ANTHROPIC:-29.5}"; CAP_OPENROUTER="${STUDY3_CAP_OPENROUTER:-15.5}"; CAP_TOTAL="${STUDY3_CAP_TOTAL:-45}"
CAPS=(--max-usd "$CAP_TOTAL" --family-cap "anthropic=$CAP_ANTHROPIC" --family-cap "openrouter=$CAP_OPENROUTER")
echo "   caps: anthropic \$$CAP_ANTHROPIC, openrouter \$$CAP_OPENROUTER, total \$$CAP_TOTAL"

if [ $DRY = 1 ]; then
  PY="${PYTHON:-python3}"; SUB="/dry_run"; DRYFLAG="--dry-run"; RETRY_SLEEP=1
  SYNC_RETRY_MIN="${SYNC_RETRY_MIN:-1}"; SYNC_RETRY_JITTER="${SYNC_RETRY_JITTER:-0}"
else
  ENVF=".env"; [ -f "$ENVF" ] || ENVF="../../.env"
  [ -f "$ENVF" ] || { echo ".env missing (ANTHROPIC_API_KEY, OPENROUTER_API_KEY), here or two levels up"; exit 1; }
  set -a; source "$ENVF"; set +a
  for K in ANTHROPIC_API_KEY OPENROUTER_API_KEY; do
    if [ -z "${!K:-}" ]; then echo "$K missing in $ENVF"; exit 1; fi
  done
  PY="${PYTHON:-}"
  if [ -z "$PY" ]; then
    if [ -x .venv/bin/python ]; then PY=.venv/bin/python; elif [ -x ../../.venv/bin/python ]; then PY=../../.venv/bin/python
    else echo "no .venv/bin/python here or two levels up (set PYTHON=...)"; exit 1; fi
  fi
  SUB=""; DRYFLAG=""; RETRY_SLEEP=60
  SYNC_RETRY_MIN=120; SYNC_RETRY_JITTER=60
  command -v caffeinate >/dev/null && caffeinate -dimsu -w $$ &
fi
export PYTHONDONTWRITEBYTECODE=1
$PY -c "import anthropic" 2>/dev/null || { echo "the batch driver needs the anthropic SDK in $PY"; exit 1; }

echo "== harness check (src6/FREEZE.md: src6, src6_batch, src6_verify/dry_check6.py, run_conc_study3.sh)"
$PY src6/freeze6.py --check || { echo "!! a frozen file differs from src6/FREEZE.md - not starting"; exit 1; }
echo "== reference-policy validity gate (scripted agents, no cost)"
if [ -f "$BASE/validity$SUB/ok" ]; then
  echo "   passed earlier ($(cat "$BASE/validity$SUB/ok"))"
else
  $PY src6/validity6.py --out "$BASE/validity$SUB" > "$BASE/validity_run.log" 2>&1 \
    || { echo "!! validity gate failed - see $BASE/validity_run.log; nothing was spent"; exit 1; }
  tail -1 "$BASE/validity_run.log"; date > "$BASE/validity$SUB/ok"
fi

PREF="$BASE/preflight$SUB"; mkdir -p "$PREF"
ALL_SPEND="$PREF/spend.jsonl"
for fm in anthropic openrouter; do ALL_SPEND="$ALL_SPEND,$BASE/n2-$fm$SUB/spend.jsonl"; done
echo "== preflight"
if [ -f "$PREF/ok" ]; then
  echo "   passed earlier ($(cat "$PREF/ok"))"
else
  $PY src6/preflight6.py --models "openrouter:qwen/qwen3.6-27b-20260422,claude-haiku-4-5-20251001,claude-sonnet-5" \
    --spend-log "$PREF/spend.jsonl" $DRYFLAG || { echo "!! preflight failed - not started"; exit 1; }
  date > "$PREF/ok"
fi

is_batch_model() { case "$1" in claude-*) return 0 ;; esac; return 1; }

# block runner: prio family model n configs tasks instances seeds aware model_cap mode
run_block() {
  local prio=$1 fam=$2 model=$3 n=$4 configs=$5 tasks=$6 inst=$7 seeds=$8 aware=$9 mcap=${10} mode=${11:-episodes}
  local out="$BASE/n$n-$fam" status attempt idle=0 before after total  # one directory per lane: no shared files
  local common=(--models "$model" --configs "$configs" --tasks "$tasks" --instances "$inst" --seeds "$seeds"
                --agents "$n" --aware "$aware")
  local mc=(); [ "$mcap" != "-" ] && mc=(--model-cap "$mcap")
  echo "== [$fam] prio $prio  $mode  $model  n=$n aware=$aware  inst=$inst seeds=$seeds  model cap ${mcap}  $(date)"
  if is_batch_model "$model"; then
    for attempt in 1 2 3 4 5; do
      $PY src6_batch/batch_driver.py "${common[@]}" "${CAPS[@]}" ${mc[@]+"${mc[@]}"} --extra-spend-logs "$ALL_SPEND" --out "$out" $DRYFLAG
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
  read -r before total < <($PY src6_batch/cells_done.py --model "$model" --out "$out$SUB" --configs "$configs" --aware "$aware" \
                             --tasks "$tasks" --instances "$inst" --seeds "$seeds" --agents "$n")
  attempt=0
  while :; do
    attempt=$((attempt + 1))
    $PY src6/run6.py "${common[@]}" "${CAPS[@]}" ${mc[@]+"${mc[@]}"} --extra-spend-logs "$ALL_SPEND" --out "$out" $DRYFLAG
    status=$?
    read -r after total < <($PY src6_batch/cells_done.py --model "$model" --out "$out$SUB" --configs "$configs" --aware "$aware" \
                              --tasks "$tasks" --instances "$inst" --seeds "$seeds" --agents "$n")
    echo "   [$fam] attempt $attempt: run6 exit $status; done $before -> $after of $total"
    case $status in
      2) echo "   [$fam] cost cap reached for this block; moving on"; return 2 ;;
      4) echo "!! [$fam] OpenRouter credit/key limit (402) - lane stops"; return 4 ;;
      1) echo "!! [$fam] run6 refused (see above)"; return 1 ;;
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
  if [ "$lane" = openrouter ] && [ $DRY = 0 ]; then
    $PY analysis6/balance6.py --base "$BASE" --phase before || echo "   (balance log before failed; the lane runs anyway)"
  fi
  while IFS=$'\t' read -r prio fam model n configs tasks inst seeds aware mcap mode; do
    [ "$fam" = "$lane" ] || continue
    run_block "$prio" "$fam" "$model" "$n" "$configs" "$tasks" "$inst" "$seeds" "$aware" "$mcap" "$mode"
    st=$?
    case $st in
      0|2) ;;
      1|4) echo "!! lane $lane stops (exit $st)"; worst=$st; break ;;
      *) worst=$st ;;
    esac
  done < <($PY src6/plan6.py --blocks "$PLAN")
  if [ "$lane" = openrouter ] && [ $DRY = 0 ]; then
    $PY analysis6/balance6.py --base "$BASE" --phase after --lane-exit "$worst" || echo "   (balance log after failed)"
  fi
  echo "=== lane $lane finished $(date) (exit $worst)"
  return $worst
}

LANES=(anthropic openrouter)
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
  $PY src6_verify/dry_check6.py "$BASE" || declare_status="$declare_status dry_check:3"
fi
CSVS=$(ls "$BASE"/n*"$SUB"/results.csv 2>/dev/null | tr '\n' ' ')
if [ -n "$CSVS" ]; then
  $PY src6/summarize6.py $CSVS --out "$BASE/summary$([ $DRY = 1 ] && echo _dry).md" > /dev/null && echo "   summary: $BASE/summary$([ $DRY = 1 ] && echo _dry).md"
fi
$PY - "$ALL_SPEND" <<'PYEOF'
import sys
sys.path.insert(0, "src6")
import budget6
paths = sys.argv[1].split(",")
print("   spend by provider:", {k: round(v, 4) for k, v in budget6.spend_by_family(paths).items()})
PYEOF
case "$declare_status" in *:1*|*:3*|*:4*) exit 3 ;; esac
exit 0
