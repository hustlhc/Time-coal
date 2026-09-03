#!/bin/bash

echo "启动服务监控（HTTP + HTTPS 双栈模式）..."
echo "监控间隔: 30秒"
echo "日志文件: /home/lhc/Time-coal/services/logs/monitor.log"
echo ""

LOG_DIR="/home/lhc/Time-coal/services/logs"
mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/monitor.log"
}

check_port() {
    local port=$1
    ss -tln 2>/dev/null | grep -q ":$port "
    return $?
}

check_pid() {
    local pid_file=$1
    local service_name=$2
    local process_pattern=$3
    
    if [ -n "$process_pattern" ]; then
        local pid=$(pgrep -f "$process_pattern" 2>/dev/null)
        if [ -z "$pid" ]; then
            log "$service_name 进程不存在"
            return 1
        fi
        return 0
    fi
    
    if [ ! -f "$pid_file" ]; then
        log "$service_name PID文件不存在"
        return 1
    fi
    
    local pid=$(cat "$pid_file" 2>/dev/null)
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        log "$service_name 进程 $pid 不存在"
        return 1
    fi
    
    return 0
}

restart_service() {
    local service_name=$1
    local script_name=$2
    
    log "重启 $service_name ..."
    
    case $service_name in
        "HTTP网站")
            /home/lhc/Time-coal/services/stop_web.sh >/dev/null 2>&1
            sleep 2
            /home/lhc/Time-coal/services/web_server.sh >/dev/null 2>&1
            ;;
        "HTTPS网站")
            pkill -f "https_server" 2>/dev/null
            sleep 2
            /home/lhc/Time-coal/services/https_server.sh >/dev/null 2>&1
            ;;
        "HTTP网站(dist)")
            pkill -f "http.server 8084" 2>/dev/null
            sleep 2
            /home/lhc/Time-coal/services/web_server_8084.sh >/dev/null 2>&1
            ;;
        "HTTPS网站(dist)")
            pkill -f "https_server_8084.py" 2>/dev/null
            sleep 2
            /home/lhc/Time-coal/services/https_server_8084.sh >/dev/null 2>&1
            ;;
        "HTTP API")
            /home/lhc/Time-coal/services/stop_api.sh >/dev/null 2>&1
            sleep 2
            /home/lhc/Time-coal/services/api_server.sh >/dev/null 2>&1
            ;;
        "HTTPS API")
            pkill -f "api_server_https" 2>/dev/null
            sleep 2
            /home/lhc/Time-coal/services/api_https.sh >/dev/null 2>&1
            ;;
    esac
    
    log "$service_name 重启完成"
}

log "========== 服务监控启动 =========="
log "监控服务: HTTP网站(8088), HTTPS网站(8443), HTTP网站dist(8084), HTTPS网站dist(8445), HTTP API(8081), HTTPS API(8444)"

while true; do
    # 1. 检查HTTP网站 (8088)
    if ! check_port 8088 || ! check_pid "/tmp/web_server.pid" "HTTP网站"; then
        restart_service "HTTP网站" "web_server.sh"
    fi
    
    # 2. 检查HTTPS网站 (8443)
    if ! check_port 8443 || ! check_pid "/tmp/https_server.pid" "HTTPS网站"; then
        restart_service "HTTPS网站" "https_server.sh"
    fi
    
    # 3. 检查HTTP网站dist (8084)
    if ! check_port 8084 || ! check_pid "/tmp/web_server_8084.pid" "HTTP网站(dist)"; then
        restart_service "HTTP网站(dist)" "web_server_8084.sh"
    fi
    
    # 4. 检查HTTPS网站dist (8445)
    if ! check_port 8445 || ! check_pid "/tmp/https_server_8084.pid" "HTTPS网站(dist)" "https_server_8084.py"; then
        restart_service "HTTPS网站(dist)" "https_server_8084.sh"
    fi
    
    # 5. 检查HTTP API (8081)
    if ! check_port 8081 || ! check_pid "/tmp/api_server.pid" "HTTP API"; then
        restart_service "HTTP API" "api_server.sh"
    fi
    
    # 6. 检查HTTPS API (8444)
    if ! check_port 8444 || ! check_pid "/tmp/api_https.pid" "HTTPS API"; then
        restart_service "HTTPS API" "api_https.sh"
    fi
    
    # 每10分钟记录一次状态
    if [ $(( $(date +%M) % 10 )) -eq 0 ] && [ $(date +%S) -lt 30 ]; then
        log "服务状态: HTTP网站:$(check_port 8088 && echo '✓' || echo '✗'), HTTPS网站:$(check_port 8443 && echo '✓' || echo '✗'), HTTP网站dist:$(check_port 8084 && echo '✓' || echo '✗'), HTTPS网站dist:$(check_port 8445 && echo '✓' || echo '✗'), HTTP API:$(check_port 8081 && echo '✓' || echo '✗'), HTTPS API:$(check_port 8444 && echo '✓' || echo '✗')"
    fi
    
    sleep 30
done
