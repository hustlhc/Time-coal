# 快速入门

## 5 分钟上手

### 1. 克隆代码（如果是新部署）

```bash
cd /opt
git clone <repository-url> coal-agent
cd coal-agent/v4
```

### 2. 安装依赖

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置

```bash
# 复制配置模板
cp config/config.example.yaml config/config.yaml

# 编辑配置（最少修改这几项）
vi config/config.yaml
```

**最小配置**：

```yaml
data:
  raw_data_root: /path/to/background/2017找煤数据0917 # 修改为实际路径
  output_dir: /path/to/processed_data # 修改为实际路径
  baseline:
    coal: ${data.output_dir}/coal_new.csv
    freight: ${data.output_dir}/coal_freight.csv
```

### 4. 运行

```bash
# 测试配置
python run_incremental.py --dry-run

# 运行增量更新（昨天）
python run_incremental.py

# 指定日期
python run_incremental.py --day 2025-09-26
```

## 常用命令

### 增量更新

```bash
# 昨日增量（默认）
python run_incremental.py

# 指定日期
python run_incremental.py --day 2025-09-26

# 回填最近7天
python run_incremental.py --backfill 7

# 只更新煤价
python run_incremental.py --only-coal

# 只更新运费
python run_incremental.py --only-freight

# 保留中间文件（调试用）
python run_incremental.py --keep-intermediate

# 详细输出
python run_incremental.py -v
```

### 查看帮助

```bash
python run_incremental.py --help
```

### 验证配置

```bash
# 空运行（显示配置但不执行）
python run_incremental.py --dry-run

# 测试配置加载
python -c "from config.config_loader import get_config; c=get_config(); c.validate()"
```

## 检查结果

### 1. 查看输出文件

```bash
ls -lh /path/to/processed_data/coal_*.csv
```

应该看到：

- `coal_new_with_cci6.csv` - 煤价数据
- `coal_freight_final.csv` - 运费数据

### 2. 验证数据完整性

```bash
# 检查行数
wc -l /path/to/processed_data/coal_*.csv

# 检查空值
python -c "
import pandas as pd
df = pd.read_csv('/path/to/processed_data/coal_freight_final.csv', encoding='utf-8-sig')
print(f'总行数: {len(df)}')
print(f'空值数: {df.isnull().sum().sum()}')
"
```

### 3. 查看日志

```bash
# 实时日志（如果配置了日志文件）
tail -f /path/to/logs/incremental_update_*.log

# 查找错误
grep -i error /path/to/logs/*.log
```

## 设置定时任务

### 使用 crontab

```bash
# 编辑 crontab
crontab -e

# 添加任务（每天早上6点）
0 6 * * * cd /opt/coal-agent/v4 && /opt/coal-agent/v4/venv/bin/python run_incremental.py >> /var/log/coal/cron.log 2>&1
```

### 使用 systemd timer

详见 [DEPLOYMENT.md](DEPLOYMENT.md#设置定时任务)

## 故障排查

### 问题 1：配置文件不存在

```bash
# 检查
ls config/config.yaml

# 解决
cp config/config.example.yaml config/config.yaml
vi config/config.yaml
```

### 问题 2：找不到模块

```bash
# 检查虚拟环境
which python

# 激活虚拟环境
source venv/bin/activate

# 重新安装
pip install -r requirements.txt
```

### 问题 3：历史基准不存在

```bash
# 检查基准文件
ls -l /path/to/processed_data/coal_new.csv
ls -l /path/to/processed_data/coal_freight.csv

# 解决：首次使用需要从全量处理生成基准文件
cd ../processed_data_cci_aligned
python run_both_pipeline.py

# 将输出复制为基准
cp coal_new_with_cci6.csv coal_new.csv
cp coal_freight_final.csv coal_freight.csv
```

### 问题 4：权限错误

```bash
# 检查权限
ls -la /path/to/processed_data/

# 修复权限
sudo chown -R $USER:$USER /path/to/processed_data/
chmod 755 /path/to/processed_data/
```

## 进阶使用

### 自定义配置

创建多个配置文件用于不同环境：

```bash
config/
├── config.yaml          # 默认配置
├── config.dev.yaml      # 开发环境
└── config.prod.yaml     # 生产环境
```

使用：

```bash
python run_incremental.py --config config/config.prod.yaml
```

### Docker 运行

```bash
# 构建镜像
docker build -t coal-incremental:v4 .

# 运行
docker run --rm \
  -v /path/to/data:/data \
  -v $(pwd)/config/config.yaml:/app/config/config.yaml:ro \
  coal-incremental:v4 \
  --day 2025-09-26
```

### 环境变量

配置文件支持环境变量：

```yaml
data:
  raw_data_root: ${DATA_ROOT}/background/2017找煤数据0917
```

使用：

```bash
export DATA_ROOT=/mnt/data
python run_incremental.py
```

## 下一步

- 阅读 [DEPLOYMENT.md](DEPLOYMENT.md) 了解生产部署
- 阅读 [CONFIGURATION.md](CONFIGURATION.md) 了解详细配置
- 阅读 [WORKFLOW.md](WORKFLOW.md) 了解工作流程

## 获取帮助

- 查看日志文件
- 检查配置文件
- 运行 `--dry-run` 验证配置
- 联系技术支持
