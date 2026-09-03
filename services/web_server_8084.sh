#!/bin/bash

echo "启动网站服务(dist)..."
echo "端口: 8084"
echo "目录: /home/lhc/Time-coal/autoinfer/html1/dist"

# 检查是否已运行
if [ -f "/tmp/web_server_8084.pid" ]; then
    OLD_PID=$(cat /tmp/web_server_8084.pid 2>/dev/null)
    if kill -0 $OLD_PID 2>/dev/null 2>/dev/null; then
        echo "网站服务(dist)已在运行 (PID: $OLD_PID)"
        exit 0
    fi
fi

# 停止旧进程
pkill -f "http.server 8084" 2>/dev/null
sleep 1

# 创建日志目录
mkdir -p /home/lhc/Time-coal/services/logs

# 启动服务 - 使用完整路径
cd /home/lhc/Time-coal/autoinfer/html1/dist
nohup python3 -m http.server 8084 >> /home/lhc/Time-coal/services/logs/web_server_8084.log 2>&1 &
NEW_PID=$!

# 保存PID
echo $NEW_PID > /tmp/web_server_8084.pid

sleep 2
# 检查是否启动成功
if kill -0 $NEW_PID 2>/dev/null && ss -tln 2>/dev/null | grep -q ":8084 "; then
    echo "✓ 网站服务(dist)启动成功"
    echo "进程PID: $NEW_PID"
    echo "访问地址: http://10.73.56.38:8084"
else
    echo "✗ 网站服务(dist)启动失败"
    tail -5 /home/lhc/Time-coal/services/logs/web_server_8084.log
fi
