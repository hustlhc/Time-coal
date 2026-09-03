
model_name=TimeMixer

#seq_len=40
#e_layers=2
down_sampling_layers=3
#down_sampling_window=2
learning_rate=0.01
#d_model=32
d_ff=32
train_epochs=10
patience=10
batch_size=16

for seq_len in 24 32 40 48 56
do
  for e_layers in 2 3 4
  do
      for down_sampling_window in 1 2
      do
        for d_model in 16 32 64 128
        do
          echo "============================="
          echo "Running with params: seq_len=$seq_len, e_layers=$e_layers, down_sampling_layers=$down_sampling_layers, down_sampling_window=$down_sampling_window, d_model=$d_model"
          echo "============================="
          python -u run.py \
            --task_name long_term_forecast \
            --csv_path ./pre_result/coal_4700_result_${seq_len}_${e_layers}_${down_sampling_layers}_${down_sampling_window}_${d_model}.csv \
            --is_training 1 \
            --root_path  ./dataset/coal/\
            --data_path coal_4700.csv \
            --model_id coal4700_TimeMixer_$seq_len'_'40 \
            --model $model_name \
            --data coal \
            --features MS \
            --seq_len $seq_len \
            --label_len 20 \
            --pred_len 20 \
            --e_layers $e_layers \
            --enc_in 101 \
            --c_out 101 \
            --des 'Exp' \
            --itr 1 \
            --d_model $d_model \
            --d_ff $d_ff \
            --learning_rate $learning_rate \
            --train_epochs $train_epochs \
            --patience $patience \
            --batch_size 16 \
            --down_sampling_layers $down_sampling_layers \
            --down_sampling_method avg \
            --channel_independence 0 \
            --down_sampling_window $down_sampling_window \
             2>&1 | tee -a grid_search4700_results.log
        done
      done
  done
done