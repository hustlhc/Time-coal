#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import glob

def _read_header_and_delimiter(file_path):
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        sample = f.read(1024)
        f.seek(0)
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample)
            delimiter = dialect.delimiter
        except Exception:
            delimiter = ','

        reader = csv.reader(f, delimiter=delimiter)
        all_rows = list(reader)
        if not all_rows:
            return None, delimiter, []

        first_row = all_rows[0]
        is_header = True
        for cell in first_row:
            try:
                float(cell)
                is_header = False
                break
            except ValueError:
                continue

        if not is_header:
            return None, delimiter, all_rows

        return first_row, delimiter, all_rows


def _should_process_file(file_path: str) -> bool:
    base = os.path.basename(file_path).lower()
    if base in {'kemen.csv', 'shaowu.csv', 'yongan.csv', 'zhangping.csv'}:
        return False
    header, _, _ = _read_header_and_delimiter(file_path)
    if not header or len(header) < 2:
        return False
    last_col = header[-1]
    second_last_col = header[-2]
    return ('运行小时' in second_last_col) and ('发电量' in last_col)


def process_csv_file(file_path):
    """
    处理CSV文件：删除满足条件的行
    条件：
    1. 最后一列为0
    2. 倒数第二列（运行小时）小于22
    """
    try:
        print(f"\n处理文件: {os.path.basename(file_path)}")
        print("-" * 50)

        if not _should_process_file(file_path):
            print("跳过：不是分机组运行小时/发电量文件（或为总表文件）")
            return 0
        
        # 读取CSV文件
        rows = []
        removed_count = 0
        removed_reasons = {}
        header = None
        
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            # 自动检测分隔符
            sample = f.read(1024)
            f.seek(0)
            
            # 检测分隔符
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample)
                delimiter = dialect.delimiter
            except:
                # 如果自动检测失败，默认使用逗号
                delimiter = ','
            
            print(f"检测到分隔符: '{delimiter}'")
            
            # 重新读取文件
            reader = csv.reader(f, delimiter=delimiter)
            
            # 读取所有行
            all_rows = list(reader)
            
            if not all_rows:
                print("文件为空")
                return 0
            
            # 检查第一行是否可能是表头
            first_row = all_rows[0]
            is_header = True
            for cell in first_row:
                try:
                    float(cell)
                    is_header = False  # 如果能转换为数字，可能不是表头
                    break
                except ValueError:
                    continue
            
            if is_header:
                header = first_row
                print(f"检测到表头: {header}")
                rows.append(header)  # 保留表头
                start_index = 1  # 从第二行开始处理数据
            else:
                start_index = 0  # 从第一行开始处理数据
            
            # 处理数据行
            for row_num in range(start_index, len(all_rows)):
                row = all_rows[row_num]
                row_number = row_num + 1  # 用于显示的行号
                
                if not row:  # 跳过空行
                    continue
                
                # 检查行是否有足够的列
                if len(row) < 2:
                    print(f"第{row_number}行列数不足，已保留")
                    rows.append(row)
                    continue
                
                # 获取最后一列和倒数第二列
                last_col = row[-1].strip()
                second_last_col = row[-2].strip()
                
                delete_reasons = []
                
                # 条件1：最后一列为0
                try:
                    if last_col=='' or float(last_col) == 0 :
                        delete_reasons.append(f"最后一列为0")
                except ValueError:
                    pass  # 如果不是数字，忽略此条件
                
                # 条件2：倒数第二列（运行小时）小于22
                try:
                    hour_value = float(second_last_col)
                    if hour_value < 22:
                        delete_reasons.append(f"运行小时({hour_value})小于22")
                except ValueError:
                    pass  # 如果不是数字，忽略此条件
                
                # 如果满足任一条件，删除该行
                if delete_reasons:
                    reason_str = "、".join(delete_reasons)
                    print(f"删除第{row_number}行: {','.join(row)} - 原因: {reason_str}")
                    removed_count += 1
                    for reason in delete_reasons:
                        removed_reasons[reason] = removed_reasons.get(reason, 0) + 1
                else:
                    rows.append(row)
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerows(rows)
        
        # 显示删除原因统计
        print(f"\n✓ 处理完成！删除行数: {removed_count}")
        if removed_reasons:
            print("  删除原因统计:")
            for reason, count in removed_reasons.items():
                print(f"    - {reason}: {count}行")
        
        return removed_count
        
    except Exception as e:
        print(f"✗ 处理文件时出错: {e}")
        import traceback
        traceback.print_exc()
        return 0

def main():
    # 获取当前文件夹路径
    current_folder = os.getcwd()
    print(f"当前文件夹: {current_folder}")
    
    # 查找所有CSV文件
    csv_files = glob.glob(os.path.join(current_folder, "*.csv"))
    csv_files.extend(glob.glob(os.path.join(current_folder, "*.CSV")))  # 支持大写扩展名
    
    if not csv_files:
        print("未找到任何CSV文件！")
        return
    
    print(f"找到 {len(csv_files)} 个CSV文件")
    
    total_files = 0
    total_removed = 0
    
    # 处理每个CSV文件
    for csv_file in csv_files:
        removed = process_csv_file(csv_file)
        if removed > 0:
            total_files += 1
            total_removed += removed
    
    # 显示统计信息
    print("\n" + "=" * 50)
    print("处理完成统计：")
    print(f"处理文件数: {len(csv_files)}")
    print(f"修改文件数: {total_files}")
    print(f"总共删除行数: {total_removed}")

if __name__ == "__main__":
    # 询问用户确认
    print("此脚本将处理当前文件夹内所有CSV文件")
    print("删除条件（满足任一条件即删除）：")
    print("1. 最后一列为0")
    print("2. 倒数第二列（运行小时）小于22")
    #response = input("是否继续？(y/n): ").strip().lower()
    
    #if response == 'y' or response == 'yes':
    main()
    print("\n脚本执行完毕！")
    #else:
     #   print("操作已取消")
