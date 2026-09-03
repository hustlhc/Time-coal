model_name=Mamba
for pred_len in 20
do

python -u run.py \
  --task_name long_term_forecast \
  --is_training 1 \
  --root_path ./dataset/coal/ \
  --data_path coal_3800.csv \
  --model_id Mamba_coal3800_$pred_len'_'$pred_len \
  --model $model_name \
  --data coal \
  --features MS \
  --seq_len 40 \
  --label_len 20 \
  --pred_len $pred_len \
  --e_layers 2 \
  --d_layers 1 \
  --enc_in 101 \
  --expand 2 \
  --d_ff 16 \
  --d_conv 4 \
  --c_out 101 \
  --d_model 128 \
  --des 'Exp' \
  --itr 1 \

done