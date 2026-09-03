
python -u run.py \
  --task_name classification \
  --is_training 1 \
  --root_path ./dataset/coalacc/ \
  --model_id coalclassic \
  --model TimeMixer \
  --data UEA \
  --e_layers 2 \
  --batch_size 128 \
  --d_model 16 \
  --d_ff 32 \
  --des 'Exp' \
  --itr 1 \
  --learning_rate 0.001 \
  --train_epochs 30 \
  --patience 10