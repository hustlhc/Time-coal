#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="/home/lhc/Time-coal"
SERVICE_DIR="$PROJECT_ROOT/services"
DIST_DIR="$PROJECT_ROOT/autoinfer/html1/dist"
PORT="8088"
BASE_URL="http://127.0.0.1:${PORT}"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

command -v ss >/dev/null 2>&1 || die "未找到 ss 命令"
command -v curl >/dev/null 2>&1 || die "未找到 curl 命令"
[ -f "$DIST_DIR/index.html" ] || die "前端目录不存在或缺少 index.html: $DIST_DIR"
[ -f "$SERVICE_DIR/dist_preview_server.py" ] || die "缺少静态服务程序"
grep -q 'def list_directory' "$SERVICE_DIR/dist_preview_server.py" \
    || die "静态服务尚未包含目录索引防护，请先更新 dist_preview_server.py"

echo "[1/5] 停止旧的 8088 服务"
systemctl --user stop time-coal-web.service 2>/dev/null || true

# 只处理占用 8088 的 PID，不影响其他端口服务。
mapfile -t listener_pids < <(
    ss -ltnpH "sport = :${PORT}" 2>/dev/null \
        | grep -oE 'pid=[0-9]+' \
        | cut -d= -f2 \
        | sort -u
)

for pid in "${listener_pids[@]}"; do
    [ -n "$pid" ] || continue
    if kill -0 "$pid" 2>/dev/null; then
        echo "  停止 PID $pid: $(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        kill "$pid" 2>/dev/null || true
    fi
done

for _ in 1 2 3 4 5; do
    ss -ltnH "sport = :${PORT}" 2>/dev/null | grep -q . || break
    sleep 1
done

if ss -ltnH "sport = :${PORT}" 2>/dev/null | grep -q .; then
    mapfile -t remaining_pids < <(
        ss -ltnpH "sport = :${PORT}" 2>/dev/null \
            | grep -oE 'pid=[0-9]+' \
            | cut -d= -f2 \
            | sort -u
    )
    for pid in "${remaining_pids[@]}"; do
        [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true
    done
fi

rm -f /tmp/web_server.pid

echo "[2/5] 启动安全的 8088 前端服务"
bash "$SERVICE_DIR/web_server.sh"

echo "[3/5] 检查监听进程"
sleep 1
web_pid="$(cat /tmp/web_server.pid 2>/dev/null || true)"
[ -n "$web_pid" ] && kill -0 "$web_pid" 2>/dev/null \
    || die "8088 服务未正常启动"

cmdline="$(tr '\0' ' ' < "/proc/$web_pid/cmdline" 2>/dev/null || true)"
echo "  PID: $web_pid"
echo "  CMD: $cmdline"
echo "$cmdline" | grep -q 'dist_preview_server.py' \
    || die "8088 未运行 dist_preview_server.py"
echo "$cmdline" | grep -q -- "--dist $DIST_DIR" \
    || die "8088 未使用正确的 dist 目录"

probe_dir="$(mktemp -d /tmp/time-coal-8088-check.XXXXXX)"
trap 'rm -rf "$probe_dir"' EXIT

echo "[4/5] 验证前端首页"
home_code="$(curl --noproxy '*' --max-time 5 -sS -o "$probe_dir/home" -w '%{http_code}' "$BASE_URL/")"
[ "$home_code" = "200" ] || die "首页返回 HTTP $home_code"
grep -q '<div id="app"></div>' "$probe_dir/home" \
    || die "首页不是预期的前端入口"

echo "[5/5] 验证目录索引和路径越界已关闭"
assets_code="$(curl --noproxy '*' --max-time 5 -sS -o /dev/null -w '%{http_code}' "$BASE_URL/assets/")"
traversal_code="$(curl --noproxy '*' --max-time 5 -sS -o /dev/null -w '%{http_code}' "$BASE_URL/%2e%2e/")"

[ "$assets_code" = "404" ] || die "/assets/ 仍可浏览，返回 HTTP $assets_code"
[ "$traversal_code" = "404" ] || die "路径越界未拦截，返回 HTTP $traversal_code"

echo "修复完成：8088 只提供 $DIST_DIR，目录索引和路径越界访问均已拒绝。"
