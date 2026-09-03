#!/bin/bash
# auto_task.sh

# 使用 bash 的 login shell，确保 conda 环境变量加载
source /home/coal/miniconda3/etc/profile.d/conda.sh
set -e 
# 1. 运行第一个任务
conda activate data
python v4/run_incremental.py --backfill 1
cd dataset-huodian
python fetch_date_data.py 3 && python json_to_csv.py && python process.py && python disard.py

# 可选：打印日志
echo "$(date '+%Y-%m-%d %H:%M:%S') Task1 finished." >> /home/coal/Time-coal/auto.log

