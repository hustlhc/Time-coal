
model_name=TimeMixer

seq_len=24
e_layers=4
down_sampling_layers=3
down_sampling_window=2
learning_rate=0.01
d_model=16
d_ff=32
train_epochs=10
patience=10
batch_size=16
para='24,4,3,2,16'

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --root_path  ./dataset/coal/ \
  --csv_path ./inferresult/infer_result_5000_$para.csv \
  --data_path 5000_infer2.csv \
  --model_id coal5000_TimeMixer_$seq_len'_'40 \
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
  --do_predict 1