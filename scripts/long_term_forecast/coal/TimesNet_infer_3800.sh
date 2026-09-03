#!/bin/bash

model_name=TimesNet

# 固定参数
seq_len=20
label_len=$((seq_len / 2))
pred_len=20
d_layers=2
factor=3
top_k=5

# 创建输出目录
mkdir -p ./TimesNet_inferresult

# 三层循环遍历参数
for e_layers in 3 4
do
  for d_model in 32 64
  do
    for d_ff in 32 64
    do
      echo "Running inference with d_layers=$d_layers, d_model=$d_model, d_ff=$d_ff"
      
      python -u run.py \
        --task_name long_term_forecast \
        --is_training 1 \
        --root_path ./dataset/coal/ \
        --csv_path ./TimesNet_inferresult/infer_3800_8.12/infer_result_3800new_sl${seq_len}_pl${pred_len}_el${e_layers}_dl${d_layers}_dm${d_model}_df${d_ff}.csv \
        --data_path 3800_infer8.12.csv \
        --model_id TimesNet_coal3800new_seq_len${seq_len}_${pred_len} \
        --model $model_name \
        --data coal \
        --features MS \
        --seq_len $seq_len \
        --label_len $label_len \
        --pred_len $pred_len \
        --e_layers $e_layers \
        --d_layers $d_layers \
        --factor $factor \
        --enc_in 100 \
        --dec_in 100 \
        --c_out 100 \
        --d_model $d_model \
        --d_ff $d_ff \
        --des 'Exp' \
        --itr 1 \
        --top_k $top_k \
        --do_predict 1
    done
  done
done