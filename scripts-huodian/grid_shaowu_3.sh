#!/bin/bash

model_name=TimeMixer

# 定义要搜索的超参数组合
seq_lens=(32 48 64 80 96 104 112 120)
e_layers_list=(3)
down_sampling_layers_list=(1)
learning_rates=(0.001)
d_models=(64)
d_ffs=(16)
moving_avgs=(5)

# 计数器
counter=0

# 创建日志文件名（包含时间戳）
log_file="grid_shaowu_3_$(date +%Y%m%d_%H%M%S).log"

echo "开始网格搜索，日志文件: $log_file"
echo "开始时间: $(date)"

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
              model_id="shaowu_3_TimeMixer_${seq_len}_60_${counter}"
              
              echo "==================================================================" | tee -a "$log_file"
              echo "运行配置 $counter:" | tee -a "$log_file"
              echo "seq_len=$seq_len, e_layers=$e_layers, down_sampling_layers=$down_sampling_layers" | tee -a "$log_file"
              echo "learning_rate=$learning_rate, d_model=$d_model, d_ff=$d_ff, moving_avg=$moving_avg" | tee -a "$log_file"
              echo "==================================================================" | tee -a "$log_file"
              
              # 运行Python脚本并将输出同时显示在终端和日志文件中
              python -u run.py \
                --task_name long_term_forecast \
                --is_training 1 \
                --do_finetune 0 \
                --root_path ./dataset/huodian \
                --csv_path "./testresult/shaowu/shaowu_3_${seq_len}.csv" \
                --data_path shaowu_3.csv \
                --model_id $model_id \
                --model $model_name \
                --data coal \
                --features MS \
                --target_features 1 \
                --is_testing 1 \
                --seq_len $seq_len \
                --label_len $label_len \
                --pred_len 90 \
                --e_layers $e_layers \
                --enc_in 28 \
                --c_out 28 \
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
                --target '邵武_邵武#3_发电量' \
                --moving_avg $moving_avg 2>&1 | tee -a "$log_file"
              
              # 检查Python脚本的退出状态
              if [ ${PIPESTATUS[0]} -ne 0 ]; then
                echo "错误: Python脚本在配置 $counter 执行失败!" | tee -a "$log_file"
              fi
              
              # 计数器递增
              counter=$((counter + 1))
              
              echo "完成配置 $counter" | tee -a "$log_file"
              echo "" | tee -a "$log_file"
              
            done
          done
        done
      done
    done
  done
done

echo "网格搜索完成! 总共测试的配置数: $counter" | tee -a "$log_file"
echo "结束时间: $(date)" | tee -a "$log_file"