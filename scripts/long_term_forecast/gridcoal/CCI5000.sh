model_name=TimeMixer
down_sampling_layers=3

learning_rate=0.001
train_epochs=10
patience=10

for seq_len in 80 88 96 104 112 120
do
  label_len=$((seq_len / 2))
  for e_layers in 3 4
  do
    for d_ff in 16 32 64
    do
        for down_sampling_window in 1 2
        do
          for d_model in 16 32 64
          do
              for batch_size in 16 32 64
              do
              echo "============================="
              echo "Running with params: seq_len=$seq_len, e_layers=$e_layers, d_ff=$d_ff, down_sampling_window=$down_sampling_window, d_model=$d_model, batch_size=$batch_size"
              echo "============================="

              python -u run.py \
                  --task_name long_term_forecast \
                  --csv_path ./pre_coal/coal_CCI5000outnew_result_${seq_len}_${e_layers}_${d_ff}_${down_sampling_window}_${d_model}_${down_sampling_window}.csv \
                  --is_training 1 \
                  --root_path  ./dataset/pre_coal/\
                  --data_path coal_new.csv \
                  --model_id CCI5000new_TimeMixer_${seq_len}_60 \
                  --model $model_name \
                  --data coal \
                  --features MS \
                  --target_features 1 \
                  --target 'CCI5000' \
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
                  2>&1 | tee -a gridCCI5000_search_results.log
              done
           done   
        done
      done
  done
done
