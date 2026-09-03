#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Short-term slope correction for six-index coal forecasts.

The joint trend model already corrects the latest price level. This script adds
a short-horizon slope correction when the model's first forecast segment moves
against the recent observed coal-price slope.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TargetSpec:
    label: str
    filename: str
    history_col: str
    do_round: bool = False


TARGETS = [
    TargetSpec("CCI4500", "CCI4500infer.csv", "CCI4500", True),
    TargetSpec("CCI5000", "CCI5000infer.csv", "CCI5000", True),
    TargetSpec("CCI5500", "CCI5500infer.csv", "CCI5500", True),
    TargetSpec("CCI3800out", "CCI3800outinfer.csv", "CCI进口3800", False),
    TargetSpec("CCI4700out", "CCI4700outinfer.csv", "CCI进口4700", False),
    TargetSpec("CCI5500out", "CCI5500outinfer.csv", "CCI进口5500", False),
]


def linear_slope(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=float)
    return float(np.polyfit(x, values, 1)[0])


def load_history(history_path: Path, spec: TargetSpec, history_offset: int, lookback: int) -> np.ndarray:
    df = pd.read_csv(history_path)
    if spec.history_col not in df.columns:
        raise KeyError(f"{history_path} 缺少列: {spec.history_col}")

    series = pd.to_numeric(df[spec.history_col], errors="coerce").dropna().to_numpy(dtype=float)
    if history_offset > 0:
        if len(series) <= history_offset + lookback:
            raise ValueError(f"{spec.history_col} 历史长度不足，无法 offset={history_offset}")
        series = series[:-history_offset]
    return series


def correction_weights(n: int, window: int, decay_days: int) -> np.ndarray:
    weights = np.zeros(n, dtype=float)
    window = max(1, min(window, n))
    decay_days = max(window, min(decay_days, n))

    weights[:window] = 1.0
    if decay_days > window:
        tail = np.arange(window, decay_days, dtype=float)
        weights[window:decay_days] = (decay_days - tail) / (decay_days - window)
    return weights


def correct_forecast(
    pred: np.ndarray,
    recent_slope: float,
    forecast_slope: float,
    strength: float,
    window: int,
    decay_days: int,
    mode: str,
    min_slope: float,
) -> tuple[np.ndarray, bool, float]:
    if abs(recent_slope) < min_slope:
        return pred.copy(), False, 0.0

    target_slope = recent_slope * strength
    should_correct = False
    if mode == "always":
        should_correct = np.sign(target_slope) != 0 and abs(target_slope - forecast_slope) >= min_slope
    else:
        should_correct = recent_slope * forecast_slope < 0

    if not should_correct:
        return pred.copy(), False, target_slope

    idx = np.arange(len(pred), dtype=float)
    target_path = pred[0] + target_slope * idx
    weights = correction_weights(len(pred), window, decay_days)
    corrected = pred * (1.0 - weights) + target_path * weights
    return corrected, True, target_slope


def save_single_plot(
    folder: Path,
    spec: TargetSpec,
    history_tail: np.ndarray,
    original: np.ndarray,
    corrected: np.ndarray,
    recent_slope: float,
    forecast_slope: float,
    target_slope: float,
) -> None:
    plt.figure(figsize=(11, 5))
    hist_x = np.arange(-len(history_tail), 0)
    pred_x = np.arange(len(original))
    plt.plot(hist_x, history_tail, label="recent true", color="green", linewidth=2)
    plt.plot(pred_x, original, label="before slope correction", color="gray", alpha=0.65, linewidth=1.6)
    plt.plot(pred_x, corrected, label="after slope correction", color="red", linewidth=2)
    plt.axvline(0, color="black", linewidth=1, alpha=0.25)
    plt.title(
        f"{spec.label} short slope correction "
        f"(recent={recent_slope:.2f}, forecast={forecast_slope:.2f}, target={target_slope:.2f})"
    )
    plt.xlabel("Workday index")
    plt.ylabel("Price")
    plt.grid(True, alpha=0.3)
    plt.legend()
    output = folder / f"{Path(spec.filename).stem}_short_slope.png"
    plt.savefig(output, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"📊 已保存短期斜率校正图: {output}")


def save_combined_plot(folder: Path, corrected_series: dict[str, np.ndarray]) -> None:
    plt.figure(figsize=(12, 6))
    for label, values in corrected_series.items():
        plt.plot(np.arange(len(values)), values, label=label, linewidth=1.8)
    plt.title("Six coal-index forecast after short slope correction")
    plt.xlabel("Future workday index")
    plt.ylabel("Price")
    plt.grid(True, alpha=0.3)
    plt.legend(ncol=2)
    output = folder / "coal6_short_slope_forecast.png"
    plt.savefig(output, dpi=220, bbox_inches="tight")
    plt.close()
    print(f"📊 已保存6指数预测折线图: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply short-term slope correction to six coal forecasts.")
    parser.add_argument("--folder", default="autoinfer", help="Folder containing split *infer.csv files")
    parser.add_argument("--history", default="dataset/pre_coal/coal_new.csv", help="Coal history CSV")
    parser.add_argument("--history-offset", type=int, default=0, help="Ignore latest N rows of history")
    parser.add_argument("--lookback", type=int, default=5, help="Recent history points used for slope")
    parser.add_argument("--window", type=int, default=20, help="Days fully controlled by short slope")
    parser.add_argument("--decay-days", type=int, default=35, help="Days for correction to decay to zero")
    parser.add_argument("--strength", type=float, default=0.8, help="Recent slope multiplier")
    parser.add_argument("--min-slope", type=float, default=0.2, help="Ignore tiny recent slopes")
    parser.add_argument("--mode", choices=["opposite", "always"], default="opposite")
    parser.add_argument("--round-domestic", type=int, default=1)
    args = parser.parse_args()

    folder = Path(args.folder)
    history_path = Path(args.history)
    corrected_series: dict[str, np.ndarray] = {}
    summary = []

    for spec in TARGETS:
        pred_path = folder / spec.filename
        if not pred_path.exists():
            raise FileNotFoundError(f"缺少预测文件: {pred_path}")

        pred = pd.read_csv(pred_path, header=None).iloc[:, 0].astype(float).to_numpy()
        history = load_history(history_path, spec, args.history_offset, args.lookback)
        recent_tail = history[-max(args.lookback, 2):]

        recent_slope = linear_slope(recent_tail)
        forecast_slope = linear_slope(pred[: max(2, min(args.window, len(pred)))])
        corrected, applied, target_slope = correct_forecast(
            pred,
            recent_slope,
            forecast_slope,
            args.strength,
            args.window,
            args.decay_days,
            args.mode,
            args.min_slope,
        )

        if spec.do_round and args.round_domestic:
            corrected = np.rint(corrected).astype(int)

        pd.DataFrame(corrected).to_csv(pred_path, index=False, header=False)
        save_single_plot(
            folder,
            spec,
            history[-20:],
            pred,
            corrected.astype(float),
            recent_slope,
            forecast_slope,
            target_slope,
        )
        corrected_series[spec.label] = corrected.astype(float)
        summary.append(
            {
                "label": spec.label,
                "file": str(pred_path),
                "recent_slope": recent_slope,
                "forecast_slope_before": forecast_slope,
                "target_slope": target_slope,
                "applied": int(applied),
                "first_value_after": float(corrected[0]),
                "day10_delta_after": float(corrected[min(10, len(corrected) - 1)] - corrected[0]),
                "day20_delta_after": float(corrected[min(20, len(corrected) - 1)] - corrected[0]),
            }
        )
        print(
            f"{spec.label}: recent_slope={recent_slope:.3f}, "
            f"forecast_slope={forecast_slope:.3f}, applied={applied}"
        )

    pd.DataFrame(summary).to_csv(folder / "short_slope_summary.csv", index=False, encoding="utf-8-sig")
    save_combined_plot(folder, corrected_series)
    print(f"✅ 短期斜率校正完成: {folder}")


if __name__ == "__main__":
    main()
