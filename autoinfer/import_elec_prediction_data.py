import sqlite3
import json
import os
import glob

# 连接数据库 - 使用 elec_prediction.db
conn = sqlite3.connect('elec_prediction.db')
cursor = conn.cursor()

# 处理 elecjson 目录中的预测数据 JSON 文件
elecjson_dir = os.path.join(os.path.dirname(__file__), 'elecjson')

# 查找所有 JSON 文件
json_files = glob.glob(os.path.join(elecjson_dir, '*.json'))

if not json_files:
    print(f"目录 {elecjson_dir} 中未找到 JSON 文件")
    exit(1)

print(f"找到 {len(json_files)} 个预测数据文件")

for json_file in json_files:
    print(f"\n处理文件：{json_file}")
    
    # 读取 JSON 文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 获取推理日期
    infer_date = data.get('inferDate', '')
    if not infer_date:
        print(f"文件 {json_file} 中未找到推理日期")
        continue
    
    print(f"推理日期：{infer_date}")
    
    # 获取预测数据
    predictions = data.get('data', {})
    
    # 遍历每个机组的预测数据
    imported_count = 0
    
    for key, pred_list in predictions.items():
        # 解析文件名获取电厂和机组信息
        # 格式：zhangping_5 → 电厂：zhangping，机组：5
        parts = key.split('_')
        if len(parts) < 2:
            print(f"数据键格式不正确：{key}")
            continue
        
        plant_name = parts[0]  # 电厂名称
        unit_number = parts[1]  # 机组号
        unit_id = f'unit{unit_number}'  # 机组ID
        
        print(f"处理机组：{plant_name} {unit_id}")
        
        # 遍历预测数据
        for pred_data in pred_list:
            pred_date = pred_data.get('date', '')
            predict = pred_data.get('predict', 0)
            
            if not pred_date:
                print(f"预测日期为空，跳过")
                continue
            
            # 插入预测数据到 prediction_data 表
            # 使用 INSERT OR IGNORE 避免重复插入
            try:
                cursor.execute('''
                INSERT OR IGNORE INTO prediction_data (infer_date, data_type, pred_date, predict, unit_id, is_total)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (infer_date, plant_name, pred_date, predict, unit_id, 0))
                imported_count += 1
            except Exception as e:
                print(f"插入数据失败：{e}")
                continue
    
    # 提交事务
    conn.commit()
    print(f"文件 {json_file} 处理完成，导入了 {imported_count} 条记录")

# 关闭数据库连接
conn.close()
print("\n所有文件处理完成！")
