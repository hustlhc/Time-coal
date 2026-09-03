#!/bin/bash

PID_FILE="/tmp/https_server.pid"
echo "停止HTTPS网站服务..."

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$PID" ] && kill -0 $PID 2>/dev/null; then
        kill -9 $PID 2>/dev/null
        echo "已停止进程 $PID"
    fi
    rm -f "$PID_FILE"
fi

# 清理残留进程
pkill -f "https_server_.*\.py" 2>/dev/null

echo "HTTPS服务已停止"
