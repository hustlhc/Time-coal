#!/usr/bin/env python3
"""Repair legacy freight forecasts whose first point bypassed smoothing.

The old freight pipeline saved the raw model value at index 0 after applying
a 9-point, order-2 Savitzky-Golay filter to the rest of the curve. For that
filter, the missing smoothed boundary value can be recovered exactly from the
next four stored smoothed values:

    y0 = 2.25*y1 - 0.75*y2 - 1.25*y3 + 0.75*y4

Only the first prediction in each inference batch is changed. The script also
keeps the historical JSON files and the latest inference CSV files in sync.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


FREIGHT_TYPES = ("insideinfer", "outsideinfer")
TOLERANCE = 1e-9


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Repair the first point of all legacy freight forecasts."
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
        "--qwen-freight-json",
        type=Path,
        default=project_root / "Qwen" / "data" / "freight_rates.json",
    )
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=project_root / "autoinfer" / "backups",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def corrected_first(values: list[float]) -> float:
    if len(values) < 5:
        raise ValueError("A forecast needs at least five points for first-point repair")
    return (
        2.25 * values[1]
        - 0.75 * values[2]
        - 1.25 * values[3]
        + 0.75 * values[4]
    )


def load_db_batches(
    conn: sqlite3.Connection,
) -> dict[tuple[str, str], list[tuple[int, str, float]]]:
    placeholders = ",".join("?" for _ in FREIGHT_TYPES)
    rows = conn.execute(
        f"""
        SELECT id, infer_date, data_type, pred_date, predict
        FROM prediction_data
        WHERE data_type IN ({placeholders})
        ORDER BY data_type, infer_date, pred_date
        """,
        FREIGHT_TYPES,
    ).fetchall()

    batches: dict[tuple[str, str], list[tuple[int, str, float]]] = defaultdict(list)
    for row_id, infer_date, data_type, pred_date, predict in rows:
        batches[(str(data_type), str(infer_date))].append(
            (int(row_id), str(pred_date), float(predict))
        )
    return dict(batches)


def build_db_updates(
    batches: dict[tuple[str, str], list[tuple[int, str, float]]],
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for (data_type, infer_date), rows in sorted(batches.items()):
        values = [row[2] for row in rows]
        new_value = corrected_first(values)
        old_value = values[0]
        if abs(new_value - old_value) <= TOLERANCE:
            continue
        updates.append(
            {
                "id": rows[0][0],
                "data_type": data_type,
                "infer_date": infer_date,
                "pred_date": rows[0][1],
                "old": old_value,
                "new": new_value,
                "second": values[1],
                "gap_before": abs(old_value - values[1]),
                "gap_after": abs(new_value - values[1]),
                "points": len(values),
            }
        )
    return updates


def create_backup(
    conn: sqlite3.Connection,
    args: argparse.Namespace,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = args.backup_root / f"freight_first_point_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    backup_conn = sqlite3.connect(backup_dir / "coal_prediction.db")
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()

    if args.json_dir.exists():
        shutil.copytree(args.json_dir, backup_dir / "json")

    for data_type in FREIGHT_TYPES:
        source = args.csv_dir / f"{data_type}.csv"
        if source.exists():
            shutil.copy2(source, backup_dir / source.name)

    if args.qwen_freight_json.exists():
        target = backup_dir / "Qwen" / "data" / args.qwen_freight_json.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.qwen_freight_json, target)

    export_path = backup_dir / "freight_predictions_before.csv"
    with export_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["id", "infer_date", "data_type", "pred_date", "predict"]
        )
        placeholders = ",".join("?" for _ in FREIGHT_TYPES)
        writer.writerows(
            conn.execute(
                f"""
                SELECT id, infer_date, data_type, pred_date, predict
                FROM prediction_data
                WHERE data_type IN ({placeholders})
                ORDER BY data_type, infer_date, pred_date
                """,
                FREIGHT_TYPES,
            )
        )
    return backup_dir


def update_database(
    conn: sqlite3.Connection,
    updates: list[dict[str, Any]],
) -> None:
    with conn:
        conn.executemany(
            "UPDATE prediction_data SET predict = ? WHERE id = ?",
            [(item["new"], item["id"]) for item in updates],
        )


def update_history_json(json_dir: Path) -> tuple[int, int]:
    files_changed = 0
    values_changed = 0
    for path in sorted(json_dir.glob("*_data.json")):
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        changed = False
        data = payload.get("data", {})
        for data_type in FREIGHT_TYPES:
            records = data.get(data_type)
            if not isinstance(records, list) or len(records) < 5:
                continue
            values = [float(record["predict"]) for record in records]
            new_value = corrected_first(values)
            if abs(new_value - values[0]) <= TOLERANCE:
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


def update_latest_csv(csv_dir: Path) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for data_type in FREIGHT_TYPES:
        path = csv_dir / f"{data_type}.csv"
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))
        values = [float(row[0]) for row in rows if row]
        new_value = corrected_first(values)
        old_value = values[0]
        if abs(new_value - old_value) <= TOLERANCE:
            continue

        rows[0][0] = repr(new_value)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(rows)
        temp_path.replace(path)
        updates.append(
            {"data_type": data_type, "old": old_value, "new": new_value}
        )
    return updates


def update_qwen_json(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    changed = 0
    for data_type in FREIGHT_TYPES:
        values = payload.get(data_type)
        if not isinstance(values, list) or len(values) < 5:
            continue
        numeric = [float(value) for value in values]
        new_value = corrected_first(numeric)
        if abs(new_value - numeric[0]) <= TOLERANCE:
            continue
        values[0] = new_value
        changed += 1

    if changed:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temp_path.replace(path)
    return changed


def verify_database(
    conn: sqlite3.Connection,
    expected_batches: int,
) -> dict[str, Any]:
    batches = load_db_batches(conn)
    remaining = build_db_updates(batches)
    row_count = sum(len(rows) for rows in batches.values())
    if len(batches) != expected_batches:
        raise RuntimeError(
            f"Batch count changed unexpectedly: {expected_batches} -> {len(batches)}"
        )
    if remaining:
        raise RuntimeError(f"{len(remaining)} freight first points remain unrepaired")
    return {
        "batches": len(batches),
        "rows": row_count,
        "remaining_unrepaired": len(remaining),
    }


def main() -> None:
    args = parse_args()
    conn = sqlite3.connect(args.db)
    try:
        batches = load_db_batches(conn)
        updates = build_db_updates(batches)
        summary = {
            "dry_run": args.dry_run,
            "database": str(args.db),
            "batches_checked": len(batches),
            "rows_checked": sum(len(rows) for rows in batches.values()),
            "database_first_points_to_change": len(updates),
            "by_type": {
                data_type: sum(
                    item["data_type"] == data_type for item in updates
                )
                for data_type in FREIGHT_TYPES
            },
            "changes": updates,
        }
        if args.dry_run:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        backup_dir = create_backup(conn, args)
        update_database(conn, updates)
        json_files_changed, json_values_changed = update_history_json(args.json_dir)
        csv_updates = update_latest_csv(args.csv_dir)
        qwen_values_changed = update_qwen_json(args.qwen_freight_json)
        verification = verify_database(conn, len(batches))

        summary.update(
            {
                "backup_dir": str(backup_dir),
                "history_json_files_changed": json_files_changed,
                "history_json_values_changed": json_values_changed,
                "latest_csv_updates": csv_updates,
                "qwen_values_changed": qwen_values_changed,
                "verification": verification,
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
