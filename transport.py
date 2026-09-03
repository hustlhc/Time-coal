
import subprocess
import pandas as pd
import os
import argparse
parser = argparse.ArgumentParser(description="自动执行微调/推理脚本并合并结果")
parser.add_argument("--finetune", type=int, default=0, help="是否执行微调阶段脚本 (1=执行, 0=跳过)")
parser.add_argument("--infer", type=int, default=0, help="是否执行推理阶段脚本 (1=执行, 0=跳过)")
args = parser.parse_args()

scripts1 = [
    "scripts/long_term_forecast/autotrans/inside.sh",
    "scripts/long_term_forecast/autotrans/outside.sh"
]
scripts2 = [
    "scripts/long_term_forecast/autotrans/insideinfer.sh",
    "scripts/long_term_forecast/autotrans/outsideinfer.sh"
]
csv_files = [
        "autoinfer/insideinfer.csv",
        "autoinfer/outsideinfer.csv"
]
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
if args.finetune == 1:
    for script in scripts1:
        print(f"正在运行: {script}")
        result = subprocess.run(["bash", script], capture_output=True, text=True)
        
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        
        if result.returncode != 0:
            print(f"❌ 脚本 {script} 执行失败，中断后续执行")
            break   
if args.infer == 1:
    for script in scripts2:
        print(f"正在运行: {script}")
        result = subprocess.run(["bash", script], capture_output=True, text=True)
        
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        
        if result.returncode != 0:
            print(f"❌ 脚本 {script} 执行失败，中断后续执行")
            break
    #merge_csv_as_columns(csv_files, "autoinfer/infertrans.csv")



