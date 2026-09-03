#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据合并器
负责将拆分后的数据合并到统一时间轴上
"""

import os
import glob
import pandas as pd
import logging
from typing import Dict, Optional, List
from .utils import (
    FileHandler,
    DataFrameProcessor,
    ColumnNameProcessor,
    TextNormalizer,
)

logger = logging.getLogger(__name__)


class DataMerger:
    """数据合并器主类"""

    def __init__(
        self,
        output_dir: str,
        target_file_path: Optional[str] = None,
        cci_timeline_file: Optional[str] = None,
        timeline_mode: str = "cci",
    ):
        self.output_dir = output_dir
        self.target_file_path = target_file_path
        self.cci_timeline_file = cci_timeline_file
        self.timeline_mode = (timeline_mode or "cci").lower()
        self.split_data_dir = os.path.join(output_dir, "split_data")

    def merge_all_data(
        self, reference_file: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """合并所有拆分数据"""
        logger.info("开始合并拆分数据")

        if not os.path.exists(self.split_data_dir):
            logger.error("拆分数据目录不存在，请先执行拆分步骤")
            return None

        # 创建基础时间轴
        base_df = self._create_base_timeline(reference_file)
        if base_df.empty:
            logger.error("无法创建基础时间轴")
            return None

        time_col = base_df.columns[0]
        logger.info(f"基础时间轴: {base_df.shape[0]} 个时间点")

        # 遍历所有拆分数据并合并
        merged_count = 0
        for folder_name in os.listdir(self.split_data_dir):
            folder_path = os.path.join(self.split_data_dir, folder_name)
            if not os.path.isdir(folder_path):
                continue

            logger.info(f"合并文件夹: {folder_name}")
            base_df, folder_count = self._merge_folder_data(
                base_df, folder_path, time_col
            )
            merged_count += folder_count

        logger.info(f"合并完成: {merged_count} 个数据列")
        logger.info(f"最终数据形状: {base_df.shape}")

        # 数据后处理
        final_df = self._post_process_merged_data(base_df, time_col)

        # 保存合并结果
        merged_file = os.path.join(self.output_dir, "merged_coal_data.csv")
        final_df.to_csv(merged_file, index=False, encoding="utf-8-sig")
        logger.info(f"合并结果已保存: {merged_file}")

        try:
            # 列出未匹配的目标列（仅用于诊断）
            target_columns: list[str] = []
            if self.target_file_path and os.path.exists(self.target_file_path):
                tdf = FileHandler.read_csv(self.target_file_path)
                if tdf is not None and len(tdf.columns) > 1:
                    target_columns = [c for c in tdf.columns[1:] if str(c).strip()]
            if target_columns:
                unmatched = [
                    str(c)
                    for c in target_columns
                    if (c in final_df.columns)
                    and getattr(final_df[c], "isna", lambda: None)().all()
                ]
                if unmatched:
                    logger.info(f"未匹配的目标列({len(unmatched)}): {unmatched}")
        except Exception:
            pass
        return final_df

    def _create_base_timeline(
        self, reference_file: Optional[str] = None
    ) -> pd.DataFrame:
        """鍒涘缓鍩虹鏃堕棿杞?"""
        timeline_frames: list[pd.DataFrame] = []

        if self.cci_timeline_file and os.path.exists(self.cci_timeline_file):
            logger.info(f"浣跨敤 CCI 鏃堕棿杞存枃浠? {self.cci_timeline_file}")
            cci_reference = self._load_reference_timeline(
                self.cci_timeline_file,
                time_only=True,
            )
            if cci_reference is not None and not cci_reference.empty:
                timeline_frames.append(cci_reference)

        cci_split_df = self._generate_timeline_from_specific_split_folder(
            must_include_tokens=["00000019", "CCI鎸囨暟_澶勭悊鍚?"],
        )
        if cci_split_df is not None and not cci_split_df.empty:
            logger.info("浣跨敤 CCI(00000019) 鎷嗗垎鏂囦欢澶规椂闂磋酱")
            timeline_frames.append(cci_split_df)

        if reference_file and os.path.exists(reference_file):
            logger.info(f"浣跨敤鍙傝€冩枃浠? {reference_file}")
            ref_df = self._load_reference_timeline(reference_file)
            if ref_df is not None and not ref_df.empty:
                timeline_frames.append(ref_df)

        if self.target_file_path and os.path.exists(self.target_file_path):
            logger.info(f"浣跨敤鐩爣鏂囦欢: {self.target_file_path}")
            tgt_df = self._load_reference_timeline(
                self.target_file_path,
                time_only=True,
            )
            if tgt_df is not None and not tgt_df.empty:
                timeline_frames.append(tgt_df)

        logger.info("浠庢媶鍒嗘暟鎹嚜鍔ㄧ敓鎴愭椂闂磋酱")
        split_df = self._generate_timeline_from_splits()
        if split_df is not None and not split_df.empty:
            timeline_frames.append(split_df)

        if not timeline_frames:
            logger.error("鏃犳硶鍒涘缓鍩虹鏃堕棿杞?")
            return pd.DataFrame()

        def to_series(df: pd.DataFrame) -> pd.Series:
            if df is None or df.empty:
                return pd.Series(dtype="datetime64[ns]")
            col = df.columns[0]
            ser = pd.to_datetime(df[col], errors="coerce").dropna().drop_duplicates()
            return ser

        series_list = [to_series(frame) for frame in timeline_frames if frame is not None]

        if not series_list:
            logger.error("鏃犳硶鍒涘缓鍩虹鏃堕棿杞?")
            return pd.DataFrame()

        union_ser = pd.concat(series_list, ignore_index=True)
        union_ser = union_ser.dropna().drop_duplicates().sort_values()
        base_df = pd.DataFrame({"date": union_ser})
        logger.info(f"鐢熸垚鏃堕棿杞? {base_df.shape[0]} 涓椂闂寸偣")
        return base_df

    def _load_reference_timeline(
        self, file_path: str, time_only: bool = False
    ) -> pd.DataFrame:
        """从参考文件加载时间轴"""
        df = FileHandler.read_csv(file_path)
        if df is None or df.empty:
            logger.warning(f"参考文件为空: {file_path}")
            return pd.DataFrame()

        time_col = df.columns[0]
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col])

        if time_only:
            # 仅保留时间列
            df = df[[time_col]].drop_duplicates()

        return DataFrameProcessor.standardize_time_column(df, time_col)

    def _generate_timeline_from_splits(self) -> pd.DataFrame:
        """从拆分数据生成时间轴"""
        all_dates = set()

        # 收集所有时间点
        for folder_name in os.listdir(self.split_data_dir):
            folder_path = os.path.join(self.split_data_dir, folder_name)
            if not os.path.isdir(folder_path):
                continue

            for csv_file in glob.glob(os.path.join(folder_path, "*.csv")):
                try:
                    df = FileHandler.read_csv(csv_file)
                    if df is not None and not df.empty:
                        time_col = DataFrameProcessor.detect_time_column(df)
                        if time_col:
                            dates = pd.to_datetime(
                                df[time_col], errors="coerce"
                            ).dropna()
                            all_dates.update(dates)
                except Exception as e:
                    logger.warning(f"读取文件失败 {csv_file}: {e}")
                    continue

        if not all_dates:
            logger.error("未找到任何有效的时间数据")
            return pd.DataFrame()

        # 创建时间轴DataFrame
        sorted_dates = sorted(all_dates)
        base_df = pd.DataFrame({"date": sorted_dates})
        logger.info(f"生成时间轴: {len(sorted_dates)} 个时间点")

        return base_df

    def _generate_timeline_from_specific_split_folder(
        self,
        must_include_tokens: List[str],
    ) -> pd.DataFrame:
        """从指定拆分文件夹（名称需包含所有 token）生成时间轴。
        仅聚合该文件夹内所有子表的时间点，不与其他来源取并集。
        """
        try:
            if not os.path.exists(self.split_data_dir):
                return pd.DataFrame()

            target_folder_path = None
            for folder_name in os.listdir(self.split_data_dir):
                try:
                    ok = all(token in folder_name for token in must_include_tokens)
                except Exception:
                    ok = False
                if ok:
                    target_folder_path = os.path.join(self.split_data_dir, folder_name)
                    break

            if not target_folder_path or not os.path.isdir(target_folder_path):
                return pd.DataFrame()

            all_dates = set()
            for csv_file in glob.glob(os.path.join(target_folder_path, "*.csv")):
                try:
                    df = FileHandler.read_csv(csv_file)
                    if df is None or df.empty:
                        continue
                    time_col = DataFrameProcessor.detect_time_column(df)
                    if not time_col:
                        continue
                    dates = pd.to_datetime(df[time_col], errors="coerce").dropna()
                    all_dates.update(dates)
                except Exception:
                    continue

            if not all_dates:
                return pd.DataFrame()

            sorted_dates = sorted(all_dates)
            base_df = pd.DataFrame({"date": sorted_dates})
            logger.info(f"从指定文件夹生成时间轴: {len(sorted_dates)} 个时间点")
            return base_df
        except Exception:
            return pd.DataFrame()

    def _merge_folder_data(
        self, base_df: pd.DataFrame, folder_path: str, time_col: str
    ) -> tuple[pd.DataFrame, int]:
        """合并文件夹中的数据"""
        merged_count = 0

        for csv_file in glob.glob(os.path.join(folder_path, "*.csv")):
            try:
                sub_df = FileHandler.read_csv(csv_file)
                if sub_df is None or sub_df.empty:
                    continue

                # 标准化子表
                sub_df = self._standardize_sub_table(
                    sub_df,
                    folder_path,
                    csv_file,
                )

                # 合并到主表
                base_df = self._merge_to_main(base_df, sub_df, time_col)
                merged_count += sub_df.shape[1] - 1  # 排除时间列

            except Exception as e:
                logger.error(f"合并文件失败 {csv_file}: {e}")
                continue

        return base_df, merged_count

    def _standardize_sub_table(
        self, sub_df: pd.DataFrame, folder_path: str, csv_file: str
    ) -> pd.DataFrame:
        """标准化子表格式"""
        # 标准化时间列
        time_col = sub_df.columns[0]
        sub_df = DataFrameProcessor.standardize_time_column(sub_df, time_col)

        # 重命名数据列（如果需要）
        folder_name = os.path.basename(folder_path)
        file_name = os.path.splitext(os.path.basename(csv_file))[0]

        rename_dict = {}
        for col in sub_df.columns[1:]:  # 跳过时间列
            # 检查是否已经是目标列名格式
            if not self._is_target_column_format(col):
                rename_dict[col] = f"{folder_name}--{file_name}--{col}"

        if rename_dict:
            sub_df = sub_df.rename(columns=rename_dict)

        return sub_df

    def _is_target_column_format(self, col_name: str) -> bool:
        """检查是否为目标列名格式"""
        # 放宽：包含8位数字或包含 "-CCTD-" 的列视为目标格式（以保留 60+ 派生列的原名）
        return (ColumnNameProcessor.extract_id(col_name) is not None) or (
            "-CCTD-" in str(col_name)
        )

    def _merge_to_main(
        self, main_df: pd.DataFrame, sub_df: pd.DataFrame, time_col: str
    ) -> pd.DataFrame:
        """合并子表到主表"""
        sub_time_col = sub_df.columns[0]

        # 处理重复列名
        main_cols = set(main_df.columns)
        duplicate_cols = []

        for col in sub_df.columns[1:]:  # 跳过时间列
            if col in main_cols:
                duplicate_cols.append(col)

        # 重命名重复列
        if duplicate_cols:
            rename_dict = {}
            for col in duplicate_cols:
                counter = 1
                new_name = f"{col}_dup{counter}"
                while new_name in main_cols or new_name in sub_df.columns:
                    counter += 1
                    new_name = f"{col}_dup{counter}"
                rename_dict[col] = new_name
                logger.debug(f"重命名重复列: {col} -> {new_name}")

            sub_df = sub_df.rename(columns=rename_dict)

        # 执行左连接
        merged = pd.merge(
            main_df,
            sub_df,
            left_on=time_col,
            right_on=sub_time_col,
            how="left",
        )

        # 删除重复的时间列
        if sub_time_col != time_col and sub_time_col in merged.columns:
            merged = merged.drop(columns=[sub_time_col])

        return merged

    def _post_process_merged_data(
        self, df: pd.DataFrame, time_col: str
    ) -> pd.DataFrame:
        """合并数据后处理"""
        logger.info("开始数据后处理")

        # 按时间排序
        df = df.sort_values(by=time_col).reset_index(drop=True)

        # 统一时间列名为 'date'
        if time_col != "date":
            df = df.rename(columns={time_col: "date"})

        # 规范时间列类型
        try:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        except Exception:
            pass

        # 同一日期去重（保留首次出现）
        try:
            if df["date"].is_monotonic_increasing is False:
                df = df.sort_values(by="date").reset_index(drop=True)
        except Exception:
            df = df.sort_values(by="date").reset_index(drop=True)
        try:
            df = df.drop_duplicates(subset=["date"], keep="first").reset_index(
                drop=True
            )
        except Exception:
            pass

        # 缺失值填充：先向下再向上（仅对非时间列）
        value_cols = [c for c in df.columns if c != "date"]
        try:
            df[value_cols] = df[value_cols].ffill().bfill()
            logger.info("已完成缺失值前后向填充")
        except Exception:
            try:
                df = df.ffill().bfill()
                logger.info("已完成整表缺失值前后向填充")
            except Exception:
                logger.warning("缺失值填充失败，保留原始缺失情况")

        # 数据质量统计
        total_cells = df.shape[0] * df.shape[1]
        null_cells = df.isnull().sum().sum()
        completeness = (total_cells - null_cells) / total_cells * 100

        logger.info(f"数据完整性: {completeness:.2f}%")
        logger.info(f"数据维度: {df.shape}")

        return df


class TargetAssembler:
    """目标格式组装器"""

    def __init__(self, target_file_path: str):
        self.target_file_path = target_file_path
        self.target_df = FileHandler.read_csv(target_file_path)
        # 记录最近一次组装的目标列与来源列映射（用于诊断未匹配列）
        self._last_match_map: Dict[str, Optional[str]] = {}

        if self.target_df is None:
            raise ValueError(f"无法读取目标文件: {target_file_path}")

        # 过滤目标中的冗余列（如 CR/CV/CR-CV），避免传播到最终表
        try:
            cols = list(self.target_df.columns)
            drop_cols = []
            for c in cols:
                name = str(c).strip()
                upper = name.upper()
                if upper in {"CR", "CV", "CR-CV", "CR_CV"}:
                    drop_cols.append(c)
            if drop_cols:
                self.target_df = self.target_df.drop(columns=drop_cols, errors="ignore")
                import logging as _logging

                _logging.getLogger(__name__).info(f"已从目标中移除冗余列: {drop_cols}")
        except Exception:
            pass

    def assemble_to_target_format(self, merged_df: pd.DataFrame) -> pd.DataFrame:
        """按目标格式组装数据"""
        logger.info("开始按目标格式组装数据")

        # 统一时间列名
        src_time_col = merged_df.columns[0]
        tgt_time_col = self.target_df.columns[0]

        if src_time_col != tgt_time_col:
            merged_df = merged_df.rename(columns={src_time_col: tgt_time_col})

        target_columns = [col for col in self.target_df.columns if col != tgt_time_col]

        # 构建最终数据框
        final_df = pd.DataFrame({tgt_time_col: merged_df[tgt_time_col]})
        matched_count = 0

        for target_col in target_columns:
            best_match = self._find_best_match(
                target_col,
                merged_df.columns,
            )

            if best_match:
                final_df[target_col] = merged_df[best_match]
                matched_count += 1
                logger.debug(f"匹配成功: {target_col} <- {best_match}")
                try:
                    self._last_match_map[str(target_col)] = str(best_match)
                except Exception:
                    self._last_match_map[str(target_col)] = best_match  # type: ignore
            else:
                # 未匹配到时也保留目标列，使用空值占位，确保结构严格对齐目标
                final_df[target_col] = None
                self._last_match_map[str(target_col)] = None

        logger.info(f"目标格式组装完成: 匹配 {matched_count}/{len(target_columns)} 列")

        return final_df

    def get_last_match_map(self) -> Dict[str, Optional[str]]:
        """返回最近一次 assemble 的匹配映射。"""
        return dict(self._last_match_map)

    def _find_best_match(
        self, target_col: str, source_cols: List[str]
    ) -> Optional[str]:
        """为目标列寻找最佳匹配的源列"""
        # 1. 完全匹配
        for col in source_cols:
            if col == target_col:
                return col

        # 2. 清理pandas后缀后匹配
        for col in source_cols:
            clean_col = ColumnNameProcessor.clean_pandas_suffix(col)
            if clean_col == target_col:
                return col

        # 3. 基于ID和特征的模糊匹配
        target_id, target_product, target_region, target_measure = (
            ColumnNameProcessor.parse_target_column(target_col)
        )

        if not target_id:
            return None

        best_col = None
        best_score = 0

        for col in source_cols:
            score = self._calculate_match_score(
                col,
                target_id,
                target_product,
                target_region,
                target_measure,
                target_col,
            )

            if score > best_score:
                best_score = score
                best_col = col

        # 只返回分数足够高的匹配
        return best_col if best_score >= 3 else None

    def _calculate_match_score(
        self,
        source_col: str,
        target_id: str,
        target_product: Optional[str],
        target_region: Optional[str],
        target_measure: Optional[str],
        target_full_col: Optional[str] = None,
    ) -> int:
        """计算匹配分数"""
        source_id = ColumnNameProcessor.extract_id(source_col)
        if source_id != target_id:
            return 0

        score = 1  # ID匹配基础分

        # 若目标列显式为 CCTD（60+），进一步偏好含 CCTD 的来源列；
        # 避免与 500+ 的同号表（公司/港口口径）混淆
        # 调整：根据目标列名是否包含 CCTD 来偏好来源列
        tgt_has_cctd = (
            ("CCTD" in str(target_id))
            or ("CCTD" in str(target_product or ""))
            or ("CCTD" in str(target_region or ""))
        )
        # 若目标列名本身包含 "-CCTD-" 关键字（更稳妥的判断）
        try:
            if not tgt_has_cctd:
                # 在完整目标列名中查找（调用栈上可用）
                pass
        except Exception:
            pass
        # 明确：若目标完整列名含 CCTD，来源列名含 CCTD 再加分，否则减分
        try:
            if target_full_col and (
                ("-CCTD-" in str(target_full_col)) or ("CCTD" in str(target_full_col))
            ):
                if "-CCTD-" in source_col:
                    score += 4
                else:
                    score -= 2
        except Exception:
            pass
        if "-CCTD-" in source_col and tgt_has_cctd:
            score += 4
        elif "-CCTD-" not in source_col and tgt_has_cctd:
            score -= 2

        # 计量匹配
        if target_measure and ColumnNameProcessor.match_measure(
            source_col, target_measure
        ):
            score += 3
        else:
            # 放宽：基于单位/关键词的弱匹配加分，提升运费/指数类列名匹配稳健性
            try:
                tm = str(target_measure)
                sc = str(source_col)
                tm_l, sc_l = tm.lower(), sc.lower()
                def has_any(s, keys):
                    return any(k in s for k in keys)
                unit_added = False
                if has_any(tm_l, ["美元", "usd"]):
                    if has_any(sc_l, ["美元", "usd"]) and has_any(sc_l, ["本期", "当期", "价格", "price", "value", "指数", "index"]):
                        score += 2; unit_added = True
                if not unit_added and ("元" in tm_l or "rmb" in tm_l):
                    if has_any(sc_l, ["元", "rmb"]) and has_any(sc_l, ["本期", "当期", "价格", "price", "value"]):
                        score += 2; unit_added = True
                if not unit_added and ("点" in tm_l or "index" in tm_l or "指数" in tm_l):
                    if has_any(sc_l, ["点", "index", "指数"]) and has_any(sc_l, ["本期", "当期", "价格", "value", "price", "指数", "index"]):
                        score += 2
            except Exception:
                pass

        # 产品匹配
        if target_product:
            product_norm = TextNormalizer.normalize(target_product)
            source_norm = TextNormalizer.normalize(source_col)
            if (
                product_norm in source_norm
                or product_norm.replace("煤", "") in source_norm
            ):
                score += 2

        # 地区匹配
        if target_region:
            region_norm = TextNormalizer.normalize(target_region)
            source_norm = TextNormalizer.normalize(source_col)
            if region_norm in source_norm:
                score += 1

        return score
