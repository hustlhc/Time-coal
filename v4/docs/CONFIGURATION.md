# 配置文件说明

`v4/config/config.yaml` 负责增量流程的全部参数，支持环境变量（`${ENV}`）和内部引用（`${data.output_dir}`）。

## 示例配置
```yaml
data:
  raw_data_root: /data/background/2017找煤数据0917
  output_dir: /data/processed_data_cci_aligned
  baseline:
    coal: ${data.output_dir}/coal_new.csv
    freight: ${data.output_dir}/coal_freight.csv
  cci_timeline: ${data.raw_data_root}/60+/输入00000019-CCI指数_处理后.csv
  cci_processed_path: ${data.raw_data_root}/60+/输入00000019-CCI指数_处理后.csv
  cci_coal_source: ${data.output_dir}/coal_new.csv

api:
  config_file: ${APP_ROOT}/data_api/data_config.json
  timeout: 30
  max_retries: 3

incremental:
  mode: direct
  use_cci_gate: true
  keep_intermediate: false
  stabilization:
    enabled: true
  forward_fill:
    enabled: true

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: ${data.output_dir}/logs/incremental_update_{date}.log

env:
  type: production
  app_root: ${APP_ROOT}

performance:
  max_workers: 1
  chunk_size: 10000
```

## 字段说明
- `raw_data_root`：原始数据根目录，需包含 500+/60+ 子目录。
- `output_dir`：处理后文件输出位置。
- `baseline`：历史目标表，增量将以此为基准合并。
- `cci_timeline` / `cci_processed_path`：CCI 时间轴与指数文件；留空则自动搜索 00000019。
- `cci_coal_source`：可选，若已有包含 CCI6 的 `coal_new.csv` 可指定。
- `raw_data_root` 在 direct 模式下仅用于校验，可指向任意存在的目录（fetch 会使用临时目录）。
- `mode`：增量模式，`legacy` 继续使用拆分合并；`direct` 仅依赖目标表与增量数据（推荐）。
- `use_cci_gate`：当 CCI 当日无数据时跳过该日期。
- `keep_intermediate`：是否保留拆分/合并的中间文件（direct 模式下建议保持 false）。
- `logging`：日志级别、格式及可选输出文件。

> 自 V4 起，CCI5000 修补仅依赖处理后的 CCI 指数，无需再配置找煤网参考文件。

## 校验配置
```bash
python -c "from config.config_loader import get_config; cfg = get_config('config/config.yaml'); print('配置有效' if cfg.validate() else '配置无效')"
```

## 常见场景
- **测试环境**：路径指向 `/tmp`，可开启 `keep_intermediate` 方便调试。
- **生产环境**：指定真实目录，日志输出到 `/var/log/coal/...`。
- **容器部署**：将主机目录挂载到容器 `/data`，并在配置中引用该路径。

## 常见问题
| 现象 | 可能原因 | 处理建议 |
| --- | --- | --- |
| 找不到 `config.yaml` | 未复制配置文件 | 执行 `cp config/config.example.yaml config/config.yaml`。 |
| “原始数据目录不存在” | 路径错误或挂载缺失 | 确认 `raw_data_root`，并确保目录存在。 |
| “API 配置文件缺失” | `config_file` 路径无效 | 上传正确的 JSON 或更新路径。 |
| 日志文件未生成 | `logging.file` 未配置或目录无权限 | 指定可写目录并调整权限。 |

## 建议
- 将 `config.yaml` 排除在版本控制之外，只提交示例文件。
- 使用绝对路径并统一挂载，避免定时任务运行时路径变化。
- 涉及敏感信息时，可用环境变量注入，在 YAML 中引用 `${ENV_VAR}`。
