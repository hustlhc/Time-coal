
import subprocess
import pandas as pd
import os
import argparse
parser = argparse.ArgumentParser(description="自动执行微调/推理脚本并合并结果")
parser.add_argument("--finetune", type=int, default=0, help="是否执行微调阶段脚本 (1=执行, 0=跳过)")
parser.add_argument("--infer", type=int, default=0, help="是否执行推理阶段脚本 (1=执行, 0=跳过)")
parser.add_argument("--sync", type=int, default=1, help="是否在推理后同步6个煤价指数走势 (1=执行, 0=跳过)")
parser.add_argument("--sync_strength", type=float, default=float(os.environ.get("SYNC_STRENGTH", 0.8)),
                    help="同步强度，0=不调整，1=完全共享相对趋势")
parser.add_argument(
    "--sync_anchor_mode",
    choices=["all_mean", "domestic_mean", "imported_mean"],
    default=os.environ.get("SYNC_ANCHOR_MODE", "imported_mean"),
    help="同步锚点：all_mean=6指数共同均值；domestic_mean=国内均值；imported_mean=进口均值",
)
parser.add_argument(
    "--sync_align_targets",
    choices=["all", "domestic", "imported"],
    default=os.environ.get("SYNC_ALIGN_TARGETS", "domestic"),
    help="同步对象：all=6条线都调整；domestic=只调整国内；imported=只调整进口",
)
parser.add_argument(
    "--forecast_mode",
    choices=["legacy", "trend"],
    default=os.environ.get("COAL_FORECAST_MODE", "legacy"),
    help="煤价预测模式：legacy=老的6个单模型流程；trend=趋势优先6指数联合模型",
)
parser.add_argument(
    "--trend_train_on_infer",
    type=int,
    default=int(os.environ.get("COAL_TREND_TRAIN_ON_INFER", 0)),
    help="trend模式推理时是否顺便训练/测试 (1=训练后推理, 0=直接加载已有checkpoint推理)",
)
args = parser.parse_args()
scripts1 = [
    "scripts/long_term_forecast/autocoal/CCI4500.sh",
    "scripts/long_term_forecast/autocoal/CCI5000.sh",
    "scripts/long_term_forecast/autocoal/CCI5500.sh",
    "scripts/long_term_forecast/autocoal/CCI3800out.sh",
    "scripts/long_term_forecast/autocoal/CCI4700out.sh",
    "scripts/long_term_forecast/autocoal/CCI5500out.sh"
]
scripts2 = [
    "scripts/long_term_forecast/autocoal/CCI4500infer.sh",
    "scripts/long_term_forecast/autocoal/CCI5000infer.sh",
    "scripts/long_term_forecast/autocoal/CCI5500infer.sh",
    "scripts/long_term_forecast/autocoal/CCI3800outinfer.sh",
    "scripts/long_term_forecast/autocoal/CCI4700outinfer.sh",
    "scripts/long_term_forecast/autocoal/CCI5500outinfer.sh"
]
csv_files = [
        "autoinfer/CCI3800outinfer.csv",
        "autoinfer/CCI4700outinfer.csv",
        "autoinfer/CCI5500outinfer.csv",
        "autoinfer/CCI4500infer.csv",
        "autoinfer/CCI5000infer.csv",
        "autoinfer/CCI5500infer.csv",
]


def run_command(command, env=None):
    print(f"正在运行: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    print("stdout:", result.stdout)
    print("stderr:", result.stderr)
    if result.returncode != 0:
        print(f"❌ 命令执行失败: {' '.join(command)}")
        return False
    return True


def trend_env(run_train, run_infer, run_teninfer):
    env = os.environ.copy()
    env.update({
        "SEQ_LEN": env.get("SEQ_LEN", "32"),
        "MODEL_TAG": env.get("MODEL_TAG", "_seq32_shortfirst"),
        "RUN_TRAIN": str(run_train),
        "RUN_INFER": str(run_infer),
        "RUN_TENINFER": str(run_teninfer),
        "TESTRESULT_FOLDER": env.get("TESTRESULT_FOLDER", "testresult/sync_sweep/seq32_shortfirst"),
        "AUTOINFER_FOLDER": env.get("AUTOINFER_FOLDER", "autoinfer"),
        "TENINFER_FOLDER": env.get("TENINFER_FOLDER", "teninfer"),
        "SYNC_INFER_TARGETS": env.get("SYNC_INFER_TARGETS", "0"),
        "POST_SYNC_FORECASTS": env.get("POST_SYNC_FORECASTS", "0"),
        "USE_LEVEL_DELTA_CORRECTION": env.get("USE_LEVEL_DELTA_CORRECTION", "0"),
        "SYNC_STRENGTH": str(args.sync_strength),
        "SYNC_ANCHOR_MODE": args.sync_anchor_mode,
        "SYNC_ALIGN_TARGETS": args.sync_align_targets,
        "SMOOTH_OUTPUTS": env.get("SMOOTH_OUTPUTS", "1"),
        "FORECAST_LOSS": env.get("FORECAST_LOSS", "mse"),
        "USE_SHORT_HORIZON_WEIGHT_LOSS": env.get("USE_SHORT_HORIZON_WEIGHT_LOSS", "1"),
        "SHORT_HORIZON_WEIGHT_DAYS": env.get("SHORT_HORIZON_WEIGHT_DAYS", "20"),
        "SHORT_HORIZON_WEIGHT": env.get("SHORT_HORIZON_WEIGHT", "3.0"),
        "SHORT_HORIZON_WEIGHT_NORMALIZE": env.get("SHORT_HORIZON_WEIGHT_NORMALIZE", "1"),
        "USE_ACC_LOSS": env.get("USE_ACC_LOSS", "0"),
        "ACC_LOSS_WEIGHT": env.get("ACC_LOSS_WEIGHT", "0.0"),
        "USE_SHORT_TREND_LOSS": env.get("USE_SHORT_TREND_LOSS", "1"),
        "SHORT_TREND_LOSS_WEIGHT": env.get("SHORT_TREND_LOSS_WEIGHT", "2.0"),
        "SHORT_TREND_MONTH_LEN": env.get("SHORT_TREND_MONTH_LEN", "5"),
        "SHORT_TREND_MONTH_WEIGHTS": env.get(
            "SHORT_TREND_MONTH_WEIGHTS",
            "0.45,0.22,0.11,0.07,0.05,0.035,0.025,0.015,0.01,0.005",
        ),
        "SHORT_TREND_MAX_SEGMENTS": env.get("SHORT_TREND_MAX_SEGMENTS", "10"),
        "SYNC_LOSS_WEIGHT": env.get("SYNC_LOSS_WEIGHT", "0.02"),
    })
    return env


def run_trend_pipeline(run_train, run_infer, run_teninfer):
    return run_command(
        ["bash", "scripts/long_term_forecast/autocoal_sync/run_joint.sh"],
        env=trend_env(run_train, run_infer, run_teninfer),
    )


def merge_csv_as_columns(files, output_file):
    """
    将多个CSV文件按列合并，列名为文件名
    :param files: CSV文件路径列表
    :param output_file: 输出合并后的CSV路径
    """
    dfs = []
    for f in files:
        try:
            # 只取第一列或单列数据（假设CSV只有一列数据）
            df = pd.read_csv(f)

            # 如果有多列，可以按需求选取，这里默认取第一列
            if df.shape[1] > 1:
                series = df.iloc[:, 0]
            else:
                series = df.squeeze("columns")

            # 列名改成文件名（去掉路径和扩展名）
            col_name = os.path.splitext(os.path.basename(f))[0]
            dfs.append(series.rename(col_name))

            print(f"✅ 已加载 {f} → 列名: {col_name}")

        except Exception as e:
            print(f"❌ 读取 {f} 失败: {e}")

    if dfs:
        merged_df = pd.concat(dfs, axis=1)
        merged_df.to_csv(output_file, index=False, encoding="utf-8-sig")
        print(f"🎉 合并完成，输出到 {output_file}")
    else:
        print("⚠️ 没有成功读取任何CSV文件")
if args.forecast_mode == "trend":
    if args.finetune == 1:
        if not run_trend_pipeline(run_train=1, run_infer=0, run_teninfer=0):
            raise SystemExit(1)
    if args.infer == 1:
        if not run_trend_pipeline(
            run_train=args.trend_train_on_infer,
            run_infer=1,
            run_teninfer=1,
        ):
            raise SystemExit(1)
    raise SystemExit(0)

if args.finetune == 1:
    for script in scripts1:
        if not run_command(["bash", script]):
            print(f"❌ 脚本 {script} 执行失败，中断后续执行")
            break   
if args.infer == 1:
    infer_failed = False
    for script in scripts2:
        if not run_command(["bash", script]):
            print(f"❌ 脚本 {script} 执行失败，中断后续执行")
            infer_failed = True
            break
    if not infer_failed and args.sync == 1:
        print("正在同步6个煤价指数预测走势")
        result = subprocess.run(
            [
                "python",
                "autoinfer/sync_forecasts.py",
                "--folder",
                "autoinfer",
                "--strength",
                str(args.sync_strength),
                "--anchor-mode",
                args.sync_anchor_mode,
                "--align-targets",
                args.sync_align_targets,
            ],
            capture_output=True,
            text=True,
        )
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        if result.returncode != 0:
            print("❌ 同步预测走势失败")
    #merge_csv_as_columns(csv_files, "autoinfer/coalinfer.csv")
