import argparse
import csv
import os
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UnitPoint:
    plant: str
    unit_id: str
    unit_no: int
    day: date
    runtime_hours: float
    real_generation: float


def _try_parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    if s.isdigit() and len(s) == 8:
        try:
            return datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            return None
    if s.endswith(".0"):
        base = s[:-2]
        if base.isdigit() and len(base) == 8:
            try:
                return datetime.strptime(base, "%Y%m%d").date()
            except ValueError:
                return None
        try:
            as_int = int(float(s))
            as_str = str(as_int)
            if len(as_str) == 8:
                return datetime.strptime(as_str, "%Y%m%d").date()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _try_parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    lowered = s.lower()
    if lowered in {"nan", "none", "null"}:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _sqlite_uri_path(db_path: Path) -> str:
    return str(db_path.resolve()).replace("\\", "/")


def _connect_sqlite(db_path: Path, mode: str) -> sqlite3.Connection:
    uri = f"file:{_sqlite_uri_path(db_path)}?mode={mode}"
    return sqlite3.connect(uri, uri=True)


def _ensure_db_writable(db_path: Path, create_if_missing: bool = False) -> None:
    if not db_path.exists():
        if not create_if_missing:
            raise SystemExit(f"数据库不存在: {db_path}")
        parent = db_path.parent
        if not os.access(str(parent), os.W_OK):
            raise SystemExit(f"数据库所在目录不可写(无法创建数据库文件): {parent}")
        return

    parent = db_path.parent
    if not os.access(str(parent), os.W_OK):
        raise SystemExit(f"数据库所在目录不可写(无法创建journal/WAL文件): {parent}")

    if os.access(str(db_path), os.W_OK):
        return

    try:
        current_mode = db_path.stat().st_mode
        db_path.chmod(current_mode | 0o200)
    except Exception:
        pass

    if not os.access(str(db_path), os.W_OK):
        raise SystemExit(f"数据库文件不可写(可能是只读属性/权限/被占用): {db_path}")


def _open_csv_with_fallback_encodings(path: Path) -> tuple[Iterable[str], str]:
    last_error: Exception | None = None
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            f = path.open("r", newline="", encoding=enc)
            f.read(4096)
            f.seek(0)
            return f, enc
        except Exception as e:
            last_error = e
    raise RuntimeError(f"无法读取CSV文件: {path} ({last_error})")


def _pick_date_column(fieldnames: list[str], preferred: str | None) -> str:
    if preferred and preferred in fieldnames:
        return preferred
    candidates = [
        "date",
        "Date",
        "日期",
        "period_id",
        "periodId",
        "periodID",
        "period",
        "periodId".lower(),
    ]
    for c in candidates:
        if c in fieldnames:
            return c
    for name in fieldnames:
        lowered = name.lower()
        if "date" in lowered or "日期" in name or "period" in lowered:
            return name
    return fieldnames[0]


def _get_latest_rows(
    csv_path: Path,
    n: int,
    preferred_date_col: str | None,
) -> tuple[list[dict[str, str]], list[str], str, str, int]:
    f, enc = _open_csv_with_fallback_encodings(csv_path)
    with f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise RuntimeError(f"CSV缺少表头: {csv_path}")
        date_col = _pick_date_column(list(reader.fieldnames), preferred_date_col)
        rows: list[tuple[date, dict[str, str]]] = []
        scanned = 0
        for r in reader:
            scanned += 1
            d = _try_parse_date(r.get(date_col))
            if d is None:
                continue
            r["date"] = d.isoformat()
            rows.append((d, r))
        rows.sort(key=lambda x: x[0])
        latest = [r for _, r in rows[-n:]]
        return latest, list(reader.fieldnames), enc, date_col, scanned


def _extract_unit_points(plant: str, rows: list[dict[str, str]], columns: list[str]) -> list[UnitPoint]:
    runtime_cols = [c for c in columns if "运行小时" in c and "#" in c]
    points: list[UnitPoint] = []
    for runtime_col in runtime_cols:
        unit_no_match = None
        try:
            hash_idx = runtime_col.index("#")
            after_hash = runtime_col[hash_idx + 1 :]
            digits = []
            for ch in after_hash:
                if ch.isdigit():
                    digits.append(ch)
                else:
                    break
            if digits:
                unit_no_match = int("".join(digits))
        except Exception:
            unit_no_match = None
        if unit_no_match is None:
            continue
        unit_no = unit_no_match
        unit_id = f"unit{unit_no}"
        if runtime_col.endswith("_运行小时"):
            gen_col = runtime_col[: -len("_运行小时")] + "_发电量"
        else:
            gen_col = runtime_col.replace("运行小时", "发电量")
        if gen_col not in columns:
            gen_col = None
        for r in rows:
            d = _try_parse_date(r.get("date"))
            if d is None:
                continue
            runtime = _try_parse_float(r.get(runtime_col))
            if runtime is None:
                continue
            if runtime >= 24:
                continue
            gen = _try_parse_float(r.get(gen_col)) if gen_col else None
            if gen is None and runtime == 0:
                gen = 0.0
            if gen is None:
                continue
            points.append(
                UnitPoint(
                    plant=plant,
                    unit_id=unit_id,
                    unit_no=unit_no,
                    day=d,
                    runtime_hours=runtime,
                    real_generation=gen,
                )
            )
    return points


def _update_db_points(
    conn: sqlite3.Connection,
    points: list[UnitPoint],
    infer_date: str | None,
    dry_run: bool,
) -> tuple[int, int]:
    updated_rows = 0
    touched_points = 0
    cursor = conn.cursor()
    for p in points:
        touched_points += 1
        date_str = p.day.isoformat()
        data_types = (p.plant, f"{p.plant}_{p.unit_no}")
        if infer_date:
            sql = (
                "UPDATE prediction_data SET predict = ? "
                "WHERE pred_date = ? AND is_total = 0 AND unit_id = ? "
                "AND infer_date = ? AND data_type IN (?, ?)"
            )
            args = (p.real_generation, date_str, p.unit_id, infer_date, *data_types)
        else:
            sql = (
                "UPDATE prediction_data SET predict = ? "
                "WHERE pred_date = ? AND is_total = 0 AND unit_id = ? "
                "AND data_type IN (?, ?)"
            )
            args = (p.real_generation, date_str, p.unit_id, *data_types)
        if dry_run:
            cursor.execute(
                "SELECT COUNT(*) FROM prediction_data "
                "WHERE pred_date = ? AND is_total = 0 AND unit_id = ? "
                + ("AND infer_date = ? " if infer_date else "")
                + "AND data_type IN (?, ?)",
                (date_str, p.unit_id, infer_date, *data_types) if infer_date else (date_str, p.unit_id, *data_types),
            )
            count = cursor.fetchone()[0]
            updated_rows += int(count)
            continue
        cursor.execute(sql, args)
        updated_rows += cursor.rowcount
    return touched_points, updated_rows


def _ensure_override_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS prediction_override_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        data_type TEXT,
        infer_date DATE,
        pred_date DATE,
        unit_id TEXT,
        is_total BOOLEAN,
        override_predict REAL
    )
    ''')
    cursor.execute('''
    CREATE UNIQUE INDEX IF NOT EXISTS idx_prediction_override_unique
    ON prediction_override_data(data_type, infer_date, pred_date, unit_id, is_total)
    ''')
    cursor.execute('''
    CREATE UNIQUE INDEX IF NOT EXISTS idx_prediction_override_global
    ON prediction_override_data(data_type, pred_date, unit_id, is_total)
    WHERE infer_date IS NULL
    ''')
    cursor.execute('''
    CREATE UNIQUE INDEX IF NOT EXISTS idx_prediction_override_infer
    ON prediction_override_data(data_type, infer_date, pred_date, unit_id, is_total)
    WHERE infer_date IS NOT NULL
    ''')


def _resolve_infer_date_for_point(
    cursor: sqlite3.Cursor,
    p: UnitPoint,
    infer_date: str | None,
) -> str | None:
    if infer_date:
        return infer_date
    date_str = p.day.isoformat()
    data_types = (p.plant, f"{p.plant}_{p.unit_no}")
    cursor.execute(
        "SELECT MAX(infer_date) FROM prediction_data "
        "WHERE pred_date = ? AND is_total = 0 AND unit_id = ? AND data_type IN (?, ?)",
        (date_str, p.unit_id, *data_types),
    )
    row = cursor.fetchone()
    return row[0] if row and row[0] else None


def _upsert_override_points(
    override_conn: sqlite3.Connection,
    base_conn: sqlite3.Connection,
    points: list[UnitPoint],
    infer_date: str | None,
    override_scope: str,
    dry_run: bool,
) -> tuple[int, int]:
    touched_points = 0
    affected_rows = 0
    base_cursor = base_conn.cursor()
    override_cursor = override_conn.cursor()

    if not dry_run:
        _ensure_override_schema(override_conn)

    now_str = datetime.now().isoformat(timespec="seconds")
    for p in points:
        touched_points += 1
        date_str = p.day.isoformat()
        data_types = (p.plant, f"{p.plant}_{p.unit_no}")
        target_infer = None
        if override_scope == "infer":
            target_infer = _resolve_infer_date_for_point(base_cursor, p, infer_date)
            if not target_infer:
                continue
            base_cursor.execute(
                "SELECT COUNT(*) FROM prediction_data "
                "WHERE pred_date = ? AND is_total = 0 AND unit_id = ? "
                "AND infer_date = ? AND data_type IN (?, ?)",
                (date_str, p.unit_id, target_infer, *data_types),
            )
        else:
            base_cursor.execute(
                "SELECT COUNT(*) FROM prediction_data "
                "WHERE pred_date = ? AND is_total = 0 AND unit_id = ? "
                "AND data_type IN (?, ?)",
                (date_str, p.unit_id, *data_types),
            )
        if base_cursor.fetchone()[0] <= 0:
            continue

        affected_rows += 1
        if dry_run:
            continue

        if override_scope == "infer":
            override_cursor.execute(
                '''
                INSERT INTO prediction_override_data(
                    created_at, data_type, infer_date, pred_date, unit_id, is_total, override_predict
                )
                VALUES (?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(data_type, infer_date, pred_date, unit_id, is_total)
                DO UPDATE SET
                    created_at = excluded.created_at,
                    override_predict = excluded.override_predict
                ''',
                (now_str, p.plant, target_infer, date_str, p.unit_id, p.real_generation),
            )
        else:
            override_cursor.execute(
                '''
                INSERT INTO prediction_override_data(
                    created_at, data_type, infer_date, pred_date, unit_id, is_total, override_predict
                )
                VALUES (?, ?, NULL, ?, ?, 0, ?)
                ON CONFLICT(data_type, pred_date, unit_id, is_total) WHERE infer_date IS NULL
                DO UPDATE SET
                    created_at = excluded.created_at,
                    override_predict = excluded.override_predict
                ''',
                (now_str, p.plant, date_str, p.unit_id, p.real_generation),
            )

    return touched_points, affected_rows


def _print_hit_points(points: list[UnitPoint], max_show: int) -> None:
    points_sorted = sorted(points, key=lambda p: (p.plant, p.unit_no, p.day))
    total = len(points_sorted)
    to_show = points_sorted[:max_show] if max_show > 0 else points_sorted
    print(f"[命中明细] 共{total}条，展示{len(to_show)}条")
    for p in to_show:
        print(
            f"[命中] plant={p.plant} unit={p.unit_id} date={p.day.isoformat()} "
            f"runtime_hours={p.runtime_hours:g} real_generation={p.real_generation:g}"
        )
    if max_show > 0 and total > max_show:
        print(f"[命中明细] 仅展示前{max_show}条，其余{total - max_show}条已省略")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("n", type=int)
    parser.add_argument("--infer-date", dest="infer_date", default=None)
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--db", dest="db_path", default=None)
    parser.add_argument("--override-db", dest="override_db_path", default=None)
    parser.add_argument("--csv-dir", dest="csv_dir", default=None)
    parser.add_argument("--date-col", dest="date_col", default=None)
    parser.add_argument("--max-show", dest="max_show", type=int, default=200)
    parser.add_argument("--write-mode", dest="write_mode", choices=["override", "update"], default="override")
    parser.add_argument("--override-scope", dest="override_scope", choices=["global", "infer"], default="global")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    csv_dir = Path(args.csv_dir).resolve() if args.csv_dir else (repo_root / "dataset-huodian")
    db_path = Path(args.db_path).resolve() if args.db_path else (repo_root / "autoinfer" / "elec_prediction.db")
    override_db_path = (
        Path(args.override_db_path).resolve()
        if args.override_db_path
        else (repo_root / "autoinfer" / "elec_prediction_override.db")
    )

    if args.n <= 0:
        raise SystemExit("n 必须是正整数")
    if not db_path.exists():
        raise SystemExit(f"数据库不存在: {db_path}")

    plants = ["kemen", "shaowu", "yongan", "zhangping"]

    all_points: list[UnitPoint] = []
    for plant in plants:
        csv_path = csv_dir / f"{plant}.csv"
        if not csv_path.exists():
            print(f"[跳过] 缺少CSV: {csv_path}")
            continue
        rows, columns, enc, date_col, scanned = _get_latest_rows(csv_path, args.n, args.date_col)
        points = _extract_unit_points(plant, rows, columns)
        all_points.extend(points)
        print(
            f"[读取] {plant}: {csv_path.name} 编码={enc} date_col={date_col} 扫描={scanned}行 "
            f"最新{len(rows)}天, 命中{len(points)}条(运行小时<24)"
        )

    if not all_points:
        print("未找到需要修正的机组记录(运行小时<24)")
        return 0

    _print_hit_points(all_points, args.max_show)

    base_conn = _connect_sqlite(db_path, "ro")
    try:
        cur = base_conn.cursor()
        cur.execute("SELECT MIN(pred_date), MAX(pred_date) FROM prediction_data")
        db_min_date, db_max_date = cur.fetchone()
        min_point_day = min(p.day for p in all_points).isoformat()
        max_point_day = max(p.day for p in all_points).isoformat()
        print(f"[日期] CSV点位范围: {min_point_day} ~ {max_point_day}")
        print(f"[日期] DB预测范围: {db_min_date} ~ {db_max_date}")

        db_min = _try_parse_date(db_min_date) if isinstance(db_min_date, str) else None
        db_max = _try_parse_date(db_max_date) if isinstance(db_max_date, str) else None
        min_pt = min(p.day for p in all_points)
        max_pt = max(p.day for p in all_points)
        if db_min and db_max and (max_pt < db_min or min_pt > db_max):
            print("[跳过] CSV命中日期与数据库pred_date范围不重叠，本次无需写库")
            return 0

        if args.write_mode == "override":
            if not args.dry_run:
                _ensure_db_writable(override_db_path, create_if_missing=True)
            override_conn = _connect_sqlite(override_db_path, "ro" if args.dry_run else "rwc")
            try:
                override_conn.execute("BEGIN")
                touched, updated = _upsert_override_points(
                    override_conn, base_conn, all_points, args.infer_date, args.override_scope, args.dry_run
                )
                if args.dry_run:
                    override_conn.rollback()
                    print(f"[干跑] 写入模式=override scope={args.override_scope}, 命中点位={touched}, 将写入覆盖行数={updated} (未写入数据库)")
                else:
                    override_conn.commit()
                    print(f"[完成] 写入模式=override scope={args.override_scope}, 命中点位={touched}, 已写入覆盖行数={updated}")
                print(f"[覆盖库] {override_db_path}")
            except Exception:
                override_conn.rollback()
                raise
            finally:
                override_conn.close()
        else:
            if not args.dry_run:
                _ensure_db_writable(db_path)
            write_conn = _connect_sqlite(db_path, "ro" if args.dry_run else "rw")
            try:
                write_conn.execute("BEGIN")
                touched, updated = _update_db_points(write_conn, all_points, args.infer_date, args.dry_run)
                if args.dry_run:
                    write_conn.rollback()
                    print(f"[干跑] 写入模式=update, 命中点位={touched}, 将影响预测行数={updated} (未写入数据库)")
                else:
                    write_conn.commit()
                    print(f"[完成] 写入模式=update, 命中点位={touched}, 已更新预测行数={updated}")
            except Exception:
                write_conn.rollback()
                raise
            finally:
                write_conn.close()
    except Exception:
        raise
    finally:
        base_conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
