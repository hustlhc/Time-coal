#!/bin/bash

WEB_DIR="/home/lhc/Time-coal/autoinfer/html1/dist"
HTTPS_PORT="8445"
SSL_DIR="/home/lhc/Time-coal/services/ssl"
PID_FILE="/tmp/https_server_8084.pid"
LOG_DIR="/home/lhc/Time-coal/services/logs"

echo "启动HTTPS网站服务(dist)(端口: $HTTPS_PORT)..."

# 创建日志目录
mkdir -p "$LOG_DIR"
mkdir -p "$SSL_DIR"

# 检查证书是否存在
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

# 停止旧进程
pkill -9 -f "https_server_8084.py" 2>/dev/null
pkill -9 -f "http.server 8445" 2>/dev/null
sleep 1

# 清理端口
fuser -k 8445/tcp 2>/dev/null
sleep 1

# 创建Python HTTPS服务器脚本 - 支持SPA路由
cat > /tmp/https_server_8084.py << 'INNEREOF'
import http.server
import ssl
import sys
import os

port = int(sys.argv[1])
cert_file = sys.argv[2]
key_file = sys.argv[3]
web_dir = sys.argv[4]

os.chdir(web_dir)

class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=web_dir, **kwargs)
    
    def do_GET(self):
        # 获取请求的文件路径
        path = self.translate_path(self.path)
        
        # 如果文件不存在或是目录，则返回 index.html (支持SPA路由)
        if not os.path.exists(path) or os.path.isdir(path):
            index_path = os.path.join(web_dir, 'index.html')
            if os.path.exists(index_path):
                self.path = '/index.html'
        
        return super().do_GET()

    
    def log_message(self, format, *args):
        # 减少日志输出
        if 'favicon' not in self.path:
            print(f"{self.address_string()} - {format % args}")

httpd = http.server.HTTPServer(('0.0.0.0', port), SPAHandler)
httpd.allow_reuse_address = True

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile=cert_file, keyfile=key_file)
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

print(f"HTTPS服务启动成功: https://0.0.0.0:{port}")
print(f"共享目录: {web_dir}")
print(f"PID: {os.getpid()}")
sys.stdout.flush()

httpd.serve_forever()
INNEREOF

# 启动服务器
cd "$WEB_DIR"
python3 /tmp/https_server_8084.py $HTTPS_PORT "$SSL_DIR/server.crt" "$SSL_DIR/server.key" "$WEB_DIR" >> "$LOG_DIR/https_server_8084.log" 2>&1 &
HTTPS_PID=$!

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
    tail -10 "$LOG_DIR/https_server_8084.log"
fi
