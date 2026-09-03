#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../.."

index="${1:-CCI4500}"

model_name=TimeMixer
seq_len="${SEQ_LEN:-32}"
pred_len="${PRED_LEN:-120}"
down_sampling_layers="${DOWN_SAMPLING_LAYERS:-3}"
down_sampling_window="${DOWN_SAMPLING_WINDOW:-1}"
learning_rate="${LEARNING_RATE:-0.001}"
train_epochs="${TRAIN_EPOCHS:-10}"
patience="${PATIENCE:-10}"
batch_size="${BATCH_SIZE:-16}"

case "$index" in
  CCI4500)
    model_prefix=CCI4500
    target="CCI4500"
    e_layers="${E_LAYERS:-5}"
    d_model="${D_MODEL:-64}"
    d_ff="${D_FF:-16}"
    moving_avg="${MOVING_AVG:-25}"
    ;;
  CCI5000)
    model_prefix=CCI5000
    target="CCI5000"
    e_layers="${E_LAYERS:-3}"
    d_model="${D_MODEL:-32}"
    d_ff="${D_FF:-16}"
    moving_avg="${MOVING_AVG:-15}"
    ;;
  CCI5500)
    model_prefix=CCI5500
    target="CCI5500"
    e_layers="${E_LAYERS:-3}"
    d_model="${D_MODEL:-32}"
    d_ff="${D_FF:-16}"
    moving_avg="${MOVING_AVG:-15}"
    ;;
  CCI3800out|CCI3800|CCI进口3800)
    model_prefix=CCI3800out
    target="CCI进口3800"
    e_layers="${E_LAYERS:-3}"
    d_model="${D_MODEL:-64}"
    d_ff="${D_FF:-16}"
    moving_avg="${MOVING_AVG:-15}"
    ;;
  CCI4700out|CCI4700|CCI进口4700)
    model_prefix=CCI4700out
    target="CCI进口4700"
    e_layers="${E_LAYERS:-4}"
    d_model="${D_MODEL:-32}"
    d_ff="${D_FF:-16}"
    moving_avg="${MOVING_AVG:-15}"
    ;;
  CCI5500out|CCI进口5500)
    model_prefix=CCI5500out
    target="CCI进口5500"
    e_layers="${E_LAYERS:-4}"
    d_model="${D_MODEL:-64}"
    d_ff="${D_FF:-32}"
    moving_avg="${MOVING_AVG:-15}"
    ;;
  *)
    echo "Unknown index: $index"
    echo "Use one of: CCI4500 CCI5000 CCI5500 CCI3800out CCI4700out CCI5500out"
    exit 1
    ;;
esac

model_id="${model_prefix}_TimeMixerseasonal_${seq_len}_${pred_len}"

seasonal_flags=(
  --use_month_onehot 1
  --use_seasonal_loss 1
  --seasonal_loss_months "${SEASONAL_LOSS_MONTHS:-1,4,6,9,11,12}"
  --seasonal_loss_weight "${SEASONAL_LOSS_WEIGHT:-1.3}"
  --seasonal_loss_normalize "${SEASONAL_LOSS_NORMALIZE:-1}"
)

common_args=(
  --task_name long_term_forecast
  --root_path ./dataset/pre_coal/
  --data_path coal_new.csv
  --model_id "$model_id"
  --model "$model_name"
  --data coal
  --features MS
  --target_features 1
  --seq_len "$seq_len"
  --label_len "$((seq_len / 2))"
  --pred_len "$pred_len"
  --e_layers "$e_layers"
  --enc_in 103
  --c_out 103
  --des Seasonal
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
  --gpu_type "${GPU_TYPE:-cuda}"
)

echo "==> [seasonal] train/test: $model_prefix target=$target model_id=$model_id"
python -u run.py \
  "${common_args[@]}" \
  "${seasonal_flags[@]}" \
  --is_training 1 \
  --do_finetune 0 \
  --do_predict 0 \
  --is_testing "${IS_TESTING:-1}" \
  --is_full_training "${IS_FULL_TRAINING:-1}" \
  --csv_path "./testresult/seasonal/${model_prefix}.csv"

echo "==> [seasonal] infer latest window: $model_prefix"
python -u run.py \
  "${common_args[@]}" \
  "${seasonal_flags[@]}" \
  --is_training 0 \
  --do_predict 1 \
  --is_testing 0 \
  --last_ten 0 \
  --csv_path "./autoinfer/seasonal/${model_prefix}infer.csv"

echo "==> [seasonal] smooth latest forecast: $model_prefix"
case "$model_prefix" in
  CCI4500)
    python autoinfer/smooth2.py "./autoinfer/seasonal/${model_prefix}infer.csv" "./autoinfer/seasonal/${model_prefix}infer.csv" --round --true-col -6
    ;;
  CCI5000)
    python autoinfer/smooth2.py "./autoinfer/seasonal/${model_prefix}infer.csv" "./autoinfer/seasonal/${model_prefix}infer.csv" --round --true-col -5
    ;;
  CCI5500)
    python autoinfer/smooth2.py "./autoinfer/seasonal/${model_prefix}infer.csv" "./autoinfer/seasonal/${model_prefix}infer.csv" --round --true-col -4
    ;;
  CCI3800out)
    python autoinfer/smooth2.py "./autoinfer/seasonal/${model_prefix}infer.csv" "./autoinfer/seasonal/${model_prefix}infer.csv" --true-col -3
    ;;
  CCI4700out)
    python autoinfer/smooth2.py "./autoinfer/seasonal/${model_prefix}infer.csv" "./autoinfer/seasonal/${model_prefix}infer.csv" --true-col -2
    ;;
  CCI5500out)
    python autoinfer/smooth2.py "./autoinfer/seasonal/${model_prefix}infer.csv" "./autoinfer/seasonal/${model_prefix}infer.csv" --true-col -1
    ;;
esac

echo "==> [seasonal] infer previous window: $model_prefix"
python -u run.py \
  "${common_args[@]}" \
  "${seasonal_flags[@]}" \
  --is_training 0 \
  --do_predict 1 \
  --is_testing 0 \
  --last_ten 1 \
  --csv_path "./teninfer/seasonal/${model_prefix}infer.csv"

echo "==> done: $model_prefix"
