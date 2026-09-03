#!/bin/bash

# =============================
# 超参数循环设置（在这里修改即可）
# =============================
seq_len_list="32 64 96 120"
e_layers=3
down_sampling_window_list='1 2'
d_model=32
d_ff=32
batch_size=16
down_sampling_layers_list="1 3"
moving_avg_list="5 15"
decomp_method=("moving_avg")
if [ $# -gt 0 ]; then
  targets=($1)   # 传入时支持多个，如 "A B C"
else
  # 默认值（如果没传就用全部）
  targets=("输入00000351--煤炭运费_水运价格_进口煤炭运费_印尼萨马林达-中国广州_当期值(美元/吨)" "输入00000347--煤炭运费_水运价格_沿海煤炭运费_秦皇岛-厦门(5-6万DWT)_本期(元/吨)")
fi


# 固定参数
model_name=TimeMixer
learning_rate=0.001
train_epochs=10
patience=10

# =============================
# 循环遍历
# =============================
for target in $targets; do
  for seq_len in $seq_len_list; do
    for down_sampling_window in $down_sampling_window_list; do
      for down_sampling_layers in $down_sampling_layers_list; do
        for moving_avg in $moving_avg_list; do
          for decomp_method in $decomp_method; do
            # 运行脚本
            python -u run.py \
              --task_name long_term_forecast \
              --csv_path ./pre_coal/${target}new_result_${seq_len}_${down_sampling_window}_${down_sampling_layers}_${moving_avg}_${decomp_method}.csv \
              --is_training 1 \
              --root_path ./dataset/pre_coal/ \
              --data_path coal_freight.csv \
              --model_id ${target}_TimeMixerauto_${seq_len}_60 \
              --model $model_name \
              --data coal \
              --features MS \
              --target_features 1 \
              --target "$target" \
              --seq_len $seq_len \
              --label_len $((seq_len / 2)) \
              --pred_len 60 \
              --e_layers $e_layers \
              --enc_in 64 \
              --c_out 64 \
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
              --moving_avg $moving_avg \
              --decomp_method "$decomp_method" 
            
              python -u run.py \
              --task_name long_term_forecast \
              --is_training 0 \
              --root_path  ./dataset/pre_coal/ \
              --csv_path ./choiceinfer/${target}/infer_${seq_len}_${down_sampling_window}_${down_sampling_layers}_${moving_avg}_${decomp_method}.csv \
              --data_path coal_freight.csv \
              --model_id ${target}_TimeMixerauto_$seq_len'_'60 \
              --model $model_name \
              --data coal \
              --features MS \
              --target_features 1 \
              --is_testing 0 \
              --seq_len $seq_len \
              --label_len $((seq_len / 2)) \
              --pred_len 60 \
              --e_layers $e_layers \
              --enc_in 64 \
              --c_out 64 \
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
              --do_predict 1 \
              --last_ten 1 \
              --decomp_method "$decomp_method" \
              --moving_avg $moving_avg \
              --target "$target"
          done
        done
      done
    done
  done
done
