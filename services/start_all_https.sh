#!/bin/bash

echo "========================================================="
echo "     启动煤价系统所有服务（HTTP + HTTPS 双栈模式）"
echo "========================================================="
echo "启动时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 定义颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 停止所有旧服务
echo -e "${YELLOW}[1/8] 停止所有旧服务...${NC}"
./stop_all.sh 2>/dev/null
pkill -f "https_server" 2>/dev/null
pkill -f "https_server_8084" 2>/dev/null
pkill -f "api_server_https" 2>/dev/null
pkill -f "monitor_services" 2>/dev/null
sleep 3

# 清理端口
echo -e "${YELLOW}[2/8] 清理端口...${NC}"
sudo fuser -k 8088/tcp 2>/dev/null
sudo fuser -k 8084/tcp 2>/dev/null
sudo fuser -k 8081/tcp 2>/dev/null
sudo fuser -k 8443/tcp 2>/dev/null
sudo fuser -k 8444/tcp 2>/dev/null
sudo fuser -k 8445/tcp 2>/dev/null
sleep 2

# 启动HTTP网站 (8088) - 旧系统
echo -e "${YELLOW}[3/8] 启动HTTP网站服务 (端口:8088)...${NC}"
./web_server.sh
sleep 3
if ss -tln 2>/dev/null | grep -q ":8088 "; then
    echo -e "${GREEN}  ✓ HTTP网站启动成功${NC}"
else
    echo -e "${RED}  ✗ HTTP网站启动失败${NC}"
fi

# 启动HTTPS网站 (8443) - 安全访问（旧系统）
echo -e "\n${YELLOW}[4/8] 启动HTTPS网站服务 (端口:8443)...${NC}"
./https_server.sh
sleep 3
if ss -tln 2>/dev/null | grep -q ":8443 "; then
    echo -e "${GREEN}  ✓ HTTPS网站启动成功${NC}"
else
    echo -e "${RED}  ✗ HTTPS网站启动失败${NC}"
fi

# 启动HTTP网站dist (8084) - 新系统
echo -e "\n${YELLOW}[5/8] 启动HTTP网站服务dist (端口:8084)...${NC}"
./web_server_8084.sh
sleep 3
if ss -tln 2>/dev/null | grep -q ":8084 "; then
    echo -e "${GREEN}  ✓ HTTP网站dist启动成功${NC}"
else
    echo -e "${RED}  ✗ HTTP网站dist启动失败${NC}"
fi

# 启动HTTPS网站dist (8445) - 安全访问（新系统）
echo -e "\n${YELLOW}[6/8] 启动HTTPS网站服务dist (端口:8445)...${NC}"
./https_server_8084.sh
sleep 3
if ss -tln 2>/dev/null | grep -q ":8445 "; then
    echo -e "${GREEN}  ✓ HTTPS网站dist启动成功${NC}"
else
    echo -e "${RED}  ✗ HTTPS网站dist启动失败${NC}"
fi

# 启动HTTP API (8081) - 兼容旧系统
echo -e "\n${YELLOW}[7/8] 启动HTTP API服务 (端口:8081)...${NC}"
./api_server.sh
if [ $? -eq 0 ] && ss -tln 2>/dev/null | grep -q ":8081 "; then
    echo -e "${GREEN}  ✓ HTTP API启动成功${NC}"
else
    echo -e "${RED}  ✗ HTTP API启动失败${NC}"
fi
sleep 2

# 启动HTTPS API (8444) - 用于HTTPS页面
echo -e "\n${YELLOW}[8/8] 启动HTTPS API服务 (端口:8444)...${NC}"
./api_https.sh
if [ $? -eq 0 ] && ss -tln 2>/dev/null | grep -q ":8444 "; then
    echo -e "${GREEN}  ✓ HTTPS API启动成功${NC}"
else
    echo -e "${RED}  ✗ HTTPS API启动失败${NC}"
fi
sleep 2

# 启动监控服务
echo -e "\n${YELLOW}[监控] 启动服务监控...${NC}"
nohup ./monitor_services.sh > logs/monitor_daemon.log 2>&1 &
MONITOR_PID=$!
echo $MONITOR_PID > /tmp/monitor.pid
echo -e "${GREEN}  ✓ 监控服务启动 (PID: $MONITOR_PID)${NC}"

echo ""
echo "========================================================="
echo -e "${GREEN}✅ 所有服务启动完成！${NC}"
echo "========================================================="
echo ""
echo -e "${YELLOW}📌 访问地址：${NC}"
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  旧系统 (html1)                             │"
echo "  │  🔵 HTTP             http://10.73.56.38:8088  │"
echo "  │  🟢 HTTPS            https://10.73.56.38:8443 │"
echo "  ├─────────────────────────────────────────────┤"
echo "  │  新系统 (dist)                              │"
echo "  │  🔵 HTTP             http://10.73.56.38:8084  │"
echo "  │  🟢 HTTPS            https://10.73.56.38:8445 │"
echo "  ├─────────────────────────────────────────────┤"
echo "  │  API服务                                   │"
echo "  │  🔵 HTTP API        http://10.73.56.38:8081  │"
echo "  │  🟢 HTTPS API       https://10.73.56.38:8444 │"
echo "  └─────────────────────────────────────────────┘"
echo ""
echo -e "${YELLOW}🧪 测试命令：${NC}"
echo "  curl -k https://10.73.56.38:8443"
echo "  curl -k https://10.73.56.38:8445"
echo "  curl -k https://10.73.56.38:8444/api/data_types"
echo ""
echo -e "${YELLOW}📋 日志文件：${NC}"
echo "  tail -f logs/web_server.log"
echo "  tail -f logs/https_server.log"
echo "  tail -f logs/web_server_8084.log"
echo "  tail -f logs/https_server_8084.log"
echo "  tail -f logs/api_server.log"
echo "  tail -f logs/api_https.log"
echo "  tail -f logs/monitor.log"
echo ""
echo "========================================================="
