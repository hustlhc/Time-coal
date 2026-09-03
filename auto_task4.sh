#!/bin/bash
#进行采需决策
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
    cd /home/Time-coal/Qwen && python update_user_inputs.py && python gre_coal.py && python test_chat_single.py kemen && python test_chat_single.py shaowu && python test_chat_single.py yongan && python test_chat_single.py zhangping
"
