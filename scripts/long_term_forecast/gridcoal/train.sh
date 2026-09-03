
model_name=TimeMixer
down_sampling_layers=3

learning_rate=0.01
d_ff=32
train_epochs=10
patience=10

for seq_len in 60 72 88 104 120
do
  label_len=$((seq_len / 2))
  for e_layers in 3 4 5
  do
      for down_sampling_window in 1
      do
        for d_model in 32 64 128
        do
            for d_ff in 32 64 128
            do
                for batch_size in 16
                do
                echo "============================="
                echo "Running with params: seq_len=$seq_len, e_layers=$e_layers, down_sampling_layers=$down_sampling_layers, down_sampling_window=$down_sampling_window, d_model=$d_model"
                echo "============================="
                python -u run.py \
                    --task_name long_term_forecast \
                    --csv_path ./pre_coal/coal_result_sl${seq_len}_el${e_layers}_downsamplingl${down_sampling_layers}_downsamplingw${down_sampling_window}_dm${d_model}_df${d_ff}.csv \
                    --is_training 1 \
                    --root_path  ./dataset/pre_coal/\
                    --data_path coal.csv \
                    --model_id CCI3800outnew_TimeMixer_$seq_len'_'30 \
                    --model $model_name \
                    --data coal \
                    --features M \
                    --target_features 6 \
                    --target 'CCI3800out' \
                    --seq_len $seq_len \
                    --label_len $label_len \
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
                    2>&1 | tee -a grid_coal_result_sl${seq_len}_el${e_layers}_downsamplingl${down_sampling_layers}_downsamplingw${down_sampling_window}_dm${d_model}_df${d_ff}.log
                done
            done
        done
      done
  done
done