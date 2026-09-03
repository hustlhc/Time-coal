import pandas as pd
import glob
import json

# 1️⃣ 匹配所有 JSON 文件
json_files = sorted(glob.glob("./*.json"))

all_rows = []

# 2️⃣ 读取每个 JSON 文件并追加到总列表
for f in json_files:
    with open(f, "r", encoding="utf-8") as jf:
        data = json.load(jf)
        all_rows.extend(data)  # 直接叠加每一条记录
    print(f"✅ 已加载 {f}, 共 {len(data)} 条记录")

# 3️⃣ 保存成一个 JSON 文件
output_file = "merged_simple.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_rows, f, ensure_ascii=False, indent=4)

print(f"\n🎯 已完成简单叠加，输出文件：{output_file}, 总记录数：{len(all_rows)}")
