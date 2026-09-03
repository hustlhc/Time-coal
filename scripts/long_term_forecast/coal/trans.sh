
model_name=TimeMixer

seq_len=96
label_len=$((seq_len / 2))
e_layers=3
down_sampling_layers=3
down_sampling_window=2
learning_rate=0.001
d_model=64
batch_size=64
d_ff=16
train_epochs=10
patience=10

para='96,3,64,64,16,2'

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --root_path  ./dataset/pre_coal/ \
  --csv_path ./transresult/transout_result_$para.csv \
  --data_path transport.csv \
  --model_id trans_TimeMixer_$seq_len'_'60 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 1 \
  --seq_len $seq_len \
  --label_len $label_len \
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
  --do_predict 0 \
  --target 'outside' 