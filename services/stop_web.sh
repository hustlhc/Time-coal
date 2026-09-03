#!/bin/bash

echo "停止网站服务..."

systemctl --user stop time-coal-web.service 2>/dev/null

if [ -f "/tmp/web_server.pid" ]; then
    PID=$(cat /tmp/web_server.pid 2>/dev/null)
    if [ -n "$PID" ] && kill -0 $PID 2>/dev/null; then
        echo "停止进程 $PID..."
        kill -9 $PID 2>/dev/null
        echo "网站服务已停止"
    else
        echo "网站进程不存在"
    fi
    rm -f /tmp/web_server.pid
else
    echo "网站服务未运行"
fi

# 清理端口
if command -v fuser >/dev/null 2>&1; then
    fuser -k 8088/tcp 2>/dev/null
fi
