
model_name=Transformer

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --root_path ./dataset/coal/ \
  --data_path coal_3800new.csv \
  --csv_path ./inferresult/tsfresult_3800.csv \
  --model_id transformercoal3800_96_96 \
  --model $model_name \
  --data coal \
  --features MS \
  --seq_len 60 \
  --label_len 20 \
  --pred_len 20 \
  --e_layers 2 \
  --d_layers 1 \
  --factor 3 \
  --enc_in 100 \
  --dec_in 100 \
  --c_out 100 \
  --des 'Exp' \
  --itr 1