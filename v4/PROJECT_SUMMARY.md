# Coal Data Incremental Update V4 - 项目总结

## 📋 项目概述

V4 是针对电煤采需大模型数据处理系统的 Linux 友好重构版本，专注于**增量更新**功能，解决了 V3 版本的关键问题并提供了更好的跨平台支持。

## 🎯 核心目标

1. **Linux/Docker 友好**：完全兼容 Linux 服务器部署
2. **配置文件化**：使用 YAML 配置，无硬编码路径
3. **模块化设计**：清晰的模块划分，易于维护
4. **历史数据保护**：确保增量更新不丢失历史数据
5. **低频列处理**：自动填充周更新列的空值

## 📁 项目结构

```
v4/
├── README.md                           # 项目说明
├── CHANGELOG.md                        # 更新日志
├── PROJECT_SUMMARY.md                  # 本文件
├── requirements.txt                    # Python依赖
├── setup.sh                            # 安装脚本
├── .gitignore                          # Git忽略规则
│
├── config/                             # 配置文件
│   ├── config.example.yaml            # 配置模板（提交到Git）
│   ├── config.yaml                    # 实际配置（不提交）
│   └── config_loader.py               # 配置加载器
│
├── incremental_update/                 # 核心模块
│   ├── __init__.py                    # 模块初始化
│   ├── core.py                        # 增量更新核心逻辑
│   ├── stabilizer.py                  # 历史稳定化模块
│   ├── filler.py                      # 前向填充模块
│   └── fetcher.py                     # 数据获取模块
│
├── run_incremental.py                  # 主入口脚本
│
├── docs/                               # 文档
│   ├── QUICKSTART.md                  # 快速入门
│   ├── DEPLOYMENT.md                  # 部署指南
│   ├── CONFIGURATION.md               # 配置说明
│   └── WORKFLOW.md                    # 工作流程
│
├── Dockerfile                          # Docker镜像
└── docker-compose.yml                  # Docker Compose配置
```

## ✨ 核心特性

### 1. 历史稳定化（HistoryStabilizer）

**问题**：V3 版本从输出文件读取历史，导致增量更新后历史数据丢失。

**解决**：

```python
# ❌ V3错误做法
old_data = pd.read_csv('coal_freight_final.csv')  # 输出文件

# ✅ V4正确做法
old_data = pd.read_csv('coal_freight.csv')  # 目标表（历史基准）
```

**效果**：

```
第1次增量（9-26）：
  coal_freight.csv（2174行）+ 增量（1行）= coal_freight_final.csv（2175行）✓

第2次增量（9-27）：
  coal_freight.csv（2174行）+ 已有（9-26）+ 增量（1行）= coal_freight_final.csv（2176行）✓
```

### 2. 前向填充（ForwardFiller）

**问题**：周更新列（如 349 表）在非更新日为空值。

**解决**：

```python
# 只填充增量日期的空值，保护历史数据
ForwardFiller.fill_incremental_rows(
    df,
    incremental_dates=['2025-09-26'],
    preserve_history=True
)
```

**效果**：

| 日期       | CCI | 349 表（周更新） |
| ---------- | --- | ---------------- |
| 2025-09-23 | 100 | 50               |
| 2025-09-24 | 101 | 50（历史值）     |
| 2025-09-25 | 102 | 50（历史值）     |
| 2025-09-26 | 103 | NaN → **50**     |

### 3. 配置文件化（ConfigLoader）

**问题**：V3 硬编码 Windows 路径。

**解决**：

```yaml
# config/config.yaml
data:
  raw_data_root: /data/background/2017找煤数据0917 # Linux路径
  output_dir: /data/processed
  baseline:
    coal: ${data.output_dir}/coal_new.csv # 变量引用
    freight: ${data.output_dir}/coal_freight.csv
```

**支持**：

- 环境变量：`${ENV_VAR}`
- 内部变量：`${data.output_dir}`
- 默认值：`${ENV_VAR:-default}`

## 🔧 使用指南

### 快速开始

```bash
# 1. 安装
cd v4
bash setup.sh

# 2. 配置
cp config/config.example.yaml config/config.yaml
vi config/config.yaml  # 修改路径

# 3. 运行
python run_incremental.py --day 2025-09-26
```

### 常用命令

```bash
# 昨日增量（默认）
python run_incremental.py

# 指定日期
python run_incremental.py --day 2025-09-26

# 回填7天
python run_incremental.py --backfill 7

# 只更新煤价
python run_incremental.py --only-coal

# 测试配置
python run_incremental.py --dry-run

# 详细输出
python run_incremental.py -v
```

### Docker 部署

```bash
# 构建镜像
docker build -t coal-incremental:v4 .

# 运行
docker run --rm \
  -v /data:/data \
  -v $(pwd)/config/config.yaml:/app/config/config.yaml:ro \
  coal-incremental:v4 --day 2025-09-26
```

### 定时任务

```bash
# crontab
crontab -e

# 每天早上6点运行
0 6 * * * cd /opt/coal-agent/v4 && /opt/coal-agent/v4/venv/bin/python run_incremental.py
```

## 📊 数据流程

```
API抓取
  ↓
原始CSV（追加）
  ↓
数据拆分（按目标列）
  ↓
数据合并（时间轴对齐）
  ↓
临时输出（仅增量）
  ↓
历史稳定化（基准 + 增量）
  ↓
前向填充（低频列）
  ↓
最终输出（完整无缺失）
```

## 🐛 问题修复记录

### 已修复（V3 → V4）

| 问题                        | V3 表现                  | V4 修复                      |
| --------------------------- | ------------------------ | ---------------------------- |
| 历史数据丢失                | 只保留增量日期           | 从目标表读取历史基准         |
| 低频列空值                  | 周更新列非更新日为空     | 前向填充                     |
| 运费数据源错误              | 347/349/351/353 表无数据 | 修复数据源映射               |
| Windows 路径硬编码          | 无法在 Linux 运行        | 配置文件化                   |
| 配置分散                    | 参数散落在多个文件       | 统一 YAML 配置               |
| 无配置验证                  | 运行时才发现配置错误     | 启动时验证配置               |
| 日志不完整                  | 难以追踪问题             | 详细的结构化日志             |
| 无 Docker 支持              | 部署困难                 | Dockerfile + docker-compose  |
| 文档缺失                    | 使用方法不清晰           | 完整文档（快速入门、部署等） |
| 最后两列历史数据缺失        | 增量更新后历史值丢失     | 从目标表读取历史基准         |
| 9-28 日期混入（实际未混入） | 用户误解（已澄清为误判） | 加强日志说明                 |

## 📖 文档索引

| 文档                         | 用途                  |
| ---------------------------- | --------------------- |
| `README.md`                  | 项目概述和快速入门    |
| `QUICKSTART.md`              | 5 分钟上手指南        |
| `DEPLOYMENT.md`              | Linux/Docker 部署指南 |
| `CONFIGURATION.md`           | 配置文件详细说明      |
| `WORKFLOW.md`                | 增量更新工作流程      |
| `CHANGELOG.md`               | 版本更新历史          |
| `PROJECT_SUMMARY.md`         | 项目总结（本文件）    |
| `FIX_FREIGHT_INCREMENTAL.md` | V3 问题修复记录       |

## 🔗 依赖关系

### Python 依赖

```
pandas>=1.3.0
PyYAML>=5.4.1
requests>=2.26.0
python-dateutil>=2.8.2
```

### 外部依赖

- 复用`processed_data_cci_aligned/`的核心模块：
  - `coal_data_processor.py`
  - `data_splitter.py`
  - `data_merger.py`
  - `utils.py`
  - `config.py`

## 🚀 部署建议

### 生产环境

```bash
# 目录结构
/data/
├── background/           # 原始数据
├── processed/            # 处理后数据
│   ├── coal_new.csv      # 历史基准（重要！）
│   ├── coal_freight.csv  # 历史基准（重要！）
│   ├── coal_new_with_cci6.csv
│   └── coal_freight_final.csv
└── logs/                 # 日志

/opt/coal-incremental/
├── v4/                   # 应用代码
└── venv/                 # 虚拟环境
```

### 监控

```bash
# 数据完整性检查
python -c "
import pandas as pd
df = pd.read_csv('/data/processed/coal_freight_final.csv', encoding='utf-8-sig')
print(f'行数: {len(df)}')
print(f'空值: {df.isnull().sum().sum()}')
"

# 日志监控
tail -f /data/logs/incremental_update_$(date +%Y%m%d).log
grep -i error /data/logs/*.log
```

### 备份

```bash
# 每天备份历史基准
cp /data/processed/coal_freight.csv \
   /backup/coal_freight_$(date +%Y%m%d).csv
```

## 🔍 故障排查

| 问题           | 检查                                     | 解决                                 |
| -------------- | ---------------------------------------- | ------------------------------------ |
| 配置文件不存在 | `ls config/config.yaml`                  | `cp config.example.yaml config.yaml` |
| 路径不存在     | `ls -la /data/processed/`                | 检查配置文件路径                     |
| 权限错误       | `ls -la /data/processed/*.csv`           | `chmod 644 *.csv`                    |
| 历史基准缺失   | `wc -l coal_freight.csv`                 | 从备份恢复或全量处理                 |
| 数据行数不增   | 检查日志中的"最终总行数"                 | 检查 CCI 门控，可能当天无数据        |
| 空值过多       | `df.isnull().sum()`                      | 检查前向填充日志                     |
| 依赖模块找不到 | `python -c "import coal_data_processor"` | 检查路径，确保在正确目录运行         |

## 🎓 学习路径

1. **快速体验**：`QUICKSTART.md`
2. **理解流程**：`WORKFLOW.md`
3. **配置调整**：`CONFIGURATION.md`
4. **生产部署**：`DEPLOYMENT.md`
5. **深入理解**：阅读源代码注释

## 🤝 贡献

欢迎贡献代码和文档！关键模块：

- `core.py`：增量更新核心逻辑
- `stabilizer.py`：历史稳定化（关键！）
- `filler.py`：前向填充
- `fetcher.py`：数据获取

## 📝 待办事项

- [ ] 实现并行数据处理
- [ ] 添加数据质量检查
- [ ] Web 管理界面
- [ ] 性能监控和指标
- [ ] 单元测试覆盖

## 📞 支持

- 查看文档：`docs/`
- 查看日志：`logs/incremental_update_*.log`
- 运行测试：`python run_incremental.py --dry-run`

---

**版本**: 4.0.0  
**更新日期**: 2025-10-03  
**维护者**: Coal Data Team
