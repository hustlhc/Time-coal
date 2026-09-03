#!/usr/bin/env bash
set -Eeuo pipefail

# Daily local task for this migrated machine.
# It intentionally leaves auto_task*.sh untouched and mirrors their core flow:
#   1) update coal/freight data
#   2) monitor coal forecast error and safely retrain when needed
#   3) run coal and freight inference
#   4) generate JSON/output files
#   5) import coal/freight real and prediction data into sqlite

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/home/lhc/miniconda3/envs/time/bin/python}"
PYTHON_DIR="$(dirname "$PYTHON_BIN")"

BACKFILL_DAYS="${BACKFILL_DAYS:-1}"
COAL_FORECAST_MODE="${COAL_FORECAST_MODE:-trend}"
COAL_TREND_TRAIN_ON_INFER="${COAL_TREND_TRAIN_ON_INFER:-0}"
SYNC_STRENGTH="${SYNC_STRENGTH:-0.8}"
SYNC_ANCHOR_MODE="${SYNC_ANCHOR_MODE:-imported_mean}"
SYNC_ALIGN_TARGETS="${SYNC_ALIGN_TARGETS:-domestic}"
SYNC_INFER_TARGETS="${SYNC_INFER_TARGETS:-0}"
POST_SYNC_FORECASTS="${POST_SYNC_FORECASTS:-0}"
USE_SHORT_SLOPE_CORRECTION="${USE_SHORT_SLOPE_CORRECTION:-0}"
USE_LEVEL_DELTA_CORRECTION="${USE_LEVEL_DELTA_CORRECTION:-0}"
GPU_TYPE="${GPU_TYPE:-cpu}"

RUN_DATA_UPDATE="${RUN_DATA_UPDATE:-1}"
RUN_HUODIAN_DATA_UPDATE="${RUN_HUODIAN_DATA_UPDATE:-0}"
FETCH_HUODIAN_DAYS="${FETCH_HUODIAN_DAYS:-3}"

RUN_COAL_INFER="${RUN_COAL_INFER:-1}"
RUN_FREIGHT_INFER="${RUN_FREIGHT_INFER:-1}"
RUN_TOJS="${RUN_TOJS:-1}"
RUN_PROCESS_OUTPUT="${RUN_PROCESS_OUTPUT:-1}"
RUN_DB_IMPORT="${RUN_DB_IMPORT:-1}"

RUN_COAL_AUTO_RETRAIN="${RUN_COAL_AUTO_RETRAIN:-1}"
COAL_AUTO_RETRAIN_EXECUTE="${COAL_AUTO_RETRAIN_EXECUTE:-1}"
COAL_AUTO_RETRAIN_WINDOW="${COAL_AUTO_RETRAIN_WINDOW:-5}"
COAL_AUTO_RETRAIN_EVAL_HORIZON="${COAL_AUTO_RETRAIN_EVAL_HORIZON:-5}"
COAL_AUTO_RETRAIN_OVERALL_MAPE="${COAL_AUTO_RETRAIN_OVERALL_MAPE:-3.0}"
COAL_AUTO_RETRAIN_INDEX_MAPE="${COAL_AUTO_RETRAIN_INDEX_MAPE:-5.0}"
COAL_AUTO_RETRAIN_DIRECTION="${COAL_AUTO_RETRAIN_DIRECTION:-0.55}"
COAL_AUTO_RETRAIN_STREAK="${COAL_AUTO_RETRAIN_STREAK:-2}"
COAL_AUTO_RETRAIN_COOLDOWN_DAYS="${COAL_AUTO_RETRAIN_COOLDOWN_DAYS:-7}"
COAL_AUTO_RETRAIN_ATTEMPT_COOLDOWN_DAYS="${COAL_AUTO_RETRAIN_ATTEMPT_COOLDOWN_DAYS:-3}"
COAL_AUTO_RETRAIN_MIN_IMPROVEMENT="${COAL_AUTO_RETRAIN_MIN_IMPROVEMENT:-0.01}"
COAL_ACTIVE_MODEL_ID="${COAL_ACTIVE_MODEL_ID:-${MODEL_ID:-Coal6_JulyShort_Trend5dStrong32_Prod_20260730}}"

# Optional extensions, off by default because this task targets coal price/freight.
RUN_HUODIAN_INFER="${RUN_HUODIAN_INFER:-0}"
RUN_ELEC_TOJS="${RUN_ELEC_TOJS:-0}"
RUN_ELEC_DB_IMPORT="${RUN_ELEC_DB_IMPORT:-0}"
RUN_QWEN_DECISION="${RUN_QWEN_DECISION:-0}"
FIX_ELEC_DAYS="${FIX_ELEC_DAYS:-7}"

DRY_RUN="${DRY_RUN:-0}"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/log/cron}"
LOCK_FILE="${LOCK_FILE:-/tmp/time_coal_daily_coal_freight.lock}"

mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_FILE:-$LOG_DIR/daily_coal_freight_$(date '+%Y%m%d').log}"
exec > >(tee -a "$LOG_FILE") 2>&1

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] another daily task is running; skip."
  exit 0
fi

trap 'echo "[$(date "+%Y-%m-%d %H:%M:%S")] failed at line $LINENO"; exit 1' ERR

run() {
  echo "+ $*"
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  "$@"
}

run_in_dir() {
  local dir="$1"
  shift
  echo "+ (cd $dir && $*)"
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  (
    cd "$dir"
    "$@"
  )
}

require_python() {
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Python not found or not executable: $PYTHON_BIN"
    exit 1
  fi
}

main() {
  require_python
  export PATH="$PYTHON_DIR:$PATH"
  export PYTHON_BIN
  export PYTHONUNBUFFERED=1
  export COAL_FORECAST_MODE
  export COAL_TREND_TRAIN_ON_INFER
  export SYNC_STRENGTH
  export SYNC_ANCHOR_MODE
  export SYNC_ALIGN_TARGETS
  export SYNC_INFER_TARGETS
  export POST_SYNC_FORECASTS
  export USE_SHORT_SLOPE_CORRECTION
  export USE_LEVEL_DELTA_CORRECTION
  export GPU_TYPE

  cd "$SCRIPT_DIR"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily coal/freight task start"
  echo "repo=$SCRIPT_DIR"
  echo "python=$PYTHON_BIN"
  echo "forecast_mode=$COAL_FORECAST_MODE, gpu_type=$GPU_TYPE, dry_run=$DRY_RUN"
  echo "sync_infer_targets=$SYNC_INFER_TARGETS, post_sync_forecasts=$POST_SYNC_FORECASTS"
  echo "sync_strength=$SYNC_STRENGTH, sync_anchor_mode=$SYNC_ANCHOR_MODE, sync_align_targets=$SYNC_ALIGN_TARGETS"
  echo "short_slope_correction=$USE_SHORT_SLOPE_CORRECTION"
  echo "level_delta_correction=$USE_LEVEL_DELTA_CORRECTION"

  if [[ "$RUN_DATA_UPDATE" == "1" ]]; then
    run "$PYTHON_BIN" v4/run_incremental.py --backfill "$BACKFILL_DAYS"
  else
    echo "skip data update"
  fi

  if [[ "$RUN_HUODIAN_DATA_UPDATE" == "1" ]]; then
    run_in_dir "$SCRIPT_DIR/dataset-huodian" "$PYTHON_BIN" fetch_date_data.py "$FETCH_HUODIAN_DAYS"
    run_in_dir "$SCRIPT_DIR/dataset-huodian" "$PYTHON_BIN" json_to_csv.py
    run_in_dir "$SCRIPT_DIR/dataset-huodian" "$PYTHON_BIN" process.py
    run_in_dir "$SCRIPT_DIR/dataset-huodian" "$PYTHON_BIN" disard.py
  fi

  if [[ "$RUN_COAL_AUTO_RETRAIN" == "1" ]]; then
    auto_retrain_args=(
      --active-model-id "$COAL_ACTIVE_MODEL_ID"
      --window "$COAL_AUTO_RETRAIN_WINDOW"
      --evaluation-horizon "$COAL_AUTO_RETRAIN_EVAL_HORIZON"
      --overall-mape-threshold "$COAL_AUTO_RETRAIN_OVERALL_MAPE"
      --index-mape-threshold "$COAL_AUTO_RETRAIN_INDEX_MAPE"
      --direction-threshold "$COAL_AUTO_RETRAIN_DIRECTION"
      --breach-streak-required "$COAL_AUTO_RETRAIN_STREAK"
      --cooldown-days "$COAL_AUTO_RETRAIN_COOLDOWN_DAYS"
      --attempt-cooldown-days "$COAL_AUTO_RETRAIN_ATTEMPT_COOLDOWN_DAYS"
      --min-candidate-improvement "$COAL_AUTO_RETRAIN_MIN_IMPROVEMENT"
      --gpu-type "$GPU_TYPE"
    )
    if [[ "$COAL_AUTO_RETRAIN_EXECUTE" == "1" ]]; then
      auto_retrain_args+=(--execute-training)
    fi
    if ! run "$PYTHON_BIN" autoinfer/auto_retrain_coal.py "${auto_retrain_args[@]}"; then
      echo "[$(date '+%Y-%m-%d %H:%M:%S')] coal auto-retrain failed safely; continue with active checkpoint"
    fi
  else
    echo "skip coal auto-retrain monitor"
  fi

  if [[ "$RUN_COAL_INFER" == "1" ]]; then
    run env MODEL_ID="$COAL_ACTIVE_MODEL_ID" \
      "$PYTHON_BIN" coal.py --forecast_mode "$COAL_FORECAST_MODE" --infer 1
  else
    echo "skip coal inference"
  fi

  if [[ "$RUN_FREIGHT_INFER" == "1" ]]; then
    run "$PYTHON_BIN" transport.py --infer 1
  else
    echo "skip freight inference"
  fi

  if [[ "$RUN_HUODIAN_INFER" == "1" ]]; then
    run "$PYTHON_BIN" huodian.py --infer 1
  fi

  if [[ "$RUN_TOJS" == "1" ]]; then
    run "$PYTHON_BIN" tojs.py
  fi

  if [[ "$RUN_ELEC_TOJS" == "1" ]]; then
    run "$PYTHON_BIN" elec_tojs.py
  fi

  if [[ "$RUN_PROCESS_OUTPUT" == "1" ]]; then
    run "$PYTHON_BIN" process.py
  fi

  if [[ "$RUN_DB_IMPORT" == "1" ]]; then
    run_in_dir "$SCRIPT_DIR/autoinfer" "$PYTHON_BIN" import_real_data.py
    run_in_dir "$SCRIPT_DIR/autoinfer" "$PYTHON_BIN" import_data.py
    run_in_dir "$SCRIPT_DIR/autoinfer" "$PYTHON_BIN" add_unique_constraint.py
  fi

  if [[ "$RUN_ELEC_DB_IMPORT" == "1" ]]; then
    run_in_dir "$SCRIPT_DIR/autoinfer" "$PYTHON_BIN" import_real_elec_data.py
    run_in_dir "$SCRIPT_DIR/autoinfer" "$PYTHON_BIN" import_elec_prediction_data.py
    run_in_dir "$SCRIPT_DIR/autoinfer" "$PYTHON_BIN" fix_partial_runtime_unit_predictions.py "$FIX_ELEC_DAYS"
  fi

  if [[ "$RUN_QWEN_DECISION" == "1" ]]; then
    run_in_dir "$SCRIPT_DIR/Qwen" "$PYTHON_BIN" update_user_inputs.py
    run_in_dir "$SCRIPT_DIR/Qwen" "$PYTHON_BIN" gre_coal.py
    run_in_dir "$SCRIPT_DIR/Qwen" "$PYTHON_BIN" test_chat_single.py kemen
    run_in_dir "$SCRIPT_DIR/Qwen" "$PYTHON_BIN" test_chat_single.py shaowu
    run_in_dir "$SCRIPT_DIR/Qwen" "$PYTHON_BIN" test_chat_single.py yongan
    run_in_dir "$SCRIPT_DIR/Qwen" "$PYTHON_BIN" test_chat_single.py zhangping
    run_in_dir "$SCRIPT_DIR/autoinfer" "$PYTHON_BIN" save_decision_to_db.py
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] daily coal/freight task finished"
}

main "$@"
