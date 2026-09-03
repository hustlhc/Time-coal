#!/bin/bash

echo "========================================="
echo "    模拟系统重启 - 服务自启动测试"
echo "========================================="
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. 记录当前状态
echo "[1/6] 记录当前服务状态..."
./status.sh > /tmp/status_before.log
echo "  已保存到: /tmp/status_before.log"

# 2. 停止所有服务
echo "[2/6] 停止所有服务（模拟关机）..."
./stop_all.sh
sleep 2

# 3. 强制清理
echo "[3/6] 强制清理残留进程..."
pkill -f "http.server" 2>/dev/null
pkill -f "api_server" 2>/dev/null
pkill -f "https_server" 2>/dev/null
pkill -f "monitor" 2>/dev/null
rm -f /tmp/*.pid 2>/dev/null
sudo fuser -k 8001/tcp 2>/dev/null
sudo fuser -k 8081/tcp 2>/dev/null
sudo fuser -k 8443/tcp 2>/dev/null
sudo fuser -k 8444/tcp 2>/dev/null
sleep 3

# 4. 验证服务已停止
echo "[4/6] 验证服务已停止..."
if ss -tln | grep -E "8001|8081|8443|8444" > /dev/null; then
    echo "  ⚠️  警告: 仍有服务在运行"
    ss -tln | grep -E "8001|8081|8443|8444"
else
    echo "  ✓ 所有服务已停止"
fi
echo ""

# 5. 模拟开机启动
echo "[5/6] 模拟开机启动（执行@reboot）..."
echo "  等待30秒（模拟系统启动延迟）..."
sleep 30

echo "  执行: cd /home/lhc/Time-coal/services && ./start_all_https.sh"
cd /home/lhc/Time-coal/services && ./start_all_https.sh

echo "  等待服务启动..."
sleep 15

# 6. 验证服务状态
echo "[6/6] 验证服务状态..."
echo ""

echo "=== 服务端口状态 ==="
ss -tln | grep -E "8001|8081|8443|8444" || echo "无服务监听"

echo ""
echo "=== 服务进程状态 ==="
ps aux | grep -E "http.server|api_server|https_server|monitor" | grep -v grep

echo ""
echo "=== 服务访问测试 ==="
echo -n "HTTP网站 (8001): "
curl -s -o /dev/null -w "%{http_code}\n" http://10.73.56.38:8001 2>/dev/null || echo "失败"

echo -n "HTTPS网站 (8443): "
curl -k -s -o /dev/null -w "%{http_code}\n" https://10.73.56.38:8443 2>/dev/null || echo "失败"

echo -n "HTTP API (8081): "
curl -s -o /dev/null -w "%{http_code}\n" http://10.73.56.38:8081/api/data_types 2>/dev/null || echo "失败"

echo -n "HTTPS API (8444): "
curl -k -s -o /dev/null -w "%{http_code}\n" https://10.73.56.38:8444/api/data_types 2>/dev/null || echo "失败"

echo ""
echo "=== 最终服务状态 ==="
./status.sh

echo ""
echo "========================================="
echo "测试完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="

# 保存测试结果
{
    echo "========================================="
    echo "重启模拟测试报告 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================="
    echo ""
    echo "测试前状态:"
    cat /tmp/status_before.log
    echo ""
    echo "测试后状态:"
    ./status.sh
} > /tmp/reboot_test_$(date +%Y%m%d_%H%M%S).log

echo ""
echo "测试报告已保存到: /tmp/reboot_test_*.log"
