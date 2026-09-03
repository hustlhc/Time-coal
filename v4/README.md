# v4 目录说明

这是一个用于煤炭数据增量更新的独立目录，适合在 Linux/Windows 环境直接部署。

## 主要特性
- **单目录部署**：拷贝 `v4/` 至服务器即可运行。
- **配置驱动**：所有路径、行为由 `config/config.yaml` 控制。
- **自动定位文件**：未提供路径时，会在原始目录自动搜索 00000019 指数文件等关键资源。
- **结构清晰**：`pipeline/` 负责拆分合并；`incremental_update/` 负责增量抓取、历史稳定化与前向填充。

## 目录结构
```
v4/
├── README.md
├── requirements.txt
├── run_incremental.py
├── config/
│   ├── config_loader.py
│   └── config.example.yaml
├── pipeline/
│   ├── coal_data_processor.py
│   ├── data_splitter.py
│   ├── data_merger.py
│   └── utils.py
├── incremental_update/
│   ├── core.py
│   ├── fetcher.py
│   ├── stabilizer.py
│   ├── filler.py
│   └── __init__.py
├── data_api/
│   ├── fetch_api_data.py
│   ├── save_to_csv_cci.py
│   └── data_config.json
└── docs/
    ├── CONFIGURATION.md
    ├── DEPLOYMENT.md
    └── WORKFLOW.md
```

## 使用步骤
1. **准备环境**
   ```bash
   python -m venv venv
   source venv/bin/activate          # Windows: venv\Scriptsctivate
   pip install -r requirements.txt
   ```
2. **创建配置**
   ```bash
   cp config/config.example.yaml config/config.yaml
   vi config/config.yaml             # 修改 raw_data_root、output_dir、baseline 等路径
   ```
3. **运行增量**
   ```bash
   python run_incremental.py                     # 默认处理昨日
   python run_incremental.py --day 2025-09-26    # 指定日期
   python run_incremental.py --backfill 7        # 回填最近 7 天
   python run_incremental.py --only-coal         # 仅处理煤价
   python run_incremental.py --only-freight      # 仅处理运费
   python run_incremental.py --dry-run           # 查看配置后退出
   ```
> direct 模式下仅依赖目标表与增量数据，CCI5000 修补完全来源于 00000019 指数，已取消找煤网参考文件。

## 工作流程（摘要）
1. DataFetcher 调用 API 把增量数据写入临时目录。
2. pipeline 执行拆分、合并，得到增量临时输出。
3. HistoryStabilizer 将临时输出与基准表合并，只覆盖新增日期。
4. ForwardFiller 对增量日期做前向填充。
5. 清理临时文件，仅保留目标表和统一日志。

更多细节请参阅 `docs/WORKFLOW.md`。

## 运行日志
- 默认输出到控制台；如需写入文件，可在配置中设置 `logging.file`。
- 不再生成拆分/检验的独立日志，保持目录整洁。

## 部署提示
- 可结合 cron 或 systemd 周期运行。
- 建议将 `config.yaml` 排除在版本库之外，只保留示例文件。

部署完成后执行 `python run_incremental.py --config config/config.yaml` 即可在服务器上运行增量更新。
