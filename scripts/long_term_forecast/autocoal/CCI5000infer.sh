
model_name=TimeMixer

seq_len=32
e_layers=3
down_sampling_layers=3
down_sampling_window=1
learning_rate=0.001
d_model=32
d_ff=16
train_epochs=10
patience=10
batch_size=16
moving_avg=15

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --root_path  ./dataset/pre_coal/ \
  --csv_path ./autoinfer/CCI5000infer.csv \
  --data_path coal_new.csv \
  --model_id CCI5000_TimeMixerauto_$seq_len'_'120 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 1 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 120 \
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
  --do_predict 1 \
  --moving_avg $moving_avg \
  --target 'CCI5000' \
  #--gpu_type ${GPU_TYPE:-xpu} 

python autoinfer/smooth2.py autoinfer/CCI5000infer.csv autoinfer/CCI5000infer.csv --round --true-col -5

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --root_path  ./dataset/pre_coal/ \
  --csv_path ./teninfer/CCI5000infer.csv \
  --data_path coal_new.csv \
  --model_id CCI5000_TimeMixerauto_$seq_len'_'120 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 1 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 120 \
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
  --do_predict 1 \
  --last_ten 1 \
  --moving_avg $moving_avg \
  --target 'CCI5000' \
  #--gpu_type ${GPU_TYPE:-xpu} 