# 部署指南

## 1. 打包与上传
1. 在开发机进入项目根目录，压缩 `processed_data_cci_aligned/v4`：
   ```bash
   cd /path/to/coal-agent
   tar czf v4.tar.gz processed_data_cci_aligned/v4
   ```
2. 将 `v4.tar.gz` 传至服务器（`scp`、`rsync` 等均可）。
3. 登录服务器解压：
   ```bash
   tar xf v4.tar.gz
   cd processed_data_cci_aligned/v4
   ```

## 2. 环境准备（Linux）
```bash
python3 -m venv venv
source venv/bin/activate            # Windows 可跳过或使用 PowerShell Activate
pip install -r requirements.txt
```

## 3. 配置
```bash
cp config/config.example.yaml config/config.yaml
vi config/config.yaml                # 修改 raw_data_root / output_dir / baseline 等路径
```
> 提示：所有路径可写绝对路径或 `~/...`，脚本会自动标准化。

配置完成后，可用干跑检查：
```bash
python run_incremental.py --dry-run
```

## 4. 手动执行
```bash
# 默认抓取昨日并处理
deactivate && source venv/bin/activate
python run_incremental.py

# 指定日期或范围
python run_incremental.py --day 2025-09-26
python run_incremental.py --backfill 7
```
脚本输出日志到控制台；若在配置文件设置了 `logging.file`，会写入对应文件。

## 5. 定时任务
### 5.1 crontab
```bash
crontab -e
0 6 * * * cd /opt/coal/v4 && /opt/coal/v4/venv/bin/python run_incremental.py >> /opt/coal/logs/cron.log 2>&1
```
> 保证 `raw_data_root` 与 `output_dir` 在定时任务触发时挂载完毕。

### 5.2 systemd timer（示例）
`/etc/systemd/system/coal-incremental.service`
```ini
[Unit]
Description=Coal Incremental Update
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/opt/coal/v4
ExecStart=/opt/coal/v4/venv/bin/python run_incremental.py
StandardOutput=append:/var/log/coal/incremental.log
StandardError=append:/var/log/coal/incremental_error.log
User=coal

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/coal-incremental.timer`
```ini
[Unit]
Description=Daily Coal Incremental Update
Requires=coal-incremental.service

[Timer]
OnCalendar=Mon-Fri 06:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now coal-incremental.timer
sudo systemctl status coal-incremental.timer
```

## 6. Docker（可选）
若使用容器部署，可直接复用仓库提供的 `Dockerfile`：
```bash
docker build -t coal-incremental-v4 .
docker run \
  -v /data/background:/data/background \
  -v /data/processed:/data/processed \
  -v $(pwd)/config/config.yaml:/app/config/config.yaml \
  coal-incremental-v4 --day 2025-09-26
```
确保挂载目录与 `config.yaml` 中路径一致。

## 7. 常见问题
| 现象 | 排查建议 |
| ---- | -------- |
| 日志提示 “API 配置文件缺失” | 确认 `config.yaml` 的 `api.config_file` 指向服务器上实际的 `data_config.json`。 |
| 没有增量日期 | 检查 API 是否当日无数据，或将 `use_cci_gate` 设置为 `false`。 |
| 输出目录无权限 | `chmod -R 755 /data/processed` 或调整运行用户。 |
| 历史基准缺失 | 将最新的 `coal_new.csv` / `coal_freight.csv` 上传到配置指定路径。 |

## 8. 备份建议
- 定期复制 `output_dir` 下的 CSV 与 `config/config.yaml`：
  ```bash
  rsync -az /data/processed/ /backup/coal/$(date +%Y%m%d)/
  ```
- 若需要清理旧备份，可结合 `find … -mtime +7 -delete`。

## 9. 升级提醒
从旧版本切换至 V4 时，务必：
1. 备份历史输出与配置；
2. 按照新的 `config.yaml` 模板填写路径；
3. 首次运行前使用 `--dry-run` 检查；
4. 确认定时任务指向新的虚拟环境与工作目录。
