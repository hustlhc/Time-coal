import os
import glob
import pandas as pd

# ========== 文件路径 ==========
REAL_COAL_PATH = "./dataset/pre_coal/coal_new.csv"
REAL_FREIGHT_PATH = "./dataset/pre_coal/coal_freight.csv"
PRED_DIR = "./autoinfer"
OUTPUT_DIR = "./merged_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ========== 映射 ==========
COAL_TARGETS = {
    "CCI4500": "CCI4500",
    "CCI5000": "CCI5000",
    "CCI5500": "CCI5500",
    "CCI3800outinfer": "CCI进口3800",
    "CCI4700outinfer": "CCI进口4700",
    "CCI5500outinfer": "CCI进口5500",
}
FREIGHT_TARGETS = {
    "insideinfer": "输入00000347--煤炭运费_水运价格_沿海煤炭运费_秦皇岛-厦门(5-6万DWT)_本期(元/吨)",
    "outsideinfer": "输入00000351--煤炭运费_水运价格_进口煤炭运费_印尼萨马林达-中国广州_当期值(美元/吨)",
}

# ========== 核心函数 ==========
def update_rolling_csv(real_df, pred_file, target_col, out_path, future_len=60):
    """正序历史真实值 + 未来预测值（日期列空）"""
    df_pred = pd.read_csv(pred_file, header=None)
    df_pred_values = df_pred.iloc[:, -1].tolist()

    # 最新真实值
    latest_real_date = pd.to_datetime(real_df.iloc[-1, 0]).date()
    latest_real_val = real_df[target_col].iloc[-1]

    # 加载已有CSV（如果存在）
    if os.path.exists(out_path):
        df_out = pd.read_csv(out_path)
        # 提取已有真实值列，去掉空值
        history_real = df_out['真实值'].dropna().tolist()
    else:
        history_real = []

    # 最新真实值追加到历史真实值末尾
    all_real = history_real + [latest_real_val]

    # 构建新的DataFrame
    df_new = pd.DataFrame({
        "日期": [""] * (len(all_real) + future_len),
        "真实值": all_real + [None] * future_len,
        "预测值": [None] * len(all_real) + df_pred_values[:future_len]
    })

    df_new.to_csv(out_path, index=False)
    print(f"[UPDATE] 已生成/更新 {out_path}")


# ========== 主程序 ==========
def main():
    coal_real = pd.read_csv(REAL_COAL_PATH)
    freight_real = pd.read_csv(REAL_FREIGHT_PATH)

    # --- 煤炭指数 ---
    for pred_name, col_name in COAL_TARGETS.items():
        pattern = os.path.join(PRED_DIR, f"{pred_name}*.csv")
        files = glob.glob(pattern)
        if not files:
            print(f"[WARN] 未找到 {col_name} 的预测文件 ({pattern})")
            continue
        latest_file = max(files, key=os.path.getmtime)
        out_path = os.path.join(OUTPUT_DIR, f"{pred_name}_merged.csv")
        update_rolling_csv(coal_real, latest_file, col_name, out_path)

    # --- 运费 ---
    for pred_name, col_name in FREIGHT_TARGETS.items():
        pattern = os.path.join(PRED_DIR, f"{pred_name}*.csv")
        files = glob.glob(pattern)
        if not files:
            print(f"[WARN] 未找到 {col_name} 的预测文件 ({pattern})")
            continue
        latest_file = max(files, key=os.path.getmtime)
        out_path = os.path.join(OUTPUT_DIR, f"{pred_name}_merged.csv")
        update_rolling_csv(freight_real, latest_file, col_name, out_path)


if __name__ == "__main__":
    main()
