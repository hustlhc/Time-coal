#!/bin/bash

echo "========================================"
echo "     停止煤价系统所有服务"
echo "========================================"
echo "停止时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 先停止用户级systemd单元，防止直接结束进程后被自动拉起
systemctl --user stop time-coal-web.service time-coal-api.service 2>/dev/null

# 停止网站服务
echo "[1/5] 停止网站服务(8088)..."
if [ -f "/tmp/web_server.pid" ]; then
    WEB_PID=$(cat /tmp/web_server.pid 2>/dev/null)
    if [ -n "$WEB_PID" ] && kill -0 $WEB_PID 2>/dev/null; then
        echo "  停止进程 $WEB_PID..."
        kill -9 $WEB_PID 2>/dev/null
        echo "  ✓ 网站服务(8088)已停止"
    else
        echo "  ℹ️  网站进程(8088)不存在"
    fi
    rm -f /tmp/web_server.pid 2>/dev/null
else
    echo "  ℹ️  网站服务(8088)未运行"
fi

# 停止网站服务(dist)
echo "[2/5] 停止网站服务dist(8084)..."
if [ -f "/tmp/web_server_8084.pid" ]; then
    WEB_PID=$(cat /tmp/web_server_8084.pid 2>/dev/null)
    if [ -n "$WEB_PID" ] && kill -0 $WEB_PID 2>/dev/null; then
        echo "  停止进程 $WEB_PID..."
        kill -9 $WEB_PID 2>/dev/null
        echo "  ✓ 网站服务dist(8084)已停止"
    else
        echo "  ℹ️  网站进程dist(8084)不存在"
    fi
    rm -f /tmp/web_server_8084.pid 2>/dev/null
else
    echo "  ℹ️  网站服务dist(8084)未运行"
fi

# 停止API服务
echo "[3/5] 停止API服务..."
if [ -f "/tmp/api_server.pid" ]; then
    API_PID=$(cat /tmp/api_server.pid 2>/dev/null)
    if [ -n "$API_PID" ] && kill -0 $API_PID 2>/dev/null; then
        echo "  停止进程 $API_PID..."
        kill -9 $API_PID 2>/dev/null
        echo "  ✓ API服务已停止"
    else
        echo "  ℹ️  API进程不存在"
    fi
    rm -f /tmp/api_server.pid 2>/dev/null
else
    echo "  ℹ️  API服务未运行"
fi

# 清理端口占用
echo "[4/5] 清理端口占用..."
if command -v fuser >/dev/null 2>&1; then
    fuser -k 8001/tcp 2>/dev/null
    fuser -k 8081/tcp 2>/dev/null
    fuser -k 8084/tcp 2>/dev/null
    fuser -k 8088/tcp 2>/dev/null
    echo "  ✓ 端口已清理"
else
    echo "  ℹ️  fuser命令不可用，跳过端口清理"
fi

# 清理监控进程
echo "[5/5] 清理监控进程..."
pkill -f "monitor_services.sh" 2>/dev/null
echo "  ✓ 监控进程已清理"

echo ""
echo "========================================"
echo "所有服务已停止"
echo "========================================"
