model_name=TimesNet

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --root_path ./dataset/coal/ \
  --data_path coal_3800.csv \
  --model_id coal_seqlen40_predlen20 \
  --model $model_name \
  --data coal \
  --features MS \
  --seq_len 40 \
  --label_len 20 \
  --pred_len 20 \
  --e_layers 2 \
  --d_layers 1 \
  --factor 3 \
  --enc_in 101 \
  --dec_in 101 \
  --c_out 101 \
  --d_model 16 \
  --d_ff 32 \
  --des 'Exp' \
  --itr 1 \
  --top_k 5 