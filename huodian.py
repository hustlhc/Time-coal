
import subprocess
import pandas as pd
import os
import argparse
parser = argparse.ArgumentParser(description="自动执行微调/推理脚本并合并结果")
parser.add_argument("--finetune", type=int, default=0, help="是否执行微调阶段脚本 (1=执行, 0=跳过)")
parser.add_argument("--infer", type=int, default=0, help="是否执行推理阶段脚本 (1=执行, 0=跳过)")
args = parser.parse_args()
scripts1 = [
    "scripts-huodian/yongan.sh",
    "scripts-huodian/kemen.sh",
    "scripts-huodian/shaowu.sh",
    "scripts-huodian/zhangping.sh"
]
scripts2 = [
    "scripts-huodian/yongan_infer.sh",
    "scripts-huodian/kemen_infer.sh",
    "scripts-huodian/shaowu_infer.sh",
    "scripts-huodian/zhangping_infer.sh"
]

if args.finetune == 1:
    for script in scripts1:
        print(f"正在运行: {script}")
        result = subprocess.run(["bash", script], text=True)
        
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        
        
if args.infer == 1:
    for script in scripts2:
        print(f"正在运行: {script}")
        result = subprocess.run(["bash", script], text=True)
        
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)
        
        
    #merge_csv_as_columns(csv_files, "autoinfer/coalinfer.csv")


