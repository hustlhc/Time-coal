#!/usr/bin/env python3
"""Synchronize coal-index forecast curves by configurable market trend anchors."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil

import numpy as np
import pandas as pd


SERIES = [
    ("CCI4500", "CCI4500infer.csv", True),
    ("CCI5000", "CCI5000infer.csv", True),
    ("CCI5500", "CCI5500infer.csv", True),
    ("CCI3800out", "CCI3800outinfer.csv", False),
    ("CCI4700out", "CCI4700outinfer.csv", False),
    ("CCI5500out", "CCI5500outinfer.csv", False),
]

DOMESTIC_NAMES = [name for name, _, should_round in SERIES if should_round]
IMPORTED_NAMES = [name for name, _, should_round in SERIES if not should_round]


def read_series(path: Path) -> pd.Series:
    df = pd.read_csv(path, header=None)
    if df.empty:
        raise ValueError(f"{path} is empty")
    return df.iloc[:, 0].astype(float).reset_index(drop=True)


def direction_agreement(values: np.ndarray) -> float:
    """Average pairwise agreement of daily up/down direction."""
    diffs = np.diff(values, axis=0)
    signs = np.sign(diffs)
    agreements = []
    for i in range(signs.shape[1]):
        for j in range(i + 1, signs.shape[1]):
            active = (signs[:, i] != 0) | (signs[:, j] != 0)
            if active.any():
                agreements.append((signs[active, i] == signs[active, j]).mean())
    return float(np.mean(agreements)) if agreements else 1.0


def mean_pairwise_corr(values: np.ndarray) -> float:
    if values.shape[0] < 2:
        return 1.0
    corr = np.corrcoef(values.T)
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    vals = corr[mask]
    vals = vals[~np.isnan(vals)]
    return float(vals.mean()) if vals.size else 1.0


def save_plot(before: pd.DataFrame, after: pd.DataFrame, output: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover - plotting is best effort.
        print(f"skip plot: {exc}")
        return

    fig, axes = plt.subplots(3, 2, figsize=(13, 10), sharex=True)
    for ax, name in zip(axes.ravel(), before.columns):
        ax.plot(before.index + 1, before[name], label="before", linewidth=1.8, alpha=0.65)
        ax.plot(after.index + 1, after[name], label="after sync", linewidth=2.0)
        ax.set_title(name)
        ax.grid(True, alpha=0.25)
    axes.ravel()[0].legend(frameon=False)
    fig.suptitle("Coal forecast synchronization", y=0.995)
    fig.tight_layout()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def resolve_anchor(log_rel: pd.DataFrame, anchor_mode: str) -> pd.Series:
    if anchor_mode == "all_mean":
        columns = list(log_rel.columns)
    elif anchor_mode == "domestic_mean":
        columns = DOMESTIC_NAMES
    elif anchor_mode == "imported_mean":
        columns = IMPORTED_NAMES
    else:
        raise ValueError(f"unknown anchor mode: {anchor_mode}")

    missing = [name for name in columns if name not in log_rel.columns]
    if missing:
        raise ValueError(f"missing anchor columns: {missing}")
    return log_rel[columns].mean(axis=1)


def resolve_targets(columns: pd.Index, align_targets: str) -> list[str]:
    if align_targets == "all":
        targets = list(columns)
    elif align_targets == "domestic":
        targets = DOMESTIC_NAMES
    elif align_targets == "imported":
        targets = IMPORTED_NAMES
    else:
        raise ValueError(f"unknown align targets: {align_targets}")

    missing = [name for name in targets if name not in columns]
    if missing:
        raise ValueError(f"missing target columns: {missing}")
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize six coal forecast curves.")
    parser.add_argument("--folder", default="autoinfer", help="Folder containing *infer.csv files")
    parser.add_argument("--strength", type=float, default=0.8, help="Blend weight for the shared trend, 0~1")
    parser.add_argument(
        "--anchor-mode",
        choices=["all_mean", "domestic_mean", "imported_mean"],
        default="all_mean",
        help="Trend anchor: all six curves, domestic curves, or imported curves",
    )
    parser.add_argument(
        "--align-targets",
        choices=["all", "domestic", "imported"],
        default="all",
        help="Curves to align toward the chosen anchor",
    )
    parser.add_argument("--backup-dir", default="raw_before_sync", help="Backup subfolder name")
    parser.add_argument("--no-backup", action="store_true", help="Do not create backups")
    parser.add_argument("--no-plot", action="store_true", help="Do not write sync_compare.png")
    args = parser.parse_args()

    folder = Path(args.folder)
    strength = min(1.0, max(0.0, args.strength))

    paths = [(name, folder / filename, should_round) for name, filename, should_round in SERIES]
    missing = [str(path) for _, path, _ in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("missing forecast files: " + ", ".join(missing))

    if not args.no_backup:
        backup = folder / args.backup_dir
        backup.mkdir(parents=True, exist_ok=True)
        for _, path, _ in paths:
            shutil.copy2(path, backup / path.name)

    before = pd.DataFrame({name: read_series(path) for name, path, _ in paths})
    if before.isnull().any().any():
        before = before.interpolate(limit_direction="both")

    base = before.iloc[0].replace(0, np.nan)
    log_rel = np.log(before.divide(base, axis=1).clip(lower=1e-9))
    anchor_log_rel = resolve_anchor(log_rel, args.anchor_mode)
    target_names = resolve_targets(log_rel.columns, args.align_targets)
    synced_log_rel = log_rel.copy()
    synced_log_rel.loc[:, target_names] = (
        log_rel.loc[:, target_names].mul(1.0 - strength).add(anchor_log_rel.mul(strength), axis=0)
    )
    after = np.exp(synced_log_rel).multiply(base, axis=1)
    after.iloc[0] = before.iloc[0]

    for name, path, should_round in paths:
        out = after[name]
        if should_round:
            out = out.round().astype(int)
        out.to_csv(path, index=False, header=False)

    before_rel = before.divide(before.iloc[0], axis=1).subtract(1.0)
    after_rel = after.divide(after.iloc[0], axis=1).subtract(1.0)
    summary = pd.DataFrame(
        [
            {
                "stage": "before",
                "anchor_mode": args.anchor_mode,
                "align_targets": args.align_targets,
                "mean_pairwise_corr": mean_pairwise_corr(before_rel.to_numpy()),
                "direction_agreement": direction_agreement(before.to_numpy()),
                "terminal_pct_std": float(before_rel.iloc[-1].std()),
                "terminal_pct_range": float(before_rel.iloc[-1].max() - before_rel.iloc[-1].min()),
            },
            {
                "stage": "after",
                "anchor_mode": args.anchor_mode,
                "align_targets": args.align_targets,
                "mean_pairwise_corr": mean_pairwise_corr(after_rel.to_numpy()),
                "direction_agreement": direction_agreement(after.to_numpy()),
                "terminal_pct_std": float(after_rel.iloc[-1].std()),
                "terminal_pct_range": float(after_rel.iloc[-1].max() - after_rel.iloc[-1].min()),
            },
        ]
    )
    summary.to_csv(folder / "sync_summary.csv", index=False)
    after.to_csv(folder / "sync_forecasts.csv", index=False)
    if not args.no_plot:
        save_plot(before, after, folder / "sync_compare.png")

    print(
        f"synced forecasts in {folder} with strength={strength:.2f}, "
        f"anchor_mode={args.anchor_mode}, align_targets={args.align_targets}"
    )
    print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
