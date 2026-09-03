#!/bin/bash
set -e

echo "==== 检查 Python 环境 ===="
which python || { echo "❌ 没找到 Python，请先安装 conda 或 python3"; exit 1; }
python --version

echo "==== 安装基础依赖 ===="
pip install --upgrade pip setuptools wheel
pip install ninja einops "causal-conv1d>=1.2.0"

echo "==== 检查 PyTorch 是否安装 ===="
if python -c "import torch" 2>/dev/null; then
    echo "✅ PyTorch 已安装"
else
    echo "⚠️ 没检测到 PyTorch，正在安装 CPU 版本 (如需 GPU 请自行改成 CUDA 对应命令)"
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
fi

echo "==== 克隆并安装 mamba_ssm ===="
pip install git+https://github.com/state-spaces/mamba.git

echo "==== 验证安装 ===="
python -c "from mamba_ssm import Mamba; print('✅ Mamba 安装成功，可以使用!')"
