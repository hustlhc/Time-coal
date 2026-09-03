#!/usr/bin/env bash
# Configure the conda "time" environment for this project.

set -euo pipefail

echo "========================================="
echo "Configure conda time environment"
echo "========================================="
echo

if ! command -v conda >/dev/null 2>&1; then
    echo "Error: conda is not available in PATH"
    exit 1
fi

CONDA_BASE="${CONDA_BASE:-$(conda info --base)}"
if [ ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    echo "Error: conda.sh not found under $CONDA_BASE"
    exit 1
fi
source "$CONDA_BASE/etc/profile.d/conda.sh"

ENV_NAME="${TIME_ENV_NAME:-time}"
PYTHON_VERSION="${TIME_PYTHON_VERSION:-3.11}"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "Creating conda env: $ENV_NAME (Python $PYTHON_VERSION)"
    conda create -y -n "$ENV_NAME" "python=$PYTHON_VERSION"
fi

conda activate "$ENV_NAME"

echo "Python: $(python --version)"
echo "Python path: $(which python)"
echo "Pip: $(python -m pip --version)"
echo

python -m pip install --upgrade pip "setuptools<82" wheel

REQ_FILE="${TIME_REQUIREMENTS_FILE:-requirements-time.txt}"
if [ ! -f "$REQ_FILE" ]; then
    echo "Error: $REQ_FILE not found"
    echo "The original requirements.txt pins old packages that are not suitable for this Python version."
    exit 1
fi

echo
echo "Installing dependencies from $REQ_FILE"
python -m pip install -r "$REQ_FILE"

if [ -f "v4/requirements.txt" ]; then
    echo
    echo "Installing v4 dependencies"
    python -m pip install -r v4/requirements.txt
fi

echo
echo "========================================="
echo "time environment is ready"
echo "========================================="
echo "Activate it with:"
echo "  source $CONDA_BASE/etc/profile.d/conda.sh"
echo "  conda activate $ENV_NAME"
echo
