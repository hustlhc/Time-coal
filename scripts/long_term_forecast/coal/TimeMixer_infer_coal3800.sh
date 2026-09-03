
model_name=TimeMixer

seq_len=40
e_layers=5
down_sampling_layers=3
down_sampling_window=1
learning_rate=0.01
d_model=128
d_ff=32
train_epochs=10
patience=10
batch_size=16
para='40,5,3,1,128'

python -u run.py \
  --task_name long_term_forecast \
  --is_training 0 \
  --root_path  ./dataset/coal/ \
  --csv_path ./inferresult/infer_result8.12_3800__$para.csv \
  --data_path 3800_infer8.12.csv \
  --model_id coal3800_TimeMixer2_$seq_len'_'40 \
  --model $model_name \
  --data coal \
  --features M \
  --target_features 3 \
  --seq_len $seq_len \
  --label_len 20 \
  --pred_len 20 \
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
  --do_predict 1