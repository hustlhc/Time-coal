#!/bin/bash

echo "========================================"
echo "     启动煤价系统所有服务"
echo "========================================"
echo "启动时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 创建日志目录
PROJECT_ROOT="/home/lhc/Time-coal"
SERVICE_DIR="$PROJECT_ROOT/services"
mkdir -p "$SERVICE_DIR/logs"

# 停止可能存在的旧服务
echo "[1/6] 清理旧进程..."
pkill -f "http.server 8088" 2>/dev/null
pkill -f "api_server_stdlib.py" 2>/dev/null
sleep 2

# 清理端口占用
echo "[2/6] 清理端口..."
if command -v fuser >/dev/null 2>&1; then
    fuser -k 8088/tcp 2>/dev/null
    fuser -k 8081/tcp 2>/dev/null
    sleep 1
fi

# 移除旧的PID文件
rm -f /tmp/web_server.pid /tmp/api_server.pid 2>/dev/null

# 启动网站服务
echo "[3/6] 启动网站服务(端口:8088)..."
"$SERVICE_DIR/web_server.sh"
WEB_PID=$(cat /tmp/web_server.pid 2>/dev/null)

# 启动API服务
echo "[4/6] 启动API服务(端口:8081)..."
"$SERVICE_DIR/api_server.sh"
API_PID=$(cat /tmp/api_server.pid 2>/dev/null)

# 等待服务初始化
echo "[5/6] 等待服务初始化..."
sleep 3

# 验证启动结果
echo "[6/6] 验证服务状态..."
echo ""

# 检查进程
echo "进程状态:"
if kill -0 $WEB_PID 2>/dev/null; then
    echo "  ✓ 网站服务: 运行中 (PID: $WEB_PID)"
else
    echo "  ✗ 网站服务: 启动失败"
fi

if kill -0 $API_PID 2>/dev/null; then
    echo "  ✓ API服务:  运行中 (PID: $API_PID)"
else
    echo "  ✗ API服务:  启动失败"
fi

echo ""
echo "端口状态:"
if ss -tln 2>/dev/null | grep -q ":8088 "; then
    echo "  ✓ 端口8088: 监听中"
else
    echo "  ✗ 端口8088: 未监听"
fi

echo ""
echo "========================================"
echo "服务启动完成！"
echo ""
echo "访问地址:"
echo "  网站服务: http://localhost:8088"
echo "  API服务:  http://localhost:8081"
echo ""
echo "管理命令:"
echo "  停止服务: ./stop_all.sh"
echo "  查看状态: ./status.sh"
echo "  重启服务: ./restart_all.sh"
echo "========================================"
