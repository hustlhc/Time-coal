
model_name=TimeMixer


down_sampling_layers=3
learning_rate=0.001
train_epochs=10
patience=10

for seq_len in 80 88 96
do
    label_len=$((seq_len / 2))
    for e_layers in 2 3 4
    do
        for d_model in 16 32 64
        do
            for batch_size in 16 32 64
            do
                for d_ff in 16 32 64
                do
                    for down_sampling_window in 1 2
                    do
                        python -u run.py \
                        --task_name long_term_forecast \
                        --is_training 1 \
                        --root_path  ./dataset/pre_coal/ \
                        --csv_path ./transresult/trans_out_result_${seq_len}_${e_layers}_${d_model}_${batch_size}_${d_ff}_${down_sampling_window}.csv \
                        --data_path coal_freight.csv \
                        --model_id trans_TimeMixer_$seq_len'_'60 \
                        --model $model_name \
                        --data coal \
                        --features MS \
                        --target_features 1 \
                        --is_testing 1 \
                        --seq_len $seq_len \
                        --label_len $label_len \
                        --pred_len 60 \
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
                        --trans 1 \
                        --is_full_training 1 \
                        --target '输入00000351--煤炭运费_水运价格_进口煤炭运费_印尼萨马林达-中国广州_当期值(美元/吨)' \
                        2>&1 | tee -a auto_gridtrans_outside1_search_results.log
                    done
                done
            done
        done
    done
done

