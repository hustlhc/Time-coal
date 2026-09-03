#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前向填充模块 - 处理低频更新列的空值
"""

import pandas as pd
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class ForwardFiller:
    """前向填充器"""

    @staticmethod
    def fill_incremental_rows(
        df: pd.DataFrame,
        incremental_dates: List[str],
        date_column: Optional[str] = None,
        preserve_history: bool = True,
    ) -> pd.DataFrame:
        """
        对增量新增的日期行进行前向填充

        策略：
        1. 识别增量日期的行
        2. 对这些行中的空值，用该列最近的历史值填充
        3. 保留历史日期的数据不变（如果 preserve_history=True）

        Args:
            df: 数据框
            incremental_dates: 增量日期列表 (YYYY-MM-DD)
            date_column: 日期列名（默认第一列）
            preserve_history: 是否保护历史数据

        Returns:
            填充后的数据框
        """
        if df is None or df.empty or not incremental_dates:
            return df

        # 确定日期列
        if date_column is None:
            date_column = df.columns[0]

        logger.info(f"开始前向填充...")
        logger.info(f"  增量日期: {incremental_dates}")
        logger.info(f"  保护历史: {preserve_history}")

        # 复制数据框
        result = df.copy()

        # 转换日期
        result[date_column] = pd.to_datetime(result[date_column], errors="coerce")

        increment_dates_set = set(
            pd.to_datetime(d).normalize() for d in incremental_dates
        )

        # 识别增量日期的行
        new_rows_mask = result[date_column].isin(increment_dates_set)
        new_row_indices = result[new_rows_mask].index.tolist()

        if not new_row_indices:
            logger.info("未找到增量日期行，跳过填充")
            return result

        # 统计填充前的空值
        value_cols = [c for c in result.columns if c != date_column]
        before_nulls = result.loc[new_rows_mask, value_cols].isnull().sum().sum()

        logger.info(f"  增量行数: {len(new_row_indices)}")
        logger.info(f"  填充前空值: {before_nulls}")

        # 对每个增量行，逐列进行前向填充
        for idx in new_row_indices:
            for col in value_cols:
                # 如果该位置为空，则向前查找最近的非空值
                if pd.isnull(result.loc[idx, col]):
                    # 获取该行之前的所有行
                    prev_rows = result.loc[: idx - 1, col]

                    # 找到最后一个非空值
                    last_valid_idx = prev_rows.last_valid_index()

                    if last_valid_idx is not None:
                        result.loc[idx, col] = result.loc[last_valid_idx, col]

        # 统计填充后的空值
        after_nulls = result.loc[new_rows_mask, value_cols].isnull().sum().sum()
        filled_count = before_nulls - after_nulls

        if filled_count > 0:
            logger.info(
                f"填充完成: 填充 {filled_count} 个空值 "
                f"({before_nulls} -> {after_nulls})"
            )
        else:
            logger.info("增量日期无需填充")

        # 如果仍有空值，记录警告
        if after_nulls > 0:
            null_cols = result.loc[new_rows_mask, value_cols].isnull().sum()
            null_cols = null_cols[null_cols > 0]

            if not null_cols.empty:
                logger.warning(
                    f"增量日期仍有 {after_nulls} 个空值" "（可能是首行或无历史数据）"
                )
                logger.debug(f"空值列: {null_cols.to_dict()}")

        return result

    @staticmethod
    def analyze_column_frequency(
        df: pd.DataFrame, date_column: Optional[str] = None
    ) -> pd.DataFrame:
        """
        分析各列的更新频率

        Args:
            df: 数据框
            date_column: 日期列名

        Returns:
            频率分析结果
        """
        if date_column is None:
            date_column = df.columns[0]

        result = pd.DataFrame()
        value_cols = [c for c in df.columns if c != date_column]

        for col in value_cols:
            # 计算非空值的间隔
            non_null_dates = df[df[col].notna()][date_column]

            if len(non_null_dates) < 2:
                continue

            # 计算中位数间隔
            diffs = pd.Series(non_null_dates).diff().dropna()
            median_interval = diffs.median().days if len(diffs) > 0 else None

            # 判断频率
            if median_interval is None:
                frequency = "sparse"
            elif median_interval <= 2:
                frequency = "daily"
            elif median_interval <= 10:
                frequency = "weekly"
            elif median_interval <= 40:
                frequency = "monthly"
            else:
                frequency = "sparse"

            result = pd.concat(
                [
                    result,
                    pd.DataFrame(
                        {
                            "column": [col],
                            "median_interval_days": [median_interval],
                            "frequency": [frequency],
                            "total_values": [df[col].notna().sum()],
                            "null_percentage": [df[col].isnull().mean() * 100],
                        }
                    ),
                ],
                ignore_index=True,
            )

        return result


if __name__ == "__main__":
    # 测试
    import numpy as np

    logging.basicConfig(level=logging.INFO)

    # 创建模拟数据
    dates = pd.date_range("2025-09-01", periods=30, freq="D")

    df = pd.DataFrame(
        {
            "date": dates,
            "daily_col": range(30),
            "weekly_col": [100 if i % 7 == 0 else None for i in range(30)],
            "sparse_col": [200 if i in [0, 15, 29] else None for i in range(30)],
        }
    )

    print("原始数据:")
    print(df.tail(10))

    # 前向填充最后5天
    incremental_dates = df["date"].tail(5).dt.strftime("%Y-%m-%d").tolist()

    filled = ForwardFiller.fill_incremental_rows(
        df, incremental_dates, preserve_history=True
    )

    print("\n填充后数据:")
    print(filled.tail(10))

    # 频率分析
    print("\n频率分析:")
    freq_analysis = ForwardFiller.analyze_column_frequency(df)
    print(freq_analysis)

