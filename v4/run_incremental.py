#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量更新主入口

用法:
    python run_incremental.py                    # 昨日增量
    python run_incremental.py --day 2025-09-26   # 指定日期
    python run_incremental.py --backfill 7       # 回填7天
    python run_incremental.py --only-coal        # 只更新煤价
    python run_incremental.py --only-freight     # 只更新运费
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

from config.config_loader import get_config
from incremental_update.core import IncrementalUpdater
from incremental_update.fetcher import DataFetcher


def setup_logging(config):
    """设置日志"""
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO"))
    log_format = log_config.get(
        "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    handlers = [logging.StreamHandler()]

    # 日志文件（如果配置）
    log_file = log_config.get("file")
    if log_file:
        # 替换日期占位符
        log_file = log_file.replace("{date}", datetime.now().strftime("%Y%m%d"))
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(level=level, format=log_format, handlers=handlers)


def get_date_list(day: str = None, backfill: int = None) -> list:
    """
    生成日期列表

    Args:
        day: 指定日期 (YYYY-MM-DD)
        backfill: 回填天数

    Returns:
        日期列表
    """
    if day:
        return [day]

    if backfill and backfill > 0:
        return [
            (datetime.today() - timedelta(days=i + 1)).strftime("%Y-%m-%d")
            for i in range(backfill)
        ]

    # 默认昨天
    return [(datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")]


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Coal Data Incremental Update V4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s                    # 昨日增量
  %(prog)s --day 2025-09-26   # 指定日期
  %(prog)s --backfill 7       # 回填7天
  %(prog)s --only-coal        # 只更新煤价
  %(prog)s --only-freight     # 只更新运费
  %(prog)s --config config/my_config.yaml  # 自定义配置
        """,
    )

    # 日期参数
    parser.add_argument("--day", help="指定日期 (YYYY-MM-DD)")
    parser.add_argument("--backfill", type=int, help="回填天数（从昨天往前）")

    # 更新范围
    parser.add_argument("--only-coal", action="store_true", help="只更新煤价数据")
    parser.add_argument("--only-freight", action="store_true", help="只更新运费数据")

    # 配置文件
    parser.add_argument("--config", help="配置文件路径 (默认: config/config.yaml)")

    # 调试选项
    parser.add_argument(
        "--keep-intermediate", action="store_true", help="保留中间文件（调试用）"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="空运行（不执行数据获取）"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    args = parser.parse_args()

    # 加载配置
    try:
        config_loader = get_config(args.config)
        config_dict = config_loader.to_dict()

        if not config_loader.validate():
            print("配置验证失败，请检查配置文件")
            return 1

    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("提示: cp config/config.example.yaml config/config.yaml")
        return 1
    except Exception as e:
        print(f"加载配置失败: {e}")
        return 1

    # 设置日志
    logging_cfg = config_dict.setdefault("logging", {})
    if args.verbose:
        logging_cfg["level"] = "DEBUG"
    setup_logging(config_dict)

    logger = logging.getLogger(__name__)

    # 生成日期列表
    update_dates = get_date_list(args.day, args.backfill)

    logger.info("=" * 70)
    logger.info("Coal Data Incremental Update V4")
    logger.info("=" * 70)
    logger.info(f"配置文件: {config_loader.config_path}")
    logger.info(f"原始数据: {config_dict['data']['raw_data_root']}")
    logger.info(f"输出目录: {config_dict['data']['output_dir']}")
    logger.info(f"更新日期: {update_dates}")

    # 空运行模式
    if args.dry_run:
        logger.info("--- 空运行模式，仅显示配置 ---")
        import yaml

        print(yaml.dump(config_dict, allow_unicode=True, default_flow_style=False))
        return 0

    incremental_cfg = config_dict.get("incremental", {})
    mode = str(incremental_cfg.get("mode", "legacy")).lower()
    direct_mode = mode == "direct"
    use_cci_gate = incremental_cfg.get("use_cci_gate", True)

    fetcher = DataFetcher(config_dict.get("api", {}), app_root=Path(__file__).parent)
    updater = IncrementalUpdater(config_dict, fetcher=fetcher)

    if direct_mode:
        if args.keep_intermediate:
            logger.warning("direct 模式会自动清理中间文件，忽略 --keep-intermediate 参数。")
        try:
            return updater.run_direct(
                update_dates=update_dates,
                only_coal=args.only_coal,
                only_freight=args.only_freight,
                use_cci_gate=use_cci_gate,
            )
        except Exception as exc:
            logger.error("direct 模式执行失败: %s", exc, exc_info=True)
            return 1

    try:
        raw_root = config_dict["data"]["raw_data_root"]
        fetch_rc, kept_days = fetcher.fetch_for_dates(update_dates, raw_root, use_cci_gate=use_cci_gate)
    except FileNotFoundError as exc:
        logger.error("API 配置文件缺失: %s", exc)
        return 1
    except Exception as exc:
        logger.error("数据抓取失败: %s", exc, exc_info=True)
        return 1

    if not kept_days:
        logger.info("本次没有可用的增量日期，流程结束。")
        return fetch_rc

    update_dates = kept_days

    pipeline_rc = updater.run(
        update_dates=update_dates,
        only_coal=args.only_coal,
        only_freight=args.only_freight,
        keep_intermediate=args.keep_intermediate,
    )

    return max(fetch_rc, pipeline_rc)


if __name__ == "__main__":
    sys.exit(main())
