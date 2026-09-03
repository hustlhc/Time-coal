#!/bin/bash

# HTTPS API服务
API_SCRIPT="/home/lhc/Time-coal/autoinfer/api_server_https.py"
HTTPS_API_PORT="8444"
PID_FILE="/tmp/api_https.pid"
LOG_DIR="/home/lhc/Time-coal/services/logs"
SSL_DIR="/home/lhc/Time-coal/services/ssl"

echo "启动HTTPS API服务(端口: $HTTPS_API_PORT)..."

# 创建日志目录
mkdir -p "$LOG_DIR"
mkdir -p "$SSL_DIR"

# 检查证书
if [ ! -f "$SSL_DIR/server.crt" ]; then
    echo "SSL证书不存在，请先启动HTTPS网站服务..."
    exit 1
fi

# 检查API脚本是否存在
if [ ! -f "$API_SCRIPT" ]; then
    echo "错误: HTTPS API脚本不存在!"
    exit 1
fi

# 停止旧服务
pkill -f "api_server_https.py" 2>/dev/null
sleep 2
rm -f "$PID_FILE" 2>/dev/null

# 启动HTTPS API
cd /home/lhc/Time-coal/autoinfer
nohup python3 api_server_https.py >> "$LOG_DIR/api_https.log" 2>&1 &
API_PID=$!

# 保存PID
echo $API_PID > "$PID_FILE"
echo "HTTPS API服务启动命令已执行"
echo "PID: $API_PID"

# 等待5秒确保启动
sleep 5

# 检查进程
if ps -p $API_PID > /dev/null 2>&1; then
    echo "进程状态: ✓ 运行中"
else
    echo "进程状态: ✗ 已退出"
fi

# 检查端口
if ss -tln 2>/dev/null | grep -q ":$HTTPS_API_PORT "; then
    echo "端口状态: ✓ 监听中 (端口 $HTTPS_API_PORT)"
    echo ""
    echo "✅ HTTPS API服务启动成功!"
    echo "访问: https://10.73.56.38:$HTTPS_API_PORT"
    echo "测试: curl -k https://10.73.56.38:$HTTPS_API_PORT/api/data_types"
else
    echo "端口状态: ✗ 未监听"
    echo ""
    echo "错误日志:"
    tail -20 "$LOG_DIR/api_https.log"
fi
