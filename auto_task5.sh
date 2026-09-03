#!/bin/bash
# 2. 运行第二个任务docker exec -it coal2 /bin/bash
# 检查容器是否运行
if ! docker ps | grep -q coal2; then
    echo "Error: Docker container coal2 is not running"
    exit 1
fi
# 在docker容器中执行命令，使用绝对路径
# 先激活conda环境，然后执行Python脚本
docker exec coal2 bash -c "
    source /root/miniconda/etc/profile.d/conda.sh
    conda activate python310_torch25_cuda
    cd /home/Time-coal && python generate_complete_excel.py
"