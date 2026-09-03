#!/bin/bash

model_name=TimeMixer

# 固定参数
down_sampling_layers=3
learning_rate=0.001
d_ff=64
train_epochs=10
patience=10
batch_size=16
use_weighted_loss=1
#loss_weight_mode=linear  #线性
#loss_weight_mode=exp   #指数
loss_weight_mode=piecewise  #分段
loss_weight_alpha=0.3
loss_weight_split=0.6
use_acc_loss=1
acc_loss_weight=0.5

# 循环参数
for seq_len in 120; do
  for e_layers in 4; do
    for down_sampling_window in 1; do
      for d_model in 128; do
        #for acc_loss_weight in 0.3 0.4 0.5 0.6 0.7; do
         #for loss_weight_alpha in 0.1 0.2 0.3 0.4 0.5; do
          #for loss_weight_split in 0.3 0.4 0.5 0.6 0.7; do
              echo "============================="
              echo "Running with params:"
              echo "seq_len=$seq_len, e_layers=$e_layers"
              echo "down_sampling_layers=$down_sampling_layers"
              echo "down_sampling_window=$down_sampling_window"
              echo "d_model=$d_model, d_ff=$d_ff"
              #echo "use_weighted_loss=$use_weighted_loss"
              #echo "loss_weight_mode=$loss_weight_mode"
              #echo "loss_weight_alpha=$loss_weight_alpha"
              #echo "loss_weight_split=$loss_weight_split"
              #echo "use_acc_loss=$use_acc_loss"
              #echo "acc_loss_weight=$acc_loss_weight"
              echo "============================="

              # 结果文件
              result_file="coal_weights_result_sl${seq_len}_el${e_layers}_dsl${down_sampling_layers}_dsw${down_sampling_window}_dm${d_model}_df${d_ff}_weights${use_weighted_loss}_mode${loss_weight_mode}_alpha${loss_weight_alpha}_split${loss_weight_split}_accLoss${use_acc_loss}_accLossWeight${acc_loss_weight}.csv"
              csv_path="./pre_result_weights/${result_file}"

              # 日志文件（和结果文件同名，只是放在 logs/ 并改成 .log）
              mkdir -p logs
              log_path="logs/${result_file%.csv}.log"

              python -u run.py \
                --task_name long_term_forecast \
                --csv_path "$csv_path" \
                --is_training 1 \
                --root_path "./dataset/pre_coal/" \
                --data_path coal.csv \
                --model_id "coal_TimeMixer_sl${seq_len}_el${e_layers}_dsl${down_sampling_layers}_dsw${down_sampling_window}_dm${d_model}_df${d_ff}_weights${use_weighted_loss}_mode${loss_weight_mode}_alpha${loss_weight_alpha}_split${loss_weight_split}_accLoss${use_acc_loss}_accLossWeight${acc_loss_weight}" \
                --model $model_name \
                --data coal \
                --features M \
                --target_features 6 \
                --seq_len $seq_len \
                --label_len 60 \
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
                --use_weighted_loss $use_weighted_loss \
                --loss_weight_mode $loss_weight_mode \
                --loss_weight_alpha $loss_weight_alpha \
                --loss_weight_split $loss_weight_split \
                --use_acc_loss $use_acc_loss \
                --acc_loss_weight $acc_loss_weight \
                2>&1 | tee "$log_path"
            done
          done
        done
      done
    done
  done
done
