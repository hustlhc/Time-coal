#!/bin/bash

echo "启动全服务监控（HTTP + HTTPS + API）..."
echo "监控间隔: 30秒"
echo "日志文件: /home/lhc/Time-coal/services/logs/monitor_https.log"
echo ""

mkdir -p /home/lhc/Time-coal/services/logs

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> /home/lhc/Time-coal/services/logs/monitor_https.log
}

# 检查服务
check_service() {
    local name="$1"
    local pid_file="$2"
    local port="$3"
    local is_https="$4"
    
    # 检查PID文件
    if [ ! -f "$pid_file" ]; then
        log "$name PID文件不存在"
        return 1
    fi
    
    local pid=$(cat "$pid_file" 2>/dev/null)
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        log "$name 进程 $pid 不存在"
        return 1
    fi
    
    # 检查端口
    if ! ss -tln 2>/dev/null | grep -q ":$port "; then
        log "$name 端口 $port 未监听"
        return 1
    fi
    
    return 0
}

# 重启服务
restart_https() {
    log "重启HTTPS服务..."
    /home/lhc/Time-coal/services/stop_https.sh >/dev/null 2>&1
    sleep 2
    /home/lhc/Time-coal/services/https_server.sh >/dev/null 2>&1
    log "HTTPS服务重启完成"
}

restart_web() {
    log "重启HTTP网站服务..."
    /home/lhc/Time-coal/services/stop_web.sh >/dev/null 2>&1
    sleep 2
    /home/lhc/Time-coal/services/web_server.sh >/dev/null 2>&1
    log "HTTP网站服务重启完成"
}

restart_api() {
    log "重启API服务..."
    /home/lhc/Time-coal/services/stop_api.sh >/dev/null 2>&1
    sleep 2
    /home/lhc/Time-coal/services/api_server.sh >/dev/null 2>&1
    log "API服务重启完成"
}

log "全服务监控启动"

while true; do
    # 检查HTTP网站服务 (8001)
    if ! check_service "HTTP网站" "/tmp/web_server.pid" "8001" "0"; then
        restart_web
    fi
    
    # 检查HTTPS网站服务 (8443)
    if ! check_service "HTTPS网站" "/tmp/https_server.pid" "8443" "1"; then
        restart_https
    fi
    
    # 检查API服务 (8081)
    if ! check_service "API服务" "/tmp/api_server.pid" "8081" "0"; then
        restart_api
    fi
    
    sleep 30
done
