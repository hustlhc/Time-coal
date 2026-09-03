#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对预测结果进行平滑处理，并将首个预测点锚定到最新真实值。

支持平滑方法：
- moving_average: 滑动平均
- ema: 指数加权平均
- median: 中值滤波
- savgol: Savitzky-Golay 平滑

用法：
    python smooth_csv.py pred.csv output.csv [method] [--round] [--true-col -1]
"""
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import medfilt, savgol_filter
import numpy as np

# 固定真实数据路径（请改为你自己的）
DATASET_PATH = "./dataset/pre_coal/coal_new.csv"

# ===================== 平滑函数 =====================
def smooth_moving_average(data, window_size=5):
    return pd.Series(data).rolling(window=window_size, min_periods=1, center=True).mean().tolist()

def smooth_ema(data, alpha=0.3):
    return pd.Series(data).ewm(alpha=alpha, adjust=False).mean().tolist()

def smooth_median(data, kernel_size=5):
    return medfilt(data, kernel_size=kernel_size)

def smooth_savgol(data, window_length=7, polyorder=2):
    if window_length > len(data):
        window_length = len(data) // 2 * 2 + 1
    return savgol_filter(data, window_length=window_length, polyorder=polyorder)

def smooth_and_anchor(data, latest_real, method="savgol"):
    """
    Smooth the complete raw forecast, then apply one constant level offset.

    The offset anchors the smoothed first point to the latest real value.
    It changes only the curve level, while all trend and shape information
    continues to come from the model output and the selected smoother.
    """
    values = np.asarray(data, dtype=float)
    if values.size == 0:
        return values.copy()

    if method == "moving_average":
        smoothed = smooth_moving_average(values, window_size=5)
    elif method == "ema":
        smoothed = smooth_ema(values, alpha=0.3)
    elif method == "median":
        smoothed = smooth_median(values, kernel_size=5)
    elif method == "savgol":
        smoothed = smooth_savgol(values, window_length=9, polyorder=2)
    else:
        raise ValueError(f"未知平滑方法: {method}")

    smoothed = np.asarray(smoothed, dtype=float)
    level_offset = float(latest_real) - float(smoothed[0])
    return smoothed + level_offset

# ===================== 主逻辑 =====================
def smooth_csv(pred_file, output_file, method="moving_average", do_round=False, true_col=-1):
    # 1️⃣ 读取预测值
    pred = pd.read_csv(pred_file, header=None).iloc[:, 0].astype(float).tolist()

    # 2️⃣ 读取真实值
    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"❌ 未找到真实数据文件：{DATASET_PATH}")
    df_true = pd.read_csv(DATASET_PATH)
    real = df_true.iloc[:, true_col].astype(float).tolist()
    real_tail = real[-5:]

    # 3️⃣ 只平滑原始预测，再整体平移到最新真实值。
    # 不再外推最近5日斜率，也不再混合预测前5点。
    smoothed_pred = smooth_and_anchor(pred, real_tail[-1], method)

    # 6️⃣ 可选四舍五入
    if do_round:
        smoothed_pred = [round(x) for x in smoothed_pred]

    # 7️⃣ 保存结果（单列、无表头）
    pd.DataFrame(smoothed_pred).to_csv(output_file, header=False, index=False)
    print(f"✅ 已保存平滑结果到 {output_file}")
    print(f"方法: {method} | 四舍五入: {do_round} | 使用真实值列: 倒数第 {abs(true_col)} 列")

    # 8️⃣ 绘图比较
    plt.figure(figsize=(10, 5))
    x_real = range(len(real_tail))
    x_pred = range(len(real_tail), len(real_tail) + len(pred))

    plt.plot(x_real, real_tail, label="true (last 5)", color="green", linewidth=2)
    plt.plot(x_pred, pred, label="original pred", color="gray", alpha=0.6)
    plt.plot(x_pred, smoothed_pred, label=f"smoothed ({method})", color="red", linewidth=2)

    plt.title(f"Prediction smoothing with real tail connection ({method})", fontsize=14)
    plt.xlabel("Time index")
    plt.ylabel("Value")
    plt.legend()
    plt.grid(True)

    img_path = os.path.splitext(output_file)[0] + "_smooth.png"
    plt.savefig(img_path, dpi=200, bbox_inches="tight")
    plt.show()
    print(f"📊 已保存平滑衔接对比图：{img_path}")

# ===================== 命令行入口 =====================
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python smooth_csv.py pred.csv output.csv [method] [--round] [--true-col -1]")
        sys.exit(1)

    pred_file = sys.argv[1]
    output_file = sys.argv[2]
    method = "savgol"
    do_round = False
    true_col = -1  # 默认最后一列

    for i, arg in enumerate(sys.argv[3:]):
        if arg.lower() in ["moving_average", "ema", "median", "savgol"]:
            method = arg.lower()
        elif arg in ["--round", "--int"]:
            do_round = True
        elif arg in ["--true-col", "--true", "-t"]:
            try:
                true_col = int(sys.argv[3 + i + 1])
            except:
                print("⚠️ 参数错误：请在 --true-col 后输入整数（如 -1 表示倒数第一列）")
                sys.exit(1)

    smooth_csv(pred_file, output_file, method, do_round, true_col)
