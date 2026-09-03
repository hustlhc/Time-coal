import csv
import json
import os

# 找到所有以 outinfer.csv 结尾的文件
csv_files = [f for f in os.listdir('.') if f.endswith('infer.csv')]

# 用于存储所有文件数据的字典
all_data = {}

for csv_file in csv_files:
    data = []
    try:
        with open(csv_file, mode='r', encoding='utf-8-sig') as f:  # 使用utf-8-sig处理BOM
            reader = csv.reader(f)
            headers = next(reader)  # 读取标题行
            print(f"处理文件: {csv_file}, 列名: {headers}")
            
            for row in reader:
                if len(row) >= 3:  # 确保有足够的列
                    cleaned_row = {
                        'date': row[0],
                        '真实值': float(row[1]) if row[1] and row[1].strip() else None,
                        '预测值': float(row[2]) if row[2] and row[2].strip() else None
                    }
                    data.append(cleaned_row)
        
        # 使用文件名（不含扩展名）作为键
        file_key = os.path.splitext(csv_file)[0]
        all_data[file_key] = data
        print(f"成功读取 {csv_file}: {len(data)} 条记录")
        
    except Exception as e:
        print(f"处理文件 {csv_file} 时出错: {e}")
        import traceback
        traceback.print_exc()

# 写入到一个总的 JSON 文件中
output_file = 'combined_predictions.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)

print(f"\n转换完成！所有数据已保存到 {output_file}")
print(f"共处理了 {len(csv_files)} 个文件:")
for file in csv_files:
    print(f"  - {file}")