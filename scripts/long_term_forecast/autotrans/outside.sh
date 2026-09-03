
model_name=TimeMixer

seq_len=120
e_layers=3
down_sampling_layers=3
down_sampling_window=2
learning_rate=0.001
d_model=64
d_ff=16
train_epochs=10
patience=10
batch_size=16
moving_avg=25

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --do_finetune 0 \
  --root_path  ./dataset/pre_coal/ \
  --csv_path ./testresult/outside.csv \
  --data_path coal_freight.csv \
  --model_id autotransout_TimeMixer_$seq_len'_'120 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 1 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 120 \
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
  --is_full_training 1 \
  --moving_avg $moving_avg \
  --target '输入00000351--煤炭运费_水运价格_进口煤炭运费_印尼萨马林达-中国广州_当期值(美元/吨)' 