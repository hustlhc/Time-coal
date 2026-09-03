#!/usr/bin/env python3
"""Replay historical six-index coal forecasts with the active model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta

import chinese_calendar as cc
import numpy as np
import pandas as pd

os.environ.setdefault("MPLBACKEND", "Agg")

from smooth2 import smooth_and_anchor


COAL_TYPES = (
    "CCI4500infer",
    "CCI5000infer",
    "CCI5500infer",
    "CCI3800outinfer",
    "CCI4700outinfer",
    "CCI5500outinfer",
)

TYPE_SPECS = (
    ("CCI4500infer", -6, True),
    ("CCI5000infer", -5, True),
    ("CCI5500infer", -4, True),
    ("CCI3800outinfer", -3, False),
    ("CCI4700outinfer", -2, False),
    ("CCI5500outinfer", -1, False),
)

PROCESSING_VERSION = "full_savgol9_anchor_smoothed_first_v1"
DEFAULT_MODEL_ID = "Coal6_TimeMixerNoEasy_32_120_seq32_shortfirst"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--through-date", default="2026-07-24")
    parser.add_argument("--start-date")
    parser.add_argument(
        "--dates",
        nargs="+",
        help="explicit inference dates to replay, including dates absent from the database",
    )
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--seq-len", type=int, default=32)
    parser.add_argument("--dataset", default="dataset/pre_coal/coal_new.csv")
    parser.add_argument("--database", default="autoinfer/coal_prediction.db")
    parser.add_argument("--json-dir", default="autoinfer/json")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--gpu-type", default="cuda")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir")
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_path(repo: Path, model_id: str, seq_len: int) -> Path:
    setting = (
        "long_term_forecast_"
        f"{model_id}_TimeMixer_coal_ftM_sl{seq_len}_ll{seq_len // 2}_pl120_"
        "dm64_nh8_el4_dl1_df32_expand2_dc4_fc1_ebtimeF_dtTrue_Sync6_0"
    )
    return repo / "checkpoints" / setting / "checkpoint.pth"


def replay_dates(
    database: Path, through_date: str, start_date: str | None
) -> list[str]:
    placeholders = ",".join("?" for _ in COAL_TYPES)
    sql = f"""
        SELECT infer_date
        FROM prediction_data
        WHERE infer_date <= ?
          AND data_type IN ({placeholders})
          AND (? IS NULL OR infer_date >= ?)
        GROUP BY infer_date
        HAVING COUNT(DISTINCT data_type) = ?
        ORDER BY infer_date
    """
    params = (through_date, *COAL_TYPES, start_date, start_date, len(COAL_TYPES))
    with sqlite3.connect(database) as conn:
        return [row[0] for row in conn.execute(sql, params)]


def get_next_workdays(start_date: date, count: int) -> list[date]:
    result: list[date] = []
    current = start_date
    while len(result) < count:
        is_workday = (
            cc.is_workday(current)
            if 2004 <= current.year <= 2026
            else current.weekday() < 5
        )
        if is_workday:
            result.append(current)
        current += timedelta(days=1)
    return result


def smooth2_values(
    prediction: np.ndarray, real_values: np.ndarray, do_round: bool
) -> np.ndarray:
    result = smooth_and_anchor(prediction, real_values[-1], method="savgol")
    if do_round:
        result = np.rint(result)
    return result


def valid_stage(path: Path, model_id: str, checkpoint_hash: str) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if payload.get("modelId") != model_id:
        return False
    if payload.get("checkpointSha256") != checkpoint_hash:
        return False
    if payload.get("processingVersion") != PROCESSING_VERSION:
        return False
    data = payload.get("data", {})
    return all(
        len(data.get(data_type, [])) == 120
        and all(np.isfinite(item.get("predict", np.nan)) for item in data[data_type])
        for data_type in COAL_TYPES
    )


def run_one(
    repo: Path,
    infer_date: str,
    base_data: pd.DataFrame,
    date_values: pd.Series,
    work_dir: Path,
    args: argparse.Namespace,
    checkpoint_hash: str,
) -> Path:
    stage_path = work_dir / "staged" / f"{infer_date}.json"
    if args.resume and valid_stage(stage_path, args.model_id, checkpoint_hash):
        print(f"[skip] {infer_date} already staged", flush=True)
        return stage_path

    cutoff = pd.Timestamp(infer_date)
    asof_data = base_data.loc[date_values < cutoff].copy()
    if len(asof_data) < args.seq_len:
        raise RuntimeError(f"{infer_date}: only {len(asof_data)} source rows")
    if asof_data.iloc[:, -6:].isna().any().any():
        raise RuntimeError(f"{infer_date}: target columns contain missing values")

    input_dir = work_dir / "input"
    output_dir = work_dir / "output"
    log_dir = work_dir / "logs"
    input_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    input_path = input_dir / "coal_new.csv"
    asof_data.to_csv(input_path, index=False)

    env = os.environ.copy()
    env.update(
        {
            "PYTHON_BIN": args.python_bin,
            "DATA_ROOT": f"{input_dir}/",
            "DATA_PATH": input_path.name,
            "FEATURE_COUNT": str(base_data.shape[1] - 1),
            "MODEL_ID": args.model_id,
            "SEQ_LEN": str(args.seq_len),
            "PRED_LEN": "120",
            "RUN_TRAIN": "0",
            "RUN_INFER": "1",
            "RUN_TENINFER": "0",
            "AUTOINFER_FOLDER": str(output_dir),
            "TENINFER_FOLDER": str(work_dir / "teninfer"),
            "TESTRESULT_FOLDER": str(work_dir / "testresult"),
            "SMOOTH_OUTPUTS": "0",
            "SYNC_INFER_TARGETS": "0",
            "POST_SYNC_FORECASTS": "0",
            "USE_SHORT_SLOPE_CORRECTION": "0",
            "USE_LEVEL_DELTA_CORRECTION": "0",
            "USE_ACC_LOSS": "1",
            "ACC_LOSS_WEIGHT": "0.2",
            "USE_SHORT_TREND_LOSS": "1",
            "SHORT_TREND_LOSS_WEIGHT": "0.6",
            "SHORT_TREND_MONTH_WEIGHTS": "0.8,0.15,0.05",
            "SYNC_LOSS_WEIGHT": "0.06",
            "GPU_TYPE": args.gpu_type,
            "MPLBACKEND": "Agg",
        }
    )
    completed = subprocess.run(
        ["bash", "scripts/long_term_forecast/autocoal_sync/run_joint.sh"],
        cwd=repo,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log_path = log_dir / f"{infer_date}.log"
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        tail = "\n".join(completed.stdout.splitlines()[-30:])
        raise RuntimeError(f"{infer_date}: inference failed\n{tail}")

    future_dates = get_next_workdays(datetime.strptime(infer_date, "%Y-%m-%d").date(), 120)
    result: dict[str, list[dict[str, object]]] = {}
    for data_type, true_col, do_round in TYPE_SPECS:
        values = (
            pd.read_csv(output_dir / f"{data_type}.csv", header=None)
            .iloc[:, 0]
            .astype(float)
            .to_numpy()
        )
        if len(values) != 120 or not np.isfinite(values).all():
            raise RuntimeError(f"{infer_date}: invalid raw output for {data_type}")
        real_values = asof_data.iloc[:, true_col].astype(float).to_numpy()
        values = smooth2_values(values, real_values, do_round)
        result[data_type] = [
            {"date": str(pred_date), "predict": float(value)}
            for pred_date, value in zip(future_dates, values)
        ]

    payload = {
        "inferDate": infer_date,
        "sourceLastDate": str(asof_data.iloc[-1, 0]),
        "modelId": args.model_id,
        "checkpointSha256": checkpoint_hash,
        "processingVersion": PROCESSING_VERSION,
        "data": result,
    }
    stage_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = stage_path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temp_path, stage_path)
    print(
        f"[done] {infer_date} source={payload['sourceLastDate']} "
        f"first={[round(result[key][0]['predict'], 2) for key in COAL_TYPES]}",
        flush=True,
    )
    return stage_path


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)


def prepare_updated_json(
    dates: list[str], stage_dir: Path, source_dir: Path, output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for infer_date in dates:
        source_path = source_dir / f"{infer_date}_data.json"
        if source_path.exists():
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        else:
            payload = {"inferDate": infer_date, "data": {}}
        staged = json.loads(
            (stage_dir / f"{infer_date}.json").read_text(encoding="utf-8")
        )
        for data_type in COAL_TYPES:
            payload["data"][data_type] = staged["data"][data_type]
        target_path = output_dir / source_path.name
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=4), encoding="utf-8"
        )


def prepare_updated_database(
    source_db: Path, output_db: Path, dates: list[str], stage_dir: Path
) -> int:
    if output_db.exists():
        output_db.unlink()
    sqlite_backup(source_db, output_db)
    date_placeholders = ",".join("?" for _ in dates)
    type_placeholders = ",".join("?" for _ in COAL_TYPES)
    inserted = 0
    with sqlite3.connect(output_db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"""
            DELETE FROM prediction_data
            WHERE infer_date IN ({date_placeholders})
              AND data_type IN ({type_placeholders})
            """,
            (*dates, *COAL_TYPES),
        )
        rows: list[tuple[str, str, str, float]] = []
        for infer_date in dates:
            staged = json.loads(
                (stage_dir / f"{infer_date}.json").read_text(encoding="utf-8")
            )
            for data_type in COAL_TYPES:
                rows.extend(
                    (
                        infer_date,
                        data_type,
                        item["date"],
                        float(item["predict"]),
                    )
                    for item in staged["data"][data_type]
                )
        conn.executemany(
            """
            INSERT INTO prediction_data (infer_date, data_type, pred_date, predict)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        inserted = len(rows)
        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"new database integrity check failed: {integrity}")
    return inserted


def apply_results(
    repo: Path,
    dates: list[str],
    work_dir: Path,
    database: Path,
    json_dir: Path,
    backup_dir: Path,
    model_id: str,
    checkpoint_hash: str,
) -> None:
    if backup_dir.exists():
        raise FileExistsError(f"backup directory already exists: {backup_dir}")
    backup_json = backup_dir / "json"
    backup_json.mkdir(parents=True)
    sqlite_backup(database, backup_dir / database.name)
    missing_json_before: list[str] = []
    for infer_date in dates:
        source_json = json_dir / f"{infer_date}_data.json"
        if source_json.exists():
            shutil.copy2(source_json, backup_json / source_json.name)
        else:
            missing_json_before.append(infer_date)
    (backup_dir / "manifest.json").write_text(
        json.dumps(
            {
                "createdAt": datetime.now().isoformat(timespec="seconds"),
                "modelId": model_id,
                "checkpointSha256": checkpoint_hash,
                "processingVersion": PROCESSING_VERSION,
                "dates": dates,
                "coalTypes": COAL_TYPES,
                "missingJsonBefore": missing_json_before,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    prepared_json = work_dir / "updated_json"
    if prepared_json.exists():
        shutil.rmtree(prepared_json)
    prepare_updated_json(dates, work_dir / "staged", json_dir, prepared_json)

    prepared_db = work_dir / "coal_prediction.updated.db"
    inserted = prepare_updated_database(
        database, prepared_db, dates, work_dir / "staged"
    )
    os.replace(prepared_db, database)
    for infer_date in dates:
        os.replace(
            prepared_json / f"{infer_date}_data.json",
            json_dir / f"{infer_date}_data.json",
        )
    print(
        f"[apply] replaced {inserted} coal prediction rows; backup={backup_dir}",
        flush=True,
    )


def main() -> None:
    args = parse_args()
    repo = Path(__file__).resolve().parents[1]
    dataset = (repo / args.dataset).resolve()
    database = (repo / args.database).resolve()
    json_dir = (repo / args.json_dir).resolve()
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = checkpoint_path(repo, args.model_id, args.seq_len)
    if not checkpoint.is_file():
        raise FileNotFoundError(f"checkpoint not found: {checkpoint}")
    checkpoint_hash = file_sha256(checkpoint)
    if args.dates:
        dates = sorted(dict.fromkeys(args.dates))
        for infer_date in dates:
            datetime.strptime(infer_date, "%Y-%m-%d")
    else:
        dates = replay_dates(database, args.through_date, args.start_date)
    if args.limit is not None:
        dates = dates[: args.limit]
    if not dates:
        raise RuntimeError("no replay dates selected")

    base_data = pd.read_csv(dataset)
    date_values = pd.to_datetime(base_data.iloc[:, 0], errors="raise")
    print(
        f"[start] dates={len(dates)} range={dates[0]}..{dates[-1]} "
        f"model={args.model_id} seq_len={args.seq_len} checkpoint={checkpoint_hash}",
        flush=True,
    )
    for index, infer_date in enumerate(dates, start=1):
        print(f"[{index}/{len(dates)}] {infer_date}", flush=True)
        run_one(
            repo,
            infer_date,
            base_data,
            date_values,
            work_dir,
            args,
            checkpoint_hash,
        )

    if args.apply:
        if args.limit is not None:
            raise RuntimeError("--apply cannot be combined with --limit")
        backup_dir = (
            Path(args.backup_dir).resolve()
            if args.backup_dir
            else repo
            / "autoinfer"
            / "backups"
            / f"coal_history_before_replay_{datetime.now():%Y%m%d_%H%M%S}"
        )
        apply_results(
            repo,
            dates,
            work_dir,
            database,
            json_dir,
            backup_dir,
            args.model_id,
            checkpoint_hash,
        )
    else:
        print("[stage-only] production database and JSON were not changed", flush=True)


if __name__ == "__main__":
    main()
