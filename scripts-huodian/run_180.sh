#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

model_name=TimeMixer
seq_len="${SEQ_LEN:-32}"
pred_len="${PRED_LEN:-180}"
e_layers="${E_LAYERS:-4}"
down_sampling_layers="${DOWN_SAMPLING_LAYERS:-3}"
down_sampling_window="${DOWN_SAMPLING_WINDOW:-1}"
learning_rate="${LEARNING_RATE:-0.001}"
d_model="${D_MODEL:-64}"
d_ff="${D_FF:-16}"
train_epochs="${TRAIN_EPOCHS:-5}"
patience="${PATIENCE:-5}"
batch_size="${BATCH_SIZE:-16}"
moving_avg="${MOVING_AVG:-15}"
eval_pred_len="${EVAL_PRED_LEN:-60}"
gpu_type="${GPU_TYPE:-cpu}"
python_bin="${PYTHON_BIN:-python}"
run_train="${RUN_TRAIN:-1}"
run_infer="${RUN_INFER:-1}"
use_short_horizon_weight_loss="${USE_SHORT_HORIZON_WEIGHT_LOSS:-1}"
short_horizon_weight_days="${SHORT_HORIZON_WEIGHT_DAYS:-30}"
short_horizon_weight="${SHORT_HORIZON_WEIGHT:-3.0}"
short_horizon_weight_normalize="${SHORT_HORIZON_WEIGHT_NORMALIZE:-1}"
short_horizon_weight_tag="${short_horizon_weight//./p}"
if [[ "$use_short_horizon_weight_loss" == "1" ]]; then
  default_run_tag="short${short_horizon_weight_days}d_w${short_horizon_weight_tag}"
else
  default_run_tag="base"
fi
run_tag="${RUN_TAG:-$default_run_tag}"
test_dir="${TEST_DIR:-testresult/huodian_180_${run_tag}}"
infer_dir="${INFER_DIR:-autoinfer/elecdata_180_${run_tag}}"

mkdir -p "$test_dir" "$infer_dir"

run_one() {
  local name="$1"
  local data_path="$2"
  local target="$3"
  local enc_in="$4"
  local unit_eval_pred_len="${5:-$eval_pred_len}"
  local model_id="${name}_TimeMixer_${seq_len}_${pred_len}_${run_tag}"

  common_args=(
    --task_name long_term_forecast
    --root_path ./dataset-huodian
    --data_path "$data_path"
    --model_id "$model_id"
    --model "$model_name"
    --data coal
    --features MS
    --target_features 1
    --seq_len "$seq_len"
    --label_len "$((seq_len / 2))"
    --pred_len "$pred_len"
    --eval_pred_len "$unit_eval_pred_len"
    --use_short_horizon_weight_loss "$use_short_horizon_weight_loss"
    --short_horizon_weight_days "$short_horizon_weight_days"
    --short_horizon_weight "$short_horizon_weight"
    --short_horizon_weight_normalize "$short_horizon_weight_normalize"
    --e_layers "$e_layers"
    --enc_in "$enc_in"
    --c_out "$enc_in"
    --des Huodian180
    --itr 1
    --d_model "$d_model"
    --d_ff "$d_ff"
    --learning_rate "$learning_rate"
    --train_epochs "$train_epochs"
    --patience "$patience"
    --batch_size "$batch_size"
    --down_sampling_layers "$down_sampling_layers"
    --down_sampling_method avg
    --channel_independence 0
    --down_sampling_window "$down_sampling_window"
    --moving_avg "$moving_avg"
    --target "$target"
    --num_workers "${NUM_WORKERS:-0}"
    --gpu_type "$gpu_type"
    --delt 0
    --is_full_training 1
  )

  if [[ "$run_train" == "1" ]]; then
    echo "==> [huodian180] train $name target=$target"
    "$python_bin" -u run.py \
      "${common_args[@]}" \
      --is_training 1 \
      --do_predict 0 \
      --is_testing 0 \
      --csv_path "${test_dir}/${name}.csv"
  else
    echo "==> [huodian180] skip train $name"
  fi

  if [[ "$run_infer" == "1" ]]; then
    echo "==> [huodian180] infer $name"
    "$python_bin" -u run.py \
      "${common_args[@]}" \
      --is_training 0 \
      --do_predict 1 \
      --is_testing 0 \
      --last_ten 0 \
      --csv_path "${infer_dir}/${name}.csv"
  fi
}

run_one yongan_7 yongan_7.csv '永安_永安#7_发电量' 26
run_one yongan_8 yongan_8.csv '永安_永安#8_发电量' 26
run_one kemen_1 kemen_1.csv '可门_可门#1_发电量' 29
run_one kemen_2 kemen_2.csv '可门_可门#2_发电量' 29
run_one kemen_3 kemen_3.csv '可门_可门#3_发电量' 29
run_one kemen_4 kemen_4.csv '可门_可门#4_发电量' 29
run_one kemen_5 kemen_5.csv '可门_可门#5_发电量' 29
run_one kemen_6 kemen_6.csv '可门_可门#6_发电量' 29 "${KEMEN_6_EVAL_PRED_LEN:-20}"
run_one shaowu_3 shaowu_3.csv '邵武_邵武#3_发电量' 23
run_one shaowu_4 shaowu_4.csv '邵武_邵武#4_发电量' 23
run_one zhangping_5 zhangping_5.csv '漳平_漳平#5_发电量' 28
run_one zhangping_6 zhangping_6.csv '漳平_漳平#6_发电量' 28

echo "==> done: huodian180"
