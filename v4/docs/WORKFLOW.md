# 增量更新工作流程

## 流程概览
```
run_incremental.py
 ├─ 加载 config/config.yaml
 ├─ 解析日期参数（默认：昨日）
 ├─ DataFetcher 拉取增量数据（direct 模式可使用临时目录）
 └─ IncrementalUpdater 执行增量管道
```

## 1. 数据抓取
1. 读取 `data_api/data_config.json` 中的表清单。
2. 针对每个目标日期：
   - 若 `use_cci_gate=true`，先检查 00000019（CCI 指数）当天是否有数据。
   - 调用 API 并将结果写入临时目录或配置的 `raw_data_root`。
3. 返回成功抓取的日期列表；部分失败会记录警告并返回状态码 2。

## 2. 管道处理
- **拆分与合并**：沿用既有拆分/合并逻辑，将增量数据映射到目标表结构。
- **direct 模式**：抓取数据后会放入临时目录，处理完成立即删除，仅保留目标表。

主要步骤：
1. `DataSplitter` 拆分原始 CSV，生成临时 `split_data/`。
2. `DataMerger` 合并拆分结果，输出 `merged_coal_data.csv`。
3. `CoalDataProcessor` 生成增量结果（煤价 `coal_new_with_cci6.csv`、运费 `coal_freight_final.csv`）。
   - CCI5000 修补仅使用处理后的 CCI 指数表，已移除找煤网参考文件。

## 3. 历史稳定化
`HistoryStabilizer` 将临时结果与 `baseline` 指定的目标表合并：
- 历史数据保持不变，仅覆盖增量日期。
- 若合并后行列数小于历史基准，记录日志并放弃覆盖。

## 4. 前向填充
`ForwardFiller` 只处理增量日期的缺失值：
- 记录填充前后的空值数量。
- 如仍存在缺失，提示人工核查；历史数据不会修改。

## 5. 输出与清理
- 最终输出保留：`coal_new_with_cci6.csv`、`coal_freight_final.csv`。
- 当 `keep_intermediate=false`（direct 模式下默认），会删除 `split_data/`、`merged_coal_data.csv`、`timeline_custom.csv` 等临时文件。
- 为避免额外日志，内部模块仅使用标准输出；如需统一日志，可在 `config.yaml` 的 `logging.file` 中指定。

## 日志示例
```
INFO - Coal Data Incremental Update V4
INFO - 更新日期: ['2025-09-26']
INFO - 开始抓取日期: 2025-09-26
INFO - 日期 2025-09-26 抓取完成：成功 112，失败 0
INFO - 更新煤价数据
INFO - 执行煤价历史稳定化...
INFO - 执行煤价前向填充...
INFO - 更新运费数据
INFO - 执行运费历史稳定化...
INFO - 执行运费前向填充...
INFO - ✓ 增量更新完成
```

## 常见问题
| 现象 | 可能原因 | 处理建议 |
| --- | --- | --- |
| “本次没有可用的增量日期” | API 返回为空或 CCI 门控过滤 | 检查数据源，必要时设置 `use_cci_gate=false`。 |
| 合并后行数减少 | 基准文件缺失或日期格式不一致 | 确认 `baseline` 路径，校验日期列格式。 |
| 输出仍有空值 | 新日期缺乏历史参考 | 查看日志提示列名，补录或回填历史值。 |
| CCI5000 未更新 | 00000019 指数文件缺失或无数据 | 提供有效的 `cci_processed_path` 或放入原始目录。 |

## 设计原则
- 历史数据不会被整体覆盖，只更新增量日期。
- 前向填充限定在新增日期，确保低频列无缺口。
- direct 模式只保留目标表和统一日志，所有临时文件用后即删。
- 找煤网参考文件已从流程中移除，CCI 修补完全依赖处理后的指数表。
