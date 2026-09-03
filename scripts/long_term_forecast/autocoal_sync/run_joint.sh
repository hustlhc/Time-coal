#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../.."

model_name=TimeMixer
python_bin="${PYTHON_BIN:-python}"
seq_len="${SEQ_LEN:-32}"
pred_len="${PRED_LEN:-120}"
model_id="${MODEL_ID:-Coal6_TimeMixerNoEasy_${seq_len}_${pred_len}${MODEL_TAG:-}}"
data_root="${DATA_ROOT:-./dataset/pre_coal/}"
data_path="${DATA_PATH:-coal_new.csv}"
feature_count="${FEATURE_COUNT:-$($python_bin -c "import os, pandas as pd; print(pd.read_csv(os.path.join('$data_root', '$data_path'), nrows=0).shape[1] - 1)")}"
testresult_folder="${TESTRESULT_FOLDER:-testresult/sync_joint}"
autoinfer_folder="${AUTOINFER_FOLDER:-autoinfer/sync_joint}"
teninfer_folder="${TENINFER_FOLDER:-teninfer/sync_joint}"
sync_infer_targets="${SYNC_INFER_TARGETS:-0}"
smooth_outputs="${SMOOTH_OUTPUTS:-1}"
short_slope_correction="${USE_SHORT_SLOPE_CORRECTION:-0}"
level_delta_correction="${USE_LEVEL_DELTA_CORRECTION:-0}"
post_sync_forecasts="${POST_SYNC_FORECASTS:-0}"
sync_strength="${SYNC_STRENGTH:-0.8}"
sync_anchor_mode="${SYNC_ANCHOR_MODE:-imported_mean}"
sync_align_targets="${SYNC_ALIGN_TARGETS:-domestic}"
run_train="${RUN_TRAIN:-1}"
run_infer="${RUN_INFER:-1}"
run_teninfer="${RUN_TENINFER:-0}"

echo "==> [sync6] model=$model_id data=${data_root}${data_path} features=$feature_count seq_len=$seq_len pred_len=$pred_len sync_infer_targets=$sync_infer_targets post_sync_forecasts=$post_sync_forecasts short_slope_correction=$short_slope_correction level_delta_correction=$level_delta_correction"

common_args=(
  --task_name long_term_forecast
  --root_path "$data_root"
  --data_path "$data_path"
  --model_id "$model_id"
  --model "$model_name"
  --data coal
  --features M
  --target_features 6
  --seq_len "$seq_len"
  --label_len "$((seq_len / 2))"
  --pred_len "$pred_len"
  --delt "$level_delta_correction"
  --e_layers "${E_LAYERS:-4}"
  --enc_in "$feature_count"
  --c_out "$feature_count"
  --des Sync6
  --itr 1
  --d_model "${D_MODEL:-64}"
  --d_ff "${D_FF:-32}"
  --learning_rate "${LEARNING_RATE:-0.001}"
  --forecast_loss "${FORECAST_LOSS:-mse}"
  --huber_delta "${HUBER_DELTA:-1.0}"
  --use_short_horizon_weight_loss "${USE_SHORT_HORIZON_WEIGHT_LOSS:-0}"
  --short_horizon_weight_days "${SHORT_HORIZON_WEIGHT_DAYS:-30}"
  --short_horizon_weight "${SHORT_HORIZON_WEIGHT:-2.0}"
  --short_horizon_weight_normalize "${SHORT_HORIZON_WEIGHT_NORMALIZE:-1}"
  --train_epochs "${TRAIN_EPOCHS:-10}"
  --patience "${PATIENCE:-10}"
  --batch_size "${BATCH_SIZE:-16}"
  --down_sampling_layers "${DOWN_SAMPLING_LAYERS:-3}"
  --down_sampling_method avg
  --channel_independence 0
  --down_sampling_window "${DOWN_SAMPLING_WINDOW:-1}"
  --moving_avg "${MOVING_AVG:-15}"
  --num_workers "${NUM_WORKERS:-0}"
  --gpu_type "${GPU_TYPE:-cuda}"
  --use_month_onehot "${USE_MONTH_ONEHOT:-1}"
  --use_seasonal_loss "${USE_SEASONAL_LOSS:-1}"
  --seasonal_loss_months "${SEASONAL_LOSS_MONTHS:-1,4,6,9,11,12}"
  --seasonal_loss_weight "${SEASONAL_LOSS_WEIGHT:-1.3}"
  --seasonal_loss_normalize "${SEASONAL_LOSS_NORMALIZE:-1}"
  --use_acc_loss "${USE_ACC_LOSS:-0}"
  --acc_loss_weight "${ACC_LOSS_WEIGHT:-0.5}"
  --use_short_trend_loss "${USE_SHORT_TREND_LOSS:-0}"
  --short_trend_loss_weight "${SHORT_TREND_LOSS_WEIGHT:-0.5}"
  --short_trend_month_len "${SHORT_TREND_MONTH_LEN:-20}"
  --short_trend_month_weights "${SHORT_TREND_MONTH_WEIGHTS:-0.6,0.25,0.15}"
  --short_trend_max_segments "${SHORT_TREND_MAX_SEGMENTS:-3}"
  --use_sync_loss 1
  --sync_loss_weight "${SYNC_LOSS_WEIGHT:-0.05}"
  --sync_infer_targets "$sync_infer_targets"
  --sync_infer_strength "${SYNC_INFER_STRENGTH:-0.4}"
  --sync_anchor_mode "$sync_anchor_mode"
  --sync_align_targets "$sync_align_targets"
)

mkdir -p "$testresult_folder" "$autoinfer_folder" "$teninfer_folder"

if [[ "$run_train" == "1" ]]; then
  echo "==> [sync6] train/test joint six-index model: $model_id"
  "$python_bin" -u run.py \
    "${common_args[@]}" \
    --is_training 1 \
    --do_finetune 0 \
    --do_predict 0 \
    --is_testing "${IS_TESTING:-1}" \
    --is_full_training "${IS_FULL_TRAINING:-1}" \
    --csv_path "${testresult_folder}/coal6.csv"
else
  echo "==> [sync6] skip train/test: $model_id"
fi

if [[ "$run_infer" != "1" ]]; then
  echo "==> done: sync6 train/test only"
  exit 0
fi

run_predict_window() {
  local output_folder="$1"
  local last_ten="$2"
  local label="$3"

  echo "==> [sync6] infer ${label} window"
  "$python_bin" -u run.py \
    "${common_args[@]}" \
    --is_training 0 \
    --do_predict 1 \
    --is_testing 0 \
    --last_ten "$last_ten" \
    --csv_path "${output_folder}/coal6infer.csv"

  echo "==> [sync6] split ${label} forecast"
  "$python_bin" autoinfer/split_joint_forecast.py \
    --input "${output_folder}/coal6infer.csv" \
    --output-folder "${output_folder}"

  if [[ "$smooth_outputs" == "1" ]]; then
    echo "==> [sync6] smooth ${label} split forecasts"
    "$python_bin" autoinfer/smooth2.py "${output_folder}/CCI4500infer.csv" "${output_folder}/CCI4500infer.csv" --round --true-col -6
    "$python_bin" autoinfer/smooth2.py "${output_folder}/CCI5000infer.csv" "${output_folder}/CCI5000infer.csv" --round --true-col -5
    "$python_bin" autoinfer/smooth2.py "${output_folder}/CCI5500infer.csv" "${output_folder}/CCI5500infer.csv" --round --true-col -4
    "$python_bin" autoinfer/smooth2.py "${output_folder}/CCI3800outinfer.csv" "${output_folder}/CCI3800outinfer.csv" --true-col -3
    "$python_bin" autoinfer/smooth2.py "${output_folder}/CCI4700outinfer.csv" "${output_folder}/CCI4700outinfer.csv" --true-col -2
    "$python_bin" autoinfer/smooth2.py "${output_folder}/CCI5500outinfer.csv" "${output_folder}/CCI5500outinfer.csv" --true-col -1
  fi

  if [[ "$short_slope_correction" == "1" ]]; then
    local history_offset=0
    if [[ "$last_ten" == "1" ]]; then
      history_offset="${SHORT_SLOPE_HISTORY_OFFSET_PREVIOUS:-30}"
    fi
    echo "==> [sync6] short slope correct ${label} forecasts"
    "$python_bin" autoinfer/short_slope_correct.py \
      --folder "${output_folder}" \
      --history "${data_root}${data_path}" \
      --history-offset "$history_offset" \
      --lookback "${SHORT_SLOPE_LOOKBACK:-5}" \
      --window "${SHORT_SLOPE_WINDOW:-20}" \
      --decay-days "${SHORT_SLOPE_DECAY_DAYS:-35}" \
      --strength "${SHORT_SLOPE_STRENGTH:-0.8}" \
      --min-slope "${SHORT_SLOPE_MIN_ABS:-0.2}" \
      --mode "${SHORT_SLOPE_MODE:-opposite}"
  fi

  if [[ "$post_sync_forecasts" == "1" ]]; then
    echo "==> [sync6] align ${label} domestic forecasts to imported trend"
    "$python_bin" autoinfer/sync_forecasts.py \
      --folder "${output_folder}" \
      --strength "$sync_strength" \
      --anchor-mode "$sync_anchor_mode" \
      --align-targets "$sync_align_targets"
  fi
}

run_predict_window "$autoinfer_folder" 0 latest

if [[ "$run_teninfer" == "1" ]]; then
  run_predict_window "$teninfer_folder" 1 previous
fi

echo "==> done: sync6"
