#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史稳定化模块 - 确保增量更新不丢失历史数据
"""

import pandas as pd
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class HistoryStabilizer:
    """历史稳定化器"""

    def __init__(self, baseline_path: str):
        """
        初始化稳定化器

        Args:
            baseline_path: 历史基准文件路径（目标表）
        """
        self.baseline_path = Path(baseline_path)
        self._baseline = None

    def load_baseline(self) -> pd.DataFrame:
        """
        加载历史基准

        Returns:
            历史基准DataFrame
        """
        if not self.baseline_path.exists():
            raise FileNotFoundError(
                f"历史基准文件不存在: {self.baseline_path}\n" f"请确保目标表文件存在"
            )

        logger.info(f"加载历史基准: {self.baseline_path}")

        # 尝试多种编码
        encodings = ["utf-8-sig", "gbk", "gb18030"]
        for encoding in encodings:
            try:
                self._baseline = pd.read_csv(self.baseline_path, encoding=encoding)
                logger.info(
                    f"历史基准加载成功 ({encoding}): "
                    f"{len(self._baseline)} 行, {len(self._baseline.columns)} 列"
                )
                return self._baseline
            except UnicodeDecodeError:
                continue

        raise ValueError(f"无法读取文件: {self.baseline_path}")

    def merge_with_incremental(
        self,
        incremental_df: pd.DataFrame,
        incremental_dates: List[str],
        date_column: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        合并历史基准与增量数据

        策略：
        1. 保留历史基准中的所有行
        2. 只用增量日期覆盖/新增对应行
        3. 历史日期的数据不变

        Args:
            incremental_df: 增量数据
            incremental_dates: 增量日期列表 (YYYY-MM-DD)
            date_column: 日期列名（默认第一列）

        Returns:
            合并后的DataFrame
        """
        if self._baseline is None:
            self.load_baseline()

        # 确定日期列
        if date_column is None:
            date_column = self._baseline.columns[0]

        logger.info(f"开始历史稳定化合并...")
        logger.info(f"  历史基准: {len(self._baseline)} 行")
        logger.info(f"  增量数据: {len(incremental_df)} 行")
        logger.info(f"  增量日期: {incremental_dates}")

        # 复制并规范化日期
        baseline = self._baseline.copy()
        incremental = incremental_df.copy()

        # 转换日期为 datetime
        baseline[date_column] = pd.to_datetime(
            baseline[date_column], errors="coerce"
        ).dt.normalize()

        incremental[date_column] = pd.to_datetime(
            incremental[date_column], errors="coerce"
        ).dt.normalize()

        # 转换增量日期列表
        increment_dates_set = set(
            pd.to_datetime(d).normalize() for d in incremental_dates
        )

        # 对齐列（确保两个DataFrame有相同的列）
        all_columns = set(baseline.columns) | set(incremental.columns)
        for col in all_columns:
            if col not in baseline.columns:
                baseline[col] = None
            if col not in incremental.columns:
                incremental[col] = None

        # 保持列顺序一致
        column_order = list(baseline.columns)
        incremental = incremental[column_order]

        # 合并策略：
        # 1. 历史数据中不在增量日期的行 -> 保留
        # 2. 增量数据中在增量日期的行 -> 使用
        historical_rows = baseline[~baseline[date_column].isin(increment_dates_set)]
        incremental_rows = incremental[
            incremental[date_column].isin(increment_dates_set)
        ]

        # 合并
        result = pd.concat([historical_rows, incremental_rows], ignore_index=True)

        # 按日期排序
        result = result.sort_values(by=date_column).reset_index(drop=True)

        logger.info(f"历史稳定化完成:")
        logger.info(f"  保留历史行: {len(historical_rows)}")
        logger.info(f"  新增/更新行: {len(incremental_rows)}")
        logger.info(f"  最终总行数: {len(result)}")

        return result

    def validate_merge(
        self, result_df: pd.DataFrame, date_column: Optional[str] = None
    ) -> bool:
        """
        验证合并结果

        Args:
            result_df: 合并后的DataFrame
            date_column: 日期列名

        Returns:
            是否有效
        """
        if self._baseline is None:
            self.load_baseline()

        if date_column is None:
            date_column = self._baseline.columns[0]

        # 检查行数
        if len(result_df) < len(self._baseline):
            logger.error(
                f"合并后行数减少！"
                f"基准: {len(self._baseline)}, 结果: {len(result_df)}"
            )
            return False

        # 检查列数
        if len(result_df.columns) < len(self._baseline.columns):
            logger.error(
                f"合并后列数减少！"
                f"基准: {len(self._baseline.columns)}, "
                f"结果: {len(result_df.columns)}"
            )
            return False

        # 检查空值比例
        baseline_null_pct = (
            self._baseline.isnull().sum().sum()
            / (len(self._baseline) * len(self._baseline.columns))
            * 100
        )
        result_null_pct = (
            result_df.isnull().sum().sum()
            / (len(result_df) * len(result_df.columns))
            * 100
        )

        if result_null_pct > baseline_null_pct * 1.1:  # 允许 10% 误差
            logger.warning(
                f"合并后空值比例增加！"
                f"基准: {baseline_null_pct:.2f}%, 结果: {result_null_pct:.2f}%"
            )

        logger.info("合并结果验证通过")
        return True


if __name__ == "__main__":
    # 测试
    import sys

    logging.basicConfig(level=logging.INFO)

    # 示例用法
    stabilizer = HistoryStabilizer("coal_freight.csv")

    # 加载基准
    baseline = stabilizer.load_baseline()
    print(f"基准数据: {baseline.shape}")

    # 创建模拟增量数据
    incremental = baseline.tail(10).copy()
    incremental.iloc[:, 0] = pd.to_datetime("2025-09-26")

    # 合并
    result = stabilizer.merge_with_incremental(incremental, ["2025-09-26"])

    print(f"合并结果: {result.shape}")

    # 验证
    if stabilizer.validate_merge(result):
        print("验证通过")

