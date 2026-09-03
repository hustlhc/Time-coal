#!/bin/bash

WEB_DIR="/home/lhc/Time-coal/autoinfer/html1"
HTTPS_PORT="8443"
SSL_DIR="/home/lhc/Time-coal/services/ssl"
PID_FILE="/tmp/https_server.pid"
LOG_DIR="/home/lhc/Time-coal/services/logs"

echo "启动HTTPS网站服务(端口: $HTTPS_PORT)..."

# 创建日志目录
mkdir -p "$LOG_DIR"
mkdir -p "$SSL_DIR"

# 检查并生成证书
if [ ! -f "$SSL_DIR/server.crt" ] || [ ! -f "$SSL_DIR/server.key" ]; then
    echo "生成新的SSL证书..."
    cd "$SSL_DIR"
    openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout server.key \
        -out server.crt \
        -days 3650 \
        -subj "/C=CN/ST=Beijing/L=Beijing/O=Coal/CN=10.73.56.38" \
        -addext "subjectAltName=IP:10.73.56.38,IP:127.0.0.1,DNS:localhost" 2>/dev/null
    cd - > /dev/null
fi

# 创建Python HTTPS服务器脚本
cat > /tmp/https_server.py << 'INNEREOF'
import http.server
import ssl
import sys
import os
import socket
import time

port = int(sys.argv[1])
cert_file = sys.argv[2]
key_file = sys.argv[3]
web_dir = sys.argv[4]

# 切换到网站目录
os.chdir(web_dir)

# 创建Handler
handler = http.server.SimpleHTTPRequestHandler

try:
    # 创建HTTP服务器
    httpd = http.server.HTTPServer(('0.0.0.0', port), handler)
    httpd.allow_reuse_address = True
    
    # SSL包装
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    
    print(f"HTTPS服务启动成功: https://0.0.0.0:{port}")
    print(f"共享目录: {web_dir}")
    print(f"PID: {os.getpid()}")
    
    # 保持运行
    httpd.serve_forever()
    
except Exception as e:
    print(f"启动失败: {e}")
    sys.exit(1)
INNEREOF

# 启动服务器
nohup python3 /tmp/https_server.py $HTTPS_PORT "$SSL_DIR/server.crt" "$SSL_DIR/server.key" "$WEB_DIR" >> "$LOG_DIR/https_server.log" 2>&1 &
HTTPS_PID=$!

# 保存PID
echo $HTTPS_PID > "$PID_FILE"
echo "HTTPS服务启动命令已执行"
echo "PID: $HTTPS_PID"

# 等待3秒检查
sleep 3

# 检查端口
if ss -tln 2>/dev/null | grep -q ":$HTTPS_PORT "; then
    echo "状态: ✓ 运行成功 (端口 $HTTPS_PORT 已监听)"
    echo "访问: https://10.73.56.38:$HTTPS_PORT"
else
    echo "状态: ✗ 启动失败"
    echo "错误日志:"
    tail -5 "$LOG_DIR/https_server.log"
fi
