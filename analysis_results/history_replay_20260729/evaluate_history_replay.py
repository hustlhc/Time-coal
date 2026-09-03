#!/usr/bin/env python3
"""Compare replayed coal forecasts with the pre-replay database."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


TARGETS = {
    "CCI4500infer": ("CCI4500", "domestic"),
    "CCI5000infer": ("CCI5000", "domestic"),
    "CCI5500infer": ("CCI5500", "domestic"),
    "CCI3800outinfer": ("CCI3800out", "import"),
    "CCI4700outinfer": ("CCI4700out", "import"),
    "CCI5500outinfer": ("CCI5500out", "import"),
}
START_DATE = "2025-10-21"
END_DATE = "2026-07-24"
RECENT_START = "2026-07-14"
KEYS = ["infer_date", "data_type", "pred_date"]


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--new-db", type=Path, default=repo_root / "autoinfer/coal_prediction.db"
    )
    parser.add_argument(
        "--old-db",
        type=Path,
        default=repo_root
        / "autoinfer/backups/coal_history_before_replay_20260729_110057"
        / "coal_prediction.db",
    )
    parser.add_argument("--output-dir", type=Path, default=script_dir)
    return parser.parse_args()


def read_predictions(path: Path) -> pd.DataFrame:
    placeholders = ",".join("?" for _ in TARGETS)
    query = f"""
        SELECT id, infer_date, data_type, pred_date, predict
        FROM prediction_data
        WHERE infer_date BETWEEN ? AND ?
          AND data_type IN ({placeholders})
        ORDER BY id
    """
    params = [START_DATE, END_DATE, *TARGETS]
    with sqlite3.connect(path) as conn:
        frame = pd.read_sql_query(query, conn, params=params)
    frame = frame.drop_duplicates(KEYS, keep="last")
    frame["infer_date"] = pd.to_datetime(frame["infer_date"])
    frame["pred_date"] = pd.to_datetime(frame["pred_date"])
    frame["predict"] = pd.to_numeric(frame["predict"], errors="coerce")
    frame = frame.dropna(subset=["infer_date", "pred_date", "predict"])
    frame = frame.sort_values(KEYS).reset_index(drop=True)
    frame["horizon"] = (
        frame.groupby(["infer_date", "data_type"]).cumcount() + 1
    )
    frame["actual_type"] = frame["data_type"].map(
        {key: value[0] for key, value in TARGETS.items()}
    )
    frame["market"] = frame["data_type"].map(
        {key: value[1] for key, value in TARGETS.items()}
    )
    return frame


def read_actuals(path: Path) -> pd.DataFrame:
    placeholders = ",".join("?" for _ in TARGETS)
    actual_types = [value[0] for value in TARGETS.values()]
    query = f"""
        SELECT id, date, data_type AS actual_type, value AS actual
        FROM real_data
        WHERE data_type IN ({placeholders})
        ORDER BY id
    """
    with sqlite3.connect(path) as conn:
        frame = pd.read_sql_query(query, conn, params=actual_types)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["actual"] = pd.to_numeric(frame["actual"], errors="coerce")
    frame = frame.dropna(subset=["date", "actual_type", "actual"])
    return frame.drop_duplicates(["date", "actual_type"], keep="last")


def attach_actuals(predictions: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    frame = predictions.merge(
        actuals[["date", "actual_type", "actual"]],
        left_on=["pred_date", "actual_type"],
        right_on=["date", "actual_type"],
        how="left",
    ).drop(columns="date")

    baselines = []
    groups = frame[["infer_date", "actual_type"]].drop_duplicates()
    for actual_type, infer_dates in groups.groupby("actual_type"):
        history = actuals[actuals["actual_type"] == actual_type].sort_values("date")
        dates = history["date"].to_numpy(dtype="datetime64[ns]")
        values = history["actual"].to_numpy(dtype=float)
        for infer_date in infer_dates["infer_date"]:
            position = np.searchsorted(
                dates, np.datetime64(infer_date), side="left"
            ) - 1
            if position >= 0:
                baselines.append(
                    {
                        "infer_date": infer_date,
                        "actual_type": actual_type,
                        "baseline_date": pd.Timestamp(dates[position]),
                        "baseline": float(values[position]),
                    }
                )
    baseline_frame = pd.DataFrame(baselines)
    return frame.merge(
        baseline_frame, on=["infer_date", "actual_type"], how="left"
    )


def common_realized(
    new_frame: pd.DataFrame, old_frame: pd.DataFrame
) -> pd.DataFrame:
    new_cols = KEYS + [
        "predict",
        "horizon",
        "actual_type",
        "market",
        "actual",
        "baseline",
        "baseline_date",
    ]
    old_cols = KEYS + ["predict", "horizon"]
    common = new_frame[new_cols].merge(
        old_frame[old_cols],
        on=KEYS,
        how="inner",
        suffixes=("_new", "_old"),
        validate="one_to_one",
    )
    common = common.rename(
        columns={
            "predict_new": "new_predict",
            "predict_old": "old_predict",
            "horizon_new": "horizon",
            "horizon_old": "old_horizon",
        }
    )
    common = common.dropna(
        subset=["new_predict", "old_predict", "actual", "baseline"]
    )
    common = common[common["actual"] != 0].copy()
    return common.sort_values(KEYS).reset_index(drop=True)


def point_metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    result: dict[str, float | int] = {"n": int(len(frame))}
    if frame.empty:
        return result

    actual = frame["actual"].to_numpy(dtype=float)
    old_pred = frame["old_predict"].to_numpy(dtype=float)
    new_pred = frame["new_predict"].to_numpy(dtype=float)
    old_error = old_pred - actual
    new_error = new_pred - actual
    old_abs = np.abs(old_error)
    new_abs = np.abs(new_error)

    result.update(
        {
            "old_mae": float(old_abs.mean()),
            "new_mae": float(new_abs.mean()),
            "mae_improvement_pct": float(
                (old_abs.mean() - new_abs.mean()) / old_abs.mean() * 100.0
            ),
            "old_rmse": float(np.sqrt(np.square(old_error).mean())),
            "new_rmse": float(np.sqrt(np.square(new_error).mean())),
            "old_mape": float(np.mean(old_abs / np.abs(actual)) * 100.0),
            "new_mape": float(np.mean(new_abs / np.abs(actual)) * 100.0),
            "mape_improvement_pct": float(
                (
                    np.mean(old_abs / np.abs(actual))
                    - np.mean(new_abs / np.abs(actual))
                )
                / np.mean(old_abs / np.abs(actual))
                * 100.0
            ),
            "old_bias": float(old_error.mean()),
            "new_bias": float(new_error.mean()),
            "new_better_pct": float(np.mean(new_abs < old_abs) * 100.0),
            "ties_pct": float(np.mean(new_abs == old_abs) * 100.0),
        }
    )

    actual_direction = np.sign(actual - frame["baseline"].to_numpy(dtype=float))
    old_direction = np.sign(old_pred - frame["baseline"].to_numpy(dtype=float))
    new_direction = np.sign(new_pred - frame["baseline"].to_numpy(dtype=float))
    valid = (
        (actual_direction != 0)
        & (old_direction != 0)
        & (new_direction != 0)
    )
    result["direction_n"] = int(valid.sum())
    if valid.any():
        result["old_direction_accuracy"] = float(
            np.mean(old_direction[valid] == actual_direction[valid]) * 100.0
        )
        result["new_direction_accuracy"] = float(
            np.mean(new_direction[valid] == actual_direction[valid]) * 100.0
        )
    return result


def comparison_tables(common: pd.DataFrame) -> dict[str, pd.DataFrame]:
    recent = common[common["infer_date"] >= pd.Timestamp(RECENT_START)]
    cumulative_scopes = {
        "all_common_realized": common,
        "h1": common[common["horizon"] == 1],
        "h1_5": common[common["horizon"] <= 5],
        "h1_20": common[common["horizon"] <= 20],
        "h1_60": common[common["horizon"] <= 60],
        f"recent_since_{RECENT_START}": recent,
        f"recent_h1_since_{RECENT_START}": recent[recent["horizon"] == 1],
    }
    overall = pd.DataFrame(
        [{"scope": name, **point_metrics(frame)} for name, frame in cumulative_scopes.items()]
    )

    index_rows = []
    for data_type, group in common.groupby("data_type", sort=True):
        for scope, limit in (("all", None), ("h1", 1), ("h1_20", 20)):
            subset = group if limit is None else group[group["horizon"] <= limit]
            index_rows.append(
                {"data_type": data_type, "scope": scope, **point_metrics(subset)}
            )

    market_rows = []
    for market, group in common.groupby("market", sort=True):
        for scope, limit in (("all", None), ("h1", 1), ("h1_20", 20)):
            subset = group if limit is None else group[group["horizon"] <= limit]
            market_rows.append(
                {"market": market, "scope": scope, **point_metrics(subset)}
            )

    recent_index_rows = [
        {
            "data_type": data_type,
            **point_metrics(group),
        }
        for data_type, group in recent.groupby("data_type", sort=True)
    ]

    buckets = {
        "h1": common["horizon"] == 1,
        "h2_5": common["horizon"].between(2, 5),
        "h6_20": common["horizon"].between(6, 20),
        "h21_60": common["horizon"].between(21, 60),
        "h61_120": common["horizon"].between(61, 120),
    }
    horizon = pd.DataFrame(
        [
            {"horizon_bucket": name, **point_metrics(common[mask])}
            for name, mask in buckets.items()
            if mask.any()
        ]
    )
    return {
        "overall_comparison": overall,
        "by_index": pd.DataFrame(index_rows),
        "by_market": pd.DataFrame(market_rows),
        "by_horizon": horizon,
        "recent_by_index": pd.DataFrame(recent_index_rows),
    }


def linear_slope(values: np.ndarray) -> float:
    x = np.arange(len(values), dtype=float)
    centered = x - x.mean()
    return float(np.dot(values - values.mean(), centered) / np.dot(centered, centered))


def trend_records(common: pd.DataFrame, horizon: int) -> pd.DataFrame:
    rows = []
    expected = set(range(1, horizon + 1))
    for (infer_date, data_type), group in common.groupby(
        ["infer_date", "data_type"], sort=False
    ):
        window = group[group["horizon"] <= horizon].sort_values("horizon")
        if len(window) != horizon or set(window["horizon"]) != expected:
            continue
        actual = window["actual"].to_numpy(dtype=float)
        old_pred = window["old_predict"].to_numpy(dtype=float)
        new_pred = window["new_predict"].to_numpy(dtype=float)
        rows.append(
            {
                "infer_date": infer_date,
                "data_type": data_type,
                "market": window["market"].iloc[0],
                "horizon": horizon,
                "actual_slope": linear_slope(actual),
                "old_slope": linear_slope(old_pred),
                "new_slope": linear_slope(new_pred),
                "old_correlation": (
                    float(np.corrcoef(old_pred, actual)[0, 1])
                    if np.std(old_pred) > 0 and np.std(actual) > 0
                    else np.nan
                ),
                "new_correlation": (
                    float(np.corrcoef(new_pred, actual)[0, 1])
                    if np.std(new_pred) > 0 and np.std(actual) > 0
                    else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def summarize_trends(records: pd.DataFrame) -> pd.DataFrame:
    rows = []
    groupings = [("overall", "all", records)]
    groupings.extend(
        ("market", str(name), group)
        for name, group in records.groupby("market", sort=True)
    )
    groupings.extend(
        ("data_type", str(name), group)
        for name, group in records.groupby("data_type", sort=True)
    )
    for level, name, group in groupings:
        actual_sign = np.sign(group["actual_slope"].to_numpy(dtype=float))
        old_sign = np.sign(group["old_slope"].to_numpy(dtype=float))
        new_sign = np.sign(group["new_slope"].to_numpy(dtype=float))
        valid = (actual_sign != 0) & (old_sign != 0) & (new_sign != 0)
        rows.append(
            {
                "horizon": int(group["horizon"].iloc[0]),
                "level": level,
                "name": name,
                "n": int(len(group)),
                "direction_n": int(valid.sum()),
                "old_slope_direction_accuracy": (
                    float(np.mean(old_sign[valid] == actual_sign[valid]) * 100.0)
                    if valid.any()
                    else np.nan
                ),
                "new_slope_direction_accuracy": (
                    float(np.mean(new_sign[valid] == actual_sign[valid]) * 100.0)
                    if valid.any()
                    else np.nan
                ),
                "old_mean_correlation": float(group["old_correlation"].mean()),
                "new_mean_correlation": float(group["new_correlation"].mean()),
            }
        )
    return pd.DataFrame(rows)


def new_only_extension(new_realized: pd.DataFrame) -> pd.DataFrame:
    extension = new_realized[new_realized["horizon"].between(61, 120)].copy()
    rows = []
    for level, name, group in [
        ("overall", "all", extension),
        *[
            ("market", str(key), value)
            for key, value in extension.groupby("market", sort=True)
        ],
        *[
            ("data_type", str(key), value)
            for key, value in extension.groupby("data_type", sort=True)
        ],
    ]:
        if group.empty:
            continue
        error = group["predict"].to_numpy(float) - group["actual"].to_numpy(float)
        rows.append(
            {
                "level": level,
                "name": name,
                "n": int(len(group)),
                "mae": float(np.abs(error).mean()),
                "rmse": float(np.sqrt(np.square(error).mean())),
                "mape": float(
                    np.mean(np.abs(error) / np.abs(group["actual"].to_numpy(float)))
                    * 100.0
                ),
                "bias": float(error.mean()),
            }
        )
    return pd.DataFrame(rows)


def recent_table(common: pd.DataFrame) -> pd.DataFrame:
    recent = common[common["infer_date"] >= pd.Timestamp(RECENT_START)]
    rows = []
    for infer_date, group in recent.groupby("infer_date", sort=True):
        rows.append(
            {
                "infer_date": infer_date.date().isoformat(),
                "max_realized_horizon": int(group["horizon"].max()),
                **point_metrics(group),
            }
        )
    return pd.DataFrame(rows)


def rounded_records(frame: pd.DataFrame) -> list[dict]:
    clean = frame.copy()
    for column in clean.select_dtypes(include=[np.number]).columns:
        clean[column] = clean[column].round(4)
    clean = clean.replace({np.nan: None})
    return clean.to_dict(orient="records")


def format_table(frame: pd.DataFrame, columns: list[str]) -> str:
    view = frame[columns].copy()
    for column in view.select_dtypes(include=[np.number]).columns:
        view[column] = view[column].map(
            lambda value: "" if pd.isna(value) else f"{value:.2f}"
        )
    return "```\n" + view.to_string(index=False) + "\n```"


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    actuals = read_actuals(args.new_db)
    new_all = attach_actuals(read_predictions(args.new_db), actuals)
    old_all = attach_actuals(read_predictions(args.old_db), actuals)
    common = common_realized(new_all, old_all)
    new_realized = new_all.dropna(subset=["actual", "baseline"])
    new_realized = new_realized[new_realized["actual"] != 0]

    tables = comparison_tables(common)
    trend_details = pd.concat(
        [trend_records(common, 5), trend_records(common, 20)],
        ignore_index=True,
    )
    trend_summary = pd.concat(
        [
            summarize_trends(trend_details[trend_details["horizon"] == horizon])
            for horizon in (5, 20)
        ],
        ignore_index=True,
    )
    recent_trend_details = trend_details[
        trend_details["infer_date"] >= pd.Timestamp(RECENT_START)
    ]
    recent_trend_summary = pd.concat(
        [
            summarize_trends(
                recent_trend_details[recent_trend_details["horizon"] == horizon]
            )
            for horizon in (5, 20)
            if not recent_trend_details[
                recent_trend_details["horizon"] == horizon
            ].empty
        ],
        ignore_index=True,
    )
    tables["trend_summary"] = trend_summary
    tables["recent_trend_summary"] = recent_trend_summary
    tables["recent_by_infer_date"] = recent_table(common)
    tables["new_h61_120"] = new_only_extension(new_realized)

    coverage = {
        "period": {"start": START_DATE, "end": END_DATE},
        "latest_actual_date": actuals["date"].max().date().isoformat(),
        "new_prediction_rows": int(len(new_all)),
        "old_prediction_rows": int(len(old_all)),
        "new_realized_rows": int(len(new_realized)),
        "old_realized_rows": int(old_all["actual"].notna().sum()),
        "common_realized_rows": int(len(common)),
        "common_infer_dates": int(common["infer_date"].nunique()),
        "common_forecast_groups": int(
            common[["infer_date", "data_type"]].drop_duplicates().shape[0]
        ),
    }

    for name, table in tables.items():
        table.to_csv(args.output_dir / f"{name}.csv", index=False)
    trend_details.to_csv(args.output_dir / "trend_details.csv", index=False)

    payload = {
        "coverage": coverage,
        "tables": {name: rounded_records(table) for name, table in tables.items()},
        "notes": [
            "Point comparisons use identical infer_date/data_type/pred_date keys.",
            "Direction accuracy excludes flat actual, old, or new directions.",
            "Direction baseline is the latest actual strictly before infer_date.",
            "Historical replay with a current checkpoint is not leakage-free.",
        ],
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    overall = tables["overall_comparison"]
    by_index = tables["by_index"]
    trend_overall = trend_summary[trend_summary["level"] == "overall"]
    report = [
        "# Coal history replay evaluation",
        "",
        f"- Period: {START_DATE} through {END_DATE}",
        f"- Latest actual: {coverage['latest_actual_date']}",
        f"- Common realized points: {coverage['common_realized_rows']}",
        "",
        "## Point accuracy",
        "",
        format_table(
            overall,
            [
                "scope",
                "n",
                "old_mape",
                "new_mape",
                "mape_improvement_pct",
                "old_mae",
                "new_mae",
                "new_better_pct",
            ],
        ),
        "",
        "## Per-index accuracy (first 20 horizons)",
        "",
        format_table(
            by_index[by_index["scope"] == "h1_20"],
            [
                "data_type",
                "n",
                "old_mape",
                "new_mape",
                "mape_improvement_pct",
                "old_direction_accuracy",
                "new_direction_accuracy",
            ],
        ),
        "",
        "## Slope direction",
        "",
        format_table(
            trend_overall,
            [
                "horizon",
                "n",
                "old_slope_direction_accuracy",
                "new_slope_direction_accuracy",
                "old_mean_correlation",
                "new_mean_correlation",
            ],
        ),
        "",
        "## Interpretation warning",
        "",
        "The replay uses a current checkpoint for historical inference dates. It "
        "therefore measures retrospective fit and database replacement quality, "
        "not a leakage-free live backtest.",
        "",
    ]
    (args.output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")

    print(json.dumps(coverage, indent=2))
    print(overall.to_string(index=False))
    print(trend_overall.to_string(index=False))


if __name__ == "__main__":
    main()
