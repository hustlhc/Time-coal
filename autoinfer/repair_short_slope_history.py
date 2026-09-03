#!/usr/bin/env python3
"""Restore historical coal forecasts that were changed by slope correction.

The first slope-controlled points cannot be recovered byte-for-byte because
the correction assigned them directly to a synthetic line. This utility
recovers the invertible portion, bridges the overwritten portion smoothly,
then reapplies the configured imported-to-domestic trend synchronization.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import requests
from scipy.interpolate import PchipInterpolator


COAL_KEYS = [
    "CCI3800outinfer",
    "CCI4500infer",
    "CCI4700outinfer",
    "CCI5000infer",
    "CCI5500infer",
    "CCI5500outinfer",
]
DOMESTIC_KEYS = ["CCI4500infer", "CCI5000infer", "CCI5500infer"]
IMPORTED_KEYS = ["CCI3800outinfer", "CCI4700outinfer", "CCI5500outinfer"]
LABEL_TO_KEY = {
    "CCI4500": "CCI4500infer",
    "CCI5000": "CCI5000infer",
    "CCI5500": "CCI5500infer",
    "CCI3800out": "CCI3800outinfer",
    "CCI4700out": "CCI4700outinfer",
    "CCI5500out": "CCI5500outinfer",
}
KEY_TO_REAL_TYPE = {
    "CCI4500infer": "CCI4500",
    "CCI5000infer": "CCI5000",
    "CCI5500infer": "CCI5500",
    "CCI3800outinfer": "CCI3800out",
    "CCI4700outinfer": "CCI4700out",
    "CCI5500outinfer": "CCI5500out",
}

LATEST_START = "==> [sync6] short slope correct latest forecasts"
LATEST_END = "==> [sync6] align latest domestic forecasts to imported trend"
APPLIED_RE = re.compile(
    r"^(CCI(?:4500|5000|5500|3800out|4700out|5500out)):.*applied=True\s*$",
    re.MULTILINE,
)
LOG_DATE_RE = re.compile(r"daily_coal_freight_(\d{8})\.log$")


@dataclass
class BatchRepair:
    infer_date: str
    direct_keys: list[str]
    json_path: Path
    original_payload: dict[str, Any]
    repaired_payload: dict[str, Any]
    curve_metrics: list[dict[str, Any]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore and optionally resend historical forecasts affected by short slope correction."
    )
    parser.add_argument("--db", default="autoinfer/coal_prediction.db")
    parser.add_argument("--json-dir", default="autoinfer/json")
    parser.add_argument("--log-dir", default="log/cron")
    parser.add_argument("--apply", action="store_true", help="Back up and overwrite JSON/SQLite data")
    parser.add_argument("--send", action="store_true", help="Send repaired payloads after a successful apply")
    parser.add_argument(
        "--backup-root",
        default="autoinfer/repair_backups",
        help="Parent directory for timestamped backups and reports",
    )
    parser.add_argument("--sync-strength", type=float, default=0.8)
    parser.add_argument("--slope-strength", type=float, default=0.8)
    parser.add_argument("--window", type=int, default=20)
    parser.add_argument("--decay-days", type=int, default=35)
    parser.add_argument(
        "--url",
        default=os.environ.get(
            "INFER_RESULT_URL",
            "https://crm.zhaomei.com/crm/called/v1/aiapi/infer-result",
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("INFER_RESULT_TIMEOUT", "30")),
    )
    return parser.parse_args()


def correction_weights(n: int, window: int, decay_days: int) -> np.ndarray:
    weights = np.zeros(n, dtype=float)
    window = max(1, min(window, n))
    decay_days = max(window, min(decay_days, n))
    weights[:window] = 1.0
    if decay_days > window:
        tail = np.arange(window, decay_days, dtype=float)
        weights[window:decay_days] = (decay_days - tail) / (decay_days - window)
    return weights


def linear_slope(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return 0.0
    return float(np.polyfit(np.arange(values.size, dtype=float), values, 1)[0])


def latest_complete_section(text: str) -> str | None:
    starts = [match.start() for match in re.finditer(re.escape(LATEST_START), text)]
    for start in reversed(starts):
        end = text.find(LATEST_END, start)
        if end >= 0:
            return text[start:end]
    return None


def discover_affected(
    log_dir: Path,
    json_dir: Path,
    conn: sqlite3.Connection,
) -> dict[str, list[str]]:
    affected: dict[str, list[str]] = {}
    for log_path in sorted(log_dir.glob("daily_coal_freight_????????.log")):
        match = LOG_DATE_RE.search(log_path.name)
        if not match:
            continue
        infer_date = datetime.strptime(match.group(1), "%Y%m%d").strftime("%Y-%m-%d")
        json_path = json_dir / f"{infer_date}_data.json"
        if not json_path.exists():
            continue

        section = latest_complete_section(log_path.read_text(encoding="utf-8", errors="replace"))
        if not section:
            continue
        keys = sorted({LABEL_TO_KEY[label] for label in APPLIED_RE.findall(section)})
        if not keys:
            continue

        row = conn.execute(
            "SELECT COUNT(*) FROM prediction_data WHERE infer_date = ?",
            (infer_date,),
        ).fetchone()
        if row and row[0] > 0:
            affected[infer_date] = keys
    return affected


def load_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload.get("data"), dict):
        raise ValueError(f"{path} 缺少 data 对象")
    for key in COAL_KEYS:
        records = payload["data"].get(key)
        if not isinstance(records, list) or len(records) != 120:
            count = len(records) if isinstance(records, list) else "missing"
            raise ValueError(f"{path}: {key} 应为 120 条，实际 {count}")
        values = np.asarray([record["predict"] for record in records], dtype=float)
        if not np.isfinite(values).all() or np.any(values <= 0):
            raise ValueError(f"{path}: {key} 存在非正数或非有限预测值")
    return payload


def payload_arrays(payload: dict[str, Any]) -> dict[str, np.ndarray]:
    return {
        key: np.asarray([record["predict"] for record in payload["data"][key]], dtype=float)
        for key in COAL_KEYS
    }


def imported_anchor_log_rel(curves: dict[str, np.ndarray]) -> np.ndarray:
    logs = []
    for key in IMPORTED_KEYS:
        values = curves[key]
        logs.append(np.log(np.clip(values / values[0], 1e-9, None)))
    return np.mean(np.column_stack(logs), axis=1)


def invert_domestic_sync(
    final_curves: dict[str, np.ndarray],
    strength: float,
) -> dict[str, np.ndarray]:
    if not 0 <= strength < 1:
        raise ValueError("sync strength 必须在 [0, 1) 内，才能逆向恢复国内曲线")
    anchor = imported_anchor_log_rel(final_curves)
    before_sync = {key: values.copy() for key, values in final_curves.items()}
    for key in DOMESTIC_KEYS:
        final = final_curves[key]
        base = final[0]
        final_log_rel = np.log(np.clip(final / base, 1e-9, None))
        raw_log_rel = (final_log_rel - strength * anchor) / (1.0 - strength)
        recovered = base * np.exp(raw_log_rel)
        recovered[0] = final[0]
        before_sync[key] = recovered
    return before_sync


def recent_slope(
    conn: sqlite3.Connection,
    infer_date: str,
    key: str,
    lookback: int = 5,
) -> tuple[float, list[float]]:
    rows = conn.execute(
        """
        SELECT value
        FROM real_data
        WHERE data_type = ? AND date < ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (KEY_TO_REAL_TYPE[key], infer_date, lookback),
    ).fetchall()
    values = [float(row[0]) for row in reversed(rows)]
    if len(values) < lookback:
        raise ValueError(f"{infer_date} {key}: 真实数据不足 {lookback} 条")
    return linear_slope(np.asarray(values)), values


def smooth_bridge(
    first_value: float,
    recovered: np.ndarray,
    recovery_start: int,
) -> np.ndarray:
    result = recovered.copy()
    support_end = min(len(result), recovery_start + 6)
    support_x = np.concatenate(([0.0], np.arange(recovery_start, support_end, dtype=float)))
    support_y = np.concatenate(([first_value], result[recovery_start:support_end]))
    interpolator = PchipInterpolator(support_x, support_y)
    result[:recovery_start] = interpolator(np.arange(recovery_start, dtype=float))
    result[0] = first_value
    return result


def undo_slope_correction(
    corrected: np.ndarray,
    recent_slope_value: float,
    slope_strength: float,
    window: int,
    decay_days: int,
    is_domestic: bool,
) -> np.ndarray:
    weights = correction_weights(len(corrected), window, decay_days)
    target_slope = recent_slope_value * slope_strength
    target = corrected[0] + target_slope * np.arange(len(corrected), dtype=float)

    recovered = corrected.copy()
    invertible = weights < 1.0 - 1e-12
    recovered[invertible] = (
        corrected[invertible] - weights[invertible] * target[invertible]
    ) / (1.0 - weights[invertible])

    # Imported curves were not rounded, so point 22 onward is recoverable.
    # Domestic curves were rounded twice; use the first completely unaffected
    # point to avoid amplifying rounding noise during inversion.
    recovery_start = decay_days if is_domestic else window + 1
    return smooth_bridge(corrected[0], recovered, recovery_start)


def apply_domestic_sync(
    before_sync: dict[str, np.ndarray],
    strength: float,
) -> dict[str, np.ndarray]:
    anchor = imported_anchor_log_rel(before_sync)
    final = {key: values.copy() for key, values in before_sync.items()}
    for key in DOMESTIC_KEYS:
        values = before_sync[key]
        base = values[0]
        own_log_rel = np.log(np.clip(values / base, 1e-9, None))
        synced = base * np.exp((1.0 - strength) * own_log_rel + strength * anchor)
        synced[0] = values[0]
        final[key] = np.rint(synced)
    return final


def max_relative_step(values: np.ndarray) -> float:
    return float(np.max(np.abs(np.diff(values) / values[:-1])))


def repair_batch(
    conn: sqlite3.Connection,
    infer_date: str,
    direct_keys: list[str],
    json_path: Path,
    sync_strength: float,
    slope_strength: float,
    window: int,
    decay_days: int,
) -> BatchRepair:
    original_payload = load_payload(json_path)
    original_curves = payload_arrays(original_payload)
    before_sync = invert_domestic_sync(original_curves, sync_strength)
    slope_details: dict[str, tuple[float, list[float]]] = {}

    for key in direct_keys:
        slope_value, history = recent_slope(conn, infer_date, key)
        slope_details[key] = (slope_value, history)
        before_sync[key] = undo_slope_correction(
            before_sync[key],
            slope_value,
            slope_strength,
            window,
            decay_days,
            key in DOMESTIC_KEYS,
        )

    repaired_curves = apply_domestic_sync(before_sync, sync_strength)
    repaired_payload = json.loads(json.dumps(original_payload, ensure_ascii=False))
    curve_metrics: list[dict[str, Any]] = []

    for key in COAL_KEYS:
        old = original_curves[key]
        new = repaired_curves[key]
        if not np.isfinite(new).all() or np.any(new <= 0):
            raise ValueError(f"{infer_date} {key}: 修复后出现非法预测值")
        if abs(new[0] - old[0]) > 1e-6:
            raise ValueError(f"{infer_date} {key}: 修复没有保住首点")
        if max_relative_step(new) > 0.08:
            raise ValueError(
                f"{infer_date} {key}: 修复后最大单步变化 {max_relative_step(new):.2%} 超过 8%"
            )

        records = repaired_payload["data"][key]
        for index, value in enumerate(new):
            records[index]["predict"] = float(value)

        detail: dict[str, Any] = {
            "infer_date": infer_date,
            "data_type": key,
            "directly_corrected": key in direct_keys,
            "first_value": float(new[0]),
            "max_abs_change": float(np.max(np.abs(new - old))),
            "old_max_daily_pct": max_relative_step(old),
            "new_max_daily_pct": max_relative_step(new),
            "old_first35_range": float(np.ptp(old[:35])),
            "new_first35_range": float(np.ptp(new[:35])),
        }
        if key in slope_details:
            detail["recent_slope"] = slope_details[key][0]
            detail["recent_history"] = slope_details[key][1]
        curve_metrics.append(detail)

    return BatchRepair(
        infer_date=infer_date,
        direct_keys=direct_keys,
        json_path=json_path,
        original_payload=original_payload,
        repaired_payload=repaired_payload,
        curve_metrics=curve_metrics,
    )


def validate_db_matches_json(
    conn: sqlite3.Connection,
    repairs: list[BatchRepair],
    use_repaired: bool,
) -> None:
    for repair in repairs:
        payload = repair.repaired_payload if use_repaired else repair.original_payload
        for key in COAL_KEYS:
            records = payload["data"][key]
            rows = conn.execute(
                """
                SELECT pred_date, predict
                FROM prediction_data
                WHERE infer_date = ? AND data_type = ?
                ORDER BY pred_date
                """,
                (repair.infer_date, key),
            ).fetchall()
            expected = sorted((str(record["date"]), float(record["predict"])) for record in records)
            actual = [(str(row[0]), float(row[1])) for row in rows]
            if len(actual) != 120:
                raise ValueError(f"{repair.infer_date} {key}: 数据库预测条数为 {len(actual)}，不是 120")
            for (expected_date, expected_value), (actual_date, actual_value) in zip(expected, actual):
                if expected_date != actual_date or abs(expected_value - actual_value) > 1e-6:
                    raise ValueError(
                        f"{repair.infer_date} {key}: JSON/数据库不一致 "
                        f"({expected_date}, {expected_value}) != ({actual_date}, {actual_value})"
                    )


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=4, default=str)
        handle.write("\n")
    os.replace(temporary, path)


def make_backup(
    conn: sqlite3.Connection,
    db_path: Path,
    repairs: list[BatchRepair],
    backup_root: Path,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_root / f"short_slope_restore_{stamp}"
    json_backup = backup_dir / "json"
    json_backup.mkdir(parents=True, exist_ok=False)

    backup_conn = sqlite3.connect(backup_dir / db_path.name)
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()

    for repair in repairs:
        shutil.copy2(repair.json_path, json_backup / repair.json_path.name)
    return backup_dir


def update_db(conn: sqlite3.Connection, repairs: list[BatchRepair]) -> None:
    with conn:
        for repair in repairs:
            for key in COAL_KEYS:
                for record in repair.repaired_payload["data"][key]:
                    cursor = conn.execute(
                        """
                        UPDATE prediction_data
                        SET predict = ?
                        WHERE infer_date = ? AND data_type = ? AND pred_date = ?
                        """,
                        (
                            float(record["predict"]),
                            repair.infer_date,
                            key,
                            str(record["date"]),
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError(
                            f"{repair.infer_date} {key} {record['date']}: "
                            f"数据库更新行数为 {cursor.rowcount}"
                        )


def build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("INFER_RESULT_AUTH_TOKEN")
    api_key = os.environ.get("INFER_RESULT_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def send_repairs(
    repairs: list[BatchRepair],
    url: str,
    timeout: float,
) -> list[dict[str, Any]]:
    results = []
    for repair in repairs:
        try:
            response = requests.post(
                url,
                json=repair.repaired_payload,
                headers=build_headers(),
                timeout=timeout,
            )
            result = {
                "infer_date": repair.infer_date,
                "status_code": response.status_code,
                "ok": response.ok,
                "response": response.text[:1000],
            }
        except requests.RequestException as exc:
            result = {
                "infer_date": repair.infer_date,
                "status_code": None,
                "ok": False,
                "response": str(exc),
            }
        results.append(result)
        print(
            f"发送 {repair.infer_date}: status={result['status_code']} "
            f"ok={result['ok']} response={result['response'][:160]!r}"
        )
        time.sleep(0.15)
    return results


def print_summary(repairs: list[BatchRepair]) -> None:
    direct_count = sum(len(repair.direct_keys) for repair in repairs)
    all_metrics = [metric for repair in repairs for metric in repair.curve_metrics]
    changed_count = sum(metric["max_abs_change"] > 1e-8 for metric in all_metrics)
    old_worst = max(metric["old_max_daily_pct"] for metric in all_metrics)
    new_worst = max(metric["new_max_daily_pct"] for metric in all_metrics)
    print(f"受影响批次: {len(repairs)}")
    print(f"直接受斜率校正曲线: {direct_count}")
    print(f"因直接/同步关系重建曲线: {changed_count}/{len(all_metrics)}")
    print(f"最大单日跳变: 修复前 {old_worst:.2%} -> 修复后 {new_worst:.2%}")
    for repair in repairs:
        labels = ", ".join(repair.direct_keys)
        batch_changes = [metric["max_abs_change"] for metric in repair.curve_metrics]
        print(f"  {repair.infer_date}: direct=[{labels}], max_change={max(batch_changes):.2f}")


def write_report(
    backup_dir: Path,
    repairs: list[BatchRepair],
    send_results: list[dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "method": {
            "sync_strength": args.sync_strength,
            "slope_strength": args.slope_strength,
            "window": args.window,
            "decay_days": args.decay_days,
            "note": (
                "Imported points after the fully overwritten window were inverted. "
                "Domestic curves use the first correction-free point because sync rounding "
                "makes earlier inversion unstable. Overwritten points use PCHIP bridging."
            ),
        },
        "affected": [
            {"infer_date": repair.infer_date, "direct_keys": repair.direct_keys}
            for repair in repairs
        ],
        "curve_metrics": [
            metric for repair in repairs for metric in repair.curve_metrics
        ],
        "send_results": send_results,
    }
    atomic_write_json(backup_dir / "repair_report.json", report)


def main() -> int:
    args = parse_args()
    if args.send and not args.apply:
        raise SystemExit("--send 必须和 --apply 一起使用，避免发送未落库的数据")

    db_path = Path(args.db)
    json_dir = Path(args.json_dir)
    log_dir = Path(args.log_dir)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        affected = discover_affected(log_dir, json_dir, conn)
        if not affected:
            raise ValueError("没有找到同时存在于 latest 日志、JSON 和数据库的斜率校正记录")

        repairs = [
            repair_batch(
                conn,
                infer_date,
                direct_keys,
                json_dir / f"{infer_date}_data.json",
                args.sync_strength,
                args.slope_strength,
                args.window,
                args.decay_days,
            )
            for infer_date, direct_keys in sorted(affected.items())
        ]
        validate_db_matches_json(conn, repairs, use_repaired=False)
        print_summary(repairs)
        if not args.apply:
            print("DRY RUN 完成：未修改 JSON、数据库，也未发送。")
            return 0

        backup_dir = make_backup(conn, db_path, repairs, Path(args.backup_root))
        print(f"备份目录: {backup_dir}")

        for repair in repairs:
            atomic_write_json(repair.json_path, repair.repaired_payload)
        update_db(conn, repairs)
        validate_db_matches_json(conn, repairs, use_repaired=True)

        send_results: list[dict[str, Any]] = []
        if args.send:
            send_results = send_repairs(repairs, args.url, args.timeout)
        write_report(backup_dir, repairs, send_results, args)

        failed = [result for result in send_results if not result["ok"]]
        print(f"修复完成：JSON/数据库已更新，报告位于 {backup_dir / 'repair_report.json'}")
        if failed:
            print(f"发送失败批次: {[result['infer_date'] for result in failed]}", file=sys.stderr)
            return 2
        if args.send:
            print(f"发送完成：{len(send_results)}/{len(repairs)} 批成功")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
