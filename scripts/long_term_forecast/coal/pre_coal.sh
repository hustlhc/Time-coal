model_name=TimeMixer

seq_len=56
e_layers=4
down_sampling_layers=3
down_sampling_window=2
learning_rate=0.01
d_model=32
d_ff=32
train_epochs=10
patience=10
batch_size=16

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --root_path  ./dataset/pre_coal/ \
  --csv_path ./pre_coal/coal_resultCCI5500_${seq_len}_${e_layers}_${down_sampling_layers}_${down_sampling_window}_${d_model}.csv \
  --data_path coal.csv \
  --model_id coal_TimeMixer_sl$seq_len'_'pl60 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --target 'CCI5500' \
  --seq_len $seq_len \
  --label_len 28 \
  --pred_len 30 \
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
  --batch_size 16 \
  --down_sampling_layers $down_sampling_layers \
  --down_sampling_method avg \
   --channel_independence 0 \
  --down_sampling_window $down_sampling_window 