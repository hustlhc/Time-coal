import sqlite3
import json
import os
import glob

# 连接数据库
conn = sqlite3.connect('elec_prediction.db')
cursor = conn.cursor()

# 获取所有JSON文件
json_files = glob.glob('elecjson/*_data.json')
print(f"找到 {len(json_files)} 个JSON文件")

# 统计导入数据量
total_records = 0

# 遍历JSON文件
for filename in json_files:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            infer_date = data.get('inferDate')
            print(f"处理文件: {filename}, 预测日期: {infer_date}")
            
            # 遍历每种数据类型
            for data_type, predictions in data.get('data', {}).items():
                records_count = 0
                for pred in predictions:
                    pred_date = pred.get('date')
                    predict = pred.get('predict')
                    
                    if pred_date and predict is not None:
                        # 插入数据（使用INSERT OR IGNORE避免重复）
                        cursor.execute('''
                        INSERT OR IGNORE INTO prediction_data (infer_date, data_type, pred_date, predict)
                        VALUES (?, ?, ?, ?)
                        ''', (infer_date, data_type, pred_date, predict))
                        records_count += 1
                
                print(f"  - {data_type}: 导入 {records_count} 条记录")
                total_records += records_count
                
    except Exception as e:
        print(f"处理文件 {filename} 时出错: {str(e)}")
        continue

# 提交并关闭
conn.commit()
conn.close()
print(f"\n数据导入完成！")
print(f"总共导入 {total_records} 条记录到数据库")
print("\n数据库文件: elec_prediction.db")
