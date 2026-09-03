# -*- coding: utf-8 -*-
"""Generate 2024 monthly procurement estimates from daily stock data.

Input:
  data/24各电厂存煤量_已补充CCI.csv

Assumption (important):
  - Treat the series column `存煤量` as total stock.
  - For each month, take the last available daily `存煤量` as month-end stock.
  - Estimate monthly procurement as max(month_end_stock - prev_month_end_stock, 0).

Outputs:
  - procure_plan/procurement_2024_from_stock.csv
  - procure_plan/procurement_2024_from_stock.json

Usage:
  python generate_procurement_2024.py
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple


DEFAULT_INPUT = os.path.join("data", "24各电厂存煤量_已补充CCI.csv")
DEFAULT_OUT_DIR = "procure_plan"
DEFAULT_OUT_BASENAME = "procurement_2024_from_stock"


@dataclass
class MonthlyRow:
    year_month: str
    month_start_date: str
    month_end_date: str
    month_start_stock: float
    month_end_stock: float
    prev_month_end_stock: Optional[float]
    net_change: Optional[float]
    procurement_est: Optional[float]


def _parse_period_id(period_id: str) -> datetime:
    period_id = str(period_id).strip()
    # expected yyyymmdd
    return datetime.strptime(period_id, "%Y%m%d")


def _to_float(value: str) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    try:
        return float(s)
    except Exception:
        return None


def load_daily_stock(csv_path: str) -> List[Tuple[datetime, float]]:
    """Load (date, stock) from CSV, skipping rows without stock."""
    rows: List[Tuple[datetime, float]] = []
    # NOTE: file may contain UTF-8 BOM, use utf-8-sig to strip it.
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header")

        # Normalize field names (strip whitespace + BOM)
        fieldnames_norm = [str(x).strip().lstrip("\ufeff") for x in reader.fieldnames]
        # Map normalized -> original
        norm_to_orig = {str(orig).strip().lstrip("\ufeff"): orig for orig in reader.fieldnames}

        if "period_id" not in fieldnames_norm or "存煤量" not in fieldnames_norm:
            raise ValueError(f"CSV missing required columns: {reader.fieldnames}")

        period_key = norm_to_orig["period_id"]
        stock_key = norm_to_orig["存煤量"]

        for r in reader:
            d = _parse_period_id(r.get(period_key, ""))
            stock = _to_float(r.get(stock_key))
            if stock is None:
                continue
            rows.append((d, float(stock)))

    rows.sort(key=lambda x: x[0])
    return rows


def group_month_end(rows: List[Tuple[datetime, float]], year: int) -> Dict[str, Dict[str, object]]:
    """Return mapping year_month -> {start_date,end_date,start_stock,end_stock}."""
    by_month: Dict[str, Dict[str, object]] = {}
    for d, stock in rows:
        if d.year != year:
            continue
        ym = f"{d.year:04d}-{d.month:02d}"
        if ym not in by_month:
            by_month[ym] = {
                "start_date": d,
                "end_date": d,
                "start_stock": stock,
                "end_stock": stock,
            }
        else:
            # update end as we iterate sorted
            by_month[ym]["end_date"] = d
            by_month[ym]["end_stock"] = stock

    # Ensure deterministic order by month
    return dict(sorted(by_month.items(), key=lambda kv: kv[0]))


def compute_monthly_procurement(by_month: Dict[str, Dict[str, object]]) -> List[MonthlyRow]:
    out: List[MonthlyRow] = []
    prev_end: Optional[float] = None

    for ym, info in by_month.items():
        start_date: datetime = info["start_date"]  # type: ignore[assignment]
        end_date: datetime = info["end_date"]  # type: ignore[assignment]
        start_stock = float(info["start_stock"])  # type: ignore[arg-type]
        end_stock = float(info["end_stock"])  # type: ignore[arg-type]

        if prev_end is None:
            # Jan: we don't have last month's end; we still output diagnostics.
            net_change = end_stock - start_stock
            procurement = max(net_change, 0.0)
            prev_end_stock = None
            net_change_out: Optional[float] = net_change
            procurement_out: Optional[float] = procurement
        else:
            net_change = end_stock - prev_end
            procurement = max(net_change, 0.0)
            prev_end_stock = prev_end
            net_change_out = net_change
            procurement_out = procurement

        out.append(
            MonthlyRow(
                year_month=ym,
                month_start_date=start_date.strftime("%Y-%m-%d"),
                month_end_date=end_date.strftime("%Y-%m-%d"),
                month_start_stock=start_stock,
                month_end_stock=end_stock,
                prev_month_end_stock=prev_end_stock,
                net_change=net_change_out,
                procurement_est=procurement_out,
            )
        )

        prev_end = end_stock

    return out


def write_outputs(rows: List[MonthlyRow], out_dir: str, basename: str) -> Tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)

    csv_path = os.path.join(out_dir, f"{basename}.csv")
    json_path = os.path.join(out_dir, f"{basename}.json")

    fieldnames = [
        "year_month",
        "month_start_date",
        "month_end_date",
        "month_start_stock",
        "month_end_stock",
        "prev_month_end_stock",
        "net_change",
        "procurement_est",
    ]

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(asdict(r))

    payload = {
        "assumption": "procurement_est = max(month_end_stock - prev_month_end_stock, 0); for the first month use (end-start)",
        "rows": [asdict(r) for r in rows],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return csv_path, json_path


def main() -> None:
    csv_path = os.environ.get("STOCK_CSV", DEFAULT_INPUT)
    out_dir = os.environ.get("OUT_DIR", DEFAULT_OUT_DIR)
    basename = os.environ.get("OUT_BASENAME", DEFAULT_OUT_BASENAME)

    daily = load_daily_stock(csv_path)
    by_month = group_month_end(daily, year=2024)
    monthly = compute_monthly_procurement(by_month)
    out_csv, out_json = write_outputs(monthly, out_dir=out_dir, basename=basename)

    total_proc = sum(r.procurement_est or 0.0 for r in monthly)
    print(f"OK: wrote {out_csv}")
    print(f"OK: wrote {out_json}")
    print(f"2024 total procurement_est: {total_proc:.2f}")


if __name__ == "__main__":
    main()
