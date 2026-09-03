import json
import csv
import os
from datetime import datetime

def json_to_csv(json_file, csv_file=None):
    """将JSON文件转换为CSV文件（使用标准库）"""
    try:
        # 读取JSON文件
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取数据部分
        if 'data' in data:
            records = data['data']
        else:
            records = data
        
        if not records:
            print("错误: JSON文件中没有数据")
            return None
        
        # 获取所有字段名
        fieldnames = list(records[0].keys())
        
        # 打印数据信息
        print(f"数据转换完成：")
        print(f"- 原始JSON文件: {json_file}")
        print(f"- 记录数: {len(records)}")
        print(f"- 字段数: {len(fieldnames)}")
        print(f"- 字段: {fieldnames}")
        
        # 生成CSV文件名
        if csv_file is None:
            # 从JSON文件名生成CSV文件名
            base_name = os.path.basename(json_file)
            name_without_ext = os.path.splitext(base_name)[0]
            csv_file = f"{name_without_ext}.csv"
        
        # 确保输出目录存在
        output_dir = os.path.dirname(csv_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 保存为CSV文件
        with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            # 写入表头
            writer.writeheader()
            # 写入数据
            for record in records:
                writer.writerow(record)
        
        print(f"- CSV文件已保存到: {csv_file}")
        return csv_file
    except Exception as e:
        print(f"转换失败: {e}")
        return None

def batch_convert_json_to_csv(json_dir='data_json', csv_dir='data_json'):
    """批量转换JSON文件为CSV文件"""
    # 确保目录存在
    if not os.path.exists(json_dir):
        print(f"错误: 目录 {json_dir} 不存在")
        return
    
    if not os.path.exists(csv_dir):
        os.makedirs(csv_dir)
    
    # 查找所有JSON文件
    json_files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
    
    if not json_files:
        print(f"错误: 目录 {json_dir} 中没有JSON文件")
        return
    
    print(f"找到 {len(json_files)} 个JSON文件，开始转换...")
    
    for json_file in json_files:
        json_path = os.path.join(json_dir, json_file)
        csv_path = os.path.join(csv_dir, f"{os.path.splitext(json_file)[0]}.csv")
        
        print(f"\n转换: {json_file}")
        json_to_csv(json_path, csv_path)
    
    print(f"\n批量转换完成，共处理 {len(json_files)} 个文件")

def main():
    # 单个文件转换示例
    print("=== 单个文件转换 ===")
    json_file = 'data/huodian.json'
    if os.path.exists(json_file):
        json_to_csv(json_file)
    else:
        print(f"错误: 文件 {json_file} 不存在")
    
    # 批量转换示例
    print("\n=== 批量转换 ===")
    batch_convert_json_to_csv()

if __name__ == "__main__":
    main()
