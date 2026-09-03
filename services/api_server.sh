#!/bin/bash

echo "启动API服务..."
echo "端口: 8081"
echo "脚本: api_server_stdlib.py"

# 检查是否已运行
if [ -f "/tmp/api_server.pid" ]; then
    OLD_PID=$(cat /tmp/api_server.pid 2>/dev/null)
    if kill -0 $OLD_PID 2>/dev/null 2>/dev/null; then
        echo "API服务已在运行 (PID: $OLD_PID)"
        exit 0
    fi
fi

# 停止旧进程
systemctl --user stop time-coal-api.service 2>/dev/null
pkill -f "api_server_stdlib.py" 2>/dev/null
sleep 1

# 创建日志目录
mkdir -p /home/lhc/Time-coal/services/logs

# 启动服务 - 由用户级systemd托管，避免终端退出后服务结束
systemd-run --user \
    --unit=time-coal-api \
    --description="Time-coal API service" \
    --working-directory=/home/lhc/Time-coal/autoinfer \
    --property=Restart=on-failure \
    --property=RestartSec=3 \
    --property=StandardOutput=append:/home/lhc/Time-coal/services/logs/api_server.log \
    --property=StandardError=append:/home/lhc/Time-coal/services/logs/api_server.log \
    /usr/bin/python3 api_server_stdlib.py >/dev/null

NEW_PID=""
for _ in 1 2 3 4 5; do
    NEW_PID=$(systemctl --user show time-coal-api.service -p MainPID --value 2>/dev/null)
    [ -n "$NEW_PID" ] && [ "$NEW_PID" != "0" ] && break
    sleep 1
done

# 保存PID
echo $NEW_PID > /tmp/api_server.pid

sleep 3
# 检查是否启动成功
if kill -0 $NEW_PID 2>/dev/null && ss -tln 2>/dev/null | grep -q ":8081 "; then
    HOST_IP=$(hostname -I | awk '{print $1}')
    echo "✓ API服务启动成功"
    echo "进程PID: $NEW_PID"
    echo "访问地址: http://${HOST_IP}:8081"
else
    echo "✗ API服务启动失败"
    tail -5 /home/lhc/Time-coal/services/logs/api_server.log
fi
