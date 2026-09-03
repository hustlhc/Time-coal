# 部署检查清单

## 📋 部署前检查

### 环境准备

- [ ] Python 3.8+ 已安装
- [ ] Git 已安装（如需版本控制）
- [ ] 足够的磁盘空间（建议至少 10GB）
- [ ] 网络连接正常（API 访问）

### 目录准备

- [ ] 原始数据目录存在：`/path/to/background/2017找煤数据0917`
  - [ ] `500+/` 子目录存在
  - [ ] `60+/` 子目录存在
- [ ] 输出目录存在：`/path/to/processed_data_cci_aligned`
- [ ] 历史基准文件存在：
  - [ ] `coal_new.csv`
  - [ ] `coal_freight.csv`

### 权限检查

- [ ] 对原始数据目录有读权限
- [ ] 对输出目录有读写权限
- [ ] 对日志目录有写权限

## 🔧 安装步骤

### 1. 代码部署

- [ ] 复制 v4 目录到服务器

  ```bash
  scp -r v4/ user@server:/opt/coal-agent/
  ```

- [ ] 进入目录
  ```bash
  cd /opt/coal-agent/v4
  ```

### 2. 环境安装

- [ ] 运行安装脚本

  ```bash
  bash setup.sh
  ```

  或手动安装：

- [ ] 创建虚拟环境

  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

- [ ] 安装依赖
  ```bash
  pip install -r requirements.txt
  ```

### 3. 配置

- [ ] 复制配置模板

  ```bash
  cp config/config.example.yaml config/config.yaml
  ```

- [ ] 编辑配置文件

  ```bash
  vi config/config.yaml
  ```

  必需配置项：

  - [ ] `data.raw_data_root` - 原始数据路径
  - [ ] `data.output_dir` - 输出目录路径
  - [ ] `data.baseline.coal` - 煤价基准文件
  - [ ] `data.baseline.freight` - 运费基准文件

- [ ] 配置文件权限
  ```bash
  chmod 600 config/config.yaml
  ```

### 4. 测试

- [ ] 测试配置加载

  ```bash
  python run_incremental.py --dry-run
  ```

- [ ] 测试增量更新（指定历史日期）

  ```bash
  python run_incremental.py --day 2025-09-26
  ```

- [ ] 验证输出文件

  ```bash
  ls -lh coal_new_with_cci6.csv coal_freight_final.csv
  wc -l coal_new_with_cci6.csv coal_freight_final.csv
  ```

- [ ] 检查数据完整性
  ```bash
  python -c "
  import pandas as pd
  coal = pd.read_csv('coal_new_with_cci6.csv', encoding='utf-8-sig')
  freight = pd.read_csv('coal_freight_final.csv', encoding='utf-8-sig')
  print(f'煤价: {len(coal)} 行, 空值: {coal.isnull().sum().sum()}')
  print(f'运费: {len(freight)} 行, 空值: {freight.isnull().sum().sum()}')
  "
  ```

## ⏰ 定时任务配置

### Crontab 方式

- [ ] 编辑 crontab

  ```bash
  crontab -e
  ```

- [ ] 添加定时任务（每天早上 6 点）

  ```cron
  0 6 * * * cd /opt/coal-agent/v4 && /opt/coal-agent/v4/venv/bin/python run_incremental.py >> /var/log/coal/cron.log 2>&1
  ```

- [ ] 保存并退出

- [ ] 验证 crontab
  ```bash
  crontab -l
  ```

### Systemd Timer 方式

- [ ] 创建服务文件

  ```bash
  sudo vi /etc/systemd/system/coal-incremental.service
  ```

- [ ] 创建定时器文件

  ```bash
  sudo vi /etc/systemd/system/coal-incremental.timer
  ```

- [ ] 重载 systemd

  ```bash
  sudo systemctl daemon-reload
  ```

- [ ] 启用并启动定时器

  ```bash
  sudo systemctl enable coal-incremental.timer
  sudo systemctl start coal-incremental.timer
  ```

- [ ] 查看状态
  ```bash
  sudo systemctl status coal-incremental.timer
  sudo systemctl list-timers
  ```

## 📊 监控配置

### 日志

- [ ] 创建日志目录

  ```bash
  sudo mkdir -p /var/log/coal
  sudo chown $(whoami):$(whoami) /var/log/coal
  ```

- [ ] 配置日志轮转

  ```bash
  sudo vi /etc/logrotate.d/coal-data
  ```

  内容：

  ```
  /var/log/coal/*.log {
      daily
      rotate 7
      compress
      missingok
      notifempty
  }
  ```

### 监控脚本

- [ ] 创建数据检查脚本

  ```bash
  vi /opt/coal-agent/scripts/check_data.sh
  chmod +x /opt/coal-agent/scripts/check_data.sh
  ```

- [ ] 测试监控脚本
  ```bash
  bash /opt/coal-agent/scripts/check_data.sh
  ```

## 🔐 安全配置

### 用户和权限

- [ ] 创建专用用户（可选）

  ```bash
  sudo useradd -m -s /bin/bash coal-user
  ```

- [ ] 设置目录所有者
  ```bash
  sudo chown -R coal-user:coal-user /opt/coal-agent
  sudo chown -R coal-user:coal-user /data
  ```

### 文件权限

- [ ] 配置文件权限

  ```bash
  chmod 600 config/config.yaml
  ```

- [ ] 数据目录权限
  ```bash
  chmod 755 /data/processed_data_cci_aligned
  chmod 644 /data/processed_data_cci_aligned/*.csv
  ```

## 🐳 Docker 部署（可选）

### 构建

- [ ] 构建 Docker 镜像

  ```bash
  docker build -t coal-incremental:v4 .
  ```

- [ ] 测试镜像
  ```bash
  docker run --rm coal-incremental:v4 --help
  ```

### 运行

- [ ] 编辑 docker-compose.yml（修改挂载路径）

  ```bash
  vi docker-compose.yml
  ```

- [ ] 启动容器

  ```bash
  docker-compose up -d
  ```

- [ ] 查看日志
  ```bash
  docker-compose logs -f
  ```

## 📝 文档检查

- [ ] 阅读 `README.md`
- [ ] 阅读 `QUICKSTART.md`
- [ ] 阅读 `DEPLOYMENT.md`
- [ ] 阅读 `CONFIGURATION.md`
- [ ] 保存关键配置参数到安全位置

## ✅ 验收测试

### 功能测试

- [ ] 手动运行增量更新成功
- [ ] 数据文件正确生成
- [ ] 行数符合预期（基准行数 + 增量行数）
- [ ] 无空值（或空值在预期范围内）
- [ ] 定时任务正常触发

### 性能测试

- [ ] 运行时间可接受（通常 < 5 分钟）
- [ ] 内存占用正常（< 4GB）
- [ ] 磁盘 IO 正常

### 恢复测试

- [ ] 备份历史基准文件
- [ ] 测试从备份恢复
- [ ] 测试重新运行增量更新

## 🚨 应急联系

- **技术支持**：********\_\_\_********
- **备用联系人**：********\_\_\_********
- **文档位置**：`/opt/coal-agent/v4/docs/`
- **日志位置**：`/var/log/coal/`

## 📋 部署记录

| 项目        | 信息               |
| ----------- | ------------------ |
| 部署日期    | ********\_******** |
| 部署人员    | ********\_******** |
| 服务器 IP   | ********\_******** |
| Python 版本 | ********\_******** |
| V4 版本     | 4.0.0              |
| 备注        | ********\_******** |

---

**签字确认**：********\_******** 日期：********\_********
