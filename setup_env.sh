#!/bin/bash
# Setup script to handle externally-managed Python environment
# This script creates a virtual environment and installs dependencies

set -e

echo "========================================="
echo "Time-Series-Library Environment Setup"
echo "========================================="
echo

# Check Python version
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3.9 python3.8 python3 python; do
    if command -v $cmd &> /dev/null; then
        PYTHON_VER=$($cmd --version 2>&1 | awk '{print $2}')
        MAJOR=$(echo $PYTHON_VER | cut -d. -f1)
        MINOR=$(echo $PYTHON_VER | cut -d. -f2)
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 8 ]; then
            PYTHON_CMD=$cmd
            echo "✓ Found Python: $PYTHON_CMD ($PYTHON_VER)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "✗ Error: Python 3.8+ is required"
    echo "   Please install Python 3.8 or higher"
    exit 1
fi

# Check if python3-full is installed (required for venv on some systems)
if ! $PYTHON_CMD -c "import venv" 2>/dev/null; then
    echo "⚠ Warning: venv module not available"
    echo "   Installing python3-full may be required:"
    echo "   sudo apt install python3-full"
    echo
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create virtual environment
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv $VENV_DIR
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo
echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# Upgrade pip
echo
echo "Upgrading pip..."
pip install --upgrade pip --quiet

# Install dependencies
echo
echo "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "✓ Dependencies installed from requirements.txt"
else
    echo "⚠ Warning: requirements.txt not found"
fi

# Check for v4 requirements
if [ -f "v4/requirements.txt" ]; then
    echo
    echo "Installing v4 dependencies..."
    pip install -r v4/requirements.txt
    echo "✓ v4 dependencies installed"
fi

echo
echo "========================================="
echo "Setup complete!"
echo "========================================="
echo
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo
echo "To deactivate, run:"
echo "  deactivate"
echo

