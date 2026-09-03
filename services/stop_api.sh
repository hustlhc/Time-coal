#!/bin/bash

echo "停止API服务..."

systemctl --user stop time-coal-api.service 2>/dev/null

if [ -f "/tmp/api_server.pid" ]; then
    PID=$(cat /tmp/api_server.pid 2>/dev/null)
    if [ -n "$PID" ] && kill -0 $PID 2>/dev/null; then
        echo "停止进程 $PID..."
        kill -9 $PID 2>/dev/null
        echo "API服务已停止"
    else
        echo "API进程不存在"
    fi
    rm -f /tmp/api_server.pid
else
    echo "API服务未运行"
fi

# 清理端口
if command -v fuser >/dev/null 2>&1; then
    fuser -k 8081/tcp 2>/dev/null
fi
