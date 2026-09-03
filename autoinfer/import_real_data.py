import sqlite3
import csv
import os
import glob

# 连接数据库
conn = sqlite3.connect('coal_prediction.db')
cursor = conn.cursor()

# 定义CSV文件路径
coal_csv_path = '../dataset/pre_coal/coal_new.csv'
freight_csv_path = '../dataset/pre_coal/coal_freight.csv'

# 统计导入数据量
total_records = 0

# 导入煤价数据
def import_coal_data():
    global total_records
    if not os.path.exists(coal_csv_path):
        print(f"错误：煤价数据文件不存在：{coal_csv_path}")
        return
    
    print("开始导入煤价数据...")
    
    try:
        with open(coal_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # 读取表头
            
            # 确定最后6列的索引（CCI指数）
            cci_columns = header[-6:]
            print(f"找到 {len(cci_columns)} 个CCI指数列：")
            for i, col in enumerate(cci_columns):
                print(f"  {i+1}. {col}")
            
            # 定义数据类型映射
            data_type_mapping = {
                header[-6]: 'CCI4500',
                header[-5]: 'CCI5000',
                header[-4]: 'CCI5500',
                header[-3]: 'CCI3800out',
                header[-2]: 'CCI4700out',
                header[-1]: 'CCI5500out'
            }
            
            # 导入数据
            records_count = 0
            for row in reader:
                if not row or len(row) < 6:
                    continue
                
                date = row[0]
                if not date:
                    continue
                
                # 处理最后6列（CCI指数）
                for i in range(6):
                    col_index = len(header) - 6 + i
                    if col_index >= len(row):
                        continue
                    
                    value_str = row[col_index]
                    if not value_str:
                        continue
                    
                    try:
                        value = float(value_str)
                    except ValueError:
                        continue
                    
                    # 获取数据类型
                    col_name = header[col_index]
                    data_type = data_type_mapping.get(col_name, f'cci_{i+1}')
                    
                    # 插入数据（使用INSERT OR IGNORE避免重复）
                    cursor.execute('''
                    INSERT OR IGNORE INTO real_data (date, data_type, value)
                    VALUES (?, ?, ?)
                    ''', (date, data_type, value))
                    
                    records_count += 1
            
            total_records += records_count
            print(f"煤价数据导入完成！导入 {records_count} 条记录")
            
    except Exception as e:
        print(f"导入煤价数据时出错: {str(e)}")

# 导入运费数据
def import_freight_data():
    global total_records
    if not os.path.exists(freight_csv_path):
        print(f"错误：运费数据文件不存在：{freight_csv_path}")
        return
    
    print("\n开始导入运费数据...")
    
    try:
        with open(freight_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # 读取表头
            
            # 确定最后2列的索引（国内外运费）
            freight_columns = header[-2:]
            print(f"找到 {len(freight_columns)} 个运费列：")
            for i, col in enumerate(freight_columns):
                print(f"  {i+1}. {col}")
            
            # 定义数据类型映射
            data_type_mapping = {
                header[-1]: 'inside_freight',  # 国内运费
                header[-2]: 'outside_freight'  # 国际运费
            }
            
            # 导入数据
            records_count = 0
            for row in reader:
                if not row or len(row) < 2:
                    continue
                
                date = row[0]
                if not date:
                    continue
                
                # 处理最后2列（运费）
                for i in range(2):
                    col_index = len(header) - 2 + i
                    if col_index >= len(row):
                        continue
                    
                    value_str = row[col_index]
                    if not value_str:
                        continue
                    
                    try:
                        value = float(value_str)
                    except ValueError:
                        continue
                    
                    # 获取数据类型
                    col_name = header[col_index]
                    data_type = data_type_mapping.get(col_name, f'freight_{i+1}')
                    
                    # 插入数据（使用INSERT OR IGNORE避免重复）
                    cursor.execute('''
                    INSERT OR IGNORE INTO real_data (date, data_type, value)
                    VALUES (?, ?, ?)
                    ''', (date, data_type, value))
                    
                    records_count += 1
            
            total_records += records_count
            print(f"运费数据导入完成！导入 {records_count} 条记录")
            
    except Exception as e:
        print(f"导入运费数据时出错: {str(e)}")

# 清空 real_data 表中的数据，确保每次导入都是最新的
print("清空 real_data 表中的数据...")
cursor.execute('DELETE FROM real_data')
print("清空完成！")

# 执行导入
import_coal_data()
import_freight_data()

# 提交并关闭
conn.commit()
conn.close()

print(f"\n所有数据导入完成！")
print(f"总共导入 {total_records} 条真实数据到数据库")
print("\n数据库文件: coal_prediction.db")
print("\n真实数据表 (real_data) 包含以下数据类型：")
print("- CCI3800, CCI4500, CCI4700, CCI5000, CCI5500, CCI5800 (煤价)")
print("- inside_freight (国内运费)")
print("- outside_freight (国际运费)")
print("\n可以通过以下SQL查询数据：")
print("- 查看所有数据类型：SELECT DISTINCT data_type FROM real_data;")
print("- 查看特定类型数据：SELECT * FROM real_data WHERE data_type = 'CCI4500' ORDER BY date DESC LIMIT 10;")
