#!/bin/bash

echo "启动网站服务..."
echo "端口: 8088"
echo "目录: /home/lhc/Time-coal/autoinfer/html1/dist"

# 检查是否已运行
if [ -f "/tmp/web_server.pid" ]; then
    OLD_PID=$(cat /tmp/web_server.pid 2>/dev/null)
    if kill -0 $OLD_PID 2>/dev/null 2>/dev/null; then
        echo "网站服务已在运行 (PID: $OLD_PID)"
        exit 0
    fi
fi

# 停止旧进程
systemctl --user stop time-coal-web.service 2>/dev/null
pkill -f "http.server 8088" 2>/dev/null
pkill -f "dist_preview_server.py.*--port 8088" 2>/dev/null
sleep 1

# 创建日志目录
mkdir -p /home/lhc/Time-coal/services/logs

# 启动dist页面，并将同源/api请求代理到本机8081
systemd-run --user \
    --unit=time-coal-web \
    --description="Time-coal web service" \
    --working-directory=/home/lhc/Time-coal \
    --property=Restart=on-failure \
    --property=RestartSec=3 \
    --property=StandardOutput=append:/home/lhc/Time-coal/services/logs/web_server.log \
    --property=StandardError=append:/home/lhc/Time-coal/services/logs/web_server.log \
    /usr/bin/python3 services/dist_preview_server.py \
        --dist /home/lhc/Time-coal/autoinfer/html1/dist \
        --port 8088 >/dev/null

NEW_PID=""
for _ in 1 2 3 4 5; do
    NEW_PID=$(systemctl --user show time-coal-web.service -p MainPID --value 2>/dev/null)
    [ -n "$NEW_PID" ] && [ "$NEW_PID" != "0" ] && break
    sleep 1
done

# 保存PID
echo $NEW_PID > /tmp/web_server.pid

sleep 2
# 检查是否启动成功
if kill -0 $NEW_PID 2>/dev/null && ss -tln 2>/dev/null | grep -q ":8088 "; then
    HOST_IP=$(hostname -I | awk '{print $1}')
    echo "✓ 网站服务启动成功"
    echo "进程PID: $NEW_PID"
    echo "访问地址: http://${HOST_IP}:8088"
else
    echo "✗ 网站服务启动失败"
    tail -5 /home/lhc/Time-coal/services/logs/web_server.log
fi
