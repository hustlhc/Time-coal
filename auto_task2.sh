#!/bin/bash
# 2. 运行第二个任务docker exec -it coal2 /bin/bash
# 检查容器是否运行
if ! docker ps | grep -q coal2; then
    echo "Error: Docker container coal2 is not running"
    exit 1
fi
# 在docker容器中执行命令，使用绝对路径
# 先激活conda环境，然后执行Python脚本
COAL_FORECAST_MODE="${COAL_FORECAST_MODE:-legacy}"
docker exec coal2 bash -c "
    source /root/miniconda/etc/profile.d/conda.sh
    conda activate python310_torch25_cuda
    cd /home/Time-coal && python coal.py --forecast_mode ${COAL_FORECAST_MODE} --infer 1 && python transport.py --infer 1 && python huodian.py --infer 1 && python tojs.py && python elec_tojs.py 
    && python process.py 
    && cd autoinfer 
    && python fix_partial_runtime_unit_predictions.py 7
"
# 调整模型参数
#python adjust.py --current_model /home/chenty/Time-Series-Library/teninfer/CCI3800outinfer.csv --grid_folder /home/chenty/Time-Series-Library/choiceinfer/CCI进口3800 --threshold 0.8 --mape_threshold 0.6  --direction_threshold 0.2 --check_all --inference_scripts /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI3800out.sh /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI3800outinfer.sh
#python adjust.py --current_model /home/chenty/Time-Series-Library/teninfer/CCI4700outinfer.csv --grid_folder /home/chenty/Time-Series-Library/choiceinfer/CCI进口4700 --threshold 0.8 --mape_threshold 0.6  --direction_threshold 0.2 --check_all --inference_scripts /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI4700out.sh /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI4700outinfer.sh
#python adjust.py --current_model /home/chenty/Time-Series-Library/teninfer/CCI5500outinfer.csv --grid_folder /home/chenty/Time-Series-Library/choiceinfer/CCI进口5500 --threshold 0.8 --mape_threshold 0.6  --direction_threshold 0.2 --check_all --inference_scripts /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI5500out.sh /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI5500outinfer.sh
#python adjust.py --current_model /home/chenty/Time-Series-Library/teninfer/CCI4500infer.csv --grid_folder /home/chenty/Time-Series-Library/choiceinfer/CCI4500 --threshold 0.8 --mape_threshold 0.6  --direction_threshold 0.2 --check_all --inference_scripts /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI4500.sh /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI4500infer.sh --true_col -6
#python adjust.py --current_model /home/chenty/Time-Series-Library/teninfer/CCI5000infer.csv --grid_folder /home/chenty/Time-Series-Library/choiceinfer/CCI5000 --threshold 0.8 --mape_threshold 0.6  --direction_threshold 0.2 --check_all --inference_scripts /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI5000.sh /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI5000infer.sh --true_col -5
#python adjust.py --current_model /home/chenty/Time-Series-Library/teninfer/CCI5500infer.csv --grid_folder /home/chenty/Time-Series-Library/choiceinfer/CCI5500 --threshold 0.8 --mape_threshold 0.6  --direction_threshold 0.2 --check_all --inference_scripts /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI5500.sh /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/CCI5500infer.sh --true_col -4  
#python adjust.py --choice_script /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/transchoice.sh --current_model /home/chenty/Time-Series-Library/teninfer/insideinfer.csv --grid_folder /home/chenty/Time-Series-Library/choiceinfer/输入00000347--煤炭运费_水运价格_沿海煤炭运费_秦皇岛-厦门'(5-6万DWT)_本期(元/吨)' --threshold 0.8 --mape_threshold 0.6  --direction_threshold 0.2 --check_all --inference_scripts /home/chenty/Time-Series-Library/scripts/long_term_forecast/autotrans/inside.sh /home/chenty/Time-Series-Library/scripts/long_term_forecast/autotrans/insideinfer.sh --true_col -2  --data_file /home/chenty/Time-Series-Library/dataset/pre_coal/coal_freight.csv
#python adjust.py --choice_script /home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/transchoice.sh --current_model /home/chenty/Time-Series-Library/teninfer/outsideinfer.csv --grid_folder /home/chenty/Time-Series-Library/choiceinfer/输入00000351--煤炭运费_水运价格_进口煤炭运费_印尼萨马林达-中国广州_当期值'(美元/吨)' --threshold 0.8 --mape_threshold 0.6  --direction_threshold 0.2 --check_all --inference_scripts /home/chenty/Time-Series-Library/scripts/long_term_forecast/autotrans/outside.sh /home/chenty/Time-Series-Library/scripts/long_term_forecast/autotrans/outsideinfer.sh --true_col -1  --data_file /home/chenty/Time-Series-Library/dataset/pre_coal/coal_freight.csv
# 可选：打印日志
