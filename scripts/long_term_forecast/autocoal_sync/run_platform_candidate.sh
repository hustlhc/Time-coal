#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../.."

export PYTHON_BIN="${PYTHON_BIN:-/home/lhc/miniconda3/envs/time/bin/python}"
export MODEL_TAG="${MODEL_TAG:-_platform_huber_seq64}"
export SEQ_LEN="${SEQ_LEN:-64}"
export PRED_LEN="${PRED_LEN:-120}"
export TRAIN_EPOCHS="${TRAIN_EPOCHS:-15}"
export PATIENCE="${PATIENCE:-5}"
export LEARNING_RATE="${LEARNING_RATE:-0.0007}"
export BATCH_SIZE="${BATCH_SIZE:-16}"
export MOVING_AVG="${MOVING_AVG:-15}"
export FORECAST_LOSS="${FORECAST_LOSS:-huber}"
export HUBER_DELTA="${HUBER_DELTA:-0.7}"
export IS_TESTING="${IS_TESTING:-1}"
export IS_FULL_TRAINING="${IS_FULL_TRAINING:-0}"
export TESTRESULT_FOLDER="${TESTRESULT_FOLDER:-testresult/platform_candidate}"
export AUTOINFER_FOLDER="${AUTOINFER_FOLDER:-autoinfer/platform_candidate}"
export TENINFER_FOLDER="${TENINFER_FOLDER:-teninfer/platform_candidate}"

# Keep calendar information, but do not amplify selected seasonal months.
export USE_MONTH_ONEHOT="${USE_MONTH_ONEHOT:-1}"
export USE_SEASONAL_LOSS="${USE_SEASONAL_LOSS:-0}"

# Supervise all six 20-day trend segments and gradually reduce far-horizon weight.
export USE_SHORT_TREND_LOSS="${USE_SHORT_TREND_LOSS:-1}"
export SHORT_TREND_LOSS_WEIGHT="${SHORT_TREND_LOSS_WEIGHT:-0.35}"
export SHORT_TREND_MONTH_LEN="${SHORT_TREND_MONTH_LEN:-20}"
export SHORT_TREND_MONTH_WEIGHTS="${SHORT_TREND_MONTH_WEIGHTS:-0.42,0.24,0.14,0.09,0.06,0.05}"
export SHORT_TREND_MAX_SEGMENTS="${SHORT_TREND_MAX_SEGMENTS:-6}"

# Preserve broad co-movement without forcing all six curves onto one slope.
export SYNC_LOSS_WEIGHT="${SYNC_LOSS_WEIGHT:-0.02}"
export RUN_TENINFER="${RUN_TENINFER:-0}"
export SMOOTH_OUTPUTS="${SMOOTH_OUTPUTS:-1}"

exec scripts/long_term_forecast/autocoal_sync/run_joint.sh "$@"
