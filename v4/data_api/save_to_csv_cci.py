import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from .fetch_api_data import fetch_data as _raw_fetch_data

# 尽量与主处理解耦，但用于健壮性的轻量工具可复用
try:
    from pipeline.utils import DataFrameProcessor, TextNormalizer  # type: ignore
except Exception:
    DataFrameProcessor = None  # type: ignore
    TextNormalizer = None  # type: ignore


LOG_FILE = "fetch_log.txt"


def clean_table_name(table_name: str, source: str) -> str:
    """清理表名（用于输出文件名统一），不影响 API 请求参数。"""
    replace_rules = {
        "60plus": "-CCTD-",
        "500plus": "--",
    }
    if source in replace_rules:
        replacement = replace_rules[source]
        for flag in ["-A-", "-B-", "-C-", "-D-"]:
            table_name = table_name.replace(flag, replacement)
    return table_name


def get_last_date_from_log(
    table_name: str, source: str, default: Optional[str] = None
) -> str:
    """从日志读取该表最后一次抓取的截至日期，并返回其后一天。
    若没有日志，默认返回昨天，避免全量抓取。
    """
    if default is None:
        default = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    table_name = clean_table_name(table_name, source)
    if not os.path.exists(LOG_FILE):
        return default
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            if f"来源:{source}, 表:{table_name}" in line and "请求时间范围:" in line:
                try:
                    parts = line.split("请求时间范围:")[1].split(",")[0]
                    start_date, end_date = [p.strip() for p in parts.split(" 到 ")]
                    next_day = (
                        datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    ).strftime("%Y-%m-%d")
                    return next_day
                except Exception:
                    continue
    except Exception:
        pass
    return default


def log_fetch(
    table_name: str, source: str, start_date: str, end_date: str, df: pd.DataFrame
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record_count = len(df) if isinstance(df, pd.DataFrame) else 0
    has_null = bool(df.isnull().values.any()) if isinstance(df, pd.DataFrame) else True
    line = f"[{now}] 来源:{source}, 表:{table_name}, 请求时间范围:{start_date} 到 {end_date}, 记录数:{record_count}, 是否有空值:{has_null}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def clear_folders(
    _folders: list, source: str, table_name: str, start_date: str, end_date: str
) -> None:
    """非破坏：仅记录（避免每日运维误删历史数据）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    note = f"[{now}] 非破坏性: CCI空返回, 跳过清空目录. 来源:{source}, 表:{table_name}, 时间范围:{start_date} 到 {end_date}"
    print(note)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(note + "\n")


def fetch_data(params: Dict[str, Any]):
    """带简单重试的请求包装。"""
    last = None
    for attempt in range(1, 4):
        try:
            return _raw_fetch_data(params)
        except Exception as e:
            last = e
            if attempt >= 3:
                break
            time.sleep(1.5 ** (attempt - 1))
    if last:
        raise last
    return None


def _normalize_and_select_columns(
    raw_df: pd.DataFrame, expected_cols: List[str], date_hint: Optional[str]
) -> pd.DataFrame:
    """尽量将 API 返回列映射到期望列：
    - 日期列：优先 expected/date_hint；否则用 DataFrameProcessor 检测；最后选第1列
    - 关键名模糊同义：日期(日期/时间/发布日期)，航线(航线名称/航线/路线)，值列(本期/价格/指数)
    - 若未找到则以 None 填充，保证列序稳定
    """
    df = raw_df.copy()
    if not expected_cols:
        return df

    def norm(s: Any) -> str:
        try:
            t = str(s).strip()
            return TextNormalizer.normalize(t) if TextNormalizer else t.replace(" ", "")
        except Exception:
            return str(s)

    cols = list(df.columns)
    cols_norm = {norm(c): c for c in cols}

    def pick_time_col() -> str:
        cands = []
        if date_hint:
            cands.append(date_hint)
        if expected_cols:
            cands.append(expected_cols[0])
        for cand in cands:
            if cand and cand in df.columns:
                return cand
            if cand and norm(cand) in cols_norm:
                return cols_norm[norm(cand)]
        if DataFrameProcessor is not None:
            try:
                t = DataFrameProcessor.detect_time_column(df)
                if t:
                    return t
            except Exception:
                pass
        return df.columns[0]

    def pick_route_col() -> Optional[str]:
        keys = ["航线名称", "航线", "路线", "route"]
        for k in keys:
            if k in df.columns:
                return k
            nk = norm(k)
            if nk in cols_norm:
                return cols_norm[nk]
        return None

    def pick_value_col() -> Optional[str]:
        cand = None
        best_score = -999
        for c in df.columns:
            s = str(c).lower()
            score = 0
            if any(
                k in s
                for k in ["本期", "价格", "价", "指数", "price", "value", "index"]
            ):
                score += 5
            if any(
                k in s for k in ["上期", "环比", "同比", "区间", "范围", "上限", "下限"]
            ):
                score -= 3
            try:
                if pd.api.types.is_numeric_dtype(df[c]):
                    score += 2
                else:
                    sample = pd.to_numeric(df[c], errors="coerce")
                    if sample.notna().mean() >= 0.5:
                        score += 1
                    else:
                        score -= 2
            except Exception:
                pass
            if score > best_score:
                cand, best_score = c, score
        return cand

    out = pd.DataFrame()
    for i, exp in enumerate(expected_cols):
        chosen: Optional[str] = None
        if exp in df.columns:
            chosen = exp
        elif norm(exp) in cols_norm:
            chosen = cols_norm[norm(exp)]
        else:
            if i == 0:
                chosen = pick_time_col()
            else:
                if any(k in str(exp) for k in ["航线", "路线", "route"]):
                    chosen = pick_route_col()
                # 若期望列包含明显度量关键词，优先按度量匹配
                if chosen is None and any(
                    k in str(exp)
                    for k in ["价格", "本期", "指数", "price", "value", "index"]
                ):
                    # 1) 基于度量别名匹配（如可用）
                    if TextNormalizer is not None and DataFrameProcessor is not None:
                        try:
                            from ..utils import ColumnNameProcessor as _CNP  # type: ignore

                            target = str(exp)
                            best_c = None
                            best_score = -1
                            for c in df.columns:
                                score = 0
                                # 强偏好“本期”严格匹配
                                if "本期" in target and "本期" in str(c):
                                    score += 10
                                # 度量同义匹配
                                try:
                                    if _CNP.match_measure(str(c), target):
                                        score += 8
                                except Exception:
                                    pass
                                # 排除“上期/区间”等
                                cl = str(c)
                                if any(
                                    k in cl
                                    for k in ["上期", "区间", "范围", "上限", "下限"]
                                ):
                                    score -= 6
                                # 数值性
                                try:
                                    if pd.api.types.is_numeric_dtype(df[c]):
                                        score += 2
                                except Exception:
                                    pass
                                if score > best_score:
                                    best_score, best_c = score, c
                            if best_c is not None and best_score >= 4:
                                chosen = best_c
                        except Exception:
                            pass
                    # 2) 退化到通用打分
                    if chosen is None:
                        chosen = pick_value_col()
        if chosen is None:
            out[exp] = None
        else:
            out[exp] = df[chosen]
    return out


def save_json_to_csv(
    data: Any,
    table_name: str,
    folder: str,
    start_date: str,
    end_date: str,
    columns: Any,
    date_column: Optional[str] = None,
    append: bool = True,
    output_root: Optional[str] = None,
) -> None:
    # 列规范
    if isinstance(columns, str):
        columns = [c.strip() for c in columns.split(",") if c.strip()]

    # 构造 DataFrame
    if not data:
        df = pd.DataFrame(columns=columns)
    else:
        if isinstance(data, dict):
            if "data" in data:
                data = data["data"]
            elif "dataList" in data:
                data = data["dataList"]
            else:
                data = [data]
        df = pd.DataFrame(data)
        # 尝试映射到期望列，避免列名不一致导致数据全空（347 等运费类尤为常见）
        try:
            df = _normalize_and_select_columns(df, columns, date_column)
        except Exception:
            for col in columns:
                if col not in df.columns:
                    df[col] = None
            try:
                df = df[columns]
            except Exception:
                pass

    # 输出路径
    table_name = clean_table_name(table_name, folder)
    out_folder = folder
    if out_folder == "500plus":
        out_folder = "500+"
    elif out_folder == "60plus":
        out_folder = "60+"
    if output_root:
        out_folder = os.path.join(output_root, out_folder)
    os.makedirs(out_folder, exist_ok=True)
    filename = os.path.join(out_folder, f"{table_name}.csv")

    # 选择用于去重与过滤的日期列
    used_date_col = date_column or (
        columns[0] if columns else (df.columns[0] if len(df.columns) else None)
    )
    if used_date_col not in df.columns and len(df.columns):
        if DataFrameProcessor is not None:
            try:
                t = DataFrameProcessor.detect_time_column(df)
                if t:
                    used_date_col = t
            except Exception:
                pass
        if used_date_col not in df.columns:
            used_date_col = df.columns[0]

    # 仅保留请求时间窗口内的数据（增量期过滤）
    try:
        if used_date_col and used_date_col in df.columns:
            dts = pd.to_datetime(df[used_date_col], errors="coerce").dt.normalize()
            d0 = pd.to_datetime(start_date).normalize()
            d1 = pd.to_datetime(end_date).normalize()
            mask = dts.notna() & (dts >= d0) & (dts <= d1)
            df = df.loc[mask].copy()
            df[used_date_col] = dts[mask]
    except Exception:
        pass

    # 追加写入并按“日期 + 维度列”去重（路由/品类类表格保留同日多行）
    if append and os.path.exists(filename) and used_date_col:
        try:
            old = pd.read_csv(filename, encoding="utf-8-sig")
        except Exception:
            try:
                old = pd.read_csv(filename)
            except Exception:
                old = None
        if old is not None:
            all_cols = list(
                dict.fromkeys([used_date_col] + list(old.columns) + list(df.columns))
            )
            for c in all_cols:
                if c not in old.columns:
                    old[c] = None
                if c not in df.columns:
                    df[c] = None
            try:
                old[used_date_col] = pd.to_datetime(old[used_date_col], errors="coerce")
            except Exception:
                pass
            try:
                df[used_date_col] = pd.to_datetime(df[used_date_col], errors="coerce")
            except Exception:
                pass
            # 用新抓取窗口的数据替换旧窗口数据，避免历史上错误聚合影响增量
            try:
                d0 = pd.to_datetime(start_date).normalize()
                d1 = pd.to_datetime(end_date).normalize()
                keep_mask = old[used_date_col].dt.normalize().lt(d0) | old[
                    used_date_col
                ].dt.normalize().gt(d1)
                old = old.loc[keep_mask].copy()
            except Exception:
                pass

            # 识别“值列”（度量列），其余非时间列视为维度列
            def is_value_col(name: str) -> bool:
                s = str(name).lower()
                keys = ["本期", "当期值", "价格", "指数", "price", "value", "index"]
                return any(k in s for k in keys)

            # 期望列（来自 data.json）优先指导维度识别
            dim_cols = []
            if isinstance(columns, list) and columns:
                for c in columns:
                    if c == used_date_col:
                        continue
                    if not is_value_col(c):
                        dim_cols.append(c)
            # 回退：若没有显式维度，尝试在现有列里选择对象型文本列作为维度
            if not dim_cols:
                try:
                    obj_cols = [
                        c
                        for c in all_cols
                        if c != used_date_col
                        and (old[c].dtype == object or df[c].dtype == object)
                    ]
                    # 排除明显度量列
                    dim_cols = [c for c in obj_cols if not is_value_col(c)]
                except Exception:
                    dim_cols = []
            dedup_keys = [used_date_col] + dim_cols if dim_cols else [used_date_col]

            merged = pd.concat([old[all_cols], df[all_cols]], ignore_index=True)
            merged = merged.dropna(subset=[used_date_col])
            # 先去重再排序，keep='last' 以最新写入为准
            merged = merged.drop_duplicates(subset=dedup_keys, keep="last").sort_values(
                by=used_date_col
            )
            merged.to_csv(filename, index=False, encoding="utf-8-sig")
            print(f"OK CSV 已追加 {filename}, 新增 {len(df)} 行, 合计 {len(merged)} 行")
        else:
            df.to_csv(filename, index=False, encoding="utf-8-sig")
            print(f"OK CSV 已保存 {filename}, 记录数 {len(df)}")
    else:
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"OK CSV 已保存 {filename}, 记录数 {len(df)}")

    # 日志
    log_fetch(table_name, out_folder, start_date, end_date, df)


def fetch_and_save(
    source: str,
    table_name: str,
    columns: Any,
    date_column: str,
    force_single_date: Optional[str] = None,
    append_mode: bool = True,
    output_root: Optional[str] = None,
) -> None:
    """按日志推进或单日强制抓取并保存（非破坏、增量、去重）。"""
    if force_single_date:
        start_date = end_date = force_single_date
    else:
        start_date = get_last_date_from_log(table_name, source)
        end_date = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    params = {
        "source": source,
        "tableName": table_name,
        "columns": columns,
        "dateColumn": date_column,
        "startDate": start_date,
        "endDate": end_date,
    }

    data = fetch_data(params)

    # CCI(00000019) 当天空：只记录不清空（非破坏），避免覆盖历史
    try:
        is_cci = ("00000019" in str(table_name)) and ("CCI" in str(table_name))
    except Exception:
        is_cci = False
    if is_cci and (not data):
        if isinstance(columns, str):
            columns = [c.strip() for c in columns.split(",") if c.strip()]
        df = pd.DataFrame(columns=columns)
        print(f"WARN {table_name} 当前返回为空, 跳过清空, 仅记录日志")
        clear_folders(["60plus", "500plus"], source, table_name, start_date, end_date)
        log_fetch(
            clean_table_name(table_name, source), source, start_date, end_date, df
        )
        return

    save_json_to_csv(
        data,
        table_name,
        source,
        start_date,
        end_date,
        columns,
        date_column=date_column,
        append=append_mode,
        output_root=output_root,
    )
