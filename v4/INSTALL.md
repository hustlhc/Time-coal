# 安装指南

## 一键安装（推荐）

```bash
cd v4
bash setup.sh
```

这将自动完成：

- ✅ 检查 Python 版本（需要 3.8+）
- ✅ 创建虚拟环境
- ✅ 安装依赖
- ✅ 创建配置文件模板
- ✅ 创建日志目录

## 手动安装

### 1. Python 环境

```bash
# 检查Python版本
python3 --version  # 需要 >= 3.8

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

### 2. 安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 配置

```bash
# 复制配置模板
cp config/config.example.yaml config/config.yaml

# 编辑配置（必须！）
vi config/config.yaml
```

**最小配置**：

```yaml
data:
  raw_data_root: /path/to/background/2017找煤数据0917
  output_dir: /path/to/processed_data_cci_aligned
  baseline:
    coal: ${data.output_dir}/coal_new.csv
    freight: ${data.output_dir}/coal_freight.csv
```

### 4. 验证安装

```bash
# 测试配置
python run_incremental.py --dry-run

# 查看帮助
python run_incremental.py --help
```

如果看到配置信息输出，说明安装成功！

## Docker 安装

### 构建镜像

```bash
docker build -t coal-incremental:v4 .
```

### 运行测试

```bash
docker run --rm coal-incremental:v4 --help
```

## 故障排查

### Python 版本不符

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3.9

# CentOS/RHEL
sudo yum install python39
```

### pip 安装失败

```bash
# 使用国内镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 虚拟环境问题

```bash
# 删除并重建
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 配置验证失败

```bash
# 检查配置文件格式
python -c "import yaml; yaml.safe_load(open('config/config.yaml'))"

# 检查路径是否存在
ls -la /path/to/background/2017找煤数据0917
```

## 卸载

```bash
# 删除虚拟环境
rm -rf venv

# 删除配置文件（可选）
rm config/config.yaml

# 删除日志（可选）
rm -rf logs
```

## 下一步

- 阅读 [QUICKSTART.md](docs/QUICKSTART.md) 快速开始
- 阅读 [DEPLOYMENT.md](docs/DEPLOYMENT.md) 了解生产部署
- 阅读 [CONFIGURATION.md](docs/CONFIGURATION.md) 了解配置详情
