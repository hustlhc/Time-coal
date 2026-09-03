#!/bin/bash

model_name=TimeMixer

# 定义要搜索的超参数组合
seq_lens=(32 48 64 80 96 104 112 120)
e_layers_list=(3 4)
down_sampling_layers_list=(1 2)
learning_rates=(0.001)
d_models=(64)
d_ffs=(16)
moving_avgs=(5 15)

# 计数器
counter=0

# 网格搜索循环
for seq_len in "${seq_lens[@]}"; do
  for e_layers in "${e_layers_list[@]}"; do
    for down_sampling_layers in "${down_sampling_layers_list[@]}"; do
      for learning_rate in "${learning_rates[@]}"; do
        for d_model in "${d_models[@]}"; do
          for d_ff in "${d_ffs[@]}"; do
            for moving_avg in "${moving_avgs[@]}"; do
              
              # 计算标签长度（seq_len的一半）
              label_len=$((seq_len / 2))
              
              # 生成唯一的模型ID
              model_id="zhangping_TimeMixer_${seq_len}_60_${counter}"
              
              echo "=================================================================="
              echo "Running configuration $counter:"
              echo "seq_len=$seq_len, e_layers=$e_layers, down_sampling_layers=$down_sampling_layers"
              echo "learning_rate=$learning_rate, d_model=$d_model, d_ff=$d_ff, moving_avg=$moving_avg"
              echo "=================================================================="
              
              python -u run.py \
                --task_name long_term_forecast \
                --is_training 1 \
                --do_finetune 0 \
                --root_path ./dataset/huodian \
                --csv_path ./testresult/zhangping.csv \
                --data_path zhangping.csv \
                --model_id $model_id \
                --model $model_name \
                --data coal \
                --features M \
                --target_features 2 \
                --is_testing 1 \
                --seq_len $seq_len \
                --label_len $label_len \
                --pred_len 60 \
                --e_layers $e_layers \
                --enc_in 52 \
                --c_out 52 \
                --des "Exp" \
                --itr 1 \
                --d_model $d_model \
                --d_ff $d_ff \
                --learning_rate $learning_rate \
                --train_epochs 10 \
                --patience 10 \
                --batch_size 16 \
                --down_sampling_layers $down_sampling_layers \
                --down_sampling_method avg \
                --channel_independence 0 \
                --down_sampling_window 1 \
                --do_predict 0 \
                --is_full_training 1 \
                --moving_avg $moving_avg
              
              # 计数器递增
              counter=$((counter + 1))
              
              echo "Completed configuration $counter"
              echo ""
              
            done
          done
        done
      done
    done
  done
done

echo "Grid search completed! Total configurations tested: $counter"