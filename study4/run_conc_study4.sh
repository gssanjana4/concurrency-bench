#!/bin/bash
# Study 4 runner (harness src7) for the author's Mac. Derived from run_conc_study3.sh (Study 3): same autorun pattern
# (refuses to run twice, keeps the Mac awake, logs everything, retries until done, resumes where it stopped) and the
# same cap mechanism (budget7: one cap per provider plus a total, checked before every episode or batch wave):
#
#     Anthropic  $100   (Claude Haiku 4.5, Claude Sonnet 5, Claude Fable 5: Message Batches; paid from the API credit
#                        already on the account)
#     OpenRouter $9.50  (Qwen3.6-27B: sync, routed to Alibaba without fallbacks; the key's existing balance)
#     total      $109.50 (approved by the author on 2026-11-15)
#   (override: STUDY4_CAP_ANTHROPIC=.. STUDY4_CAP_OPENROUTER=.. STUDY4_CAP_TOTAL=..; never above the registered caps)
#
# Run from your own Terminal, in this folder (paper-concurrency/study4):
#     bash run_conc_study4.sh --dry-run            # fake models, no keys, no money (rehearsal of the whole grid)
#     bash run_conc_study4.sh                      # paid run: refuses unless .study4_registered says the OSF
#                                                  # registration finished archiving (see step 0)
#     bash run_conc_study4.sh --lane anthropic     # only one provider lane (anthropic | openrouter)
#     bash run_conc_study4.sh --sequential         # lanes one after another instead of in parallel
#
# What it does
#   0. Paid run only: refuses unless src7/gate7.py confirms the OSF registration is archived (the saved OSF API
#      record and the marker .study4_registered; see gate7.py). Study 3's run started before its registration had
#      archived, and that registration failed. Also refuses caps above the registered caps and any other plan file. Then reads .env (ANTHROPIC_API_KEY, OPENROUTER_API_KEY) and uses the project's .venv.
#   1. Checks src7/FREEZE.md and runs the reference-policy validity gate (scripted agents, no cost): it must pass.
#   2. Preflight (once): one tiny sync request per model.
#   3. Runs the grid of src7/plan_study4.json (contended episodes only, four lock configs, 16 instances) in two
#      provider lanes, in parallel by default: anthropic (batch driver: Haiku, Sonnet, then Fable in two stages:
#      locks_s2text first; the other three configs only if src7/floor_gate7.py finds at least 5 failed episodes
#      among its 128) and openrouter
#      (run7.py sync: Qwen; the key's usage is logged before and after). The grid is visited instance-major, so a
#      cost-cap stop drops whole later instances evenly over families and configs.
#   4. Sync models are re-run until every cell is done; batch models get 5 attempts per block.
#   5. Writes results7/study4/summary.md (descriptive) at the end; --dry-run also runs src7_verify/dry_check7.py.
# Resumable: run the same line again. Logs: results7/study4/run_study4.log and lane_<provider>.log.
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
for f in src7/run7.py src7_batch/batch_driver.py src7/plan7.py; do
  [ -f "$f" ] || { echo "cannot find $f under $ROOT"; exit 1; }
done
PLAN="${PLAN_ARG:-src7/plan_study4.json}"
[ -f "$PLAN" ] || { echo "no plan file $PLAN (make one: python3 src7/plan7.py --plan $PLAN)"; exit 1; }
if [ $DRY = 0 ]; then
  python3 src7/gate7.py || { echo "refusing to spend (src7/gate7.py)"; exit 3; }
  [ "$PLAN" = "src7/plan_study4.json" ] || { echo "a paid run uses the frozen plan src7/plan_study4.json only"; exit 1; }
  awk -v a="${STUDY4_CAP_ANTHROPIC:-100}" -v o="${STUDY4_CAP_OPENROUTER:-9.5}" -v t="${STUDY4_CAP_TOTAL:-109.5}" \
    'BEGIN { exit !(a <= 100 && o <= 9.5 && t <= 109.5) }' || { echo "caps above the registered caps: refusing"; exit 1; }
fi

# Never run alongside another runner or driver (ancestors of this script excluded).
ANCESTORS=" $$ "; p=$$
while [ -n "$p" ] && [ "$p" != "1" ] && [ "$p" != "0" ]; do
  p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"; ANCESTORS="$ANCESTORS$p "
done
PIDS_TMP="$(mktemp)"
for pat in 'run_conc_study4\.sh' 'src7/run7\.py' 'src7_batch/batch_driver\.py' 'run_conc_study3\.sh' 'src6/run6\.py' 'src6_batch/batch_driver\.py'; do
  pgrep -f "$pat" > "$PIDS_TMP" 2>/dev/null
  while read -r pid; do
    if [ -n "$pid" ] && [[ "$ANCESTORS" != *" $pid "* ]]; then
      echo "Refusing to start: a process matching $pat is running (pid $pid). Stop it first."; rm -f "$PIDS_TMP"; exit 1
    fi
  done < "$PIDS_TMP"
done
rm -f "$PIDS_TMP"

BASE="${BASE_ARG:-results7/study4}"
mkdir -p "$BASE"
LOCK="$BASE/.run_study4.lock"
mkdir "$LOCK" 2>/dev/null || { echo "Refusing to start: $LOCK exists (another run? remove it if not)"; exit 1; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
LOG="$BASE/run_study4.log"; [ $DRY = 1 ] && LOG="$BASE/run_study4_dry.log"
exec > >(tee -a "$LOG") 2>&1
echo "=== start $(date)  dry_run=$DRY  lane=${ONLY_LANE:-all}  base=$BASE  plan=$PLAN"

CAP_ANTHROPIC="${STUDY4_CAP_ANTHROPIC:-100}"; CAP_OPENROUTER="${STUDY4_CAP_OPENROUTER:-9.5}"; CAP_TOTAL="${STUDY4_CAP_TOTAL:-109.5}"
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

echo "== harness check (src7/FREEZE.md: src7, src7_batch, src7_verify/dry_check7.py, run_conc_study4.sh)"
$PY src7/freeze7.py --check || { echo "!! a frozen file differs from src7/FREEZE.md - not starting"; exit 1; }
echo "== reference-policy validity gate (scripted agents, no cost)"
FREEZE_SHA="$($PY -c 'import hashlib;print(hashlib.sha256(open("src7/FREEZE.md","rb").read()).hexdigest())')"
if [ -f "$BASE/validity$SUB/ok" ] && grep -q "$FREEZE_SHA" "$BASE/validity$SUB/ok"; then
  echo "   passed earlier under this freeze ($(head -1 "$BASE/validity$SUB/ok"))"
else
  $PY src7/validity7.py --out "$BASE/validity$SUB" > "$BASE/validity_run.log" 2>&1 \
    || { echo "!! validity gate failed - see $BASE/validity_run.log; nothing was spent"; exit 1; }
  tail -1 "$BASE/validity_run.log"; { date; echo "freeze $FREEZE_SHA"; } > "$BASE/validity$SUB/ok"
fi

PREF="$BASE/preflight$SUB"; mkdir -p "$PREF"
ALL_SPEND="$PREF/spend.jsonl"
for fm in anthropic openrouter; do ALL_SPEND="$ALL_SPEND,$BASE/n2-$fm$SUB/spend.jsonl"; done
if [ $DRY = 0 ]; then $PY src7/gate7.py || { echo "refusing to spend (src7/gate7.py)"; exit 3; }; fi
echo "== preflight"
if [ -f "$PREF/ok" ]; then
  echo "   passed earlier ($(cat "$PREF/ok"))"
else
  $PY src7/preflight7.py --models "openrouter:qwen/qwen3.6-27b-20260422,claude-haiku-4-5-20251001,claude-sonnet-5,claude-fable-5" \
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
      $PY src7_batch/batch_driver.py "${common[@]}" "${CAPS[@]}" ${mc[@]+"${mc[@]}"} --extra-spend-logs "$ALL_SPEND" --out "$out" $DRYFLAG
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
  read -r before total < <($PY src7_batch/cells_done.py --model "$model" --out "$out$SUB" --configs "$configs" --aware "$aware" \
                             --tasks "$tasks" --instances "$inst" --seeds "$seeds" --agents "$n")
  attempt=0
  while :; do
    attempt=$((attempt + 1))
    $PY src7/run7.py "${common[@]}" "${CAPS[@]}" ${mc[@]+"${mc[@]}"} --extra-spend-logs "$ALL_SPEND" --out "$out" $DRYFLAG
    status=$?
    read -r after total < <($PY src7_batch/cells_done.py --model "$model" --out "$out$SUB" --configs "$configs" --aware "$aware" \
                              --tasks "$tasks" --instances "$inst" --seeds "$seeds" --agents "$n")
    echo "   [$fam] attempt $attempt: run7 exit $status; done $before -> $after of $total"
    case $status in
      2) echo "   [$fam] cost cap reached for this block; moving on"; return 2 ;;
      4) echo "!! [$fam] OpenRouter credit/key limit (402) - lane stops"; return 4 ;;
      1) echo "!! [$fam] run7 refused (see above)"; return 1 ;;
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
    $PY analysis7/balance7.py --base "$BASE" --phase before || echo "   (balance log before failed; the lane runs anyway)"
  fi
  while IFS=$'\t' read -r prio fam model n configs tasks inst seeds aware mcap mode; do
    [ "$fam" = "$lane" ] || continue
    if [ "$mode" = floor_gated ]; then  # registered Fable stage rule: stage 2 runs only above the floor
      $PY src7/floor_gate7.py --out "$BASE/n$n-$fam$SUB" --model "$model" --instances "$inst" --record "$BASE/floor_gate$([ $DRY = 1 ] && echo _dry).json"
      case $? in
        0) echo "   [$fam] $model stage 1 above the floor: stage 2 runs" ;;
        10) echo "   [$fam] $model at the floor under locks_s2text: stage 2 not run (registered rule)"; continue ;;
        *) echo "   [$fam] $model stage 1 incomplete: stage 2 not run"; continue ;;
      esac
    fi
    run_block "$prio" "$fam" "$model" "$n" "$configs" "$tasks" "$inst" "$seeds" "$aware" "$mcap" "$mode"
    st=$?
    case $st in
      0|2) ;;
      1|4) echo "!! lane $lane stops (exit $st)"; worst=$st; break ;;
      *) worst=$st ;;
    esac
  done < <($PY src7/plan7.py --blocks "$PLAN")
  if [ "$lane" = openrouter ] && [ $DRY = 0 ]; then
    $PY analysis7/balance7.py --base "$BASE" --phase after --lane-exit "$worst" || echo "   (balance log after failed)"
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
  $PY src7_verify/dry_check7.py "$BASE" || declare_status="$declare_status dry_check:3"
fi
CSVS=$(ls "$BASE"/n*"$SUB"/results.csv 2>/dev/null | tr '\n' ' ')
if [ -n "$CSVS" ]; then
  $PY src7/summarize7.py $CSVS --out "$BASE/summary$([ $DRY = 1 ] && echo _dry).md" > /dev/null && echo "   summary: $BASE/summary$([ $DRY = 1 ] && echo _dry).md"
fi
$PY - "$ALL_SPEND" <<'PYEOF'
import sys
sys.path.insert(0, "src7")
import budget7
paths = sys.argv[1].split(",")
print("   spend by provider:", {k: round(v, 4) for k, v in budget7.spend_by_family(paths).items()})
PYEOF
case "$declare_status" in *:1*|*:3*|*:4*) exit 3 ;; esac
exit 0
