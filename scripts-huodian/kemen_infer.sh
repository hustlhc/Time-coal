
model_name=TimeMixer

seq_len=32
e_layers=4
down_sampling_layers=3
down_sampling_window=1
learning_rate=0.001
d_model=64
d_ff=16
train_epochs=10
patience=10
batch_size=16
moving_avg=15

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --delt 0 \
  --root_path  ./dataset-huodian \
  --csv_path ./autoinfer/elecdata/kemen_1.csv \
  --data_path kemen_1.csv \
  --model_id akemen1_TimeMixer_$seq_len'_'60 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 0 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 90 \
  --e_layers $e_layers \
  --enc_in 29 \
  --c_out 29 \
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
  --is_full_training 1 \
  --target '可门_可门#1_发电量' \
  --moving_avg $moving_avg

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --delt 0 \
  --root_path  ./dataset-huodian \
  --csv_path ./autoinfer/elecdata/kemen_2.csv \
  --data_path kemen_2.csv \
  --model_id akemen2_TimeMixer_$seq_len'_'60 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 0 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 90 \
  --e_layers $e_layers \
  --enc_in 29 \
  --c_out 29 \
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
  --is_full_training 1 \
  --target '可门_可门#2_发电量' \
  --moving_avg $moving_avg


python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --delt 0 \
  --root_path  ./dataset-huodian \
  --csv_path ./autoinfer/elecdata/kemen_3.csv \
  --data_path kemen_3.csv \
  --model_id akemen3_TimeMixer_$seq_len'_'60 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 0 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 90 \
  --e_layers $e_layers \
  --enc_in 29 \
  --c_out 29 \
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
  --is_full_training 1 \
  --target '可门_可门#3_发电量' \
  --moving_avg $moving_avg

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --delt 0 \
  --root_path  ./dataset-huodian \
  --csv_path ./autoinfer/elecdata/kemen_4.csv \
  --data_path kemen_4.csv \
  --model_id akemen4_TimeMixer_$seq_len'_'60 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 0 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 90 \
  --e_layers $e_layers \
  --enc_in 29 \
  --c_out 29 \
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
  --is_full_training 1 \
  --target '可门_可门#4_发电量' \
  --moving_avg $moving_avg

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --delt 0 \
  --root_path  ./dataset-huodian \
  --csv_path ./autoinfer/elecdata/kemen_5.csv \
  --data_path kemen_5.csv \
  --model_id akemen5_TimeMixer_$seq_len'_'60 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 0 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 90 \
  --e_layers $e_layers \
  --enc_in 29 \
  --c_out 29 \
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
  --is_full_training 1 \
  --target '可门_可门#5_发电量' \
  --moving_avg $moving_avg

  python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --delt 0 \
  --root_path  ./dataset-huodian \
  --csv_path ./autoinfer/elecdata/kemen_6.csv \
  --data_path kemen_6.csv \
  --model_id akemen6_TimeMixer_$seq_len'_'60 \
  --model $model_name \
  --data coal \
  --features MS \
  --target_features 1 \
  --is_testing 0 \
  --seq_len $seq_len \
  --label_len $((seq_len / 2)) \
  --pred_len 90 \
  --e_layers $e_layers \
  --enc_in 29 \
  --c_out 29 \
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
  --is_full_training 1 \
  --target '可门_可门#6_发电量' \
  --moving_avg $moving_avg