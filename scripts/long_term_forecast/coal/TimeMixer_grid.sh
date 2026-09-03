
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

for seq_len in 56 64 72 80 88 96 104 112 120
do
  label_len=$((seq_len / 2))
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
            --csv_path ./pre_result60/coal_3800_result_${seq_len}_${e_layers}_${down_sampling_layers}_${down_sampling_window}_${d_model}.csv \
            --is_training 1 \
            --root_path  ./dataset/coal/\
            --data_path coal_3800new.csv \
            --model_id coal3800_TimeMixer_$seq_len'_'60 \
            --model $model_name \
            --data coal \
            --features M \
            --target_features 3 \
            --seq_len $seq_len \
            --label_len $label_len \
            --pred_len 60 \
            --e_layers $e_layers \
            --enc_in 100 \
            --c_out 100 \
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
             2>&1 | tee -a grid60_search_results.log
        done
      done
  done
done