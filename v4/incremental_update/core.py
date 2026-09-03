#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Incremental update core logic."""

import logging
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Dict, Any, Optional, Sequence

from pipeline.coal_data_processor import CoalDataProcessor
from .stabilizer import HistoryStabilizer
from .filler import ForwardFiller

logger = logging.getLogger(__name__)


class IncrementalUpdater:
    """Incremental data updater."""

    def __init__(self, config: Dict[str, Any], fetcher=None):
        self.config = config
        self.data_config = config.get("data", {})
        self.incremental_config = config.get("incremental", {})
        self.fetcher = fetcher
        self._latest_cci_path: Optional[Path] = None

        self.raw_data_root = (
            Path(self.data_config.get("raw_data_root", ".")).expanduser().resolve()
        )
        self.output_dir = (
            Path(self.data_config.get("output_dir", ".")).expanduser().resolve()
        )
        self.coal_baseline = (
            Path(self.data_config.get("baseline", {}).get("coal", "coal_new.csv"))
            .expanduser()
            .resolve()
        )
        self.freight_baseline = (
            Path(
                self.data_config.get("baseline", {}).get("freight", "coal_freight.csv")
            )
            .expanduser()
            .resolve()
        )

        self.coal_stabilizer: Optional[HistoryStabilizer] = None
        self.freight_stabilizer: Optional[HistoryStabilizer] = None

        self.stabilization_enabled = self.incremental_config.get(
            "stabilization", {}
        ).get("enabled", True)
        self.forward_fill_enabled = self.incremental_config.get("forward_fill", {}).get(
            "enabled", True
        )

        self.mode = str(self.incremental_config.get("mode", "legacy")).lower()
        self.direct_mode = self.mode == "direct"

    def run(
        self,
        update_dates: List[str],
        only_coal: bool = False,
        only_freight: bool = False,
        keep_intermediate: bool = False,
    ) -> int:
        if self.direct_mode:
            logger.info("Current mode is direct; using the direct pipeline.")
            use_cci_gate = self.incremental_config.get("use_cci_gate", True)
            return self.run_direct(
                update_dates,
                only_coal=only_coal,
                only_freight=only_freight,
                use_cci_gate=use_cci_gate,
            )

        raw_dirs = self._default_raw_dirs()
        return self._process(
            update_dates, only_coal, only_freight, keep_intermediate, raw_dirs
        )

    def run_direct(
        self,
        update_dates: Sequence[str],
        only_coal: bool = False,
        only_freight: bool = False,
        use_cci_gate: bool = True,
    ) -> int:
        if not update_dates:
            logger.info("No update dates provided; direct pipeline finished.")
            return 0

        fetcher = self.fetcher
        if fetcher is None:
            from .fetcher import DataFetcher  # lazy import to avoid cycles

            env_root = self.config.get("env", {}).get("app_root")
            app_root = (
                Path(env_root) if env_root else Path(__file__).resolve().parent.parent
            )
            fetcher = DataFetcher(self.config.get("api", {}), app_root=app_root)

        with TemporaryDirectory(prefix="coal_direct_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            fetch_rc, kept_days = fetcher.fetch_for_dates(
                update_dates,
                str(tmp_path),
                use_cci_gate=use_cci_gate,
            )
            if not kept_days:
                logger.info("No incremental dates with usable data; skipping pipeline.")
                return fetch_rc

            raw_dirs = self._resolve_raw_dirs(tmp_path)
            pipeline_rc = self._process(
                kept_days,
                only_coal,
                only_freight,
                keep_intermediate=False,
                raw_dirs=raw_dirs,
            )

        self._remove_extra_files()
        return max(fetch_rc, pipeline_rc)

    def _process(
        self,
        update_dates: Sequence[str],
        only_coal: bool,
        only_freight: bool,
        keep_intermediate: bool,
        raw_dirs: List[str],
    ) -> int:
        dates_display = list(update_dates)
        logger.info("=" * 60)
        logger.info("Starting incremental update: %s", dates_display)
        logger.info(
            "Update coal: %s, update freight: %s", not only_freight, not only_coal
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)

        rc = 0
        if not only_freight:
            try:
                self._update_coal(dates_display, keep_intermediate, raw_dirs)
            except Exception as exc:
                logger.error("Coal update failed: %s", exc, exc_info=True)
                rc = 1

        if not only_coal:
            try:
                self._update_freight(dates_display, keep_intermediate, raw_dirs)
            except Exception as exc:
                logger.error("Freight update failed: %s", exc, exc_info=True)
                rc = 1

        if rc == 0:
            logger.info("✓ Incremental update complete")
        else:
            logger.error("✗ Incremental update finished with errors")
        logger.info("=" * 60)
        return rc

    def _update_coal(
        self, update_dates: List[str], keep_intermediate: bool, raw_dirs: List[str]
    ):
        logger.info("-" * 60)
        logger.info("Updating coal data")
        logger.info("-" * 60)

        coal_config = self._build_coal_config(raw_dirs)
        processor = CoalDataProcessor(coal_config)
        processor.run_full_pipeline()

        output_path = self._coal_primary_output()
        if not output_path.exists():
            output_path = self._coal_alias_path()

        if update_dates:
            try:
                self._refresh_cci_columns(update_dates)
            except Exception as exc:
                logger.warning(
                    "Failed to refresh CCI columns with latest data: %s", exc
                )

        if (
            self.stabilization_enabled
            and self.coal_baseline.exists()
            and output_path.exists()
        ):
            logger.info("Applying coal history stabilisation...")
            if self.coal_stabilizer is None:
                self.coal_stabilizer = HistoryStabilizer(self.coal_baseline)

            import pandas as pd

            new_df = pd.read_csv(output_path, encoding="utf-8-sig")
            result_df = self.coal_stabilizer.merge_with_incremental(
                new_df, update_dates
            )

            if self.forward_fill_enabled:
                logger.info("Applying coal forward fill...")
                result_df = ForwardFiller.fill_incremental_rows(
                    result_df,
                    update_dates,
                    preserve_history=True,
                )

            if self.coal_stabilizer.validate_merge(result_df):
                result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
                logger.info("✓ Coal data saved: %s", output_path)
            else:
                logger.error("Coal merge validation failed; results not saved")

        output_path = self._finalize_output_file(
            output_path,
            self._coal_alias_path(),
            "coal",
        )
        self._sync_baseline_file(output_path, self.coal_baseline, "coal baseline")

        if not keep_intermediate:
            self._cleanup_intermediate()

    def _update_freight(
        self, update_dates: List[str], keep_intermediate: bool, raw_dirs: List[str]
    ):
        logger.info("-" * 60)
        logger.info("Updating freight data")
        logger.info("-" * 60)

        freight_config = self._build_freight_config(raw_dirs)
        processor = CoalDataProcessor(freight_config)
        processor.run_full_pipeline()

        output_path = self._freight_primary_output()

        if (
            self.stabilization_enabled
            and self.freight_baseline.exists()
            and output_path.exists()
        ):
            logger.info("Applying freight history stabilisation...")
            if self.freight_stabilizer is None:
                self.freight_stabilizer = HistoryStabilizer(self.freight_baseline)

            import pandas as pd

            new_df = pd.read_csv(output_path, encoding="utf-8-sig")
            result_df = self.freight_stabilizer.merge_with_incremental(
                new_df, update_dates
            )

            if self.forward_fill_enabled:
                logger.info("Applying freight forward fill...")
                result_df = ForwardFiller.fill_incremental_rows(
                    result_df,
                    update_dates,
                    preserve_history=True,
                )

            if self.freight_stabilizer.validate_merge(result_df):
                result_df.to_csv(output_path, index=False, encoding="utf-8-sig")
                logger.info("✓ Freight data saved: %s", output_path)
            else:
                logger.error("Freight merge validation failed; results not saved")

        reference_path = self._coal_reference_path()
        if output_path.exists() and reference_path.exists():
            self._align_with_reference_timeline(output_path, reference_path, "freight")

        output_path = self._finalize_output_file(
            output_path,
            self._freight_alias_path(),
            "freight",
        )
        self._sync_baseline_file(output_path, self.freight_baseline, "freight baseline")

        if not keep_intermediate:
            self._cleanup_intermediate()

    def _build_coal_config(self, raw_dirs: List[str]) -> Dict[str, Any]:
        cci_timeline = self.data_config.get("cci_timeline")
        cci_processed = self.data_config.get("cci_processed_path") or cci_timeline
        zmw_reference = self.data_config.get("zmw_reference")
        cci_coal_source = self.data_config.get("cci_coal_source")

        dynamic_cci = self._find_latest_cci_file(raw_dirs, ("00000019", "cci"))
        self._latest_cci_path = dynamic_cci

        config: Dict[str, Any] = {
            "raw_data_dirs": raw_dirs,
            "output_dir": str(self.output_dir),
            "target_data_path": str(self.coal_baseline),
            "final_base_name": "coal_new",
            "save_with_cci6_final": True,
            "save_base_final": False,
            "enable_coal_new_cci_repair": False,
        }

        if dynamic_cci:
            config["cci_timeline_file"] = str(dynamic_cci)
            config["cci_processed_path"] = str(dynamic_cci)
        else:
            if cci_timeline:
                config["cci_timeline_file"] = str(cci_timeline)
            if cci_processed:
                config["cci_processed_path"] = str(cci_processed)

        if zmw_reference:
            config["zmw_ref_path"] = str(zmw_reference)
        if cci_coal_source:
            config["cci_coal_new_path"] = str(cci_coal_source)

        return config

    def _build_freight_config(self, raw_dirs: List[str]) -> Dict[str, Any]:
        cci_timeline = self.data_config.get("cci_timeline")

        config: Dict[str, Any] = {
            "raw_data_dirs": raw_dirs,
            "output_dir": str(self.output_dir),
            "target_data_path": str(self.freight_baseline),
            "final_base_name": "coal_freight_final",
            "strict_target_only": True,
            "save_with_cci6_final": False,
        }

        if cci_timeline:
            config["cci_timeline_file"] = str(cci_timeline)

        return config

    def _refresh_cci_columns(self, update_dates: Sequence[str]) -> None:
        if not self._latest_cci_path:
            return

        target_file = self._coal_reference_path()
        if not target_file.exists():
            return

        try:
            import pandas as pd
        except Exception as exc:
            logger.warning("pandas unavailable, cannot refresh CCI columns: %s", exc)
            return

        try:
            df = pd.read_csv(target_file, encoding="utf-8-sig")
        except Exception as exc:
            logger.warning("Failed to read %s: %s", target_file, exc)
            return

        if df.empty:
            return

        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
        target_dates = {
            pd.to_datetime(d, errors="coerce").normalize() for d in update_dates if d
        }
        target_dates.discard(pd.NaT)
        if not target_dates:
            return

        try:
            cci_df = pd.read_csv(self._latest_cci_path, encoding="utf-8-sig")
        except Exception as exc:
            logger.warning(
                "Failed to read latest CCI file %s: %s", self._latest_cci_path, exc
            )
            return

        if cci_df is None or cci_df.empty:
            return

        cci_date_col = cci_df.columns[0]
        cci_df[cci_date_col] = pd.to_datetime(
            cci_df[cci_date_col], errors="coerce"
        ).dt.normalize()
        updates = cci_df[cci_df[cci_date_col].isin(target_dates)].copy()
        if updates.empty:
            return

        cci_columns = [
            "CCI4500",
            "CCI5000",
            "CCI5500",
            "CCI进口3800",
            "CCI进口4700",
            "CCI进口5500",
        ]
        merge_cols = [
            col for col in cci_columns if col in updates.columns and col in df.columns
        ]
        if not merge_cols:
            return

        merged = df.merge(
            updates[[cci_date_col] + merge_cols],
            left_on=date_col,
            right_on=cci_date_col,
            how="left",
            suffixes=("", "__cci"),
        )

        for col in merge_cols:
            merged_col = f"{col}__cci"
            merged[col] = merged[merged_col].combine_first(merged[col])
            merged.drop(columns=[merged_col], inplace=True)

        merged.drop(columns=[cci_date_col], inplace=True)
        merged.to_csv(target_file, index=False, encoding="utf-8-sig")

        cci_timeline = self.data_config.get("cci_timeline")

        config: Dict[str, Any] = {
            "raw_data_dirs": raw_dirs,
            "output_dir": str(self.output_dir),
            "target_data_path": str(self.freight_baseline),
            "final_base_name": "coal_freight_final",
            "strict_target_only": True,
            "save_with_cci6_final": False,
        }

        if cci_timeline:
            config["cci_timeline_file"] = str(cci_timeline)

        return config

    def _find_latest_cci_file(
        self, raw_dirs: Sequence[str], tokens: Sequence[str]
    ) -> Optional[Path]:
        tokens_lower = [token.lower() for token in tokens]
        candidates: List[Path] = []

        for raw_dir in raw_dirs:
            if not raw_dir:
                continue
            base = Path(raw_dir)
            if not base.exists():
                continue
            try:
                for csv_file in base.rglob("*.csv"):
                    name_lower = csv_file.name.lower()
                    if all(token in name_lower for token in tokens_lower):
                        candidates.append(csv_file)
            except Exception:
                continue

        if not candidates:
            return None

        def score(path: Path) -> tuple[int, float]:
            prefer_60 = (
                1
                if any(part.endswith("60+") or part == "60+" for part in path.parts)
                else 0
            )
            try:
                mtime = path.stat().st_mtime
            except Exception:
                mtime = 0.0
            return prefer_60, mtime

        return max(candidates, key=score)

    def _default_raw_dirs(self) -> List[str]:
        return [
            str((self.raw_data_root / "500+").expanduser()),
            str((self.raw_data_root / "60+").expanduser()),
        ]

    def _resolve_raw_dirs(self, base: Path) -> List[str]:
        dirs: List[str] = []
        for name in ("500+", "60+"):
            target = base / name
            target.mkdir(parents=True, exist_ok=True)
            dirs.append(str(target))
        return dirs

    def _coal_primary_output(self) -> Path:
        return self.output_dir / "coal_new_with_cci6.csv"

    def _coal_alias_path(self) -> Path:
        return self.output_dir / self.coal_baseline.name

    def _coal_reference_path(self) -> Path:
        primary = self._coal_primary_output()
        if primary.exists():
            return primary
        return self._coal_alias_path()

    def _freight_primary_output(self) -> Path:
        return self.output_dir / "coal_freight_final.csv"

    def _freight_alias_path(self) -> Path:
        return self.output_dir / self.freight_baseline.name

    def _finalize_output_file(
        self, source: Path, desired: Path, label: str
    ) -> Path:
        try:
            source_path = Path(source)
            desired_path = Path(desired)
        except Exception:
            return source

        if not source_path.exists():
            if desired_path.exists():
                return desired_path
            logger.warning(
                "Cannot finalise %s output; source file missing: %s",
                label,
                source_path,
            )
            return source_path

        try:
            if source_path.resolve() == desired_path.resolve():
                return desired_path
        except Exception:
            pass

        if desired_path.exists() and desired_path != source_path:
            try:
                desired_path.unlink()
            except Exception:
                pass

        try:
            desired_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        try:
            source_path.rename(desired_path)
            logger.info("Renamed %s output to %s", label, desired_path)
            return desired_path
        except Exception as exc:
            logger.warning(
                "Failed to rename %s output to %s: %s (falling back to copy)",
                label,
                desired_path,
                exc,
            )
            try:
                shutil.copy2(source_path, desired_path)
                logger.info("Copied %s output to %s", label, desired_path)
                return desired_path
            except Exception as copy_exc:
                logger.error(
                    "Failed to copy %s output to %s: %s",
                    label,
                    desired_path,
                    copy_exc,
                )
                return source_path

    def _sync_baseline_file(self, source: Path, target: Path, label: str) -> None:
        if source is None or target is None:
            return

        try:
            source_path = Path(source)
            target_path = Path(target)
        except Exception:
            return

        if not source_path.exists():
            logger.warning(
                "Cannot sync %s; source file missing: %s", label, source_path
            )
            return

        try:
            if source_path.resolve() == target_path.resolve():
                return
        except Exception:
            pass

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        try:
            shutil.copy2(source_path, target_path)
            logger.info("Synchronized %s to %s", label, target_path)
        except Exception as exc:
            logger.error("Failed to sync %s to %s: %s", label, target_path, exc)

    def _align_with_reference_timeline(
        self, target_file: Path, reference_file: Path, label: str
    ) -> None:
        try:
            import pandas as pd
        except Exception as exc:
            logger.warning(
                "Cannot align %s timeline; pandas unavailable: %s", label, exc
            )
            return

        try:
            target_df = pd.read_csv(target_file, encoding="utf-8-sig")
            reference_df = pd.read_csv(
                reference_file, usecols=[0], encoding="utf-8-sig"
            )
        except Exception as exc:
            logger.warning(
                "Failed to read files for aligning %s timeline (%s, %s): %s",
                label,
                target_file,
                reference_file,
                exc,
            )
            return

        if target_df.empty or reference_df.empty:
            return

        target_col = target_df.columns[0]
        reference_col = reference_df.columns[0]

        target_df[target_col] = pd.to_datetime(
            target_df[target_col], errors="coerce"
        ).dt.normalize()
        allowed_dates = (
            pd.to_datetime(reference_df[reference_col], errors="coerce")
            .dropna()
            .dt.normalize()
        )
        allowed_set = set(allowed_dates.tolist())

        if not allowed_set:
            return

        filtered_df = target_df[target_df[target_col].isin(allowed_set)].copy()
        if filtered_df.empty:
            logger.warning(
                "Alignment skipped: no overlapping dates between %s and reference timeline %s",
                label,
                reference_file,
            )
            return

        filtered_df[target_col] = filtered_df[target_col].dt.strftime("%Y-%m-%d")
        filtered_df = filtered_df.sort_values(by=target_col).reset_index(drop=True)

        if len(filtered_df) != len(target_df):
            logger.info(
                "Aligned %s timeline with %s (rows %s -> %s)",
                label,
                reference_file,
                len(target_df),
                len(filtered_df),
            )

        try:
            filtered_df.to_csv(target_file, index=False, encoding="utf-8-sig")
        except PermissionError as exc:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fallback = target_file.with_name(
                f"{target_file.stem}_aligned_{timestamp}{target_file.suffix}"
            )
            try:
                filtered_df.to_csv(fallback, index=False, encoding="utf-8-sig")
                shutil.copy2(fallback, target_file)
                logger.warning(
                    "Permission issue when writing %s; wrote to %s and copied back",
                    target_file,
                    fallback,
                )
            except Exception as inner_exc:
                logger.error(
                    "Failed to copy aligned %s to %s due to %s; aligned file retained at %s",
                    label,
                    target_file,
                    inner_exc,
                    fallback,
                )
        except Exception as exc:
            logger.error(
                "Failed to write aligned %s file %s: %s", label, target_file, exc
            )

    def _cleanup_intermediate(self):
        cleanup_paths = [
            self.output_dir / "split_data",
            self.output_dir / "merged_coal_data.csv",
            self.output_dir / "timeline_custom.csv",
            self.output_dir / "coal_new_tmp.csv",
            self.output_dir / "coal_new_tmp_with_cci6.csv",
            self.output_dir / "split_summary.txt",
            self.output_dir / "tmp_output",
        ]
        for path in cleanup_paths:
            if path.exists():
                try:
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                except Exception as exc:
                    logger.debug("Failed to remove intermediate file %s: %s", path, exc)

    def _remove_extra_files(self):
        log_file = self.output_dir / "data_preprocessing.log"
        if log_file.exists():
            try:
                log_file.unlink()
            except Exception:
                pass
