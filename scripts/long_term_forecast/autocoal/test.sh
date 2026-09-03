
model_name=TimeMixer

seq_len=120
e_layers=3
down_sampling_layers=3
down_sampling_window=1
learning_rate=0.001
d_model=128
d_ff=128
train_epochs=10
patience=10
batch_size=16

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --do_finetune 0 \
  --root_path  ./dataset/pre_coal/ \
  --csv_path ./testresult/CCI3800out.csv \
  --data_path withmonth.csv \
  --model_id CCI3800out_month_$seq_len'_'60 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 1 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 60 \
  --e_layers $e_layers \
  --enc_in 105 \
  --c_out 105 \
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
  --is_full_training 1 \
  --target 'CCI进口3800' 