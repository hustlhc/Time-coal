#!/bin/bash

# =============================
# 超参数循环设置（在这里修改即可）
# =============================
seq_len_list="80 88 96 104 112 120"
e_layers_list="3"
down_sampling_window_list="1 2"
d_model_list="32 64 128"
d_ff_list="32 64 128"
batch_size_list="16 32"

# 固定参数
model_name=TimeMixer
down_sampling_layers=3
learning_rate=0.001
train_epochs=10
patience=10

# =============================
# 循环遍历
# =============================
for seq_len in $seq_len_list; do
  for e_layers in $e_layers_list; do
    for down_sampling_window in $down_sampling_window_list; do
      for d_model in $d_model_list; do
        for d_ff in $d_ff_list; do
          for batch_size in $batch_size_list; do

            echo "============================="
            echo "Running with params:"
            echo "seq_len=$seq_len, e_layers=$e_layers, down_sampling_layers=$down_sampling_layers,"
            echo "down_sampling_window=$down_sampling_window, d_model=$d_model, d_ff=$d_ff, batch_size=$batch_size"
            echo "============================="

            # 日志文件（包含所有关键参数）
            log_file="logs/CCI5500outnew_${seq_len}_${e_layers}_${down_sampling_layers}_${down_sampling_window}_${d_model}_ff${d_ff}_bs${batch_size}.log"
            mkdir -p logs

            # 运行脚本
            python -u run.py \
              --task_name long_term_forecast \
              --csv_path ./pre_coal/coal_CCI5500outnew_result_${seq_len}_${e_layers}_${down_sampling_layers}_${down_sampling_window}_${d_model}_ff${d_ff}_bs${batch_size}.csv \
              --is_training 1 \
              --root_path ./dataset/pre_coal/ \
              --data_path coal_new.csv \
              --model_id CCI5500outnew_TimeMixer_${seq_len}_60 \
              --model $model_name \
              --data coal \
              --features MS \
              --target_features 1 \
              --target 'CCI5500out' \
              --seq_len $seq_len \
              --label_len $((seq_len / 2)) \
              --pred_len 60 \
              --e_layers $e_layers \
              --enc_in 103 \
              --c_out 103 \
              --des 'Exp' \
              --itr 1 \
              --d_model $d_model \
              --d_ff $d_ff \
              --learning_rate $learning_rate \
              --train_epochs $train_epochs \
              --patience $patience \
              --batch_size $batch_size \
              --down_sampling_layers $down_sampling_layers \
              --down_sampling_method avg \
              --channel_independence 0 \
              --down_sampling_window $down_sampling_window \
              2>&1 | tee "$log_file"

          done
        done
      done
    done
  done
done
