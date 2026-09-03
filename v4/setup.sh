#!/bin/bash
# Coal Data Incremental Update V4 安装脚本

set -e

echo "========================================="
echo "Coal Data Incremental Update V4"
echo "安装脚本"
echo "========================================="
echo

# 检查 Python 版本
PYTHON_CMD=""
for cmd in python3.9 python3.8 python3 python; do
    if command -v $cmd &> /dev/null; then
        PYTHON_VER=$($cmd --version 2>&1 | awk '{print $2}')
        MAJOR=$(echo $PYTHON_VER | cut -d. -f1)
        MINOR=$(echo $PYTHON_VER | cut -d. -f2)
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 8 ]; then
            PYTHON_CMD=$cmd
            echo "✓ 找到 Python: $PYTHON_CMD ($PYTHON_VER)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "✗ 错误: 需要 Python 3.8+"
    exit 1
fi

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo
    echo "创建虚拟环境..."
    $PYTHON_CMD -m venv venv
    echo "✓ 虚拟环境创建完成"
else
    echo "✓ 虚拟环境已存在"
fi

# 激活虚拟环境
echo
echo "激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo
echo "安装Python依赖..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ 依赖安装完成"

# 创建配置文件
if [ ! -f "config/config.yaml" ]; then
    echo
    echo "创建配置文件..."
    cp config/config.example.yaml config/config.yaml
    echo "✓ 配置文件已创建: config/config.yaml"
    echo "⚠️  请编辑配置文件，修改数据路径"
else
    echo "✓ 配置文件已存在"
fi

# 创建日志目录
LOG_DIR="logs"
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
    echo "✓ 日志目录已创建: $LOG_DIR"
fi

echo
echo "========================================="
echo "安装完成！"
echo "========================================="
echo
echo "下一步:"
echo "  1. 编辑配置文件: vi config/config.yaml"
echo "  2. 测试运行: python run_incremental.py --dry-run"
echo "  3. 运行更新: python run_incremental.py --day 2025-09-26"
echo
echo "获取帮助:"
echo "  python run_incremental.py --help"
echo "  cat docs/QUICKSTART.md"
echo

