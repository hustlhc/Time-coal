#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对预测结果进行平滑处理并可视化对比。

支持的平滑方法：
- moving_average: 滑动平均
- ema: 指数加权平均
- median: 中值滤波
- savgol: Savitzky-Golay 平滑

用法：
    python smooth_csv.py input.csv output.csv [method] [--round]
"""
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import medfilt, savgol_filter

# ===================== 平滑函数定义 =====================
def smooth_moving_average(data, window_size=5):
    return pd.Series(data).rolling(window=window_size, min_periods=1, center=True).mean().tolist()

def smooth_ema(data, alpha=0.3):
    return pd.Series(data).ewm(alpha=alpha, adjust=False).mean().tolist()

def smooth_median(data, kernel_size=5):
    return medfilt(data, kernel_size=kernel_size)

def smooth_savgol(data, window_length=7, polyorder=2):
    if window_length > len(data):
        window_length = len(data) // 2 * 2 + 1  # 确保奇数
    return savgol_filter(data, window_length=window_length, polyorder=polyorder)

# ===================== 主处理逻辑 =====================
def smooth_csv(input_file, output_file, method="moving_average", do_round=False):
    df = pd.read_csv(input_file, header=None)
    data = df.iloc[:, 0].astype(float).tolist()

    # 选择平滑方法
    if method == "moving_average":
        smoothed = smooth_moving_average(data, window_size=5)
    elif method == "ema":
        smoothed = smooth_ema(data, alpha=0.3)
    elif method == "median":
        smoothed = smooth_median(data, kernel_size=5)
    elif method == "savgol":
        smoothed = smooth_savgol(data, window_length=9, polyorder=2)
    else:
        raise ValueError(f"未知平滑方法: {method}")

    # 可选四舍五入
    if do_round:
        smoothed = [round(x) for x in smoothed]

    # 输出只有一列、无表头
    pd.DataFrame(smoothed).to_csv(output_file, header=False, index=False)
    print(f"✅ 已保存平滑结果到 {output_file}，方法 = {method}，四舍五入 = {do_round}")

    # ===================== 绘图 =====================
    plt.figure(figsize=(10, 5))
    plt.plot(data, label="original", linewidth=1.5)
    plt.plot(smoothed, label=f"after({method})", linewidth=2)
    plt.title(f"Prediction smoothing comparison ({method})", fontsize=14)
    plt.xlabel("Index")
    plt.ylabel("Predicted value")
    plt.legend()
    plt.grid(True)

    # 保存图片
    img_path = os.path.splitext(output_file)[0] + "_smooth.png"
    plt.savefig(img_path, dpi=200, bbox_inches="tight")
    plt.show()
    print(f"📊 已保存平滑对比图：{img_path}")

# ===================== 程序入口 =====================
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python smooth_csv.py input.csv output.csv [method] [--round]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    method = "savgol"
    do_round = False

    # 解析命令行参数
    for arg in sys.argv[3:]:
        if arg.lower() in ["moving_average", "ema", "median", "savgol"]:
            method = arg.lower()
        elif arg in ["--round", "--int"]:
            do_round = True

    smooth_csv(input_file, output_file, method, do_round)
