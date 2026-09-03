#!/usr/bin/env bash
set -euo pipefail

# Usage:
# 1) inspect and choose one of the torch install blocks below
# 2) run: bash setup_env.sh
# If you already have a venv, activate it first. The script uses $PYTHON if set,
# otherwise falls back to `python` in PATH.

PYTHON=${PYTHON:-python}
PIP="$PYTHON -m pip"

echo "Using python: $($PYTHON -V 2>&1)"

# Upgrade pip
$PIP install -U pip

# Common dependencies from requirements.txt
$PIP install -r requirements.txt

# -----------------------------
# Pick ONE of the following PyTorch install commands depending on your machine:
# 1) CPU-only (safe, slower):
#    $PIP install torch==2.2.1+cpu torchvision==0.17.3+cpu --index-url https://download.pytorch.org/whl/cpu
# 2) CUDA 11.8 (if your driver supports CUDA 11.8):
#    $PIP install torch==2.2.1+cu118 torchvision==0.17.3+cu118 --index-url https://download.pytorch.org/whl/cu118
# 3) CUDA 12.1 (if your driver supports CUDA 12.1):
#    $PIP install torch==2.2.1+cu121 torchvision==0.17.3+cu121 --index-url https://download.pytorch.org/whl/cu121
# 4) If you prefer the generic (may pick the correct wheel automatically on many systems):
#    $PIP install "torch==2.2.1" torchvision==0.17.3 -f https://download.pytorch.org/whl/torch_stable.html

# Uncomment and run ONE appropriate command below (or copy/paste to terminal):

# CPU (uncomment to run):
# $PIP install torch==2.2.1+cpu torchvision==0.17.3+cpu --index-url https://download.pytorch.org/whl/cpu

# CUDA 11.8 (uncomment to run):
# $PIP install torch==2.2.1+cu118 torchvision==0.17.3+cu118 --index-url https://download.pytorch.org/whl/cu118

# CUDA 12.1 (uncomment to run):
# $PIP install torch==2.2.1+cu121 torchvision==0.17.3+cu121 --index-url https://download.pytorch.org/whl/cu121

# Generic fallback (uncomment to run):
# $PIP install "torch==2.2.1" torchvision==0.17.3 -f https://download.pytorch.org/whl/torch_stable.html


echo "setup_env.sh written. Edit the file to uncomment the correct torch install line, then re-run this script to install PyTorch." 
