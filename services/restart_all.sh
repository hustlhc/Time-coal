#!/bin/bash

echo "========================================"
echo "     重启煤价系统所有服务"
echo "========================================"
echo "重启时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 停止服务
echo "[1/3] 停止服务..."
./stop_all.sh >/dev/null 2>&1
sleep 2

# 启动服务
echo "[2/3] 启动服务..."
./start_all.sh

# 启动监控
echo "[3/3] 启动监控..."
nohup ./monitor_services.sh >> /home/lhc/Time-coal/services/logs/monitor.log 2>&1 &

echo ""
echo "========================================"
echo "服务重启完成"
echo "========================================"
