#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
煤价数据预处理主管道
重构后的简化版本，职责清晰，逻辑简洁
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional, List, Any

from .utils import FileHandler
from .data_splitter import DataSplitter, TargetAnalyzer
from .data_merger import DataMerger, TargetAssembler

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("data_preprocessing.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class CoalDataProcessor:
    """煤价数据预处理主类"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化数据处理器

        Args:
            config: 配置字典，包含以下键：
                - raw_data_dirs: 原始数据目录列表
                - output_dir: 输出目录
                - target_data_path: 目标数据文件路径
                - split_by_target: 是否按目标驱动拆分（默认True）
        """
        self.config = config
        self._validate_config()

        # 基础配置
        self.raw_data_dirs = self._normalize_raw_data_dirs(config["raw_data_dirs"])
        self.output_dir = config["output_dir"]
        self.target_data_path = config.get("target_data_path")
        self.split_by_target = config.get("split_by_target", True)
        # 输出命名与导出控制
        self.final_base_name = config.get("final_base_name", "coal_final")
        self.save_base_final = config.get("save_base_final", True)
        self.save_with_cci6_final = config.get("save_with_cci6_final", True)
        # 严格按目标输出（不做修补/追加），由上层管道控制
        self.strict_target_only = config.get("strict_target_only", False)
        self.enable_coal_new_cci_repair = config.get("enable_coal_new_cci_repair", True)
        self.repair_cci19_in_target = config.get("repair_cci19_in_target", False)
        self.repair_cci_in_strict = config.get("repair_cci_in_strict", False)
        # 是否为最终结果追加 259/268/275 等煤价扩展列（运费场景应置 False）
        self.append_extra_price_columns = config.get("append_extra_price_columns", True)
        # 可选外部参考文件（用于 CCI5000 修补）
        self.cci_processed_path = self._normalize_optional_path(config.get("cci_processed_path"))
        self.zmw_ref_path = self._normalize_optional_path(config.get("zmw_ref_path"))
        self.cci_coal_new_path = self._normalize_optional_path(config.get("cci_coal_new_path"))

        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)

        # 初始化组件
        self.target_analyzer = TargetAnalyzer(self.target_data_path)
        self.data_splitter = DataSplitter(
            self.raw_data_dirs,
            self.output_dir,
            self.target_analyzer,
        )
        cci_timeline_file = self.config.get("cci_timeline_file")
        self.data_merger = DataMerger(
            self.output_dir,
            self.target_data_path,
            cci_timeline_file,
        )

        logger.info("CoalDataProcessor 初始化完成")
        logger.info(f"原始数据目录: {self.raw_data_dirs}")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info(f"目标驱动拆分: {'开启' if self.split_by_target else '关闭'}")

        if self.target_data_path:
            logger.info(f"目标文件: {self.target_data_path}")
        if cci_timeline_file:
            logger.info(f"CCI 时间轴文件: {cci_timeline_file}")

    def _validate_config(self):
        """验证配置"""
        required_keys = ["raw_data_dirs", "output_dir"]
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"配置缺少必要参数: {key}")

        # 验证原始数据目录
        raw_dirs = self._normalize_raw_data_dirs(self.config["raw_data_dirs"])
        for raw_dir in raw_dirs:
            if not os.path.exists(raw_dir):
                logger.warning(f"原始数据目录不存在: {raw_dir}")

        # 验证目标文件
        target_path = self.config.get("target_data_path")
        if target_path and not os.path.exists(target_path):
            logger.warning(f"目标数据文件不存在: {target_path}")

    def _normalize_optional_path(self, path_value: Optional[Any]) -> Optional[str]:
        """将可选路径转换为标准字符串，保持 None 原样。"""
        if not path_value:
            return None
        try:
            path_str = str(path_value)
        except Exception:
            return None
        return os.path.abspath(path_str)

    def _find_file_by_tokens(self, tokens: List[str]) -> Optional[str]:
        """在原始数据目录中根据关键词查找 CSV 文件。"""
        if not tokens:
            return None
        search_dirs = [d for d in self.raw_data_dirs if d and os.path.exists(d)]
        tokens_lower = [str(t).lower() for t in tokens]
        for base in search_dirs:
            try:
                for root, _dirs, files in os.walk(base):
                    for name in files:
                        lower = name.lower()
                        if all(token in lower for token in tokens_lower):
                            return os.path.join(root, name)
            except Exception:
                continue
        return None

    def _normalize_raw_data_dirs(self, raw_data_config) -> List[str]:
        """规范化原始数据目录配置"""
        if isinstance(raw_data_config, str):
            return [raw_data_config]
        elif isinstance(raw_data_config, list):
            return raw_data_config
        else:
            raise ValueError("raw_data_dirs 必须是字符串或字符串列表")

    def step1_split_raw_data(self) -> Dict[str, int]:
        """
        步骤1: 拆分原始数据

        Returns:
            拆分摘要字典
        """
        logger.info("=== 步骤1: 开始拆分原始数据 ===")

        if not self.split_by_target:
            logger.warning("目标驱动拆分已关闭，将跳过拆分步骤")
            return {}

        # 清理历史拆分输出，避免残留旧来源子表影响本次结果
        try:
            import shutil

            split_root = os.path.join(self.output_dir, "split_data")
            if os.path.exists(split_root):
                shutil.rmtree(split_root)
                logger.info("已清理历史 split_data 目录")
        except Exception:
            pass

        # 兼容已有 out 命名的进口 CCI 列（CCI3800out/CCI4700out/CCI5500out），已齐全则不再追加
        # 移除一次性短路判断（依赖未定义变量且无必要）

        split_summary = self.data_splitter.split_all_data()

        total_splits = sum(split_summary.values())
        logger.info(f"=== 步骤1完成: 共生成 {total_splits} 个子表 ===")

        return split_summary

    def step2_merge_split_data(
        self, reference_file: Optional[str] = None
    ) -> Optional[Any]:
        """
        步骤2: 合并拆分数据

        Args:
            reference_file: 可选的参考时间轴文件

        Returns:
            合并后的DataFrame
        """
        logger.info("=== 步骤2: 开始合并拆分数据 ===")

        merged_df = self.data_merger.merge_all_data(reference_file)

        if merged_df is not None:
            logger.info(f"=== 步骤2完成: 数据形状 {merged_df.shape} ===")
        else:
            logger.error("=== 步骤2失败: 合并数据为空 ===")

        return merged_df

    def step3_generate_final_data(
        self, merged_df: Optional[Any] = None
    ) -> Optional[Any]:
        """
        步骤3: 生成最终格式数据

        Args:
            merged_df: 可选的合并数据，如果为None则从文件读取

        Returns:
            最终的DataFrame
        """
        logger.info("=== 步骤3: 生成最终数据 ===")

        # 如果没有提供merged_df，尝试从文件读取
        if merged_df is None:
            merged_file = os.path.join(self.output_dir, "merged_coal_data.csv")
            if not os.path.exists(merged_file):
                logger.error("合并数据文件不存在，请先执行步骤2")
                return None

            merged_df = FileHandler.read_csv(merged_file)
            if merged_df is None:
                logger.error("无法读取合并数据文件")
                return None

        # 应用目标格式
        if self.target_data_path and os.path.exists(self.target_data_path):
            logger.info("应用目标数据格式")
            assembler = TargetAssembler(self.target_data_path)
            final_df = assembler.assemble_to_target_format(merged_df)

        else:
            logger.info("使用默认格式")
            final_df = self._apply_default_format(merged_df)

        # 严格对齐目标列：不追加/修补任何非目标列，直接保存
        try:
            if getattr(self, "strict_target_only", False):
                final_file = self._save_final_data(final_df)
                logger.info(
                    f"=== 步骤3完成(严格对齐): 最终数据已保存到 {final_file} ==="
                )
                return final_df
        except Exception:
            pass

        # 仅对本次新增列开放：将 259/268/275 的细分子表按日期对齐追加到末尾
        try:
            final_df = self._append_additional_columns_259(final_df, merged_df)
            final_df = self._append_additional_columns_268_275(final_df, merged_df)
        except Exception as e:
            logger.warning(f"追加细分列失败，已跳过：{e}")

        # 最终表后处理：缺失值统一补、CCI5000修补、删除重复列、导出三份变体
        try:
            final_df = self._postprocess_final_df(final_df)
            # 基于 coal_new.csv 的 6 列 CCI 统一修补/替换
            try:
                final_df = self._repair_cci_from_coal_new(final_df)
            except Exception as e:
                logger.warning(f"基于 coal_new.csv 的 CCI 六档修补失败：{e}")
            # 保存主最终结果
            final_file = self._save_final_data(final_df)
            logger.info(f"=== 步骤3完成: 最终数据已保存到 {final_file} ===")
            logger.info(f"最终数据形状: {final_df.shape}")
            # 不再导出 3800/4700/5000 三个变体表
            # 追加从 CCI 指数表抽取的 6 列（按列名匹配，不按位置）并生成新表
            try:
                appended_file = self._export_final_with_cci6(final_df)
                if appended_file:
                    logger.info(f"已生成带CCI 6列的新表: {appended_file}")
            except Exception as e:
                logger.warning(f"导出带CCI 6列的新表失败：{e}")
        except Exception as e:
            logger.error(f"后处理失败：{e}")
            # 即便失败，也保存未后处理的版本
            final_file = self._save_final_data(final_df)
            logger.info(f"已保存未后处理版本到 {final_file}，请检查后处理配置")

        return final_df

    def _repair_cci_from_coal_new(self, final_df):
        """使用 coal_new.csv 中的 6 列 CCI 指数，统一替换/补齐最终表中的 CCI 六档。"""
        from .utils import FileHandler
        import pandas as pd

        if final_df is None or final_df.empty:
            return final_df
        try:
            if getattr(self, "strict_target_only", False):
                return final_df
        except Exception:
            pass

        src = getattr(self, "cci_coal_new_path", None)
        if not src or not os.path.exists(src):
            logger.warning(f"coal_new.csv 路径不可用，跳过 CCI 六档修补：{src}")
            return final_df

        cci_df = FileHandler.read_csv(src)
        if cci_df is None or cci_df.empty:
            logger.warning("coal_new.csv 为空或无法读取，跳过 CCI 六档修补")
            return final_df

        # 标准化时间列
        time_col = cci_df.columns[0]
        if time_col != "date":
            cci_df = cci_df.rename(columns={time_col: "date"})
        try:
            cci_df["date"] = pd.to_datetime(cci_df["date"], errors="coerce")
        except Exception:
            pass

        # 基于列名语义匹配 6 个目标列
        cols = list(cci_df.columns)
        cols_lower = [str(c).lower() for c in cols]

        def find_col(keys_all, keys_none=None):
            # 关键词匹配时，排除 00000019（CCI 指数分地区列），避免误配到地区列
            for c, cl in zip(cols, cols_lower):
                if "00000019" in cl:
                    continue
                if all(k in cl for k in keys_all) and not any(
                    k in cl for k in (keys_none or [])
                ):
                    return c
            return None

        target_spec = {
            "CCI4500": {"all": ["cci", "4500"], "none": ["进口"]},
            "CCI5000": {"all": ["cci", "5000"], "none": ["进口"]},
            "CCI5500": {"all": ["cci", "5500"], "none": ["进口"]},
            "CCI进口3800": {"all": ["cci", "进口", "3800"], "none": []},
            "CCI进口4700": {"all": ["cci", "进口", "4700"], "none": []},
            "CCI进口5500": {"all": ["cci", "进口", "5500"], "none": []},
        }

        matched = {}
        # 优先使用标准命名列（CCI4500/CCI5000/CCI5500）
        for exact in ["CCI4500", "CCI5000", "CCI5500"]:
            if exact in cols:
                matched[exact] = exact
        # 其余按关键词匹配（find_col 已排除了 00000019 分地区列）
        for tgt, spec in target_spec.items():
            if tgt in matched:
                continue
            col = find_col(spec["all"], spec.get("none"))
            if col is not None:
                matched[tgt] = col

        # 若 coal_new.csv 可用，允许 'CCI3800out/CCI4700out/CCI5500out' 作为进口列的替代来源
        try:
            src_cn = getattr(self, "cci_coal_new_path", None)
            if src_cn and os.path.exists(src_cn):

                def _find_out(num: str):
                    for c, cl in zip(cols, cols_lower):
                        if ("cci" in cl) and (num in cl) and ("out" in cl):
                            return c
                    return None

                if "CCI进口3800" not in matched:
                    c = _find_out("3800")
                    if c:
                        matched["CCI进口3800"] = c
                if "CCI进口4700" not in matched:
                    c = _find_out("4700")
                    if c:
                        matched["CCI进口4700"] = c
                if "CCI进口5500" not in matched:
                    c = _find_out("5500")
                    if c:
                        matched["CCI进口5500"] = c
        except Exception:
            pass

        # Fallback: handle coal_new.csv style 'CCI3800out/CCI4700out/CCI5500out'
        try:
            cols = list(cci_df.columns)
            cols_lower = [str(c).lower() for c in cols]

            def _find_out(num: str):
                for c, cl in zip(cols, cols_lower):
                    if ("cci" in cl) and (num in cl) and ("out" in cl):
                        return c
                return None

            if "CCI\u8fdb\u53e33800" not in matched:
                c = _find_out("3800")
                if c:
                    matched["CCI\u8fdb\u53e33800"] = c
            if "CCI\u8fdb\u53e34700" not in matched:
                c = _find_out("4700")
                if c:
                    matched["CCI\u8fdb\u53e34700"] = c
            if "CCI\u8fdb\u53e35500" not in matched:
                c = _find_out("5500")
                if c:
                    matched["CCI\u8fdb\u53e35500"] = c
        except Exception:
            pass

        if not matched:
            logger.warning("coal_new.csv 未匹配到任何 CCI 六档列，跳过修补")
            return final_df

        # 构造子表并重命名为标准名
        use_cols = list(matched.values())
        rename_map = {src: tgt for tgt, src in matched.items()}
        cci_sub = cci_df[["date"] + use_cols].rename(columns=rename_map)

        # 对齐并替换：先删除最终表中可能存在的 CCI 相关旧列
        base_time_col = final_df.columns[0]
        df_aligned = (
            final_df.rename(columns={base_time_col: "date"}).copy()
            if base_time_col != "date"
            else final_df.copy()
        )

        # 若最终表已包含全部六档 CCI 目标列，则不重复添加/替换，直接返回
        try:
            canonical_targets = set(rename_map.values())
            have = [c for c in df_aligned.columns if c in canonical_targets]
            if len(have) == len(canonical_targets):
                return final_df
        except Exception:
            pass

        # 删除同名列
        for col in rename_map.values():
            if col in df_aligned.columns:
                try:
                    df_aligned = df_aligned.drop(columns=[col])
                except Exception:
                    pass

        # 额外清理：粗匹配旧 CCI 列（含 00000019/CCI/热值/进口等关键词）
        try:
            from .utils import TextNormalizer as _TN

            canonical_targets = set(rename_map.values())
            drop_old = [c for c in df_aligned.columns if str(c) in canonical_targets]
            if not drop_old:
                canon_norm = {_TN.normalize(v) for v in canonical_targets}
                for c in df_aligned.columns:
                    try:
                        if _TN.normalize(c) in canon_norm:
                            drop_old.append(c)
                    except Exception:
                        continue
            if drop_old:
                logger.info(f"删除旧 CCI 相关列以统一替换: {drop_old}")
                df_aligned = df_aligned.drop(columns=drop_old, errors="ignore")
        except Exception:
            pass

        # 合并（左连接保持主表时间轴）
        merged = df_aligned.merge(cci_sub, on="date", how="left")
        # 覆盖 00000259_动力煤_价格(元/吨)--原产地_澳大利亚 列（采用目标模板值）
        try:
            merged = self._override_259_au_from_target(merged)
        except Exception as e:
            logger.warning(
                f"with_cci6 导出前覆盖 00000259_澳大利亚 列失败，已跳过：{e}"
            )
        if base_time_col != "date":
            merged = merged.rename(columns={"date": base_time_col})
        return merged

    def _apply_default_format(self, df: Any) -> Any:
        """应用默认格式"""
        # 确保日期列名为'date'
        time_col = df.columns[0]
        if time_col != "date":
            df = df.rename(columns={time_col: "date"})
        return df

    def _save_final_data(self, final_df: Any) -> str:
        """保存最终数据"""
        # 生成文件名（固定命名，不再随目标文件名变化）
        final_name = f"{getattr(self, 'final_base_name', 'coal_final')}.csv"

        final_file = os.path.join(self.output_dir, final_name)

        # 配置控制：不保存基础最终表时直接返回路径
        try:
            if not getattr(self, "save_base_final", True):
                return final_file
        except Exception:
            pass

        # 保存前确保日期列存在
        try:
            final_df = self._ensure_date_column(final_df)
        except Exception:
            pass

        # 尝试保存，处理权限问题
        try:
            # Remove CCI 'out' columns if present before saving
            try:
                _out_cols = [
                    c
                    for c in ["CCI3800out", "CCI4700out", "CCI5500out"]
                    if c in final_df.columns
                ]
            except Exception:
                _out_cols = []
            _df2 = (
                final_df.drop(columns=_out_cols, errors="ignore")
                if _out_cols
                else final_df
            )
            _df2.to_csv(final_file, index=False, encoding="utf-8-sig")
        except PermissionError:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(final_name)[0]
            alt_file = os.path.join(self.output_dir, f"{base_name}_{timestamp}.csv")
            logger.warning(f"权限问题，改为保存到: {alt_file}")
            _df2.to_csv(alt_file, index=False, encoding="utf-8-sig")
            final_file = alt_file

        return final_file

    def _override_259_au_from_target(self, df: Any) -> Any:
        """从目标模板 coal_new.csv 覆盖列：
        00000259_动力煤_价格(元/吨)--原产地_澳大利亚
        - 仅按 date 对齐覆盖该列（模板非空值优先），不影响其它列。
        """
        try:
            from .utils import FileHandler, TextNormalizer, ColumnNameProcessor
            import pandas as pd
        except Exception:
            return df

        if df is None or len(df) == 0:
            return df

        # 选择模板路径：优先 target_data_path；否则尝试 cci_coal_new_path
        src = getattr(self, "target_data_path", None) or getattr(
            self, "cci_coal_new_path", None
        )
        if not src or not os.path.exists(src):
            return df

        tdf = FileHandler.read_csv(src)
        if tdf is None or tdf.empty:
            return df

        # 标准化时间列
        t_time = tdf.columns[0]
        if t_time != "date":
            tdf = tdf.rename(columns={t_time: "date"})
        try:
            tdf["date"] = pd.to_datetime(tdf["date"], errors="coerce")
        except Exception:
            pass

        # 查找目标列
        exact = "00000259_动力煤_价格(元/吨)--原产地_澳大利亚"
        col_t = None
        if exact in tdf.columns:
            col_t = exact
        else:
            tokens = ["00000259", "动力煤", "价格", "原产地", "澳大利亚"]
            for c in tdf.columns:
                s = str(c)
                if all(tok in s for tok in tokens):
                    col_t = c
                    break
                try:
                    tid, prod, region, measure = (
                        ColumnNameProcessor.parse_target_column(s)
                    )
                    if (
                        tid == "00000259"
                        and (prod and "动力煤" in prod)
                        and (
                            measure
                            and ColumnNameProcessor.match_measure(
                                measure, "价格(元/吨)"
                            )
                        )
                        and (region and ("澳大利亚" in region or "澳洲" in region))
                    ):
                        col_t = c
                        break
                except Exception:
                    pass
        if not col_t:
            return df

        # 标准化最终表时间列
        f_time = df.columns[0]
        if f_time != "date":
            df = df.rename(columns={f_time: "date"})
        try:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        except Exception:
            pass

        if col_t not in df.columns:
            df[col_t] = None

        # 合并并覆盖（模板非空优先）
        sub = tdf[["date", col_t]].rename(columns={col_t: "__ov__"})
        out = df.merge(sub, on="date", how="left")
        try:
            out[col_t] = out["__ov__"].combine_first(out[col_t])
        except Exception:
            mask = out["__ov__"].notna()
            out.loc[mask, col_t] = out.loc[mask, "__ov__"]
        out = out.drop(columns=["__ov__"], errors="ignore")

        if f_time != "date":
            out = out.rename(columns={"date": f_time})

        return out

    def run_full_pipeline(self, reference_file: Optional[str] = None) -> Dict[str, Any]:
        """
        运行完整的预处理管道

        Args:
            reference_file: 可选的参考时间轴文件

        Returns:
            处理结果字典
        """
        logger.info("开始运行完整的数据预处理管道")
        start_time = datetime.now()

        try:
            # 步骤1: 拆分
            split_summary = self.step1_split_raw_data()

            # 步骤2: 合并
            merged_df = self.step2_merge_split_data(reference_file)
            if merged_df is None:
                raise RuntimeError("数据合并失败")

            # 步骤3: 生成最终数据
            final_df = self.step3_generate_final_data(merged_df)
            if final_df is None:
                raise RuntimeError("最终数据生成失败")

            end_time = datetime.now()
            duration = end_time - start_time

            result = {
                "status": "success",
                "split_summary": split_summary,
                "final_shape": final_df.shape,
                "duration": duration,
                "message": f"处理完成，耗时 {duration}",
            }

            logger.info(f"数据预处理管道完成，耗时: {duration}")
            return result

        except Exception as e:
            error_msg = f"预处理管道执行失败: {str(e)}"
            logger.error(error_msg)

            return {
                "status": "failed",
                "error": error_msg,
                "duration": datetime.now() - start_time,
            }

    def run_step(
        self, step_number: int, reference_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        运行指定步骤

        Args:
            step_number: 步骤编号 (1, 2, 3)
            reference_file: 可选的参考时间轴文件

        Returns:
            步骤执行结果
        """
        start_time = datetime.now()

        try:
            if step_number == 1:
                result = self.step1_split_raw_data()
                return {
                    "status": "success",
                    "step": 1,
                    "result": result,
                    "duration": datetime.now() - start_time,
                }
            elif step_number == 2:
                result = self.step2_merge_split_data(reference_file)
                return {
                    "status": "success" if result is not None else "failed",
                    "step": 2,
                    "result": result.shape if result is not None else None,
                    "duration": datetime.now() - start_time,
                }
            elif step_number == 3:
                result = self.step3_generate_final_data()
                return {
                    "status": "success" if result is not None else "failed",
                    "step": 3,
                    "result": result.shape if result is not None else None,
                    "duration": datetime.now() - start_time,
                }
            else:
                raise ValueError(f"无效的步骤编号: {step_number}")

        except Exception as e:
            return {
                "status": "failed",
                "step": step_number,
                "error": str(e),
                "duration": datetime.now() - start_time,
            }

    def _append_additional_columns_259(self, final_df, merged_df):
        try:
            if not getattr(self, "append_extra_price_columns", True):
                return final_df
        except Exception:
            pass
        """仅对 259 动力煤细分列做追加，附加在末尾。
        - 从 merged_df 自动收集列名模式：ID=259 且 product in {动力煤, 动力煤1#, 动力煤2#}
          且 measure=价格(元/吨)
        - 不改变已存在列顺序；若列已存在于 final_df，则跳过
        """
        from .utils import ColumnNameProcessor, TextNormalizer

        if merged_df is None or merged_df.empty:
            return final_df

        time_col_final = final_df.columns[0]
        time_col_merged = merged_df.columns[0]

        candidate_products = {
            TextNormalizer.normalize("动力煤"),
            TextNormalizer.normalize("动力煤1#"),
            TextNormalizer.normalize("动力煤2#"),
        }
        price_measure = TextNormalizer.normalize("价格(元/吨)")

        candidate_cols: List[str] = []
        for col in merged_df.columns[1:]:
            try:
                token_id, product, region, measure = (
                    ColumnNameProcessor.parse_target_column(col)
                )
                # 字符串模式优先：00000259_* 且包含 --原产地_
                if col.startswith("00000259_") and ("--原产地_" in col):
                    candidate_cols.append(col)
                    continue

                if token_id and token_id.lstrip("0") == "259":
                    pnorm = TextNormalizer.normalize(product or "")
                    mnorm = TextNormalizer.normalize(measure or "")
                    include_product = (
                        pnorm in candidate_products and mnorm == price_measure
                    )
                    if include_product:
                        candidate_cols.append(col)
            except Exception:
                # 解析失败时的回退：基于前缀匹配 00000259_
                if col.startswith("00000259_"):
                    candidate_cols.append(col)
                continue

        # 去重并保留相对顺序，且排除 final 中已有列
        existing = set(final_df.columns)
        ordered_cols = []
        for c in candidate_cols:
            if c not in ordered_cols and c not in existing:
                ordered_cols.append(c)

        if not ordered_cols:
            logger.info("未发现需追加的 259 细分列")
            return final_df

        logger.info(f"将追加 259 细分列: {ordered_cols}")

        extra_df = merged_df[[time_col_merged] + ordered_cols].copy()
        if time_col_merged != time_col_final:
            extra_df = extra_df.rename(columns={time_col_merged: time_col_final})

        merged_final = final_df.merge(extra_df, on=time_col_final, how="left")
        return merged_final

    def _append_additional_columns_268_275(self, final_df, merged_df):
        try:
            if not getattr(self, "append_extra_price_columns", True):
                return final_df
        except Exception:
            pass
        """对 268 和 275 的细分列做末尾追加，仅限本次新增列。
        - 268: ID=268 且 product≈动力煤2#，且列名含硫分标记
          (0.4/0.7)
        - 275: ID=275 且本次新增命名为：
          00000275_主焦煤_价格(元/吨)--到岸港口_京唐/天津
          00000275_1/3焦煤_价格(元/吨)--到岸港口_京唐/大连
        - 跳过 final 已有列
        """
        from .utils import ColumnNameProcessor

        if merged_df is None or merged_df.empty:
            return final_df

        time_col_final = final_df.columns[0]
        time_col_merged = merged_df.columns[0]
        existing = set(final_df.columns)

        cols_268: List[str] = []
        cols_275: List[str] = []

        for col in merged_df.columns[1:]:
            try:
                token_id, product, region, measure = (
                    ColumnNameProcessor.parse_target_column(col)
                )
                tid = token_id.lstrip("0") if token_id else None

                # 268: 采用新的发热量命名：00000268_动力煤2#_价格(元/吨)--发热量_XXXX
                if (tid == "268") and col.startswith(
                    "00000268_动力煤2#_价格(元/吨)--发热量_"
                ):
                    if col not in existing:
                        cols_268.append(col)
                elif tid == "275":
                    # 仅追加我们在拆分阶段新生成的命名模式列
                    if col.startswith("00000275_") and ("到岸港口_" in col):
                        if col not in existing:
                            cols_275.append(col)
            except Exception:
                continue

        # 统一同义命名，避免“度量在后”的变体与目标重复
        def _canonicalize(name: str) -> str:
            s = str(name)
            try:
                if (
                    s.startswith("00000275_")
                    and ("--到岸港口_" in s)
                    and ("_价格" in s)
                ):
                    idx_region = s.find("--到岸港口_")
                    idx_price_tag = s.rfind("_价格")
                    if idx_region >= 0 and idx_price_tag > idx_region:
                        prod = s[len("00000275_") : idx_region]
                        region = s[idx_region + len("--到岸港口_") : idx_price_tag]
                        measure = s[idx_price_tag + 1 :]
                        return f"00000275_{prod}_{measure}--到岸港口_{region}"
                if s.startswith("00000268_") and ("--发热" in s) and ("_价格" in s):
                    idx_heat = s.find("--发热")
                    idx_price_tag = s.rfind("_价格")
                    if idx_heat >= 0 and idx_price_tag > idx_heat:
                        prod = s[len("00000268_") : idx_heat]
                        heat = s[idx_heat + len("--") : idx_price_tag]
                        measure = s[idx_price_tag + 1 :]
                        return f"00000268_{prod}_{measure}--{heat}"
            except Exception:
                pass
            return s

        # 去重：按规范名检查是否已存在于最终表，且同一规范名只追加一次
        add_cols = []
        seen_canon = set()
        for c in cols_268 + cols_275:
            canon = _canonicalize(c)
            if (canon in existing) or (canon in seen_canon):
                continue
            add_cols.append(c)
            seen_canon.add(canon)

        if not add_cols:
            logger.info("未发现需追加的 268/275 细分列")
            return final_df

        logger.info(f"将追加 268/275 细分列: {add_cols}")

        extra_df = merged_df[[time_col_merged] + add_cols].copy()
        # 将列名规范化后再合并，避免与目标重复/错序
        rename_map = {c: _canonicalize(c) for c in add_cols}
        try:
            extra_df = extra_df.rename(columns=rename_map)
        except Exception:
            pass
        if time_col_merged != time_col_final:
            extra_df = extra_df.rename(columns={time_col_merged: time_col_final})

        merged_final = final_df.merge(extra_df, on=time_col_final, how="left")
        return merged_final

    def _ensure_date_column(self, df: Any) -> Any:
        """确保 DataFrame 中存在标准的日期列，并放置于首位。"""
        try:
            import pandas as pd  # type: ignore
        except Exception:
            return df

        if not isinstance(df, pd.DataFrame) or df.empty:
            return df

        def _looks_like_date(name: Any) -> bool:
            text = str(name).strip().lower()
            if not text:
                return False
            keywords = ("date", "日期", "时间", "統計", "统计", "trade_date", "stat_date")
            return any(keyword in text for keyword in keywords)

        # 若已有日期列，规范命名并置前
        date_cols = [c for c in df.columns if _looks_like_date(c)]
        if date_cols:
            first = date_cols[0]
            if first != df.columns[0]:
                other = [c for c in df.columns if c != first]
                df = df[[first] + other]
            if first != "date":
                df = df.rename(columns={first: "date"})
            return df

        idx = df.index
        # 优先从索引恢复日期列
        try:
            if isinstance(idx, pd.MultiIndex):
                for level in idx.names or []:
                    if level and _looks_like_date(level):
                        df = df.reset_index(level=level)
                        df = df.rename(columns={level: "date"})
                        return self._ensure_date_column(df)
            if isinstance(idx, pd.DatetimeIndex) or _looks_like_date(getattr(idx, "name", "")):
                df = df.reset_index()
                col0 = df.columns[0]
                if not _looks_like_date(col0):
                    df = df.rename(columns={col0: getattr(idx, "name", "date") or "date"})
                return self._ensure_date_column(df)
        except Exception:
            pass

        # 尝试从目标模板复制日期列
        base_path = getattr(self, "target_data_path", None)
        base_dates = None
        if base_path and os.path.exists(base_path):
            try:
                base_df = FileHandler.read_csv(str(base_path))
                if base_df is not None and not base_df.empty:
                    base_dates = base_df.iloc[:, 0]
                else:
                    base_dates = None
            except Exception:
                base_dates = None

        if base_dates is not None and len(base_dates) == len(df):
            df = df.copy()
            df.insert(0, "date", base_dates.values)
            return df

        # 最后退化为顺序索引，避免空列
        try:
            df = df.copy()
            df.insert(0, "date", pd.RangeIndex(start=0, stop=len(df)))
        except Exception:
            pass
        return df
    # ===== 新增：最终表后处理 =====
    def _postprocess_final_df(self, df: Any) -> Any:
        """统一缺失值填充、修补 CCI5000、删除指定列。
        - 缺失值按"用下面的值填充"（逐列向下 bfill）。
        - CCI5000 以外部 CCI 指数表为基准，缺失再用找煤网 5000K 补。
        - 删除因二次拆分而重复出现的四列。
        """
        if df is None or df.empty:
            return df

        # 确保日期列存在且命名规范
        df = self._ensure_date_column(df)

        # 修补 CCI5000：先 CCI 指数基准，再找煤网 5000K
        try:
            df = self._repair_cci5000_from_refs(df)
        except Exception as e:
            logger.warning(f"CCI5000 修补失败，已跳过：{e}")

        # 统一缺失值填充：按列自适应频率（日/周/月）在“期内填充”，并对小间隙做限幅前后填充
        try:
            df = self._fill_missing_values_smart(df)
        except Exception as e:
            logger.warning(f"智能缺失值填充失败：{e}")

        # 删除指定四列
        drop_candidates = [
            "00000259_动力煤_价格(元/吨)",
            "输入00000268-CCTD-煤炭价格_鄂尔多斯市_伊金霍洛旗_动力煤2#_价格(元/吨)",
            # 275 相关：兼容不同写法（半角/全角、主焦煤/焦煤/1/3焦煤）
            "输入00000275-CCTD-煤炭价格_到岸价格_俄罗斯_1/3焦煤_价格(元/吨)",
            "输入00000275-CCTD-煤炭价格_到岸价格_俄罗斯_1／3焦煤_价格(元/吨)",
            "输入00000275-CCTD-煤炭价格_到岸价格_俄罗斯_主焦煤_价格(元/吨)",
            "输入00000275-CCTD-煤炭价格_到岸价格_俄罗斯_焦煤_价格(元/吨)",
        ]
        existing = [c for c in drop_candidates if c in df.columns]
        if existing:
            logger.info(f"删除指定列: {existing}")
            df = df.drop(columns=existing, errors="ignore")

        return df

    def _fill_missing_values_smart(self, df):
        try:
            import numpy as np
            import pandas as pd
        except Exception:
            return df

        if df is None or df.empty:
            return df

        # 排序并拷贝
        out = df.sort_values(by="date").reset_index(drop=True).copy()
        # 确保日期列为 datetime
        try:
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
        except Exception:
            pass
        non_date_cols = [c for c in out.columns if c != "date"]

        def infer_freq(dates: pd.Series) -> str:
            # 依据相邻非缺失日期的间隔中位数判断频率
            vals = pd.to_datetime(dates.dropna().unique())
            vals = np.sort(vals)
            if len(vals) < 2:
                return "sparse"
            diffs = np.diff(vals).astype("timedelta64[D]").astype(int)
            med = int(np.median(diffs)) if len(diffs) else 999
            if med <= 2:
                return "daily"
            if med <= 10:
                return "weekly"
            if med <= 40:
                return "monthly"
            return "sparse"

        # 不同频率的“期内填充”和限幅回填参数
        gap_limit = {
            "daily": 2,  # 最多前后各补2天
            "weekly": 6,  # 最多跨6天（不跨越第二周）
            "monthly": 15,  # 最多跨15天（尽量不跨月）
            "sparse": 0,
        }

        for col in non_date_cols:
            s = out[col]
            # 频率推断基于该列自身非空的日期
            freq = (
                infer_freq(out.loc[s.notna(), "date"]) if s.notna().any() else "sparse"
            )

            try:
                if freq == "weekly":
                    # 使用周期内填充（以周日为周结束），仅在周内 ffill/bfill
                    key = out["date"].dt.to_period("W-SUN")
                    filled = (
                        s.to_frame(col)
                        .assign(__wk__=key.values)
                        .groupby("__wk__")[col]
                        .apply(lambda x: x.ffill())
                        .reset_index(level=0, drop=True)
                    )
                    out[col] = filled
                elif freq == "monthly":
                    key = out["date"].dt.to_period("M")
                    filled = (
                        s.to_frame(col)
                        .assign(__m__=key.values)
                        .groupby("__m__")[col]
                        .apply(lambda x: x.ffill())
                        .reset_index(level=0, drop=True)
                    )
                    out[col] = filled
                else:
                    # daily 或 sparse：不做期内聚合
                    pass
            except Exception:
                pass

            # 对残余缺失做“限幅”前后填充，避免跨期长距离传播
            lim = gap_limit.get(freq, 0)
            if lim > 0:
                try:
                    out[col] = out[col].ffill(limit=lim)
                except Exception:
                    pass
            # 首段不回填：不在该列“首个真实观测值”之前用任何方式填充
            try:
                first_idx = s.first_valid_index()
                if first_idx is not None:
                    first_date = out.loc[first_idx, "date"]
                    mask_head = out["date"] < first_date
                    out.loc[mask_head, col] = np.nan
            except Exception:
                pass

        return out

    def _repair_cci5000_from_refs(self, df: Any) -> Any:
        """Repair CCI5000 using reference tables.

        Priority: CCI processed table -> ZMW reference -> existing values.
        """
        cci_df = None
        cci_path = self.cci_processed_path or self._find_file_by_tokens(["00000019", "cci"])
        if cci_path and os.path.exists(cci_path):
            cci_df = FileHandler.read_csv(cci_path)
        else:
            logger.warning("CCI reference file missing: %s", cci_path)

        zmw_df = None
        zmw_candidates: List[str] = []
        if getattr(self, "zmw_ref_path", None):
            zmw_candidates.append(self.zmw_ref_path)
        auto_zmw = self._find_file_by_tokens(["00000012"])
        if auto_zmw:
            zmw_candidates.append(auto_zmw)
        for candidate in zmw_candidates:
            try:
                if candidate and os.path.exists(candidate):
                    zmw_df = FileHandler.read_csv(candidate)
                    if zmw_df is not None:
                        break
            except Exception:
                continue
        if zmw_df is None:
            logger.warning("ZMW reference file missing: %s", zmw_candidates)

        if cci_df is None and zmw_df is None:
            return df

        import pandas as pd

        def _ensure_date_col(table):
            if table is None or table.empty:
                return None
            first_col = table.columns[0]
            if first_col != "date":
                table = table.rename(columns={first_col: "date"})
            table["date"] = pd.to_datetime(table["date"], errors="coerce")
            return table

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        cci_df = _ensure_date_col(cci_df)
        zmw_df = _ensure_date_col(zmw_df)

        def _find_col(table, keywords):
            if table is None:
                return None
            for col in table.columns:
                lowered = col.lower()
                if all(keyword.lower() in lowered for keyword in keywords):
                    return col
            return None

        cci_col = _find_col(cci_df, ["cci", "5000"]) if cci_df is not None else None
        zmw_col = _find_col(zmw_df, ["5000k"]) if zmw_df is not None else None

        if cci_df is not None and cci_col is not None:
            df = df.merge(
                cci_df[["date", cci_col]].rename(columns={cci_col: "cci5000_base"}),
                on="date",
                how="left",
            )
        else:
            df["cci5000_base"] = None

        if zmw_df is not None and zmw_col is not None:
            df = df.merge(
                zmw_df[["date", zmw_col]].rename(columns={zmw_col: "cci5000_zmw"}),
                on="date",
                how="left",
            )
        else:
            df["cci5000_zmw"] = None

        target_col = None
        for col in df.columns:
            lowered = col.lower()
            if "cci" in lowered and "5000" in lowered:
                target_col = col
                break
        if target_col is None:
            target_col = "CCI5000"
            if target_col not in df.columns:
                df[target_col] = None

        combined = (
            df["cci5000_base"].combine_first(df["cci5000_zmw"]).combine_first(df[target_col])
        )
        df["CCI5000"] = combined
        if target_col != "CCI5000":
            try:
                df[target_col] = combined
            except Exception:
                pass

        df = df.drop(columns=["cci5000_base", "cci5000_zmw"], errors="ignore")
        return df

    def _export_variant_tables(self, df: Any) -> None:
        """导出 3800/4700/5000 三份变体表：
        - 倒数四列固定为 {CCI5000, CCI进口4700, CCI进口3800, OT} 的集合，
          但顺序随变体而变，以保证"当前档指数"为倒数第二列、OT 为最后一列。
        """
        if df is None or df.empty:
            logger.warning("最终数据为空，跳过变体导出")
            return

        # 精确列名优先，其次宽松匹配
        def _pick_exact_or_fuzzy(
            name_exact: str, fuzzy_keys: List[str]
        ) -> Optional[str]:
            if name_exact in df.columns:
                return name_exact
            for col in df.columns:
                low = col.lower()
                if all(k.lower() in low for k in fuzzy_keys):
                    return col
            return None

        # 更精确的列名匹配
        cci5000_col = None
        cci_imp_4700_col = None
        cci_imp_3800_col = None

        for col in df.columns:
            col_lower = col.lower()
            if ("cci" in col_lower and "5000" in col_lower) or col == "CCI5000":
                cci5000_col = col
            elif "cci" in col_lower and "进口" in col and "4700" in col:
                cci_imp_4700_col = col
            elif "cci" in col_lower and "进口" in col and "3800" in col:
                cci_imp_3800_col = col

        # 使用标准列名优先
        if cci5000_col is None and "CCI5000" in df.columns:
            cci5000_col = "CCI5000"

        # 检查可用的CCI列，至少需要一列才能导出变体
        available_cci = [
            (name, col)
            for name, col in [
                ("CCI5000", cci5000_col),
                ("CCI进口4700", cci_imp_4700_col),
                ("CCI进口3800", cci_imp_3800_col),
            ]
            if col is not None
        ]

        if len(available_cci) == 0:
            logger.warning("未找到任何CCI列，跳过变体导出")
            return

        missing_keys = [
            name
            for name, col in [
                ("CCI5000", cci5000_col),
                ("CCI进口4700", cci_imp_4700_col),
                ("CCI进口3800", cci_imp_3800_col),
            ]
            if col is None
        ]
        if missing_keys:
            logger.info(f"部分CCI列缺失但继续导出: {missing_keys}")
            logger.info(f"可用CCI列: {[name for name, _ in available_cci]}")

        for grade in ["3800", "4700", "5000"]:
            variant = df.copy()

            # 当前档指数列
            if grade == "3800":
                grade_col = cci_imp_3800_col
                tail = [
                    c for c in [cci5000_col, cci_imp_4700_col, cci_imp_3800_col] if c
                ]
            elif grade == "4700":
                grade_col = cci_imp_4700_col
                tail = [
                    c for c in [cci5000_col, cci_imp_3800_col, cci_imp_4700_col] if c
                ]
            else:  # "5000"
                grade_col = cci5000_col
                tail = [
                    c for c in [cci_imp_4700_col, cci_imp_3800_col, cci5000_col] if c
                ]

            # 如果当前档指数列不存在，跳过该变体
            if grade_col is None:
                logger.warning(f"CCI{grade} 列不存在，跳过该变体")
                continue

            # 生成 OT 列（与当前档指数相同）
            variant["OT"] = variant[grade_col]
            tail.append("OT")

            # 基础列（排除尾部四列）
            base_cols = [c for c in variant.columns if c not in set(tail)]

            # 确保时间列在首列
            if base_cols and base_cols[0] != "date":
                cols = ["date"] + [c for c in base_cols if c != "date"]
            else:
                cols = base_cols

            ordered = cols + tail
            variant = variant[ordered]

            self._save_variant_table(variant, suffix=f"_{grade}")
            logger.info(f"已导出 {grade} 变体表，形状: {variant.shape}")

    def _save_variant_table(self, df: Any, suffix: str) -> str:
        """以和最终表一致的命名规则，追加后缀保存。"""
        base_name = getattr(self, "final_base_name", None)
        if not base_name:
            if self.target_data_path and os.path.exists(self.target_data_path):
                target_base = os.path.splitext(os.path.basename(self.target_data_path))[
                    0
                ]
                base_name = f"{target_base}_final"
            else:
                base_name = "coal_final"

        final_name = f"{base_name}{suffix}.csv"
        final_file = os.path.join(self.output_dir, final_name)

        try:
            df.to_csv(final_file, index=False, encoding="utf-8-sig")
        except PermissionError:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            alt_file = os.path.join(
                self.output_dir, f"{base_name}{suffix}_{timestamp}.csv"
            )
            logger.warning(f"权限问题，改为保存到: {alt_file}")
            df.to_csv(alt_file, index=False, encoding="utf-8-sig")
            final_file = alt_file

        return final_file

    def _export_final_with_cci6(self, df: Any) -> Optional[str]:
        """将 CCI 指数表(00000019-CCI指数_处理后)中的 6 列指数按列名语义匹配并追加：
        目标列名固定为：
        [CCI4500, CCI5000, CCI5500, CCI进口4700, CCI进口3800, CCI进口5500]
        注意：按列名关键词匹配（CCI/进口/热值），而非依据列位置，避免错位。
        若主表已存在同名列（尤其 CCI进口3800/CCI进口4700/CCI5000），则先删除后再追加以去重。
        输出文件名：最终表基名 + `_with_cci6.csv`。
        """
        try:
            from .utils import FileHandler
            import pandas as pd
        except Exception as e:
            logger.error(f"依赖导入失败: {e}")
            return None

        if df is None or df.empty:
            return None

        df = self._ensure_date_column(df)

        # 若已包含 CCI 六列（标准命名或 coal_new 的 out 命名），直接导出副本为 *_with_cci6.csv，避免重复追加
        try:
            required_cols = [
                "CCI4500",
                "CCI5000",
                "CCI5500",
                "CCI进口3800",
                "CCI进口4700",
                "CCI进口5500",
            ]
            alt_imports = ["CCI3800out", "CCI4700out", "CCI5500out"]
            have_required = all((c in df.columns) for c in required_cols)
            have_alt = all(
                (c in df.columns) for c in ["CCI4500", "CCI5000", "CCI5500"]
            ) and all((c in df.columns) for c in alt_imports)
            if have_required or have_alt:
                base_name = getattr(self, "final_base_name", None) or "coal_final"
                out_path = os.path.join(self.output_dir, f"{base_name}_with_cci6.csv")
                try:
                    # 移除 CCI 'out' 形态列再保存，避免冗余
                    try:
                        _drop = [
                            c
                            for c in ["CCI3800out", "CCI4700out", "CCI5500out"]
                            if c in df.columns
                        ]
                    except Exception:
                        _drop = []
                    df2 = df.drop(columns=_drop, errors="ignore") if _drop else df
                    df2.to_csv(out_path, index=False, encoding="utf-8-sig")
                except PermissionError:
                    from datetime import datetime as _dt

                    timestamp = _dt.now().strftime("%Y%m%d_%H%M%S")
                    out_path = os.path.join(
                        self.output_dir, f"{base_name}_with_cci6_{timestamp}.csv"
                    )
                    df2 = df.drop(columns=_drop, errors="ignore") if _drop else df
                    df2.to_csv(out_path, index=False, encoding="utf-8-sig")
                return out_path
        except Exception:
            pass

        # 配置控制：如禁用导出带6列CCI的文件，则直接返回
        try:
            if not getattr(self, "save_with_cci6_final", True):
                return None
        except Exception:
            pass

        cci_file = self.config.get("cci_timeline_file")
        if not cci_file or not os.path.exists(cci_file):
            logger.warning(f"CCI 文件不存在，跳过追加 6 列: {cci_file}")
            return None

        cci_df = FileHandler.read_csv(cci_file)
        # Prefer coal_new.csv as CCI6 source when available to align with target
        try:
            src_path = getattr(self, "cci_coal_new_path", None)
            if src_path and os.path.exists(src_path):
                cci_df_alt = FileHandler.read_csv(src_path)
                if cci_df_alt is not None and not cci_df_alt.empty:
                    cci_df = cci_df_alt
        except Exception:
            pass
        if cci_df is None or cci_df.empty:
            logger.warning("CCI 文件为空或无法读取，跳过追加 6 列")
            return None

        # 标准化时间列名并对齐到 date
        time_col = cci_df.columns[0]
        if time_col != "date":
            cci_df = cci_df.rename(columns={time_col: "date"})
        # 转为 datetime 以保证合并对齐
        try:
            cci_df["date"] = pd.to_datetime(cci_df["date"], errors="coerce")
        except Exception:
            pass
        base_time_col = df.columns[0]
        if base_time_col != "date":
            df_aligned = df.rename(columns={base_time_col: "date"}).copy()
        else:
            df_aligned = df.copy()

        # 基于列名语义匹配 6 个目标列，而不是按位置
        cols = list(cci_df.columns)
        cols_lower = [str(c).lower() for c in cols]

        def find_col(keys_all, keys_none=None):
            # 关键词匹配：排除 00000019（CCI 指数分地区列），避免误配
            for c, cl in zip(cols, cols_lower):
                if "00000019" in cl:
                    continue
                if all(k in cl for k in keys_all) and not any(
                    k in cl for k in (keys_none or [])
                ):
                    return c
            return None

        # 目标列映射：目标名 -> 匹配条件
        target_spec = {
            "CCI4500": {"all": ["cci", "4500"], "none": ["进口"]},
            "CCI5000": {"all": ["cci", "5000"], "none": ["进口"]},
            "CCI5500": {"all": ["cci", "5500"], "none": ["进口"]},
            "CCI进口3800": {"all": ["cci", "进口", "3800"], "none": []},
            "CCI进口4700": {"all": ["cci", "进口", "4700"], "none": []},
            "CCI进口5500": {"all": ["cci", "进口", "5500"], "none": []},
        }

        matched = {}
        # 优先使用标准命名的国内列
        for exact in ["CCI4500", "CCI5000", "CCI5500"]:
            if exact in cols:
                matched[exact] = exact
        # 其余再关键词匹配
        for tgt, spec in target_spec.items():
            if tgt in matched:
                continue
            col = find_col(spec["all"], spec.get("none"))
            if col is not None:
                matched[tgt] = col

        # 至少命中1列才有意义
        if not matched:
            logger.warning("CCI 文件未匹配到任何 CCI 列，跳过追加 6 列")
            return None

        # 构造子表并重命名为目标名
        value_cols = list(matched.values())
        rename_map = {src: tgt for tgt, src in matched.items()}
        cci_sub = cci_df[["date"] + value_cols].rename(columns=rename_map)

        # 避免与现有列重名：若已存在（特别是 CCI进口3800/CCI进口4700/CCI5000），先删除旧列再追加
        for col in rename_map.values():
            if col in df_aligned.columns:
                try:
                    df_aligned = df_aligned.drop(columns=[col])
                except Exception:
                    pass

        # 额外清理：删除来自“输入00000019-CCI指数_处理后_*”的旧进口指数列(3800/4700)，避免与新标准列重复
        try:
            drop_old = []
            for col in list(df_aligned.columns):
                s = str(col)
                sl = s.lower()
                if (
                    ("00000019" in sl or "cci指数_处理后" in s)
                    and ("cci" in sl)
                    and (("进口" in s and ("4700" in sl or "3800" in sl)))
                ):
                    drop_old.append(col)
            if drop_old:
                logger.info(f"删除旧CCI进口列以去重: {drop_old}")
                df_aligned = df_aligned.drop(columns=drop_old, errors="ignore")
        except Exception:
            pass

        # 左连接保证不改变主表时间轴
        merged = df_aligned.merge(cci_sub, on="date", how="left")

        # 恢复时间列名（若原始不是 date）
        if base_time_col != "date":
            merged = merged.rename(columns={"date": base_time_col})

        # 保存文件（固定命名前缀）
        base_name = getattr(self, "final_base_name", None) or "coal_final"
        out_path = os.path.join(self.output_dir, f"{base_name}_with_cci6.csv")
        try:
            merged.to_csv(out_path, index=False, encoding="utf-8-sig")
        except PermissionError:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(
                self.output_dir, f"{base_name}_with_cci6_{timestamp}.csv"
            )
            merged.to_csv(out_path, index=False, encoding="utf-8-sig")

        return out_path
        # 运费场景禁用该扩展
        try:
            if not getattr(self, "append_extra_price_columns", True):
                return final_df
        except Exception:
            pass
        # 运费场景禁用该扩展
        try:
            if not getattr(self, "append_extra_price_columns", True):
                return final_df
        except Exception:
            pass

