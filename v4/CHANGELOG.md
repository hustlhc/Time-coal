# 更新日志

所有重要的项目变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [4.0.0] - 2025-10-03

### 新增 ✨

- **Linux 友好的配置系统**

  - 基于 YAML 的配置文件，支持环境变量和内部变量引用
  - 配置加载器（`ConfigLoader`）支持多环境配置
  - 配置验证功能

- **模块化架构**

  - `IncrementalUpdater` - 增量更新核心
  - `HistoryStabilizer` - 历史稳定化模块
  - `ForwardFiller` - 前向填充模块
  - `DataFetcher` - 数据获取模块

- **Docker 支持**

  - Dockerfile
  - docker-compose.yml
  - Kubernetes CronJob 示例

- **完整文档**

  - README.md - 项目概述
  - QUICKSTART.md - 快速入门
  - DEPLOYMENT.md - 部署指南
  - CONFIGURATION.md - 配置说明
  - WORKFLOW.md - 工作流程
  - CHANGELOG.md - 更新日志

- **自动化脚本**
  - `setup.sh` - 一键安装脚本
  - `.gitignore` - Git 忽略规则

### 改进 🚀

- **历史稳定化增强**

  - 明确从目标表（`coal_new.csv`/`coal_freight.csv`）读取历史基准
  - 验证合并结果，防止数据丢失
  - 详细的日志输出

- **前向填充优化**

  - 只填充增量日期的空值
  - 保护历史数据不被修改
  - 统计并报告填充情况

- **日志系统**

  - 支持文件日志和控制台日志
  - 可配置日志级别
  - 日志文件支持日期占位符

- **命令行界面**
  - 更友好的参数说明
  - 支持`--dry-run`空运行模式
  - 支持`--verbose`详细输出
  - 完整的`--help`文档

### 修复 🐛

- **解决 V3 版本的关键问题**
  - 修复历史数据丢失问题（从输出文件读取基准）
  - 修复低频列空值问题（前向填充）
  - 修复运费数据源映射错误（347、349、351、353 表）

### 变更 ⚠️

- **配置文件格式**

  - 从 Python dict 改为 YAML 格式
  - 路径配置使用变量引用

- **目录结构**
  - 配置文件统一放在`config/`目录
  - 文档统一放在`docs/`目录
  - 核心模块放在`incremental_update/`目录

### 删除 🗑️

- 移除硬编码路径
- 移除环境特定配置（改为配置文件）

### 安全 🔒

- 配置文件不提交到版本控制
- 支持权限控制和用户隔离
- 日志轮转和备份策略

### 文档 📚

- 新增快速入门指南
- 新增部署指南（Linux/Docker/K8s）
- 新增配置说明文档
- 新增工作流程图

### 测试 🧪

- 配置加载测试
- 历史稳定化测试
- 前向填充测试

## [3.0.0] - 2025-09

### 新增

- 增量更新功能
- API 数据获取
- CCI 日期门控

### 修复

- 运费数据源映射错误
- 前向填充功能

## [2.0.0] - 2025-08

### 新增

- 重构数据处理管道
- 模块化设计

## [1.0.0] - 2025-07

### 新增

- 初始版本
- 全量数据处理

---

## 版本说明

### 语义化版本

- **主版本号（MAJOR）**：不兼容的 API 变更
- **次版本号（MINOR）**：向下兼容的功能新增
- **修订号（PATCH）**：向下兼容的问题修正

### 变更类型

- `新增` - 新功能
- `改进` - 现有功能的改进
- `修复` - Bug 修复
- `变更` - 破坏性变更
- `删除` - 移除的功能
- `安全` - 安全相关的修复
- `文档` - 文档变更
- `测试` - 测试相关变更

## 升级指南

### 从 V3 升级到 V4

1. **备份现有数据**

   ```bash
   cp -r processed_data_cci_aligned processed_data_cci_aligned.backup
   ```

2. **安装 V4**

   ```bash
   cd v4
   bash setup.sh
   ```

3. **迁移配置**

   ```bash
   # 复制配置模板
   cp config/config.example.yaml config/config.yaml

   # 编辑配置，填入实际路径
   vi config/config.yaml
   ```

4. **测试运行**

   ```bash
   python run_incremental.py --dry-run
   python run_incremental.py --day 2025-09-26
   ```

5. **验证数据**

   ```bash
   # 检查行数
   wc -l coal_freight_final.csv

   # 检查空值
   python -c "import pandas as pd; df = pd.read_csv('coal_freight_final.csv'); print(df.isnull().sum().sum())"
   ```

6. **切换定时任务**

   ```bash
   # 停止V3定时任务
   crontab -e
   # 注释掉旧任务

   # 添加V4定时任务
   0 6 * * * cd /path/to/v4 && /path/to/venv/bin/python run_incremental.py
   ```

## 已知问题

### V4.0.0

- [ ] DataFetcher 模块依赖 V3 的 API 代码，需要确保路径正确
- [ ] Docker 镜像需要包含原有的核心模块
- [ ] 并行处理功能预留但未实现

## 计划功能

### V4.1.0（计划中）

- [ ] 并行数据处理
- [ ] 性能监控和指标
- [ ] Web 管理界面
- [ ] 数据质量检查

### V4.2.0（计划中）

- [ ] 支持更多数据源
- [ ] 自定义处理规则
- [ ] 数据回滚功能

## 贡献

欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可

MIT License
