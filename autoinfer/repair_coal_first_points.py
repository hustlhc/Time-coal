#!/usr/bin/env python3
"""Repair legacy coal forecasts whose first point bypassed smoothing."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


COAL_TYPES = {
    "CCI4500infer": True,
    "CCI5000infer": True,
    "CCI5500infer": True,
    "CCI3800outinfer": False,
    "CCI4700outinfer": False,
    "CCI5500outinfer": False,
}
TOLERANCE = 1e-9
ROUNDED_ERROR_BOUND = 3.0


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Repair first points in all legacy coal forecast batches."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=project_root / "autoinfer" / "coal_prediction.db",
    )
    parser.add_argument(
        "--json-dir",
        type=Path,
        default=project_root / "autoinfer" / "json",
    )
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=project_root / "autoinfer",
    )
    parser.add_argument(
        "--qwen-coal-json",
        type=Path,
        default=project_root / "Qwen" / "data" / "coal_prices.json",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=project_root / "autoinfer" / "backups",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def is_integer_context(values: list[float]) -> bool:
    return all(abs(value - round(value)) <= TOLERANCE for value in values[1:5])


def recover_first(values: list[float], domestic: bool) -> tuple[float, bool]:
    if len(values) < 5:
        raise ValueError("A forecast needs at least five points")
    recovered = (
        2.25 * values[1]
        - 0.75 * values[2]
        - 1.25 * values[3]
        + 0.75 * values[4]
    )
    rounded_context = domestic and is_integer_context(values)
    if rounded_context:
        recovered = float(round(recovered))
    return recovered, rounded_context


def should_repair(
    old_value: float,
    recovered: float,
    domestic: bool,
    rounded_context: bool,
) -> bool:
    difference = abs(recovered - old_value)
    if domestic and rounded_context:
        # Four rounded inputs can move the reconstructed boundary by up to
        # about 2.5 units. Only values beyond that bound prove that the old
        # raw first point was preserved.
        return difference > ROUNDED_ERROR_BOUND + TOLERANCE
    return difference > TOLERANCE


def load_json_payloads(json_dir: Path) -> dict[Path, dict[str, Any]]:
    payloads: dict[Path, dict[str, Any]] = {}
    for path in sorted(json_dir.glob("*_data.json")):
        with path.open("r", encoding="utf-8") as handle:
            payloads[path] = json.load(handle)
    return payloads


def build_repairs(
    payloads: dict[Path, dict[str, Any]],
) -> tuple[dict[tuple[str, str, str], float], list[dict[str, Any]]]:
    repaired_values: dict[tuple[str, str, str], float] = {}
    details: list[dict[str, Any]] = []
    for path, payload in payloads.items():
        infer_date = str(payload.get("inferDate"))
        data = payload.get("data", {})
        for data_type, domestic in COAL_TYPES.items():
            records = data.get(data_type)
            if not isinstance(records, list) or len(records) < 5:
                continue
            values = [float(record["predict"]) for record in records]
            recovered, rounded_context = recover_first(values, domestic)
            if not should_repair(
                values[0], recovered, domestic, rounded_context
            ):
                continue
            pred_date = str(records[0]["date"])
            repaired_values[(data_type, infer_date, pred_date)] = recovered
            details.append(
                {
                    "source": path.name,
                    "data_type": data_type,
                    "infer_date": infer_date,
                    "pred_date": pred_date,
                    "old": values[0],
                    "new": recovered,
                    "second": values[1],
                    "rounded_context": rounded_context,
                    "gap_before": abs(values[0] - values[1]),
                    "gap_after": abs(recovered - values[1]),
                }
            )
    return repaired_values, details


def create_backup(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = args.backup_root / f"coal_first_point_history_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    backup_conn = sqlite3.connect(backup_dir / "coal_prediction.db")
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()

    shutil.copytree(args.json_dir, backup_dir / "json")
    for data_type in COAL_TYPES:
        source = args.csv_dir / f"{data_type}.csv"
        if source.exists():
            shutil.copy2(source, backup_dir / source.name)
    if args.qwen_coal_json.exists():
        target = backup_dir / "Qwen" / "data" / args.qwen_coal_json.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.qwen_coal_json, target)

    with (backup_dir / "coal_predictions_before.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "infer_date", "data_type", "pred_date", "predict"])
        placeholders = ",".join("?" for _ in COAL_TYPES)
        writer.writerows(
            conn.execute(
                f"""
                SELECT id, infer_date, data_type, pred_date, predict
                FROM prediction_data
                WHERE data_type IN ({placeholders})
                ORDER BY data_type, infer_date, pred_date
                """,
                tuple(COAL_TYPES),
            )
        )
    return backup_dir


def update_database(
    conn: sqlite3.Connection,
    repaired_values: dict[tuple[str, str, str], float],
) -> int:
    updates: list[tuple[float, str, str, str]] = []
    for (data_type, infer_date, pred_date), value in repaired_values.items():
        row = conn.execute(
            """
            SELECT predict
            FROM prediction_data
            WHERE data_type = ? AND infer_date = ? AND pred_date = ?
            """,
            (data_type, infer_date, pred_date),
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"Missing database row: {data_type} {infer_date} {pred_date}"
            )
        if abs(float(row[0]) - value) > TOLERANCE:
            updates.append((value, data_type, infer_date, pred_date))

    with conn:
        conn.executemany(
            """
            UPDATE prediction_data
            SET predict = ?
            WHERE data_type = ? AND infer_date = ? AND pred_date = ?
            """,
            updates,
        )
    return len(updates)


def update_json_payloads(
    payloads: dict[Path, dict[str, Any]],
    repaired_values: dict[tuple[str, str, str], float],
) -> tuple[int, int]:
    files_changed = 0
    values_changed = 0
    for path, payload in payloads.items():
        infer_date = str(payload.get("inferDate"))
        changed = False
        for data_type in COAL_TYPES:
            records = payload.get("data", {}).get(data_type, [])
            if not records:
                continue
            key = (data_type, infer_date, str(records[0]["date"]))
            new_value = repaired_values.get(key)
            if new_value is None:
                continue
            if abs(float(records[0]["predict"]) - new_value) <= TOLERANCE:
                continue
            records[0]["predict"] = new_value
            values_changed += 1
            changed = True
        if changed:
            temp_path = path.with_suffix(path.suffix + ".tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=4)
                handle.write("\n")
            temp_path.replace(path)
            files_changed += 1
    return files_changed, values_changed


def latest_curves(
    conn: sqlite3.Connection,
) -> tuple[str, dict[str, list[float]]]:
    latest = conn.execute(
        f"""
        SELECT MAX(infer_date)
        FROM prediction_data
        WHERE data_type IN ({','.join('?' for _ in COAL_TYPES)})
        """,
        tuple(COAL_TYPES),
    ).fetchone()[0]
    curves: dict[str, list[float]] = {}
    for data_type in COAL_TYPES:
        curves[data_type] = [
            float(row[0])
            for row in conn.execute(
                """
                SELECT predict
                FROM prediction_data
                WHERE infer_date = ? AND data_type = ?
                ORDER BY pred_date
                """,
                (latest, data_type),
            )
        ]
    return str(latest), curves


def write_single_column(path: Path, values: list[float]) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows((repr(value),) for value in values)
    temp_path.replace(path)


def sync_latest_files(
    conn: sqlite3.Connection,
    csv_dir: Path,
    qwen_path: Path,
) -> str:
    latest, curves = latest_curves(conn)
    for data_type, values in curves.items():
        write_single_column(csv_dir / f"{data_type}.csv", values)

    if qwen_path.exists():
        with qwen_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        for data_type, values in curves.items():
            payload[data_type] = values
        temp_path = qwen_path.with_suffix(qwen_path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temp_path.replace(qwen_path)
    return latest


def count_json_db_mismatches(
    conn: sqlite3.Connection,
    payloads: dict[Path, dict[str, Any]],
) -> int:
    mismatches = 0
    for payload in payloads.values():
        infer_date = str(payload.get("inferDate"))
        for data_type in COAL_TYPES:
            for record in payload.get("data", {}).get(data_type, []):
                row = conn.execute(
                    """
                    SELECT predict
                    FROM prediction_data
                    WHERE infer_date = ? AND data_type = ? AND pred_date = ?
                    """,
                    (infer_date, data_type, str(record["date"])),
                ).fetchone()
                if row is None or abs(float(row[0]) - float(record["predict"])) > TOLERANCE:
                    mismatches += 1
    return mismatches


def main() -> None:
    args = parse_args()
    conn = sqlite3.connect(args.db)
    try:
        payloads = load_json_payloads(args.json_dir)
        repaired_values, details = build_repairs(payloads)
        summary: dict[str, Any] = {
            "dry_run": args.dry_run,
            "curves_checked": len(payloads) * len(COAL_TYPES),
            "first_points_to_change": len(repaired_values),
            "by_type": {
                data_type: sum(
                    item["data_type"] == data_type for item in details
                )
                for data_type in COAL_TYPES
            },
            "changes": details,
        }
        if args.dry_run:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        backup_dir = create_backup(conn, args)
        database_changed = update_database(conn, repaired_values)
        json_files_changed, json_values_changed = update_json_payloads(
            payloads, repaired_values
        )
        latest = sync_latest_files(conn, args.csv_dir, args.qwen_coal_json)
        mismatches = count_json_db_mismatches(conn, payloads)
        if mismatches:
            raise RuntimeError(f"JSON and database have {mismatches} mismatches")

        summary.update(
            {
                "backup_dir": str(backup_dir),
                "database_values_changed": database_changed,
                "json_files_changed": json_files_changed,
                "json_values_changed": json_values_changed,
                "latest_infer_date": latest,
                "json_database_mismatches": mismatches,
            }
        )
        report_path = backup_dir / "repair_report.json"
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
