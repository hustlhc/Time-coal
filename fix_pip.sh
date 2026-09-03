#!/bin/bash
# 快速修复pip配置脚本
# 确保使用conda time环境中的pip，避免externally-managed-environment错误

set -e

echo "========================================="
echo "修复pip配置 - 使用conda time环境"
echo "========================================="
echo

# 检查并创建pip包装脚本目录
if [ ! -d "$HOME/bin" ]; then
    echo "创建 ~/bin 目录..."
    mkdir -p "$HOME/bin"
fi

# 创建pip包装脚本
echo "创建pip包装脚本..."
cat > "$HOME/bin/pip" << 'EOF'
#!/bin/bash
# pip包装脚本 - 自动使用conda time环境中的pip
exec /home/lhc/miniconda3/envs/time/bin/pip "$@"
EOF

# 创建pip3包装脚本
cat > "$HOME/bin/pip3" << 'EOF'
#!/bin/bash
# pip3包装脚本 - 自动使用conda time环境中的pip
exec /home/lhc/miniconda3/envs/time/bin/pip "$@"
EOF

# 设置执行权限
chmod +x "$HOME/bin/pip" "$HOME/bin/pip3"
echo "✓ pip包装脚本已创建"

# 检查.profile配置
PROFILE_FILE="$HOME/.profile"
if [ -f "$PROFILE_FILE" ]; then
    # 检查是否已有~/bin的PATH配置
    if ! grep -q "PATH=\"\$HOME/bin:\$PATH\"" "$PROFILE_FILE" 2>/dev/null; then
        echo
        echo "更新 ~/.profile 配置..."
        cat >> "$PROFILE_FILE" << 'PROFILE_EOF'

# 设置pip默认使用conda time环境中的pip
# 将~/bin目录添加到PATH最前面（包含pip包装脚本）
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi
PROFILE_EOF
        echo "✓ ~/.profile 已更新"
    else
        echo "✓ ~/.profile 配置已存在"
    fi
else
    echo "⚠ 警告: ~/.profile 不存在，创建新文件..."
    cat > "$PROFILE_FILE" << 'PROFILE_EOF'
# ~/.profile: executed by the command interpreter for login shells.

# set PATH so it includes user's private bin if it exists
# 优先使用~/bin（包含pip包装脚本，指向conda time环境）
if [ -d "$HOME/bin" ] ; then
    PATH="$HOME/bin:$PATH"
fi

# set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi
PROFILE_EOF
    echo "✓ ~/.profile 已创建"
fi

# 检查.bashrc配置
BASHRC_FILE="$HOME/.bashrc"
if [ -f "$BASHRC_FILE" ]; then
    # 检查是否已有~/bin的PATH配置
    if ! grep -q "PATH=\"\$HOME/bin:\$PATH\"" "$BASHRC_FILE" 2>/dev/null; then
        echo
        echo "更新 ~/.bashrc 配置..."
        cat >> "$BASHRC_FILE" << 'BASHRC_EOF'

# 设置pip默认使用conda time环境中的pip
# 将~/bin目录添加到PATH最前面（包含pip包装脚本）
export PATH="$HOME/bin:$PATH"
BASHRC_EOF
        echo "✓ ~/.bashrc 已更新"
    else
        echo "✓ ~/.bashrc 配置已存在"
    fi
fi

# 在当前shell中应用配置
echo
echo "在当前shell中应用配置..."
export PATH="$HOME/bin:$PATH"

# 验证配置
echo
echo "========================================="
echo "验证配置"
echo "========================================="
echo "Pip路径: $(which pip)"
echo "Pip版本: $(pip --version)"
echo

# 检查是否指向正确的pip
if [[ "$(which pip)" == *"/home/lhc/bin/pip"* ]]; then
    PIP_VERSION=$(pip --version)
    if [[ "$PIP_VERSION" == *"/home/lhc/miniconda3/envs/time"* ]]; then
        echo "✅ 配置成功！pip现在使用conda time环境"
    else
        echo "⚠ 警告: pip路径正确，但Python版本可能不对"
        echo "   当前: $PIP_VERSION"
    fi
else
    echo "⚠ 警告: pip路径可能不正确"
    echo "   当前路径: $(which pip)"
    echo "   期望路径: /home/lhc/bin/pip"
    echo
    echo "请运行以下命令使配置生效:"
    echo "  source ~/.profile"
    echo "  或重新打开终端"
fi

echo
echo "========================================="
echo "完成！"
echo "========================================="
echo
echo "使用说明:"
echo "  1. 在新终端中，配置会自动生效"
echo "  2. 在当前终端，运行: source ~/.profile"
echo "  3. 然后可以直接使用: pip install 包名"
echo
