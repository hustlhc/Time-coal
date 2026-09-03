model_name=TimeXer

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --root_path ./dataset/coal/ \
  --data_path coal_3800.csv \
  --model_id TimeXer_coal3800_40_20 \
  --model $model_name \
  --data coal \
  --features MS \
  --seq_len 40 \
  --label_len 20 \
  --pred_len 20 \
  --e_layers 1 \
  --factor 3 \
  --enc_in 101 \
  --dec_in 101 \
  --c_out 101 \
  --d_model 256 \
  --batch_size 8 \
  --des 'exp' \
  --itr 1
