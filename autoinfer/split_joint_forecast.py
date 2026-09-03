#!/usr/bin/env python3
"""Split a six-target joint coal forecast into the existing one-file-per-index layout."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


OUTPUTS = [
    ("CCI4500", "CCI4500infer.csv", True),
    ("CCI5000", "CCI5000infer.csv", True),
    ("CCI5500", "CCI5500infer.csv", True),
    ("CCI3800out", "CCI3800outinfer.csv", False),
    ("CCI4700out", "CCI4700outinfer.csv", False),
    ("CCI5500out", "CCI5500outinfer.csv", False),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Split joint six-index coal forecast CSV.")
    parser.add_argument("--input", required=True, help="Joint forecast CSV, shape [pred_len, 6]")
    parser.add_argument("--output-folder", required=True, help="Folder for split *infer.csv files")
    parser.add_argument("--round-domestic", type=int, default=1, help="1: round CCI4500/5000/5500")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_folder = Path(args.output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, header=None)
    if df.shape[1] != len(OUTPUTS):
        raise ValueError(f"{input_path} has {df.shape[1]} columns, expected {len(OUTPUTS)}")

    for idx, (name, filename, should_round) in enumerate(OUTPUTS):
        series = df.iloc[:, idx].astype(float)
        if should_round and args.round_domestic:
            series = series.round().astype(int)
        path = output_folder / filename
        series.to_csv(path, index=False, header=False)
        print(f"saved {name}: {path}")


if __name__ == "__main__":
    main()
