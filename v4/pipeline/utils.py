#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据预处理工具类
集中处理文本规范化、文件读取、列名解析等公共功能
"""

import pandas as pd
import re
import os
import logging
from typing import Optional, Dict, List, Tuple, Any

logger = logging.getLogger(__name__)

# 预编译正则表达式
ID_PATTERN = re.compile(r"\d{8}")
DUP_PATTERN = re.compile(r"_dup\d+$")


class TextNormalizer:
    """文本规范化工具"""

    # 中英文符号映射
    SYMBOL_MAP = {
        "（": "(",
        "）": ")",
        "，": ",",
        "、": ",",
        "：": ":",
        "・": "-",
        "／": "/",
        "　": " ",
    }

    @classmethod
    def normalize(cls, text: str) -> str:
        """统一文本格式：中英文符号转换，去除空白"""
        text = str(text)
        for cn, en in cls.SYMBOL_MAP.items():
            text = text.replace(cn, en)
        return text.replace(" ", "")


class ColumnNameProcessor:
    """列名处理工具"""

    # 计量单位别名映射
    MEASURE_ALIASES = {
        "价格(元/吨)": {"价格(元/吨)", "本期(元/吨)"},
        "本期价格(美元/吨)": {"本期价格(美元/吨)", "当期值(美元/吨)", "本期(美元/吨)"},
        "本期(元/吨)": {"本期(元/吨)", "价格(元/吨)"},
        "当期值(美元/吨)": {"当期值(美元/吨)", "本期价格(美元/吨)"},
    }

    @staticmethod
    def extract_id(text: str) -> Optional[str]:
        """提取8位ID"""
        match = ID_PATTERN.search(str(text))
        return match.group(0) if match else None

    @staticmethod
    def clean_pandas_suffix(col_name: str) -> str:
        """清理pandas合并时添加的后缀"""
        if col_name.endswith(("_x", "_y")):
            return col_name[:-2]
        return DUP_PATTERN.sub("", col_name)

    @classmethod
    def parse_target_column(
        cls, name: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        解析目标列名: (id, product, region, measure)
        支持格式:
        - 长名: 输入{id}--...--{product}[--{region}]--{measure}
        - 短名: {id}_{product}_{measure}
        """
        name_norm = TextNormalizer.normalize(name)
        token_id = cls.extract_id(name_norm)
        product = region = measure = None

        if "--" in name_norm:
            parts = name_norm.split("--")
            if len(parts) >= 2:
                measure = parts[-1]
                # 兼容海运费等长串：形如
                # 输入{id}--煤炭运费_水运价格_进口煤炭运费_澳大利亚海波因特-中国舟山_当期值(美元/吨)
                # 从末段按下划线切分，取最后一段为计量，其前一段为“数据类目/航线”作为产品线索
                last = parts[-1]
                if "_" in last and (product is None or product == ""):
                    tokens = [t for t in last.split("_") if t]
                    if len(tokens) >= 2:
                        measure = tokens[-1]
                        product = tokens[-2] or None
                # 常见5段结构: 输入{id} -- ... -- {product} -- {region} -- {measure}
                if len(parts) >= 5 and (product is None or product == ""):
                    product = parts[-3] or None
                    region = parts[-2] or None
                elif len(parts) == 4 and (product is None or product == ""):
                    # 4段时通常只有 product，无明确 region
                    # 但若将 product-region 合在一起，用连字符分开
                    cand = parts[-2]
                    if "-" in cand and "_" not in cand:
                        pr = cand.split("-", 1)
                        product = pr[0] if pr else None
                        region = pr[1] if len(pr) > 1 else None
                    elif "_" in cand:
                        pr = cand.split("_")
                        product = pr[0] if pr else None
                        region = pr[1] if len(pr) > 1 else None
                    else:
                        product = cand
                elif len(parts) == 3 and (product is None or product == ""):
                    # {id}--{product-region}--{measure}
                    cand = parts[-2]
                    if "-" in cand and "_" not in cand:
                        pr = cand.split("-", 1)
                        product = pr[0] if pr else None
                        region = pr[1] if len(pr) > 1 else None
                    elif "_" in cand:
                        pr = cand.split("_")
                        product = pr[0] if pr else None
                        region = pr[1] if len(pr) > 1 else None
                    else:
                        product = cand
        else:
            if "_" in name_norm:
                parts = name_norm.split("_")
                if len(parts) >= 3 and parts[0].isdigit():
                    # 短名: {id}_{product}_{measure}
                    token_id = parts[0]
                    product = parts[1]
                    measure = parts[-1]
                # CCTD 下划线模式：输入{id}-CCTD-煤炭价格_{region...}_{product}_{measure}
                elif token_id and (
                    "cctd" in name_norm.lower() or "煤炭价格" in name_norm
                ):
                    if len(parts) >= 3:
                        measure = parts[-1] or None
                        product = parts[-2] or None
                        region_tokens = parts[1:-2]
                        if region_tokens:
                            region = "_".join([t for t in region_tokens if t]) or None

        return token_id, product, region, measure

    @classmethod
    def match_measure(cls, source: str, target: str) -> bool:
        """计量单位匹配"""
        source_norm = TextNormalizer.normalize(source)
        target_norm = TextNormalizer.normalize(target)

        if source_norm == target_norm:
            return True

        for _, aliases in cls.MEASURE_ALIASES.items():
            if target_norm in aliases and any(
                TextNormalizer.normalize(alias) in source_norm for alias in aliases
            ):
                return True
        return False


class FileHandler:
    """文件读写工具"""

    # 扩展编码集合，兼容更多来自不同来源的 CSV
    ENCODINGS = [
        "utf-8",
        "utf-8-sig",
        "gb18030",
        "gbk",
        "cp936",
        "gb2312",
        "big5",
        "utf-16",
        "utf-16le",
        "utf-16be",
        "latin1",
    ]

    @classmethod
    def read_csv(cls, file_path: str) -> Optional[pd.DataFrame]:
        """尝试多种编码读取CSV文件"""
        for encoding in cls.ENCODINGS:
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                # 清理异常表头前缀（如某些导出含有类似“633;C1:”的标记）
                try:
                    cleaned_columns = []
                    for col in df.columns:
                        col_str = str(col).lstrip("\ufeff").strip()
                        col_str = re.sub(r"^\s*\d+;C\d+:\s*", "", col_str)
                        cleaned_columns.append(col_str)
                    df.columns = cleaned_columns
                except Exception:
                    pass
                return df
            except UnicodeDecodeError:
                continue
            except Exception as e:
                # 非编码类错误（如分隔符、解析异常）优先改用自动分隔再试一次
                logger.warning(f"读取文件尝试失败 {file_path} 编码={encoding}: {e}")
                try:
                    df = pd.read_csv(
                        file_path,
                        encoding=encoding,
                        sep=None,
                        engine="python",
                    )
                    # 清理异常表头前缀
                    try:
                        cleaned_columns = []
                        for col in df.columns:
                            col_str = str(col).lstrip("\ufeff").strip()
                            col_str = re.sub(r"^\s*\d+;C\d+:\s*", "", col_str)
                            cleaned_columns.append(col_str)
                        df.columns = cleaned_columns
                    except Exception:
                        pass
                    return df
                except Exception:
                    continue

        logger.error(f"无法读取文件，所有编码都失败: {file_path}")
        return None

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """文件名安全化"""
        safe_name = re.sub(r'[\\/\:*?"<>|]', "_", str(name))
        return safe_name.replace("\n", "_").replace("\r", "_")


class DataFrameProcessor:
    """DataFrame处理工具"""

    # 时间列候选名称
    TIME_COLUMN_INDICATORS = ["时间", "date", "日期", "发布日期"]

    # 地区列候选名称
    REGION_COLUMN_INDICATORS = [
        "报价地",
        "报价地区",
        "到岸港口",
        "港口",
        "地区",
        "省份",
        "城市",
        "destination",
        "port",
        "region",
        "location",
    ]

    # 原产地列候选名称
    ORIGIN_COLUMN_INDICATORS = [
        "原产地",
        "产地",
        "来源地",
        "原产国",
        "来源",
        "origin",
        "source",
    ]

    # 硫份列候选名称
    SULFUR_COLUMN_INDICATORS = [
        "硫",
        "硫份",
        "硫分",
        "硫含量",
        "sulfur",
        "s",
    ]

    # 产品列候选名称
    PRODUCT_COLUMN_INDICATORS = [
        "产品名称",
        "煤种",
        "品种",
        "数据类目",
        "product",
        "coal_type",
        "type",
    ]

    # 元数据列（需要跳过的列）
    META_COLUMNS = {
        "产品名称",
        "煤种",
        "品种",
        "商品名称",
        "规格",
        "产品",
        "煤种名称",
        "报价地区",
        "港口",
        "地区",
        "到岸港口",
        "到岸地",
        "到岸港",
        "目的港",
        "报价地",
        "港口名称",
    }

    @classmethod
    def detect_time_column(cls, df: pd.DataFrame) -> Optional[str]:
        """检测时间列（更稳健）：
        1) 优先基于列名关键词匹配（包含“时间/日期/date/发布日期”）
        2) 否则在所有列中尝试解析为日期，按可解析比例选取最佳列
        3) 若无明显候选但第一列可解析，则使用第一列
        """
        # 1) 列名关键词匹配
        indicators = [s.lower() for s in cls.TIME_COLUMN_INDICATORS]
        for col in df.columns:
            col_str = str(col).lower()
            if any(ind in col_str for ind in indicators):
                return col

        # 2) 计算各列可解析比例
        best_col = None
        best_ratio = 0.0
        for col in df.columns:
            try:
                ser = pd.to_datetime(df[col], errors="coerce")
                ratio = float(ser.notna().mean())
                if pd.api.types.is_datetime64_any_dtype(ser):
                    ratio = max(ratio, 1.0)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_col = col
            except Exception:
                continue

        if best_col is not None and best_ratio >= 0.5:
            return best_col

        # 3) 回退：若第一列可解析，使用第一列
        try:
            if (
                pd.api.types.is_datetime64_any_dtype(df.iloc[:, 0])
                or pd.to_datetime(df.iloc[:, 0], errors="coerce").notna().any()
            ):
                return df.columns[0]
        except Exception:
            pass
        return None

    @classmethod
    def detect_region_columns(cls, df: pd.DataFrame) -> List[str]:
        """检测地区相关列"""
        region_cols = []
        for col in df.columns:
            col_lower = col.lower()
            if any(
                indicator in col_lower for indicator in cls.REGION_COLUMN_INDICATORS
            ):
                region_cols.append(col)
        return region_cols

    @classmethod
    def detect_product_columns(cls, df: pd.DataFrame) -> List[str]:
        """检测产品相关列"""
        product_cols = []
        for col in df.columns:
            col_lower = col.lower()
            if any(
                indicator in col_lower for indicator in cls.PRODUCT_COLUMN_INDICATORS
            ):
                product_cols.append(col)
        return product_cols

    @classmethod
    def detect_origin_columns(cls, df: pd.DataFrame) -> List[str]:
        """检测原产地/来源相关列"""
        origin_cols = []
        for col in df.columns:
            col_lower = col.lower()
            if any(ind in col_lower for ind in cls.ORIGIN_COLUMN_INDICATORS):
                origin_cols.append(col)
        return origin_cols

    @classmethod
    def detect_sulfur_columns(cls, df: pd.DataFrame) -> List[str]:
        """检测硫份相关列"""
        sulfur_cols = []
        for col in df.columns:
            col_lower = col.lower()
            if any(ind in col_lower for ind in cls.SULFUR_COLUMN_INDICATORS):
                sulfur_cols.append(col)
        return sulfur_cols

    @classmethod
    def find_best_value_column(
        cls, df: pd.DataFrame, product_hint: str = "", measure_hint: str = "价格"
    ) -> Optional[str]:
        """寻找最佳数值列"""
        import pandas as _pd

        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        object_cols = [c for c in df.columns if c not in numeric_cols]

        # 若存在数值列，优先且仅在数值列中选择，避免误选文本列
        if numeric_cols:
            candidates: list[str] = list(numeric_cols)
        else:
            # 无数值列时，才在对象列中按强相关名称做回退选择
            candidates = []
            try:
                mh = str(measure_hint or "")
                for col in object_cols:
                    col_str = str(col)
                    col_low = col_str.lower()
                    strong_name_match = (
                        ("价格" in col_str)
                        or ("price" in col_low)
                        or ColumnNameProcessor.match_measure(col_str, mh)
                    )
                    non_value_hints = ["单位", "类型", "类别", "备注", "说明"]
                    if strong_name_match and not any(h in col_str for h in non_value_hints):
                        candidates.append(col_str)
            except Exception:
                pass

        if not candidates:
            return None

        # 当目标为“价格”时，先硬性排除名称含“区间/范围/最低/最高/上下限”等候选
        if "价格" in str(measure_hint):
            range_name_hints = ["区间", "范围", "最低", "最高", "上限", "下限", "最小", "最大"]
            filtered = []
            for col in candidates:
                name = str(col)
                if any(h in name for h in range_name_hints):
                    continue
                # 再基于值采样排除形如 "1203 - 1220" 的区间文本
                try:
                    import re as _re
                    ser = df[col]
                    # 仅在对象列上做区间采样检查
                    if col not in numeric_cols:
                        svals = ser.dropna().astype(str).head(50)
                        range_pat = _re.compile(
                            r"\b\d{2,6}\s*(?:[-~–—－～]|至|到)\s*\d{2,6}\b"
                        )
                        if any(range_pat.search(v) for v in svals):
                            continue
                except Exception:
                    pass
                filtered.append(col)
            if filtered:
                candidates = filtered

        best_col = None
        best_score = -1

        # 规范化目标度量，便于精确比对
        target_measure_norm = TextNormalizer.normalize(str(measure_hint or ""))

        for col in candidates:
            score = 0
            col_lower = col.lower()

            # 根据计量提示评分
            if measure_hint:
                # 计量严格匹配与别名匹配（优先）
                try:
                    if ColumnNameProcessor.match_measure(col, measure_hint):
                        score += 12
                except Exception:
                    pass
                if "价格" in measure_hint and "价格" in col:
                    score += 10
                elif "指数" in measure_hint and "指数" in col:
                    score += 10
                elif "price" in col_lower and "价格" in measure_hint:
                    score += 10
                elif "index" in col_lower and "指数" in measure_hint:
                    score += 10

                # 度量精确一致强加分（严格等同，如“价格(元/吨)”）
                try:
                    if TextNormalizer.normalize(col) == target_measure_norm:
                        score += 30
                except Exception:
                    pass

                # 强偏好“本期”，抑制“上期”
                if "本期" in col:
                    score += 30
                if "上期" in col:
                    score -= 8

                # 当度量为“价格”时，显式压制“发热/热值/卡路里”等热值列被误选
                if "价格" in str(measure_hint):
                    heat_hints = ["发热", "热值", "卡", "kcal", "热量"]
                    if any(h in col for h in heat_hints) or any(h in col_lower for h in ["kal", "heat"]):
                        score -= 20
                    # 额外压制“区间/范围/最低/最高”等区间型字段
                    range_hints = ["区间", "范围", "最低", "最高", "上限", "下限", "最小", "最大"]
                    if any(h in col for h in range_hints):
                        score -= 25

            # 根据产品提示评分
            if product_hint and product_hint in col:
                score += 5

            # 优先包含关键词的列
            if any(
                keyword in col
                for keyword in ["价格", "价值", "指数", "price", "value", "index"]
            ):
                score += 3

            # 避免ID、日期等列
            if any(keyword in col_lower for keyword in ["id", "date", "time", "编号"]):
                score -= 10

            # 数值化可行性加分：对象列若可较好地转为数值，给予小幅加分
            try:
                if col in numeric_cols:
                    score += 2
                else:
                    ser = _pd.to_numeric(df[col], errors="coerce")
                    ratio = float(ser.notna().mean()) if len(ser) else 0.0
                    if ratio >= 0.5:
                        score += 1
                    else:
                        # 明显不可数值化的对象列整体降权
                        score -= 15
                        # 额外检测“范围/区间”样式的单元格内容并强力降权
                        try:
                            import re as _re
                            svals = df[col].dropna().astype(str).head(50)
                            range_pat = _re.compile(
                                r"\b\d{2,6}\s*(?:[-~–—－～]|至|到)\s*\d{2,6}\b"
                            )
                            if any(range_pat.search(v) for v in svals):
                                score -= 40
                        except Exception:
                            pass
            except Exception:
                pass

            if score > best_score:
                best_score = score
                best_col = col

        return best_col

    @staticmethod
    def standardize_time_column(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
        """标准化时间列"""
        df = df.copy()
        try:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce").dt.normalize()
        except Exception:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        df = df.dropna(subset=[time_col])
        df = df.drop_duplicates(subset=[time_col])
        return df.sort_values(time_col).reset_index(drop=True)
