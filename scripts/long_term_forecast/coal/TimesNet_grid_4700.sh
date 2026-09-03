#!/bin/bash

model_name=TimesNet
log_dir=./TimesNet_logs/4700
result_dir=./TimesNet_results/coal_4700
mkdir -p $log_dir
mkdir -p $result_dir

# 固定参数
top_k=5
factor=3
pred_len=20   # 预测长度保持不变

for seq_len in 20
do
  label_len=$((seq_len / 2))   # 自动计算 label_len = seq_len 一半
  for d_model in 32 64
  do
    for d_ff in 32 64
    do
      for e_layers in 3
      do
        for d_layers in 2
        do
          # 生成唯一的 CSV 文件名
          csv_filename="coal4700_sl${seq_len}_ll${label_len}_dm${d_model}_df${d_ff}_el${e_layers}_dl${d_layers}.csv"
          csv_path="$result_dir/$csv_filename"
          
          log_file=$log_dir/coal4700_sl${seq_len}_ll${label_len}_dm${d_model}_df${d_ff}_el${e_layers}_dl${d_layers}.log
          echo "Running seq_len=$seq_len, label_len=$label_len, d_model=$d_model, d_ff=$d_ff, e_layers=$e_layers, d_layers=$d_layers"
          echo "CSV will be saved to: $csv_path"
          
          python -u run.py \
            --task_name long_term_forecast \
            --is_training 1 \
            --root_path ./dataset/coal/ \
            --data_path coal_4700.csv \
            --model_id TimesNet_coal4700_seq_len${seq_len}_${pred_len} \
            --model $model_name \
            --data coal \
            --features MS \
            --seq_len $seq_len \
            --label_len $label_len \
            --pred_len $pred_len \
            --e_layers $e_layers \
            --d_layers $d_layers \
            --factor $factor \
            --enc_in 101 \
            --dec_in 101 \
            --c_out 101 \
            --d_model $d_model \
            --d_ff $d_ff \
            --des 'Exp' \
            --itr 1 \
            --top_k $top_k \
            --csv_path $csv_path > $log_file 2>&1
        done
      done
    done
  done
done