#!/usr/bin/env python3
"""Monitor realized coal forecasts and safely retrain the joint model."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TARGETS = {
    "CCI4500infer": "CCI4500",
    "CCI5000infer": "CCI5000",
    "CCI5500infer": "CCI5500",
    "CCI3800outinfer": "CCI进口3800",
    "CCI4700outinfer": "CCI进口4700",
    "CCI5500outinfer": "CCI进口5500",
}

DEFAULT_ACTIVE_MODEL_ID = "Coal6_JulyShort_Trend5dStrong32_Prod_20260730"

TRAINING_PROFILES = {
    "level_recovery": {
        "TRAIN_EPOCHS": "12",
        "PATIENCE": "5",
        "LEARNING_RATE": "0.0007",
        "FORECAST_LOSS": "mse",
        "USE_SHORT_HORIZON_WEIGHT_LOSS": "1",
        "SHORT_HORIZON_WEIGHT_DAYS": "20",
        "SHORT_HORIZON_WEIGHT": "2.0",
        "USE_ACC_LOSS": "0",
        "USE_SHORT_TREND_LOSS": "1",
        "SHORT_TREND_LOSS_WEIGHT": "1.0",
        "SHORT_TREND_MONTH_LEN": "5",
        "SHORT_TREND_MONTH_WEIGHTS": "0.45,0.22,0.11,0.07,0.05,0.035,0.025,0.015,0.01,0.005",
        "SHORT_TREND_MAX_SEGMENTS": "10",
        "SYNC_LOSS_WEIGHT": "0.02",
    },
    "trend_recovery": {
        "TRAIN_EPOCHS": "12",
        "PATIENCE": "5",
        "LEARNING_RATE": "0.0007",
        "FORECAST_LOSS": "mse",
        "USE_SHORT_HORIZON_WEIGHT_LOSS": "1",
        "SHORT_HORIZON_WEIGHT_DAYS": "20",
        "SHORT_HORIZON_WEIGHT": "3.0",
        "USE_ACC_LOSS": "0",
        "USE_SHORT_TREND_LOSS": "1",
        "SHORT_TREND_LOSS_WEIGHT": "2.0",
        "SHORT_TREND_MONTH_LEN": "5",
        "SHORT_TREND_MONTH_WEIGHTS": "0.45,0.22,0.11,0.07,0.05,0.035,0.025,0.015,0.01,0.005",
        "SHORT_TREND_MAX_SEGMENTS": "10",
        "SYNC_LOSS_WEIGHT": "0.02",
    },
}


@dataclass
class MonitorResult:
    latest_actual_date: str
    latest_evaluated_date: str
    evaluated_dates: list[str]
    overall_mape: float
    direction_accuracy: float | None
    direction_samples: int
    per_index: dict[str, dict[str, float | int | None]]
    per_horizon: dict[str, dict[str, float | int | None]]
    records: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "latest_actual_date": self.latest_actual_date,
            "latest_evaluated_date": self.latest_evaluated_date,
            "evaluated_dates": self.evaluated_dates,
            "overall_mape": self.overall_mape,
            "direction_accuracy": self.direction_accuracy,
            "direction_samples": self.direction_samples,
            "per_index": self.per_index,
            "per_horizon": self.per_horizon,
            "records": self.records,
        }


def setting_name(model_id: str) -> str:
    return (
        f"long_term_forecast_{model_id}_TimeMixer_coal_ftM_sl32_ll16_pl120_"
        "dm64_nh8_el4_dl1_df32_expand2_dc4_fc1_ebtimeF_dtTrue_Sync6_0"
    )


def resolve_path(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"breach_streak": 0, "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"breach_streak": 0, "history": []}
    data.setdefault("breach_streak", 0)
    data.setdefault("history", [])
    return data


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def load_realized_forecasts(
    actual_path: Path,
    json_dir: Path,
    window: int,
    evaluation_horizon: int,
    min_points_per_index: int,
) -> MonitorResult:
    actual = pd.read_csv(actual_path)
    if "date" not in actual.columns:
        raise ValueError(f"{actual_path} is missing the date column")
    missing_targets = [name for name in TARGETS.values() if name not in actual.columns]
    if missing_targets:
        raise ValueError(f"{actual_path} is missing targets: {missing_targets}")

    actual["date"] = pd.to_datetime(actual["date"], errors="coerce")
    actual = actual.dropna(subset=["date"]).drop_duplicates("date", keep="last")
    actual = actual.sort_values("date").set_index("date")

    rows: list[dict[str, Any]] = []
    for json_path in sorted(json_dir.glob("*_data.json")):
        try:
            infer_date = pd.Timestamp(json_path.name[:10])
        except (TypeError, ValueError):
            continue
        if infer_date > actual.index.max():
            continue

        previous_dates = actual.index[actual.index < infer_date]
        if len(previous_dates) == 0:
            continue
        baseline_date = previous_dates.max()

        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        prediction_data = payload.get("data", {})
        for prediction_key, actual_column in TARGETS.items():
            values = prediction_data.get(prediction_key) or []
            if not values:
                continue
            baseline = pd.to_numeric(
                pd.Series([actual.at[baseline_date, actual_column]]), errors="coerce"
            ).iloc[0]
            if not np.isfinite(baseline):
                continue

            for lead, point in enumerate(values[: max(1, evaluation_horizon)], start=1):
                try:
                    target_date = pd.Timestamp(point["date"])
                    prediction = float(point["predict"])
                except (KeyError, TypeError, ValueError):
                    continue
                if target_date not in actual.index:
                    continue

                true_value = pd.to_numeric(
                    pd.Series([actual.at[target_date, actual_column]]), errors="coerce"
                ).iloc[0]
                if not np.isfinite(true_value) or true_value == 0:
                    continue

                pred_direction = np.sign(prediction - baseline)
                true_direction = np.sign(float(true_value) - float(baseline))
                direction_correct: float | None = None
                if pred_direction != 0 and true_direction != 0:
                    direction_correct = float(pred_direction == true_direction)

                rows.append(
                    {
                        "infer_date": infer_date,
                        "target_date": target_date,
                        "lead": lead,
                        "index": actual_column,
                        "prediction": prediction,
                        "true": float(true_value),
                        "ape": abs(prediction - float(true_value))
                        / abs(float(true_value))
                        * 100.0,
                        "direction_correct": direction_correct,
                    }
                )

    if not rows:
        raise ValueError("no realized short-horizon coal forecasts were found")

    frame = pd.DataFrame(rows)
    complete_counts = frame.groupby("target_date")["index"].nunique()
    complete_dates = complete_counts[complete_counts >= len(TARGETS)].index.sort_values()
    selected_dates = list(complete_dates[-max(1, window) :])
    frame = frame[frame["target_date"].isin(selected_dates)].copy()

    per_index: dict[str, dict[str, float | int | None]] = {}
    for name in TARGETS.values():
        subset = frame[frame["index"] == name]
        if len(subset) < min_points_per_index:
            raise ValueError(
                f"not enough realized forecasts for {name}: {len(subset)} < {min_points_per_index}"
            )
        direction = subset["direction_correct"].dropna()
        per_index[name] = {
            "n": int(len(subset)),
            "mape": float(subset["ape"].mean()),
            "direction_accuracy": float(direction.mean()) if len(direction) else None,
            "direction_n": int(len(direction)),
        }

    per_horizon: dict[str, dict[str, float | int | None]] = {}
    for lead, subset in frame.groupby("lead", sort=True):
        lead_direction = subset["direction_correct"].dropna()
        per_horizon[f"h{int(lead)}"] = {
            "n": int(len(subset)),
            "mape": float(subset["ape"].mean()),
            "direction_accuracy": (
                float(lead_direction.mean()) if len(lead_direction) else None
            ),
            "direction_n": int(len(lead_direction)),
        }

    direction = frame["direction_correct"].dropna()
    return MonitorResult(
        latest_actual_date=actual.index.max().date().isoformat(),
        latest_evaluated_date=pd.Timestamp(selected_dates[-1]).date().isoformat(),
        evaluated_dates=[pd.Timestamp(value).date().isoformat() for value in selected_dates],
        overall_mape=float(frame["ape"].mean()),
        direction_accuracy=float(direction.mean()) if len(direction) else None,
        direction_samples=int(len(direction)),
        per_index=per_index,
        per_horizon=per_horizon,
        records=int(len(frame)),
    )


def threshold_reasons(
    result: MonitorResult,
    overall_mape_threshold: float,
    index_mape_threshold: float,
    direction_threshold: float,
) -> list[str]:
    reasons: list[str] = []
    if result.overall_mape >= overall_mape_threshold:
        reasons.append(
            f"overall MAPE {result.overall_mape:.3f}% >= {overall_mape_threshold:.3f}%"
        )
    for name, metrics in result.per_index.items():
        mape = float(metrics["mape"])
        if mape >= index_mape_threshold:
            reasons.append(f"{name} MAPE {mape:.3f}% >= {index_mape_threshold:.3f}%")
    if (
        result.direction_accuracy is not None
        and result.direction_accuracy <= direction_threshold
    ):
        reasons.append(
            "direction accuracy "
            f"{result.direction_accuracy:.3f} <= {direction_threshold:.3f}"
        )
    return reasons


def choose_profile(result: MonitorResult, direction_threshold: float) -> str:
    if (
        result.direction_accuracy is not None
        and result.direction_accuracy <= direction_threshold
    ):
        return "trend_recovery"
    return "level_recovery"


def days_since(value: str | None, current: date) -> int | None:
    if not value:
        return None
    try:
        previous = date.fromisoformat(value)
    except ValueError:
        return None
    return (current - previous).days


def model_feature_count(repo_root: Path) -> int:
    data_path = repo_root / "dataset" / "pre_coal" / "coal_new.csv"
    count = int(pd.read_csv(data_path, nrows=0).shape[1] - 1)
    if count < len(TARGETS):
        raise ValueError(f"invalid model feature count {count} in {data_path}")
    return count


def common_run_args(
    model_id: str,
    csv_path: Path,
    gpu_type: str,
    feature_count: int,
) -> list[str]:
    return [
        "--task_name", "long_term_forecast",
        "--root_path", "./dataset/pre_coal/",
        "--data_path", "coal_new.csv",
        "--model_id", model_id,
        "--model", "TimeMixer",
        "--data", "coal",
        "--features", "M",
        "--target_features", "6",
        "--seq_len", "32",
        "--label_len", "16",
        "--pred_len", "120",
        "--e_layers", "4",
        "--enc_in", str(feature_count),
        "--c_out", str(feature_count),
        "--des", "Sync6",
        "--itr", "1",
        "--d_model", "64",
        "--d_ff", "32",
        "--learning_rate", "0.001",
        "--train_epochs", "10",
        "--patience", "10",
        "--batch_size", "16",
        "--down_sampling_layers", "3",
        "--down_sampling_method", "avg",
        "--channel_independence", "0",
        "--down_sampling_window", "1",
        "--moving_avg", "15",
        "--num_workers", "0",
        "--gpu_type", gpu_type,
        "--use_month_onehot", "1",
        "--use_seasonal_loss", "1",
        "--seasonal_loss_months", "1,4,6,9,11,12",
        "--seasonal_loss_weight", "1.3",
        "--seasonal_loss_normalize", "1",
        "--use_acc_loss", "1",
        "--acc_loss_weight", "0.2",
        "--use_short_trend_loss", "1",
        "--short_trend_loss_weight", "0.6",
        "--short_trend_month_weights", "0.8,0.15,0.05",
        "--use_sync_loss", "1",
        "--sync_loss_weight", "0.06",
        "--sync_infer_targets", "0",
        "--sync_infer_strength", "0.4",
        "--sync_anchor_mode", "imported_mean",
        "--sync_align_targets", "domestic",
        "--is_testing", "1",
        "--is_full_training", "1",
        "--csv_path", str(csv_path),
    ]


def run_baseline_test(
    repo_root: Path,
    python_bin: str,
    model_id: str,
    csv_path: Path,
    gpu_type: str,
) -> bool:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        python_bin,
        "-u",
        "run.py",
        *common_run_args(
            model_id,
            csv_path,
            gpu_type,
            model_feature_count(repo_root),
        ),
        "--is_training", "0",
        "--do_predict", "0",
    ]
    print("[auto-retrain] baseline test:", " ".join(command), flush=True)
    return subprocess.run(command, cwd=repo_root, check=False).returncode == 0


def run_candidate_training(
    repo_root: Path,
    python_bin: str,
    candidate_model_id: str,
    run_dir_relative: Path,
    profile_name: str,
    gpu_type: str,
) -> bool:
    env = os.environ.copy()
    env.update(TRAINING_PROFILES[profile_name])
    env.update(
        {
            "PYTHON_BIN": python_bin,
            "GPU_TYPE": gpu_type,
            "MODEL_ID": candidate_model_id,
            "TESTRESULT_FOLDER": str(run_dir_relative / "candidate_test"),
            "AUTOINFER_FOLDER": str(run_dir_relative / "candidate_infer"),
            "TENINFER_FOLDER": str(run_dir_relative / "candidate_previous"),
            "SYNC_ANCHOR_MODE": "imported_mean",
            "SYNC_ALIGN_TARGETS": "domestic",
            "SYNC_INFER_TARGETS": "0",
        }
    )
    command = [python_bin, "coal.py", "--forecast_mode", "trend", "--finetune", "1"]
    print(
        f"[auto-retrain] candidate training profile={profile_name}: "
        + " ".join(command),
        flush=True,
    )
    return subprocess.run(command, cwd=repo_root, env=env, check=False).returncode == 0


def evaluate_saved_result(repo_root: Path, model_id: str) -> dict[str, float]:
    result_dir = repo_root / "results" / setting_name(model_id)
    pred_path = result_dir / "pred.npy"
    true_path = result_dir / "true.npy"
    if not pred_path.exists() or not true_path.exists():
        raise FileNotFoundError(f"missing test arrays in {result_dir}")

    pred = np.load(pred_path)
    true = np.load(true_path)
    if pred.shape != true.shape or pred.ndim != 3 or pred.shape[-1] != len(TARGETS):
        raise ValueError(f"unexpected test result shapes: pred={pred.shape}, true={true.shape}")

    def mape(horizon: int) -> float:
        return float(
            np.mean(
                np.abs(
                    (pred[:, :horizon, :] - true[:, :horizon, :])
                    / np.clip(np.abs(true[:, :horizon, :]), 1e-6, None)
                )
            )
            * 100.0
        )

    horizon = min(20, pred.shape[1])
    x = np.arange(horizon, dtype=float)
    centered = x - x.mean()
    denominator = float(np.square(centered).sum())
    pred_slope = (
        (pred[:, :horizon, :] - pred[:, :horizon, :].mean(axis=1, keepdims=True))
        * centered.reshape(1, -1, 1)
    ).sum(axis=1) / denominator
    true_slope = (
        (true[:, :horizon, :] - true[:, :horizon, :].mean(axis=1, keepdims=True))
        * centered.reshape(1, -1, 1)
    ).sum(axis=1) / denominator
    valid = (pred_slope != 0) & (true_slope != 0)
    slope_direction = float(
        np.mean(np.sign(pred_slope[valid]) == np.sign(true_slope[valid]))
    )

    metrics = {
        "mape5": mape(min(5, pred.shape[1])),
        "mape20": mape(horizon),
        "mape120": mape(pred.shape[1]),
        "slope20_direction": slope_direction,
    }
    metrics["composite"] = (
        0.45 * metrics["mape5"] / 3.0
        + 0.35 * metrics["mape20"] / 5.0
        + 0.20 * (1.0 - metrics["slope20_direction"]) / 0.4
    )
    return metrics


def candidate_is_better(
    baseline: dict[str, float],
    candidate: dict[str, float],
    profile_name: str,
    min_improvement: float,
) -> tuple[bool, str]:
    required_metrics = {
        "mape5",
        "mape20",
        "mape120",
        "slope20_direction",
        "composite",
    }
    for label, metrics in (("baseline", baseline), ("candidate", candidate)):
        missing = required_metrics.difference(metrics)
        if missing:
            return False, f"{label} metrics are missing: {sorted(missing)}"
        if not all(np.isfinite(float(metrics[name])) for name in required_metrics):
            return False, f"{label} metrics contain non-finite values"

    if candidate["mape5"] > baseline["mape5"] * 1.05:
        return False, "candidate 5-day MAPE regressed by more than 5%"
    if candidate["mape20"] > baseline["mape20"] * 1.05:
        return False, "candidate 20-day MAPE regressed by more than 5%"
    if candidate["slope20_direction"] < baseline["slope20_direction"] - 0.03:
        return False, "candidate 20-day slope direction regressed by more than 3 points"

    improvement = (baseline["composite"] - candidate["composite"]) / max(
        abs(baseline["composite"]), 1e-9
    )
    if improvement >= min_improvement:
        return True, f"composite improved by {improvement:.2%}"

    if (
        profile_name == "trend_recovery"
        and candidate["slope20_direction"]
        >= baseline["slope20_direction"] + 0.03
        and candidate["mape5"] <= baseline["mape5"] * 1.03
    ):
        return True, "trend accuracy improved by at least 3 points without material MAPE loss"
    return False, f"composite improvement {improvement:.2%} is below requirement"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def promote_candidate(
    repo_root: Path,
    active_model_id: str,
    candidate_model_id: str,
    run_dir: Path,
    metadata: dict[str, Any],
) -> Path:
    active_checkpoint = (
        repo_root / "checkpoints" / setting_name(active_model_id) / "checkpoint.pth"
    )
    candidate_checkpoint = (
        repo_root / "checkpoints" / setting_name(candidate_model_id) / "checkpoint.pth"
    )
    if not active_checkpoint.exists():
        raise FileNotFoundError(f"active checkpoint is missing: {active_checkpoint}")
    if not candidate_checkpoint.exists() or candidate_checkpoint.stat().st_size == 0:
        raise FileNotFoundError(f"candidate checkpoint is missing: {candidate_checkpoint}")

    backup_dir = run_dir / "active_checkpoint_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / "checkpoint.pth"
    shutil.copy2(active_checkpoint, backup_path)

    metadata = dict(metadata)
    metadata.update(
        {
            "active_checkpoint_before_sha256": sha256(active_checkpoint),
            "candidate_checkpoint_sha256": sha256(candidate_checkpoint),
            "backup_path": str(backup_path),
        }
    )
    save_json(backup_dir / "metadata.json", metadata)

    temporary = active_checkpoint.with_suffix(".candidate.tmp")
    shutil.copy2(candidate_checkpoint, temporary)
    os.replace(temporary, active_checkpoint)
    return backup_path


def print_monitor(result: MonitorResult, reasons: list[str], streak: int) -> None:
    direction = (
        "n/a" if result.direction_accuracy is None else f"{result.direction_accuracy:.2%}"
    )
    print(
        f"[auto-retrain] dates={result.evaluated_dates} records={result.records} "
        f"MAPE={result.overall_mape:.3f}% direction={direction} "
        f"(n={result.direction_samples}) streak={streak}"
    )
    for name, metrics in result.per_index.items():
        print(
            f"[auto-retrain] {name}: n={metrics['n']} MAPE={float(metrics['mape']):.3f}%"
        )
    horizon_summary = ", ".join(
        f"{name}={float(metrics['mape']):.3f}%"
        for name, metrics in result.per_horizon.items()
    )
    print(f"[auto-retrain] MAPE by forecast lead: {horizon_summary}")
    if reasons:
        for reason in reasons:
            print(f"[auto-retrain] breach: {reason}")
    else:
        print("[auto-retrain] performance is within thresholds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--actual-file", default="dataset/pre_coal/coal_new.csv")
    parser.add_argument("--json-dir", default="autoinfer/json")
    parser.add_argument("--state-file", default="autoinfer/auto_retrain_state.json")
    parser.add_argument("--runs-dir", default="autoinfer/auto_retrain_runs")
    parser.add_argument("--active-model-id", default=DEFAULT_ACTIVE_MODEL_ID)
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--evaluation-horizon", type=int, default=5)
    parser.add_argument("--min-points-per-index", type=int, default=3)
    parser.add_argument("--overall-mape-threshold", type=float, default=3.0)
    parser.add_argument("--index-mape-threshold", type=float, default=5.0)
    parser.add_argument("--direction-threshold", type=float, default=0.55)
    parser.add_argument("--breach-streak-required", type=int, default=2)
    parser.add_argument("--cooldown-days", type=int, default=7)
    parser.add_argument("--attempt-cooldown-days", type=int, default=3)
    parser.add_argument("--min-candidate-improvement", type=float, default=0.01)
    parser.add_argument("--gpu-type", default=os.environ.get("GPU_TYPE", "cpu"))
    parser.add_argument("--execute-training", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    actual_path = resolve_path(repo_root, args.actual_file)
    json_dir = resolve_path(repo_root, args.json_dir)
    state_path = resolve_path(repo_root, args.state_file)
    state = load_state(state_path)

    result = load_realized_forecasts(
        actual_path,
        json_dir,
        args.window,
        args.evaluation_horizon,
        args.min_points_per_index,
    )
    reasons = threshold_reasons(
        result,
        args.overall_mape_threshold,
        args.index_mape_threshold,
        args.direction_threshold,
    )

    is_new_evaluation = (
        state.get("last_evaluated_date") != result.latest_evaluated_date
    )
    if is_new_evaluation:
        state["breach_streak"] = int(state.get("breach_streak", 0)) + 1 if reasons else 0
        state["last_evaluated_date"] = result.latest_evaluated_date
        history = list(state.get("history", []))
        history.append(
            {
                "checked_at": datetime.now().isoformat(timespec="seconds"),
                "metrics": result.to_dict(),
                "reasons": reasons,
                "breach_streak": state["breach_streak"],
            }
        )
        state["history"] = history[-60:]
    elif not reasons:
        # A same-day data correction may clear an earlier breach.
        state["breach_streak"] = 0
    state["last_monitor"] = result.to_dict()
    save_json(state_path, state)

    streak = int(state.get("breach_streak", 0))
    print_monitor(result, reasons, streak)
    if not reasons:
        return 0
    if streak < args.breach_streak_required:
        print(
            f"[auto-retrain] waiting for {args.breach_streak_required} consecutive breaches"
        )
        return 0
    if not args.execute_training:
        print("[auto-retrain] training trigger reached; monitor-only mode leaves model unchanged")
        return 0

    current_date = date.fromisoformat(result.latest_evaluated_date)
    retrain_age = days_since(state.get("last_retrain_date"), current_date)
    if retrain_age is not None and retrain_age < args.cooldown_days:
        print(f"[auto-retrain] retrain cooldown active: {retrain_age}/{args.cooldown_days} days")
        return 0
    attempt_age = days_since(state.get("last_attempt_date"), current_date)
    if attempt_age is not None and attempt_age < args.attempt_cooldown_days:
        print(
            f"[auto-retrain] attempt cooldown active: "
            f"{attempt_age}/{args.attempt_cooldown_days} days"
        )
        return 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    configured_runs_dir = resolve_path(repo_root, args.runs_dir).resolve()
    try:
        runs_dir_relative = configured_runs_dir.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("--runs-dir must be inside --repo-root") from exc
    run_dir_relative = runs_dir_relative / timestamp
    run_dir = resolve_path(repo_root, str(run_dir_relative))
    run_dir.mkdir(parents=True, exist_ok=True)
    profile_name = choose_profile(result, args.direction_threshold)
    candidate_model_id = f"Coal6_AutoCandidate_{timestamp}"
    python_bin = os.environ.get("PYTHON_BIN", sys.executable)

    state["last_attempt_date"] = result.latest_evaluated_date
    state["last_attempt_at"] = datetime.now().isoformat(timespec="seconds")
    state["last_attempt_profile"] = profile_name
    save_json(state_path, state)

    if not run_baseline_test(
        repo_root,
        python_bin,
        args.active_model_id,
        run_dir / "baseline_test" / "coal6.csv",
        args.gpu_type,
    ):
        print("[auto-retrain] baseline test failed; active checkpoint was not changed")
        return 0

    try:
        baseline_metrics = evaluate_saved_result(repo_root, args.active_model_id)
    except Exception as exc:
        print(f"[auto-retrain] baseline metrics failed: {exc}")
        return 0

    if not run_candidate_training(
        repo_root,
        python_bin,
        candidate_model_id,
        run_dir_relative,
        profile_name,
        args.gpu_type,
    ):
        print("[auto-retrain] candidate training failed; active checkpoint was not changed")
        return 0

    try:
        candidate_metrics = evaluate_saved_result(repo_root, candidate_model_id)
    except Exception as exc:
        print(f"[auto-retrain] candidate metrics failed: {exc}")
        return 0

    promote, decision_reason = candidate_is_better(
        baseline_metrics,
        candidate_metrics,
        profile_name,
        args.min_candidate_improvement,
    )
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "monitor": result.to_dict(),
        "threshold_reasons": reasons,
        "profile": profile_name,
        "profile_parameters": TRAINING_PROFILES[profile_name],
        "active_model_id": args.active_model_id,
        "candidate_model_id": candidate_model_id,
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "promote": promote,
        "decision_reason": decision_reason,
    }
    save_json(run_dir / "summary.json", summary)

    if not promote:
        state["last_decision"] = summary
        state["breach_streak"] = 0
        save_json(state_path, state)
        print(f"[auto-retrain] candidate rejected: {decision_reason}")
        return 0

    try:
        backup_path = promote_candidate(
            repo_root,
            args.active_model_id,
            candidate_model_id,
            run_dir,
            summary,
        )
    except Exception as exc:
        print(f"[auto-retrain] promotion failed: {exc}")
        return 0

    state["last_retrain_date"] = result.latest_evaluated_date
    state["last_retrain_at"] = datetime.now().isoformat(timespec="seconds")
    state["last_promoted_candidate"] = candidate_model_id
    state["last_backup_path"] = str(backup_path)
    state["last_decision"] = summary
    state["breach_streak"] = 0
    save_json(state_path, state)
    print(f"[auto-retrain] candidate promoted: {decision_reason}")
    print(f"[auto-retrain] previous checkpoint backup: {backup_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[auto-retrain] monitor failed safely: {exc}", file=sys.stderr)
        raise SystemExit(1)
