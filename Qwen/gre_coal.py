#!/usr/bin/env python3
"""
生成煤价预测数据的 JSON 文件
从 autoinfer 目录下的 6 个 CSV 文件读取数据，生成指定格式的 JSON
"""

import os
import json

# 定义文件映射关系
file_mapping = {
    "CCI4500": "CCI4500infer.csv",
    "CCI5000": "CCI5000infer.csv",
    "CCI5500": "CCI5500infer.csv",
    "CCI进口3800": "CCI3800outinfer.csv",
    "CCI进口4700": "CCI4700outinfer.csv",
    "CCI进口5500": "CCI5500outinfer.csv"
}

# 数据目录
data_dir = "../autoinfer"

# 结果字典
result = {}

# 读取每个文件的数据
for key, filename in file_mapping.items():
    file_path = os.path.join(data_dir, filename)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            # 读取前60行数据
            values = []
            for i, line in enumerate(f):
                if i >= 60:
                    break
                # 去除换行符并添加到列表
                value = line.strip()
                values.append(value)
            
            # 添加到结果字典
            result[key] = values
            print(f"成功读取 {filename}，获取 {len(values)} 条数据")
            
    except Exception as e:
        print(f"读取 {filename} 时出错: {e}")
        # 为空的情况添加空列表
        result[key] = []

# 输出 JSON
output_file = os.path.join("data/coal_output.json")
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=4)

print(f"\nJSON 文件已生成: {output_file}")
print("\n生成的 JSON 数据:")
print(json.dumps(result, ensure_ascii=False, indent=2))
