#!/bin/bash

echo "========================================"
echo "       煤价系统服务状态"
echo "========================================"
echo "检查时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 获取本机IP
HOST_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "127.0.0.1")

# 网站服务状态
echo "[网站服务]"
echo "  端口: 8088"
echo "  目录: /home/lhc/Time-coal/autoinfer/html1/dist"

if [ -f "/tmp/web_server.pid" ]; then
    WEB_PID=$(cat /tmp/web_server.pid 2>/dev/null)
    if [ -n "$WEB_PID" ] && kill -0 $WEB_PID 2>/dev/null; then
        echo "  进程: ✓ 运行中 (PID: $WEB_PID)"
        
        # 获取运行时间
        if command -v ps >/dev/null 2>&1; then
            ETIME=$(ps -p $WEB_PID -o etime= 2>/dev/null | tr -d ' ' || echo "未知")
            echo "  运行时间: $ETIME"
        fi
    else
        echo "  进程: ✗ 进程不存在"
    fi
else
    echo "  进程: ✗ 未运行"
fi

# 检查端口
if ss -tln 2>/dev/null | grep -q ":8088 "; then
    echo "  端口: ✓ 监听中"
else
    echo "  端口: ✗ 未监听"
fi

# 测试访问
echo -n "  访问: "
if timeout 2 curl --noproxy '*' -s http://localhost:8088 >/dev/null 2>&1; then
    echo "✓ 正常"
else
    echo "✗ 异常"
fi
echo "  URL: http://${HOST_IP}:8088"

echo ""

# API服务状态
echo "[API服务]"
echo "  端口: 8081"
echo "  脚本: api_server_stdlib.py"

if [ -f "/tmp/api_server.pid" ]; then
    API_PID=$(cat /tmp/api_server.pid 2>/dev/null)
    if [ -n "$API_PID" ] && kill -0 $API_PID 2>/dev/null; then
        echo "  进程: ✓ 运行中 (PID: $API_PID)"
        
        # 获取运行时间
        if command -v ps >/dev/null 2>&1; then
            ETIME=$(ps -p $API_PID -o etime= 2>/dev/null | tr -d ' ' || echo "未知")
            echo "  运行时间: $ETIME"
        fi
    else
        echo "  进程: ✗ 进程不存在"
    fi
else
    echo "  进程: ✗ 未运行"
fi

# 检查端口
if ss -tln 2>/dev/null | grep -q ":8081 "; then
    echo "  端口: ✓ 监听中"
else
    echo "  端口: ✗ 未监听"
fi

# 测试访问
echo -n "  访问: "
if timeout 2 curl --noproxy '*' -s http://localhost:8081 >/dev/null 2>&1; then
    echo "✓ 正常"
else
    echo "✗ 异常"
fi
echo "  URL: http://${HOST_IP}:8081"

echo ""

# 监控状态
echo "[监控服务]"
MONITOR_PID=$(ps aux 2>/dev/null | grep "monitor_services.sh" | grep -v grep | awk '{print $2}')
if [ -n "$MONITOR_PID" ]; then
    echo "  状态: ✓ 运行中 (PID: $MONITOR_PID)"
else
    echo "  状态: ✗ 未运行"
fi

echo ""

# 系统信息
echo "[系统信息]"
echo "  主机IP: ${HOST_IP}"
echo "  系统负载: $(uptime | awk -F'load average:' '{print $2}')"
echo "  内存使用: $(free -h | awk '/^Mem:/ {print $3"/"$2}')"
echo "  磁盘使用: $(df -h /home | awk 'NR==2 {print $5}')"

echo ""
echo "========================================"
echo "管理命令:"
echo "  ./start_all.sh     # 启动所有服务"
echo "  ./stop_all.sh      # 停止所有服务"
echo "  ./restart_all.sh   # 重启所有服务"
echo "  ./monitor_services.sh  # 启动监控"
echo "========================================"
