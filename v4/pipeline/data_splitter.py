#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据拆分器
负责按目标驱动策略拆分原始数据
"""

import os
import pandas as pd
import logging
from typing import Dict, List, Optional
from .utils import (
    TextNormalizer,
    ColumnNameProcessor,
    FileHandler,
    DataFrameProcessor,
)

logger = logging.getLogger(__name__)


class TargetAnalyzer:
    """目标列分析器"""

    def __init__(self, target_file_path: Optional[str] = None):
        self.target_file_path = target_file_path
        self.target_columns = []
        self.split_rules = {}
        self.source_mapping = {}

        if target_file_path and os.path.exists(target_file_path):
            self._analyze_target_file()

    def _analyze_target_file(self):
        """分析目标文件，提取拆分规则"""
        target_df = FileHandler.read_csv(self.target_file_path)
        if target_df is None:
            logger.warning("目标数据文件为空或无法读取")
            return
        # 允许“只有表头、无数据行”的目标文件：仅用表头定义目标列
        if target_df.empty:
            try:
                if len(target_df.columns) <= 1:
                    logger.warning("目标数据文件为空或无法读取（表头不足）")
                    return
                else:
                    logger.info("目标文件无数据，仅使用表头定义目标列")
            except Exception:
                logger.warning("目标数据文件为空或无法读取（异常）")
                return

        # 排除时间列
        self.target_columns = [col for col in target_df.columns[1:] if str(col).strip()]

        # 构建拆分规则
        self._build_split_rules()
        self._build_source_mapping()

        logger.info(
            f"目标分析完成：{len(self.target_columns)} 个目标列，"
            f"{len(self.split_rules)} 个拆分规则"
        )

    def _build_split_rules(self):
        """构建拆分规则"""
        for col in self.target_columns:
            token_id, product, region, measure = (
                ColumnNameProcessor.parse_target_column(col)
            )
            if not token_id:
                continue

            table_id = token_id.lstrip("0")
            if table_id not in self.split_rules:
                self.split_rules[table_id] = {
                    "split_by_region": False,
                    "target_columns": [],
                }

            # 如果有地区信息，标记需要按地区拆分
            if region:
                self.split_rules[table_id]["split_by_region"] = True

            item = {
                "column_name": col,
                "table_id": table_id,
                "product": product,
                "region": region,
                "measure": measure,
            }

            # 268 动力煤2#：从列名解析严格硫分标签（S0.4 / S0.7 等）
            try:
                if table_id == "268":
                    se = self._parse_sulfur_from_name(col)
                    if se is not None:
                        item["sulfur_exact"] = se
            except Exception:
                pass

            self.split_rules[table_id]["target_columns"].append(item)

    def _build_source_mapping(self):
        """构建数据源映射"""
        for col in self.target_columns:
            token_id, _, _, _ = ColumnNameProcessor.parse_target_column(col)
            if not token_id:
                continue

            table_id = token_id.lstrip("0")
            # 根据列名特征判断数据源偏好
            if self._prefer_60_plus_source(col):
                self.source_mapping[table_id] = "60_plus"
            else:
                self.source_mapping[table_id] = "500_plus"

    def _prefer_60_plus_source(self, col_name: str) -> bool:
        """判断是否偏好60+数据源
        注意：此方法仅用于启发式判断，最终数据源由 get_preferred_source() 决定
        """
        if not col_name:
            return False
        # 移除"运费"关键词，因为运费数据实际在 500+ 中
        # 仅保留 CCTD、电力、发电、到岸价格等确实在 60+ 的数据
        keywords_60_plus = ["CCTD", "电力", "发电", "到岸价格"]
        return any(keyword in col_name for keyword in keywords_60_plus)

    def _parse_sulfur_from_name(self, column_name: str) -> Optional[str]:
        """从列名中解析硫分精确值，仅用于 268 动力煤2#
        识别常见写法：S0.4 / S=0.4 / 硫0.4% / 硫=0.7 等
        返回 '0.4' / '0.7' 或 None
        """
        try:
            import re

            name = TextNormalizer.normalize(column_name)
            m = re.search(
                r"(?i)(?:s\s*[:：=]?\s*(0\.4|0\.7)|硫(?:分|份|含量)?\s*[:：=]?\s*(0\.4|0\.7))",
                name,
            )
            if m:
                val = m.group(1) or m.group(2)
                return val
        except Exception:
            pass
        return None

    def get_split_rule(self, table_id: str) -> Optional[Dict]:
        """获取指定表格的拆分规则"""
        return self.split_rules.get(table_id.lstrip("0"))

    def get_preferred_source(self, table_id: str) -> str:
        """获取首选数据源"""
        tid = table_id.lstrip("0")
        # 指数"处理后"表（根指数直映射）在 60+ 数据集中，强制优先 60+
        # 同时对关键煤价类表格强制 60+
        # 注意：运费表（347-355）和港口数据（357、362）实际在 500+ 中，不应包含在此列表
        if tid in {
            "4",
            "5",
            "10",
            "11",
            "19",
            "268",
            "275",
            "279",
        }:
            return "60_plus"
        return self.source_mapping.get(tid, "500_plus")


class DataSplitter:
    """数据拆分器主类"""

    def __init__(
        self,
        raw_data_dirs: List[str],
        output_dir: str,
        target_analyzer: TargetAnalyzer,
    ):
        self.raw_data_dirs = raw_data_dirs
        self.output_dir = output_dir
        self.target_analyzer = target_analyzer

        # 数据源名称映射
        self.source_name_mapping = {
            "60_plus": "60+",
            "500_plus": "500+",
        }

        # 可用表格ID（按数据源聚合），在 split_all_data 中构建
        self.available_table_ids_by_source = {}

    def split_all_data(self) -> Dict[str, int]:
        """拆分所有原始数据"""
        logger.info("开始拆分原始数据")

        # 确保顶层 split_data 目录存在（即使没有任何子表生成，供后续合并阶段检测）
        try:
            os.makedirs(os.path.join(self.output_dir, "split_data"), exist_ok=True)
        except Exception:
            pass

        # 按数据源组织文件
        files_by_source = self._organize_files_by_source()

        # 预先统计各数据源可用的表格ID集合（用于偏好来源存在性判断）
        self.available_table_ids_by_source = {}
        for source_name, files in files_by_source.items():
            ids = set()
            for file_path in files:
                base = os.path.splitext(os.path.basename(file_path))[0]
                tid = ColumnNameProcessor.extract_id(base)
                if tid:
                    ids.add(tid.lstrip("0"))
            self.available_table_ids_by_source[source_name] = ids

        split_summary = {}
        processed_tables = set()

        for source_name, files in files_by_source.items():
            logger.info(f"处理数据源 {source_name}: {len(files)} 个文件")

            for file_path in files:
                table_summary = self._split_single_file(
                    file_path, source_name, processed_tables
                )
                if table_summary:
                    split_summary.update(table_summary)

        self._save_split_summary(split_summary)
        return split_summary

    def _organize_files_by_source(self) -> Dict[str, List[str]]:
        """按数据源组织文件"""
        files_by_source: Dict[str, List[str]] = {}

        # 聚合同名来源目录（例如多个批次下的 "60+"），避免后写覆盖先写
        for raw_dir in self.raw_data_dirs:
            try:
                source_name = os.path.basename(raw_dir)
                files = [f for f in os.listdir(raw_dir) if f.endswith(".csv")]
            except Exception:
                continue
            if source_name not in files_by_source:
                files_by_source[source_name] = []
            # 追加该来源下的所有文件完整路径
            files_by_source[source_name].extend(
                [os.path.join(raw_dir, f) for f in files]
            )

        # 为了在重复表时使用“较新”文件覆盖“较旧”，按修改时间排序（旧->新），保证新文件后处理
        try:
            for key, paths in files_by_source.items():
                paths.sort(key=lambda p: os.path.getmtime(p))
        except Exception:
            pass

        return files_by_source

    def _split_single_file(
        self, file_path: str, source_name: str, processed_tables: set
    ) -> Optional[Dict[str, int]]:
        """拆分单个文件"""
        base_name = os.path.splitext(os.path.basename(file_path))[0]

        # 提取表格ID
        table_id = ColumnNameProcessor.extract_id(base_name)
        if not table_id:
            logger.warning(f"无法从文件名提取表格ID: {base_name}")
            return None

        table_id_norm = table_id.lstrip("0")

        # 检查是否需要处理此表格
        split_rule = self.target_analyzer.get_split_rule(table_id_norm)
        if not split_rule:
            logger.info(f"表格 {table_id_norm} 不在目标列表中，跳过")
            return None

        # 在首次处理该ID之前，按偏好来源筛选，避免先处理到非优先来源（如500+）
        preferred_source = self.target_analyzer.get_preferred_source(table_id_norm)
        required_source_name = self.source_name_mapping.get(preferred_source)
        if required_source_name and source_name != required_source_name:
            # 仅当优先来源确实包含该表格ID时才跳过，避免因偏好导致的错过
            preferred_ids = self.available_table_ids_by_source.get(
                required_source_name, set()
            )
            if table_id_norm in preferred_ids:
                logger.info(
                    (
                        f"跳过表格 {table_id_norm} (来源: {source_name})，"
                        f"优先使用 {required_source_name}"
                    )
                )
                return None
            else:
                logger.info(
                    (
                        f"未在优先来源 {required_source_name} 找到表格 {table_id_norm}，"
                        f"使用 {source_name}"
                    )
                )

        # 处理重复表格ID
        if table_id_norm in processed_tables:
            # 若当前为优先来源，允许处理（覆盖非优先来源的先行处理）
            if required_source_name and source_name == required_source_name:
                pass
            else:
                # 非优先来源或未知偏好：跳过重复
                logger.info(f"跳过已处理表格 {table_id_norm} (来源: {source_name})")
                return None

        processed_tables.add(table_id_norm)

        # 读取并拆分数据
        df = FileHandler.read_csv(file_path)
        if df is None or df.empty:
            logger.warning(f"跳过空文件: {file_path}")
            return None

        split_count = self._execute_split(df, base_name, split_rule, source_name)

        if split_count > 0:
            logger.info(f"完成拆分: {base_name} -> {split_count} 个子表")
            return {base_name: split_count}
        else:
            logger.info(f"未生成子表: {base_name}")
            return None

    def _execute_split(
        self, df: pd.DataFrame, base_name: str, split_rule: Dict, source_name: str
    ) -> int:
        """执行具体的拆分操作"""
        output_dir = os.path.join(self.output_dir, "split_data", base_name)
        os.makedirs(output_dir, exist_ok=True)

        # 检测时间列
        time_col = DataFrameProcessor.detect_time_column(df)
        if not time_col:
            logger.warning(f"未找到时间列: {base_name}")
            return 0

        target_columns = split_rule["target_columns"]
        need_region_split = split_rule["split_by_region"]

        split_count = 0

        if not need_region_split:
            # 整体拆分
            split_count = self._split_without_region(
                df, time_col, target_columns, output_dir
            )
        else:
            # 按地区拆分
            split_count = self._split_with_region(
                df, time_col, target_columns, output_dir
            )

        # 额外生成：对特定表的“二次拆分”附加列（不影响原有列）
        try:
            # 259 动力煤：按原产地白名单生成 3 个附加列
            table_id_current = (
                target_columns[0].get("table_id") if target_columns else None
            )
            if table_id_current == "259":
                split_count += self._produce_259_origin_extras(
                    df=df,
                    time_col=time_col,
                    output_dir=output_dir,
                )
            # 268 动力煤2#：改为按发热量二次拆分（替代硫分）
            if table_id_current == "268":
                split_count += self._produce_268_heat_extras(
                    df=df,
                    time_col=time_col,
                    output_dir=output_dir,
                )
            # 275 焦煤：按到岸港口生成 主焦煤(京唐/天津)、1/3焦煤(京唐/大连) 附加列
            if table_id_current == "275":
                split_count += self._produce_275_port_extras(
                    df=df,
                    time_col=time_col,
                    output_dir=output_dir,
                )
            # 353：按航线名称二次拆分（聚合不同载重）
            if table_id_current == "353":
                split_count += self._produce_353_route_extras(
                    df=df,
                    time_col=time_col,
                    output_dir=output_dir,
                )
        except Exception:
            pass

        # 清理空目录
        if split_count == 0 and os.path.exists(output_dir):
            try:
                os.rmdir(output_dir)
            except OSError:
                pass

        return split_count

    def _split_without_region(
        self,
        df: pd.DataFrame,
        time_col: str,
        target_columns: List[Dict],
        output_dir: str,
    ) -> int:
        """不按地区拆分"""
        split_count = 0

        for target_col_info in target_columns:
            sub_table = self._extract_target_data(df, time_col, target_col_info)
            if sub_table is not None and not sub_table.empty:
                filename = FileHandler.sanitize_filename(
                    f"{target_col_info['column_name']}.csv"
                )
                file_path = os.path.join(output_dir, filename)
                sub_table.to_csv(file_path, index=False, encoding="utf-8-sig")
                split_count += 1

        return split_count

    def _split_with_region(
        self,
        df: pd.DataFrame,
        time_col: str,
        target_columns: List[Dict],
        output_dir: str,
    ) -> int:
        """按地区拆分"""
        split_count = 0

        region_cols = DataFrameProcessor.detect_region_columns(df)
        product_cols = DataFrameProcessor.detect_product_columns(df)

        for target_col_info in target_columns:
            filtered_df = self._filter_by_target(
                df, target_col_info, region_cols, product_cols
            )

            if filtered_df.empty:
                continue

            sub_table = self._extract_target_data(
                filtered_df, time_col, target_col_info
            )

            if sub_table is not None and not sub_table.empty:
                filename = FileHandler.sanitize_filename(
                    f"{target_col_info['column_name']}.csv"
                )
                file_path = os.path.join(output_dir, filename)
                sub_table.to_csv(file_path, index=False, encoding="utf-8-sig")
                split_count += 1

        return split_count

    def _extract_origin_from_region(self, region: str) -> str:
        """从类似 '原产地_山西' 的地区字段抽取产地名"""
        if not region:
            return ""
        r = TextNormalizer.normalize(region)
        if r.startswith("原产地_"):
            return r.split("_", 1)[1]
        return r

    def _extract_region_keyword(self, region: str) -> str:
        """从类似 '到岸港口_京唐' 提取用于匹配的关键词（取最后一个 '_' 之后的部分）"""
        if not region:
            return ""
        r = TextNormalizer.normalize(region)
        if "_" in r:
            return r.split("_")[-1]
        return r

    def _is_indonesia(self, text: str) -> bool:
        """判断是否为印尼（包含常见同义写法）"""
        t = TextNormalizer.normalize(text).lower()
        return t in {"印尼", "印度尼西亚", "indonesia", "印度尼西亞"}

    def _infer_origin_whitelist(self, df: pd.DataFrame) -> List[str]:
        """依据源表原产地出现频次推断白名单，排除印尼，仅返回前3位"""
        origin_cols = DataFrameProcessor.detect_origin_columns(df)
        if not origin_cols:
            # 文本列回退：基于常见产地别名统计（仅用于 259）
            try:
                from collections import Counter

                alias_map = {
                    "山西": ["山西", "晋", "晋北", "晋中", "晋南"],
                    "陕西": ["陕西", "陕", "陕北"],
                    "内蒙古": ["内蒙古", "蒙", "蒙东", "蒙西"],
                }
                obj_cols = df.select_dtypes(include=["object"]).columns
                counter = Counter()
                for c in obj_cols:
                    try:
                        vals = df[c].dropna().astype(str)
                    except Exception:
                        continue
                    for v in vals:
                        vv = TextNormalizer.normalize(v)
                        if not vv:
                            continue
                        # 跳过印尼
                        if self._is_indonesia(vv):
                            continue
                        for canon, aliases in alias_map.items():
                            if any(a in vv for a in aliases):
                                counter[canon] += 1
                if counter:
                    return [name for name, _ in counter.most_common(3)]
            except Exception:
                pass
            return []

        from collections import Counter

        counter = Counter()
        for c in origin_cols:
            try:
                vals = df[c].dropna().astype(str)
                for v in vals:
                    vv = TextNormalizer.normalize(v)
                    if not vv:
                        continue
                    if self._is_indonesia(vv):
                        continue
                    counter[vv] += 1
            except Exception:
                continue

        if not counter:
            return []

        # 取前3高频；若不足3，则按出现次数排序返回全部
        whitelist = [name for name, _ in counter.most_common(3)]
        return whitelist

    def _filter_by_target(
        self,
        df: pd.DataFrame,
        target_col_info: Dict,
        region_cols: List[str],
        product_cols: List[str],
    ) -> pd.DataFrame:
        """根据目标列信息过滤数据"""
        filtered_df = df.copy()

        target_region = target_col_info.get("region", "")
        target_product = target_col_info.get("product", "")
        table_id = target_col_info.get("table_id")
        col_name_full = target_col_info.get("column_name", "")

        # 259 动力煤：原产地白名单与严格匹配，显式排除印尼
        try:
            if table_id == "259" and TextNormalizer.normalize(
                target_product
            ) == TextNormalizer.normalize("动力煤"):
                origin_cols = DataFrameProcessor.detect_origin_columns(filtered_df)
                if origin_cols:
                    origin_whitelist = self._infer_origin_whitelist(filtered_df)
                    origin_name = self._extract_origin_from_region(target_region)

                    # 不允许印尼；不在白名单直接返回空
                    if self._is_indonesia(origin_name) or (
                        origin_whitelist
                        and origin_name
                        and origin_name not in origin_whitelist
                    ):
                        return filtered_df.iloc[0:0]

                    if origin_name:
                        import re

                        pat = re.escape(origin_name)
                        mask = pd.Series(
                            [False] * len(filtered_df), index=filtered_df.index
                        )
                        for oc in origin_cols:
                            try:
                                mask |= (
                                    filtered_df[oc]
                                    .astype(str)
                                    .str.contains(pat, na=False, case=False)
                                )
                            except Exception:
                                continue
                        if mask.any():
                            filtered_df = filtered_df[mask]
                        else:
                            # 未匹配到明确产地则返回空（避免拿到“汇总/其它”行）
                            return filtered_df.iloc[0:0]
        except Exception:
            pass

        # 按地区过滤（常规）
        if target_region and region_cols:
            region_mask = pd.Series([False] * len(filtered_df))
            for region_col in region_cols:
                if region_col in df.columns:
                    # 使用提取后的关键词做匹配，兼容如 '到岸港口_京唐'
                    search_term = (
                        self._extract_region_keyword(target_region) or target_region
                    )
                    region_mask |= (
                        df[region_col]
                        .astype(str)
                        .str.contains(search_term, na=False, case=False)
                    )
            if region_mask.any():
                filtered_df = filtered_df[region_mask]

        # 按产品过滤
        initial_len = len(filtered_df)
        if target_product and product_cols:
            product_mask = pd.Series(
                [False] * len(filtered_df), index=filtered_df.index
            )
            for product_col in product_cols:
                if product_col in filtered_df.columns:
                    product_mask |= (
                        filtered_df[product_col]
                        .astype(str)
                        .str.contains(target_product, na=False, case=False)
                    )
            if product_mask.any():
                filtered_df = filtered_df[product_mask]

        # 279 沿海运费：路线 token 必须全部命中（硬约束）
        try:
            if table_id == "279" and target_product:
                import re

                def tokenize(text: str) -> List[str]:
                    s = str(text).replace("／", "/")
                    s = re.sub(r"[-_/()（）]", " ", s)
                    return re.findall(r"[\u4e00-\u9fa5A-Za-z]+|\d+(?:\.\d+)?", s)

                tokens = set(t.lower() for t in tokenize(target_product))
                if tokens:
                    # 选择候选文本列
                    route_indicators = [
                        "航线",
                        "航线名称",
                        "路线",
                        "起点",
                        "起始",
                        "起始地",
                        "始发",
                        "出发",
                        "目的",
                        "终点",
                        "目的地",
                        "起运港",
                        "目的港",
                        "港",
                        "港口",
                        "船型",
                        "吨位",
                        "dwt",
                        "route",
                        "from",
                        "to",
                    ]
                    candidate_cols = []
                    for col in filtered_df.columns:
                        col_lower = str(col).lower()
                        if any(ind in col_lower for ind in route_indicators):
                            candidate_cols.append(col)
                    if not candidate_cols:
                        candidate_cols = [
                            col
                            for col in filtered_df.columns
                            if filtered_df[col].dtype == "object"
                        ]

                    def row_match_all_tokens(row: pd.Series) -> bool:
                        try:
                            joined = " ".join(
                                [str(row[c]) for c in candidate_cols if c in row.index]
                            )
                            joined = joined.replace("／", "/")
                            joined = re.sub(r"[-_/()（）]", " ", joined)
                            joined_tokens = set(
                                t.lower()
                                for t in re.findall(
                                    r"[\u4e00-\u9fa5A-Za-z]+|\d+(?:\.\d+)?",
                                    joined,
                                )
                            )
                            return bool(tokens) and tokens.issubset(joined_tokens)
                        except Exception:
                            return False

                    hard_mask = filtered_df.apply(row_match_all_tokens, axis=1)
                    if hard_mask.any():
                        filtered_df = filtered_df[hard_mask]
                    else:
                        # 未命中全部 token，则置空以避免误配导致系列全等
                        return filtered_df.iloc[0:0]
        except Exception:
            pass

        # 路线/港口感知的回退匹配：当常规过滤未生效时，
        # 基于目标产品中的关键字在候选列中做“包含全部词”匹配
        if target_product and len(filtered_df) == initial_len:
            route_indicators = [
                "航线",
                "航线名称",
                "路线",
                "起点",
                "起始",
                "起始地",
                "始发",
                "出发",
                "目的",
                "终点",
                "目的地",
                "起运港",
                "目的港",
                "港",
                "港口",
                "船型",
                "吨位",
                "dwt",
                "route",
                "from",
                "to",
            ]

            # 选择候选文本列
            candidate_cols = []
            for col in filtered_df.columns:
                col_lower = str(col).lower()
                if any(ind in col_lower for ind in route_indicators):
                    candidate_cols.append(col)
            if not candidate_cols:
                candidate_cols = [
                    col
                    for col in filtered_df.columns
                    if filtered_df[col].dtype == "object"
                ]

            def tokenize(text: str) -> List[str]:
                import re

                s = str(text).replace("／", "/")
                s = re.sub(r"[-_/()（）]", " ", s)
                # 拆分为中文、英文和数字片段
                return re.findall(r"[\u4e00-\u9fa5A-Za-z]+|\d+(?:\.\d+)?", s)

            tokens = set(t.lower() for t in tokenize(target_product))

            def row_match_all_tokens(row: pd.Series) -> bool:
                try:
                    import re

                    joined = " ".join(
                        [str(row[c]) for c in candidate_cols if c in row.index]
                    )
                    joined = joined.replace("／", "/")
                    joined = re.sub(r"[-_/()（）]", " ", joined)
                    joined_tokens = set(
                        t.lower()
                        for t in re.findall(
                            r"[\u4e00-\u9fa5A-Za-z]+|\d+(?:\.\d+)?", joined
                        )
                    )
                    return bool(tokens) and tokens.issubset(joined_tokens)
                except Exception:
                    return False

            try:
                token_mask = filtered_df.apply(row_match_all_tokens, axis=1)
                if token_mask.any():
                    filtered_df = filtered_df[token_mask]
            except Exception:
                pass

        # 硫分过滤（严格）：仅对 268 动力煤2# 生效
        try:
            sulfur_exact = target_col_info.get("sulfur_exact")
            # 兜底：如未写入规则，从列名再解析一次
            if (not sulfur_exact) and table_id == "268":
                try:
                    sulfur_exact = TargetAnalyzer(None)._parse_sulfur_from_name(
                        col_name_full
                    )
                except Exception:
                    sulfur_exact = None

            # 已改为按发热量拆分：禁用 268 的硫分过滤
            if table_id == "268":
                sulfur_exact = None

            if sulfur_exact is not None:
                import re

                sulfur_cols_hard = DataFrameProcessor.detect_sulfur_columns(filtered_df)
                if sulfur_cols_hard:

                    def parse_num(x):
                        try:
                            if pd.api.types.is_number(x):
                                return float(x)
                        except Exception:
                            pass
                        try:
                            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(x))
                            return float(m.group(1)) if m else None
                        except Exception:
                            return None

                    mask = pd.Series(
                        [False] * len(filtered_df), index=filtered_df.index
                    )
                    for sc in sulfur_cols_hard:
                        try:
                            vals = filtered_df[sc].apply(parse_num)
                            cond = vals.notna() & (vals.round(1) == float(sulfur_exact))
                            # 允许微小浮点误差
                            cond |= (
                                vals.notna() & (vals - float(sulfur_exact)).abs()
                                <= 0.05
                            )
                            mask |= cond.fillna(False)
                        except Exception:
                            continue
                    if mask.any():
                        filtered_df = filtered_df[mask]
                    else:
                        # 回退：在所有文本列中基于正则匹配 S0.4/S0.7/硫0.4/硫=0.4% 等
                        obj_cols = filtered_df.select_dtypes(include=["object"]).columns
                        pat = str(sulfur_exact)
                        regex = re.compile(
                            rf"(?i)(?:\bS\s*[:：=]?\s*{pat}\b|硫(?:分|份|含量)?\s*[:：=]?\s*{pat}\s*%?)"
                        )
                        mask_fb = pd.Series(
                            [False] * len(filtered_df), index=filtered_df.index
                        )
                        for c in obj_cols:
                            try:
                                mask_fb |= (
                                    filtered_df[c]
                                    .astype(str)
                                    .str.contains(regex, na=False)
                                )
                            except Exception:
                                continue
                        # 排除相反硫分
                        other = (
                            "0.7"
                            if str(sulfur_exact) == "0.4"
                            else ("0.4" if str(sulfur_exact) == "0.7" else None)
                        )
                        if other is not None:
                            regex_other = re.compile(
                                rf"(?i)(?:\bS\s*[:：=]?\s*{other}\b|硫(?:分|份|含量)?\s*[:：=]?\s*{other}\s*%?)"
                            )
                            mask_other = pd.Series(
                                [False] * len(filtered_df), index=filtered_df.index
                            )
                            for c in obj_cols:
                                try:
                                    mask_other |= (
                                        filtered_df[c]
                                        .astype(str)
                                        .str.contains(regex_other, na=False)
                                    )
                                except Exception:
                                    continue
                            mask_fb &= ~mask_other
                        if mask_fb.any():
                            filtered_df = filtered_df[mask_fb]
                        else:
                            # 未命中硫分，返回空，避免两个子表取同一行
                            return filtered_df.iloc[0:0]
        except Exception:
            pass

        return filtered_df

    def _produce_259_origin_extras(
        self,
        df: pd.DataFrame,
        time_col: str,
        output_dir: str,
    ) -> int:
        """为表 259 额外生成按原产地细分的 3 个子表（仅追加，不影响原列）"""
        try:
            origin_cols = DataFrameProcessor.detect_origin_columns(df)
            whitelist = self._infer_origin_whitelist(df)
            if not whitelist:
                return 0

            # 基础目标信息
            base_product = "动力煤"
            base_measure = "价格(元/吨)"
            split_count = 0

            import re

            obj_cols = list(df.select_dtypes(include=["object"]).columns)

            # 当不存在明确 origin 列时，使用别名在文本列上匹配
            alias_map = {
                "山西": ["山西", "晋", "晋北", "晋中", "晋南"],
                "陕西": ["陕西", "陕", "陕北"],
                "内蒙古": ["内蒙古", "蒙", "蒙东", "蒙西"],
            }

            for origin_name in whitelist:
                # 构造筛选
                if origin_cols:
                    pat = re.escape(origin_name)
                    mask = pd.Series([False] * len(df), index=df.index)
                    for oc in origin_cols:
                        try:
                            mask |= (
                                df[oc]
                                .astype(str)
                                .str.contains(pat, na=False, case=False)
                            )
                        except Exception:
                            continue
                else:
                    # 别名匹配
                    aliases = alias_map.get(origin_name, [origin_name])
                    pats = [re.escape(a) for a in aliases]
                    regex = re.compile("|".join(pats))
                    mask = pd.Series([False] * len(df), index=df.index)
                    for c in obj_cols:
                        try:
                            mask |= df[c].astype(str).str.contains(regex, na=False)
                        except Exception:
                            continue

                candidate = df[mask]
                if candidate.empty:
                    continue

                # 生成临时 target 信息
                tinfo = {
                    "column_name": f"00000259_{base_product}_{base_measure}--原产地_{origin_name}",
                    "table_id": "259",
                    "product": base_product,
                    "region": f"原产地_{origin_name}",
                    "measure": base_measure,
                }
                sub_table = self._extract_target_data(candidate, time_col, tinfo)
                if sub_table is not None and not sub_table.empty:
                    filename = FileHandler.sanitize_filename(
                        f"{tinfo['column_name']}.csv"
                    )
                    file_path = os.path.join(output_dir, filename)
                    sub_table.to_csv(file_path, index=False, encoding="utf-8-sig")
                    split_count += 1
            return split_count
        except Exception:
            return 0

    def _produce_268_sulfur_extras(
        self,
        df: pd.DataFrame,
        time_col: str,
        output_dir: str,
    ) -> int:
        """为表 268 额外生成 动力煤2# 的 S=0.4 / S=0.7 子表（严格命中）"""
        try:
            product_cols = DataFrameProcessor.detect_product_columns(df)
            base_measure = "价格(元/吨)"
            split_count = 0

            # 先按 产品=动力煤2# 过滤
            candidate = df.copy()
            if product_cols:
                p_mask = pd.Series([False] * len(candidate), index=candidate.index)
                for pc in product_cols:
                    try:
                        p_mask |= (
                            candidate[pc].astype(str).str.contains("动力煤2#", na=False)
                        )
                    except Exception:
                        continue
                if p_mask.any():
                    candidate = candidate[p_mask]

            # 在候选中按硫分严格筛选
            for sval in ["0.4", "0.7"]:
                tinfo = {
                    "column_name": f"00000268_动力煤2#_{base_measure}--S{sval}",
                    "table_id": "268",
                    "product": "动力煤2#",
                    "region": "",
                    "measure": base_measure,
                    "sulfur_exact": sval,
                }
                # 复用严格硫分逻辑：通过 _filter_by_target 约束 sulfur
                # 构造 region/product 列参数
                filt = self._filter_by_target(
                    df=candidate,
                    target_col_info=tinfo,
                    region_cols=DataFrameProcessor.detect_region_columns(candidate),
                    product_cols=product_cols,
                )
                if filt.empty:
                    continue
                sub_table = self._extract_target_data(filt, time_col, tinfo)
                if sub_table is not None and not sub_table.empty:
                    filename = FileHandler.sanitize_filename(
                        f"{tinfo['column_name']}.csv"
                    )
                    file_path = os.path.join(output_dir, filename)
                    sub_table.to_csv(file_path, index=False, encoding="utf-8-sig")
                    split_count += 1
            return split_count
        except Exception:
            return 0

    def _produce_275_port_extras(
        self,
        df: pd.DataFrame,
        time_col: str,
        output_dir: str,
    ) -> int:
        """为表 275 额外生成按到岸港口的 4 个子表：
        - 主焦煤：京唐 / 天津
        - 1/3焦煤：京唐 / 大连
        仅追加，不影响原列
        """
        try:
            product_cols = DataFrameProcessor.detect_product_columns(df)
            region_cols = DataFrameProcessor.detect_region_columns(df)
            if not region_cols:
                return 0

            combos = [
                ("主焦煤", "到岸港口_京唐"),
                ("主焦煤", "到岸港口_天津"),
                ("1/3焦煤", "到岸港口_京唐"),
                ("1/3焦煤", "到岸港口_大连"),
            ]
            base_measure = "价格(元/吨)"
            split_count = 0

            for prod, region in combos:
                tinfo = {
                    "column_name": f"00000275_{prod}_{base_measure}--{region}",
                    "table_id": "275",
                    "product": prod,
                    "region": region,
                    "measure": base_measure,
                }
                # 利用通用过滤（产品+地区/港口）
                filt = self._filter_by_target(
                    df=df,
                    target_col_info=tinfo,
                    region_cols=region_cols,
                    product_cols=product_cols,
                )
                if filt.empty:
                    continue
                sub_table = self._extract_target_data(filt, time_col, tinfo)
                if sub_table is not None and not sub_table.empty:
                    filename = FileHandler.sanitize_filename(
                        f"{tinfo['column_name']}.csv"
                    )
                    file_path = os.path.join(output_dir, filename)
                    sub_table.to_csv(file_path, index=False, encoding="utf-8-sig")
                    split_count += 1

            return split_count
        except Exception:
            return 0

    def _produce_268_heat_extras(
        self,
        df: pd.DataFrame,
        time_col: str,
        output_dir: str,
    ) -> int:
        """为表 268 额外生成基于发热量的两个子表（替代硫分）。
        策略：
        - 在母表上先筛选产品名称包含“动力煤2#”
        - 使用显式的“发热量”列（列名包含“发热”）按数值拆分
        - 目标热值优先 5000、4500、5500（按存在性生成最多三列）
        """
        try:
            base_measure = "价格(元/吨)"
            product_cols = DataFrameProcessor.detect_product_columns(df)
            if not product_cols:
                return 0

            # 仅保留产品=动力煤2# 的记录
            prod_mask = pd.Series([False] * len(df), index=df.index)
            for pc in product_cols:
                try:
                    prod_mask |= df[pc].astype(str).str.contains("动力煤2#", na=False)
                except Exception:
                    continue
            candidate = df[prod_mask]
            if candidate.empty:
                return 0

            # 寻找“发热量”列
            heat_col = None
            for col in candidate.columns:
                col_lower = str(col).lower()
                if ("发热" in str(col)) or ("热值" in str(col)):
                    heat_col = col
                    break
            if heat_col is None:
                # 找不到显式发热列则不生成
                return 0

            import re

            def parse_heat(x):
                # 提取数值，如 5000/5500/4500（支持包含文本）
                try:
                    if pd.api.types.is_number(x):
                        return float(x)
                except Exception:
                    pass
                s = re.sub(r"[\s,]", "", str(x))
                m = re.search(r"([0-9]{3,5})(?:\.\d+)?", s)
                return float(m.group(1)) if m else None

            heats = candidate[heat_col].apply(parse_heat)
            targets = [5000.0, 4500.0, 5500.0]
            split_count = 0

            for hv in targets:
                hv_mask = heats.notna() & (heats.round(0) == hv)
                subdf = candidate[hv_mask]
                if subdf.empty:
                    continue
                tinfo = {
                    "column_name": f"00000268_动力煤2#_{base_measure}--发热量_{int(hv)}",
                    "table_id": "268",
                    "product": "动力煤2#",
                    "region": "",
                    "measure": base_measure,
                }
                sub_table = self._extract_target_data(subdf, time_col, tinfo)
                if sub_table is not None and not sub_table.empty:
                    filename = FileHandler.sanitize_filename(
                        f"{tinfo['column_name']}.csv"
                    )
                    file_path = os.path.join(output_dir, filename)
                    sub_table.to_csv(file_path, index=False, encoding="utf-8-sig")
                    split_count += 1

            return split_count
        except Exception:
            return 0

    def _produce_353_route_extras(
        self,
        df: pd.DataFrame,
        time_col: str,
        output_dir: str,
    ) -> int:
        """为表 353 额外生成：将“煤炭运价分航线指数”按航线名称拆分（忽略载重，按日聚合均值）"""
        try:
            import re

            # 列定位
            item_col = None
            route_col = None
            for c in df.columns:
                s = str(c)
                if item_col is None and ("数据项目" in s or "数据类目" in s):
                    item_col = c
                if route_col is None and ("航线" in s):
                    route_col = c
            if item_col is None:
                return 0

            # 仅保留“航线指数”类别
            cand = df.copy()
            try:
                mask = cand[item_col].astype(str).str.contains("航线", na=False)
                cand = cand[mask]
            except Exception:
                return 0
            if cand.empty:
                return 0

            # 选数值列（优先“本期”相关）
            val_col = DataFrameProcessor.find_best_value_column(
                cand, product_hint="运价", measure_hint="本期"
            )
            if not val_col:
                return 0

            def pick_route(row) -> str:
                try:
                    if route_col and pd.notna(row.get(route_col, None)):
                        rc = str(row[route_col]).strip()
                        if rc and ("-" in rc or "—" in rc or "–" in rc):
                            return rc
                except Exception:
                    pass
                try:
                    t = TextNormalizer.normalize(str(row[item_col]))
                    t = re.sub(r"^.*?航线指数[_：:]?", "", t)
                    t = re.sub(r"[（(].*$", "", t)
                    m = re.search(
                        r"([\u4e00-\u9fa5A-Za-z]+)[-—–]([\u4e00-\u9fa5A-Za-z]+)", t
                    )
                    if m:
                        return f"{m.group(1)}-{m.group(2)}"
                except Exception:
                    pass
                return ""

            cand = cand.copy()
            cand["__route__"] = cand.apply(pick_route, axis=1)
            cand = cand[cand["__route__"] != ""]
            if cand.empty:
                return 0

            # 聚合
            tmp = cand[[time_col, "__route__", val_col]].copy()
            tmp = DataFrameProcessor.standardize_time_column(tmp, time_col)
            tmp[val_col] = pd.to_numeric(tmp[val_col], errors="coerce")
            tmp.dropna(subset=[val_col], inplace=True)

            produced = 0
            for route in sorted(tmp["__route__"].dropna().unique()):
                sub = tmp[tmp["__route__"] == route].copy()
                if sub.empty:
                    continue
                agg = sub.groupby(sub.columns[0])[val_col].mean().reset_index()
                colname = f"00000353_煤炭运价分航线指数_本期(点)--航线_{route}"
                out_df = agg.rename(columns={agg.columns[0]: "date", val_col: colname})
                out_df = DataFrameProcessor.standardize_time_column(out_df, "date")
                fn = FileHandler.sanitize_filename(f"{colname}.csv")
                out_df.to_csv(
                    os.path.join(output_dir, fn), index=False, encoding="utf-8-sig"
                )
                produced += 1

            return produced
        except Exception:
            return 0

    def _extract_target_data(
        self, df: pd.DataFrame, time_col: str, target_col_info: Dict
    ) -> Optional[pd.DataFrame]:
        """提取目标数据"""
        product = target_col_info.get("product", "")
        measure = target_col_info.get("measure", "价格")

        # 检测是否为直接列映射格式的根指数表格
        table_id = target_col_info.get("table_id", "")

        # 强化航线/港口类（运费/运价）目标的严格匹配，避免串线到其它目的港
        try:
            hard_route_tables = {"279", "347", "349", "351"}
            if table_id in hard_route_tables and product:
                import re

                route_indicators = [
                    "航线",
                    "航线名称",
                    "路线",
                    "起点",
                    "起始",
                    "始发",
                    "出发",
                    "目的",
                    "终点",
                    "起运",
                    "目的港",
                    "港口",
                    "船型",
                    "吨位",
                    "dwt",
                    "route",
                    "from",
                    "to",
                ]
                candidate_cols = []
                for c in df.columns:
                    cl = str(c).lower()
                    if any(ind in cl for ind in route_indicators):
                        candidate_cols.append(c)
                if not candidate_cols:
                    candidate_cols = [
                        c
                        for c in df.columns
                        if getattr(df[c], "dtype", None) == "object"
                    ]

                def tokenize(text: str) -> list[str]:
                    s = str(text).replace("，", "/")
                    s = re.sub(r"[-_/()（）]", " ", s)
                    return re.findall(r"[\u4e00-\u9fa5A-Za-z]+|\d+(?:\.\d+)?", s)

                raw_tokens = [t.lower() for t in tokenize(product)]
                must_tokens = set()
                for t in raw_tokens:
                    if t.startswith("中国") and len(t) > 2:
                        must_tokens.add(t[2:])  # 去掉“中国产地”前缀
                    elif t in {"中国", "中华人民共和国"}:
                        continue
                    else:
                        must_tokens.add(t)

                def row_match_all_tokens(row: pd.Series) -> bool:
                    try:
                        joined = " ".join(
                            [str(row[c]) for c in candidate_cols if c in row.index]
                        )
                        joined = joined.replace("，", "/")
                        joined = re.sub(r"[-_/()（）]", " ", joined)
                        joined_lower = joined.lower()
                        return bool(must_tokens) and all(
                            t in joined_lower for t in must_tokens
                        )
                    except Exception:
                        return False

                hard_mask = df.apply(row_match_all_tokens, axis=1)
                if hard_mask.any():
                    df = df[hard_mask]
                else:
                    # 回退：按目标列中显式的“起讫港口(可含DWT)”进行航线匹配
                    try:
                        col_full = str(target_col_info.get("column_name", ""))
                        # 目标列形如：输入00000347--..._沿海煤炭运费_秦皇岛-宁波(1.5-2万DWT)_本期(元/吨)
                        m = re.search(
                            r"_([^_()]+-[^_()]+)\s*(?:\(([^)]*)\))?_", col_full
                        )
                        route_target = m.group(1) if m else None
                        dwt_target = (m.group(2) or "") if m else ""

                        if route_target:
                            # 航线列优先
                            route_cols = [
                                c
                                for c in df.columns
                                if isinstance(c, str) and ("航线" in c or "路线" in c)
                            ]

                            def _route_ok(row) -> bool:
                                try:
                                    a, b = route_target.split("-", 1)
                                except Exception:
                                    a = route_target
                                    b = ""
                                # 明确航线列
                                for rc in route_cols:
                                    try:
                                        s = str(row.get(rc, ""))
                                        if a and (a in s) and (not b or b in s):
                                            return True
                                    except Exception:
                                        continue
                                # 回退：拼接文本列
                                try:
                                    joined = " ".join(
                                        [
                                            str(row[c])
                                            for c in row.index
                                            if isinstance(c, str)
                                        ]
                                    )
                                    if a and (a in joined) and (not b or b in joined):
                                        return True
                                except Exception:
                                    pass
                                return False

                            try:
                                mask_r = df.apply(_route_ok, axis=1)
                                if mask_r.any():
                                    df = df[mask_r]
                                else:
                                    return None
                            except Exception:
                                return None

                            # 若有 DWT 目标，再进一步过滤（若存在相关列）
                            if dwt_target:
                                try:
                                    dwt_cols = [
                                        c
                                        for c in df.columns
                                        if isinstance(c, str)
                                        and ("载重" in c or "DWT" in c.upper())
                                    ]
                                    if dwt_cols:
                                        dmask = False
                                        for dc in dwt_cols:
                                            try:
                                                dmask = dmask | df[dc].astype(
                                                    str
                                                ).str.contains(dwt_target, na=False)
                                            except Exception:
                                                continue
                                        if isinstance(dmask, bool):
                                            pass
                                        else:
                                            if dmask.any():
                                                df = df[dmask]
                                except Exception:
                                    pass
                        else:
                            return None
                    except Exception:
                        return None
        except Exception:
            pass
        if self._is_direct_column_mapping_table(table_id):
            # 直接列映射格式：使用精确列名匹配
            value_col = self._find_exact_column_match(df, target_col_info, time_col)
        else:
            # 传统格式：使用通用评分匹配
            value_col = DataFrameProcessor.find_best_value_column(df, product, measure)

        if not value_col:
            logger.debug(f"未找到匹配的数值列: {product} - {measure}")
            return None

        # 若存在产品/地区列，计算匹配评分以在同日多行时选择最优记录
        product_cols = DataFrameProcessor.detect_product_columns(df)
        region_cols = DataFrameProcessor.detect_region_columns(df)
        # 不使用价格类型作为偏好（仅取价格数值）
        price_type_cols = []

        # 扩充产品列以包含“数据项目”（适配 353）
        if not product_cols:
            try:
                extra_pc = [
                    c for c in df.columns if isinstance(c, str) and ("数据项目" in c)
                ]
                if extra_pc:
                    product_cols = list(set(product_cols + extra_pc))
            except Exception:
                pass

        target_product_norm = TextNormalizer.normalize(product) if product else ""
        target_region_norm = (
            TextNormalizer.normalize(target_col_info.get("region", ""))
            if target_col_info.get("region", "")
            else ""
        )

        col_name_full = target_col_info.get("column_name", "")
        prefer_price_type = None
        prefer_price_type = None

        # 特例处理：00000353 中国沿海散货运价指数 - 按“煤炭运价分航线指数_<航线>_(DWT)”精确拆分
        try:
            if table_id == "353":
                import re

                # 从列名中解析航线与载重
                # 形如：输入00000353--..._煤炭运价分航线指数_秦皇岛-广州_(5-6万DWT)_本期(点)
                m = re.search(r"_([^_()]+-[^_()]+)_(?:\(([^)]*)\))?_", col_name_full)
                route_target = m.group(1) if m else None
                dwt_target = (m.group(2) or "") if m else ""

                # 根据目标列类型（分航线/两大综合类）选择筛选策略
                item_cols = [
                    c
                    for c in df.columns
                    if isinstance(c, str) and ("数据项目" in c or "数据类目" in c)
                ]
                cand = df.copy()

                # 识别目标类型
                is_route_col = (
                    bool(route_target)
                    or ("航线" in col_name_full)
                    or ("航线指数" in col_name_full)
                )
                want_cat_route = None
                if "散货运价综合指数" in col_name_full:
                    want_cat_route = "散货运价综合指数"
                elif "煤炭货种运价指数" in col_name_full:
                    want_cat_route = "煤炭货种运价指数"

                if is_route_col:
                    # 仅保留“分航线指数”的记录
                    if item_cols:
                        mask_item = False
                        for ic in item_cols:
                            try:
                                mask_item = mask_item | cand[ic].astype(
                                    str
                                ).str.contains("航线", na=False)
                            except Exception:
                                continue
                        try:
                            cand = cand[mask_item]
                        except Exception:
                            pass
                elif want_cat_route is not None:
                    # 仅保留“散货运价综合指数”或“煤炭货种运价指数”的记录
                    if item_cols:
                        mask_item = False
                        for ic in item_cols:
                            try:
                                mask_item = mask_item | cand[ic].astype(
                                    str
                                ).str.contains(want_cat_route, na=False)
                            except Exception:
                                continue
                        try:
                            cand = cand[mask_item]
                        except Exception:
                            pass

                if is_route_col:
                    # 航线过滤：优先使用“航线名称”列；否则在文本列上同时命中起讫两端 token
                    route_cols = [
                        c for c in df.columns if isinstance(c, str) and ("航线" in c)
                    ]

                    def route_row_ok(row) -> bool:
                        if not route_target:
                            return True
                        try:
                            a, b = route_target.split("-", 1)
                        except Exception:
                            a = route_target
                            b = ""
                        # 1) 明确航线列
                        for rc in route_cols:
                            try:
                                s = str(row.get(rc, ""))
                                if a and (a in s) and (not b or b in s):
                                    return True
                            except Exception:
                                continue
                        # 2) 回退：拼接文本列
                        try:
                            joined = " ".join(
                                [str(row[c]) for c in row.index if isinstance(c, str)]
                            )
                            if a and (a in joined) and (not b or b in joined):
                                return True
                        except Exception:
                            pass
                        return False

                    try:
                        cand = cand[cand.apply(route_row_ok, axis=1)]
                    except Exception:
                        pass

                    # 载重过滤（如存在）
                    if dwt_target:
                        dwt_cols = [
                            c
                            for c in df.columns
                            if isinstance(c, str)
                            and ("载重" in c or "DWT" in c.upper())
                        ]
                        if dwt_cols:
                            dmask = False
                            for dc in dwt_cols:
                                try:
                                    dmask = dmask | cand[dc].astype(str).str.contains(
                                        dwt_target, na=False
                                    )
                                except Exception:
                                    continue
                            try:
                                cand = cand[dmask]
                            except Exception:
                                pass

                if cand.empty:
                    return None

                # 选择“本期(点)”等列作为数值列
                vcol = None
                try:
                    for c in cand.columns:
                        s = str(c)
                        if ("本期" in s) and ("点" in s):
                            vcol = c
                            break
                except Exception:
                    pass
                if not vcol:
                    vcol = DataFrameProcessor.find_best_value_column(
                        cand, product_hint="运价", measure_hint="本期"
                    )
                if not vcol:
                    return None

                # 构造子表并按日聚合（存在重复时取均值）
                sub = cand[[time_col, vcol]].copy()
                sub = sub.rename(columns={time_col: "date", vcol: col_name_full})
                sub.dropna(subset=["date", col_name_full], inplace=True)
                sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
                sub.dropna(subset=["date"], inplace=True)
                sub[col_name_full] = pd.to_numeric(sub[col_name_full], errors="coerce")
                sub = (
                    sub.groupby("date")[col_name_full]
                    .mean()
                    .reset_index()
                    .sort_values("date")
                )
                return DataFrameProcessor.standardize_time_column(sub, "date")
        except Exception:
            pass

        def row_match_score(row: pd.Series) -> int:
            score = 0
            # 产品匹配评分：精确10，包含5
            if target_product_norm and product_cols:
                vals = [
                    TextNormalizer.normalize(str(row[col]))
                    for col in product_cols
                    if col in row.index
                ]
                if any(v == target_product_norm for v in vals):
                    score += 10
                elif any(target_product_norm in v for v in vals):
                    score += 5
            # 地区匹配评分：精确6，包含3
            if target_region_norm and region_cols:
                vals = [
                    TextNormalizer.normalize(str(row[col]))
                    for col in region_cols
                    if col in row.index
                ]
                if any(v == target_region_norm for v in vals):
                    score += 6
                elif any(target_region_norm in v for v in vals):
                    score += 3
            # 价格类型偏好：根据目标列所属类别加权
            if prefer_price_type and price_type_cols:
                vals = [str(row[col]) for col in price_type_cols if col in row.index]
                if any(prefer_price_type == v for v in vals):
                    score += 4
                elif any(prefer_price_type in v for v in vals):
                    score += 2

            # 航线/港口/吨位感知匹配（针对运费类，特别是表 279）
            try:
                route_like = (
                    (table_id == "279")
                    or (table_id == "353")
                    or ("运费" in col_name_full)
                    or ("运价" in col_name_full)
                    or ("航线" in col_name_full)
                )
                if route_like and target_product_norm:
                    route_indicators = [
                        "航线",
                        "航线名称",
                        "路线",
                        "起点",
                        "起始",
                        "起始地",
                        "始发",
                        "出发",
                        "目的",
                        "终点",
                        "目的地",
                        "起运港",
                        "目的港",
                        "港",
                        "港口",
                        "船型",
                        "吨位",
                        "dwt",
                        "route",
                        "from",
                        "to",
                    ]
                    candidate_cols = [
                        c
                        for c in row.index
                        if any(ind in str(c).lower() for ind in route_indicators)
                    ]
                    if not candidate_cols:
                        candidate_cols = [
                            c for c in row.index if isinstance(row[c], str)
                        ]

                    def tokenize(text: str) -> List[str]:
                        import re

                        s = str(text).replace("／", "/")
                        s = re.sub(r"[-_/()（）]", " ", s)
                        return re.findall(r"[\u4e00-\u9fa5A-Za-z]+|\d+(?:\.\d+)?", s)

                    tokens = set(t.lower() for t in tokenize(product))
                    joined = " ".join(
                        [str(row[c]) for c in candidate_cols if c in row.index]
                    )
                    import re

                    joined = joined.replace("／", "/")
                    joined = re.sub(r"[-_/()（）]", " ", joined)
                    joined_tokens = set(
                        t.lower()
                        for t in re.findall(
                            r"[\u4e00-\u9fa5A-Za-z]+|\d+(?:\.\d+)?", joined
                        )
                    )
                    if tokens and tokens.issubset(joined_tokens):
                        score += 12
                    elif table_id == "279":
                        # 对 279 更严格：未命中全部 token 明显降权
                        score -= 8
                    elif tokens and tokens.intersection(joined_tokens):
                        score += 4
            except Exception:
                pass
            return score

        scored_df = df.copy()
        try:
            scored_df["__match_score__"] = scored_df.apply(row_match_score, axis=1)
        except Exception:
            scored_df["__match_score__"] = 0

        # 创建子表并在按日聚合时选择匹配分最高的记录
        sub = scored_df[[time_col, value_col, "__match_score__"]].copy()
        sub.rename(
            columns={time_col: "date", value_col: target_col_info["column_name"]},
            inplace=True,
        )
        # 将区间型价格（如 "930-950"、"930至950"、"930到950"、"930～950"）转换为均值，
        # 其他可解析的数字直接取数，无法解析的置为空
        try:
            import re as _re
            import pandas as _pd

            val_name = target_col_info["column_name"]
            range_pat = _re.compile(
                r"([0-9]+(?:\.[0-9]+)?)\s*(?:[-~–—－～]|至|到)\s*([0-9]+(?:\.[0-9]+)?)"
            )

            def _to_num(x):
                # 已是数值
                try:
                    if _pd.api.types.is_number(x):
                        return float(x)
                except Exception:
                    pass
                s = str(x).strip()
                if not s or s.lower() in {"nan", "none"}:
                    return _pd.NA
                s = s.replace(",", "")
                m = range_pat.search(s)
                if m:
                    try:
                        a = float(m.group(1))
                        b = float(m.group(2))
                        return (a + b) / 2.0
                    except Exception:
                        return _pd.NA
                # 单值提取
                try:
                    m2 = _re.search(r"([0-9]+(?:\.[0-9]+)?)", s)
                    return float(m2.group(1)) if m2 else _pd.NA
                except Exception:
                    return _pd.NA

            sub[val_name] = sub[val_name].apply(_to_num)
            sub[val_name] = _pd.to_numeric(sub[val_name], errors="coerce")
        except Exception:
            pass

        sub.dropna(subset=["date", target_col_info["column_name"]], inplace=True)

        # 将时间标准化为日期后再分组选择最高分记录
        sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
        sub.dropna(subset=["date"], inplace=True)
        sub.sort_values(
            ["date", "__match_score__"], ascending=[True, False], inplace=True
        )
        sub = sub.drop_duplicates(subset=["date"], keep="first")
        sub.drop(columns=["__match_score__"], inplace=True)

        return DataFrameProcessor.standardize_time_column(sub, "date")

    def _is_direct_column_mapping_table(self, table_id: str) -> bool:
        """判断是否为直接列映射格式的根指数表格"""
        # 特定的根指数表格ID列表（这些表格使用直接列映射格式）
        direct_mapping_table_ids = {"4", "5", "10", "11", "19"}
        return table_id in direct_mapping_table_ids

    def _find_exact_column_match(
        self, df: pd.DataFrame, target_col_info: Dict, time_col: str
    ) -> Optional[str]:
        """为直接列映射格式表格寻找精确匹配的列"""
        column_name = target_col_info.get("column_name", "")
        product = target_col_info.get("product", "")

        # 从目标列名中提取产品标识符
        # 例如：从"输入00000004-易煤北方港指数_处理后_Q5000S0.8"中提取"Q5000S0.8"
        if "_" in column_name:
            parts = column_name.split("_")
            if len(parts) >= 2:
                product_identifier = parts[-1]  # 取最后一部分作为产品标识符
            else:
                product_identifier = product
        else:
            product_identifier = product

        # 在数据框的列中寻找精确匹配
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

        # 去除时间列
        value_cols = [col for col in numeric_cols if col != time_col]

        # 优先进行精确匹配
        for col in value_cols:
            if col == product_identifier:
                logger.debug(f"精确匹配到列: {col} -> {product_identifier}")
                return col

        # 如果没有精确匹配，尝试包含匹配
        for col in value_cols:
            col_normalized = TextNormalizer.normalize(col)
            product_normalized = TextNormalizer.normalize(product_identifier)
            if product_normalized in col_normalized:
                logger.debug(f"包含匹配到列: {col} -> {product_identifier}")
                return col

        # 如果都没有匹配，记录警告并返回第一个数值列
        if value_cols:
            logger.warning(
                f"未找到匹配列 {product_identifier}，使用第一个数值列: {value_cols[0]}"
            )
            return value_cols[0]

        return None

    def _save_split_summary(self, summary: Dict[str, int]):
        """保存拆分摘要"""
        summary_file = os.path.join(self.output_dir, "split_summary.txt")
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write("数据拆分摘要\n")
            f.write("=" * 30 + "\n")
            total_count = 0
            for table, count in summary.items():
                f.write(f"{table}: {count} 个子表\n")
                total_count += count
            f.write(f"\n总计: {total_count} 个子表")

        logger.info(f"拆分摘要已保存: {summary_file}")
