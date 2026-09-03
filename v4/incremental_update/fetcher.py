#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据获取模块 - API 数据抓取（兼容 v4 架构）
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from data_api.fetch_api_data import fetch_data as api_fetch_data
from data_api.save_to_csv_cci import fetch_and_save

logger = logging.getLogger(__name__)


class DataFetcher:
    """按配置抓取增量数据并写入原始 CSV."""

    def __init__(self, config: Dict[str, Any], *, app_root: Optional[Path] = None) -> None:
        self.config = config
        self.app_root = Path(app_root) if app_root else Path(__file__).resolve().parent.parent

        default_config = Path("data_api") / "data_config.json"
        self.api_config_file = self._resolve_path(config.get("config_file", default_config))
        self.timeout = config.get("timeout", 30)
        self.max_retries = config.get("max_retries", 3)

    def _resolve_path(self, value: Any) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = (self.app_root / path).resolve()
        return path

    def load_api_config(self) -> List[Dict[str, Any]]:
        if not self.api_config_file.exists():
            raise FileNotFoundError(f"API 配置文件不存在: {self.api_config_file}")

        with self.api_config_file.open("r", encoding="utf-8") as fh:
            config = json.load(fh)

        logger.info("已加载 %s 个 API 配置项", len(config))
        return config

    def fetch_for_dates(
        self,
        dates: Sequence[str],
        output_root: str | Path,
        *,
        use_cci_gate: bool = True,
    ) -> Tuple[int, List[str]]:
        if not dates:
            return 0, []

        api_entries = self.load_api_config()
        cci_entry = self._find_cci_entry(api_entries) if use_cci_gate else None

        output_path = self._resolve_path(output_root)
        rc = 0
        kept_days: List[str] = []

        for date in dates:
            logger.info("开始抓取日期: %s", date)

            if cci_entry and not self._check_cci_gate(cci_entry, date):
                logger.info("CCI 门控：%s 无数据，跳过", date)
                continue

            ok, fail = 0, 0
            for entry in api_entries:
                try:
                    self._fetch_and_save_entry(entry, date, output_path)
                    ok += 1
                except Exception as exc:
                    logger.warning("抓取失败: %s -> %s", entry.get("table_name"), exc)
                    fail += 1

            logger.info("日期 %s 抓取完成：成功 %s，失败 %s", date, ok, fail)
            if ok > 0:
                kept_days.append(date)
            if fail > 0 and rc == 0:
                rc = 2

        return rc, kept_days

    def _find_cci_entry(self, entries: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for entry in entries:
            table_name = str(entry.get("table_name", ""))
            if "00000019" in table_name or "cci" in table_name.lower():
                return entry
        return None

    def _check_cci_gate(self, entry: Dict[str, Any], date: str) -> bool:
        try:
            params = {
                "source": entry["source"],
                "tableName": entry["table_name"],
                "columns": entry["columns"],
                "dateColumn": entry["date_column"],
                "startDate": date,
                "endDate": date,
            }
            data = api_fetch_data(params)
            if not DataFetcher._payload_has_records(data):
                logger.debug("CCI gate payload empty for %s", date)
                return False
            return True
        except Exception as exc:
            logger.warning("CCI 门控检查失败 (%s): %s", date, exc)
            return False

    def _fetch_and_save_entry(
        self, entry: Dict[str, Any], date: str, output_root: Path
    ) -> None:
        fetch_and_save(
            source=entry["source"],
            table_name=entry["table_name"],
            columns=entry.get("columns"),
            date_column=entry["date_column"],
            force_single_date=date,
            append_mode=True,
            output_root=str(output_root),
        )


    @staticmethod
    def _payload_has_records(payload: Any) -> bool:
        if payload is None:
            return False
        if isinstance(payload, (str, bytes)):
            return bool(payload)
        if isinstance(payload, dict):
            nested_keys = (
                "data",
                "records",
                "rows",
                "items",
                "list",
                "result",
                "value",
                "values",
            )
            for key in nested_keys:
                if key in payload and DataFetcher._payload_has_records(payload[key]):
                    return True
            meta_keys = {"code", "msg", "message", "success", "status"}
            for key, value in payload.items():
                if key not in meta_keys and DataFetcher._payload_has_records(value):
                    return True
            return False
        if isinstance(payload, (list, tuple, set)):
            return any(DataFetcher._payload_has_records(item) for item in payload)
        return True



__all__ = ["DataFetcher"]
