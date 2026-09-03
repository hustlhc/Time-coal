#!/usr/bin/env python3
import csv
import sys
import os

def round_csv(input_file, output_file=None):
    if output_file is None:
        output_file = input_file  # 默认覆盖原文件

    with open(input_file, 'r', newline='', encoding='utf-8') as f_in:
        reader = csv.reader(f_in)
        rows = list(reader)

    if not rows:
        print("CSV 文件为空")
        return

    rounded_rows = []
    for row in rows:  # 注意这里处理所有行，包括第一行
        new_row = []
        for val in row:
            try:
                num = float(val)
                new_row.append(str(int(round(num))))
            except ValueError:
                new_row.append(val)  # 非数值保持原样
        rounded_rows.append(new_row)

    # 写入 CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f_out:
        writer = csv.writer(f_out)
        writer.writerows(rounded_rows)

    print(f"已保存四舍五入后的 CSV 到 {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python int.py input.csv [output.csv]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) >= 3 else None

    if not os.path.exists(input_file):
        print(f"错误: 文件 {input_file} 不存在")
        sys.exit(1)

    round_csv(input_file, output_file)
