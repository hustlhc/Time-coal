import sqlite3
import csv
import os
import glob

# 连接数据库 - 使用 elec_prediction.db
conn = sqlite3.connect('elec_prediction.db')
cursor = conn.cursor()

# 处理 dataset-huodian 目录中的分机组 CSV 文件
huodian_dir = '../dataset-huodian'

# 定义电厂名称映射
plant_mapping = {
    'kemen': 'kemen',
    'shaowu': 'shaowu',
    'yongan': 'yongan',
    'zhangping': 'zhangping'
}

def clean_date_string(date_str):
    """
    清理日期字符串，处理 .0 的情况
    """
    if not date_str:
        return None
    
    # 转换为字符串并清理
    date_str = str(date_str).strip()
    
    # 处理 .0 结尾的情况（如 20240101.0）
    if date_str.endswith('.0'):
        date_str = date_str[:-2]
    
    # 如果还有小数点，取小数点前面的部分
    if '.' in date_str:
        date_str = date_str.split('.')[0]
    
    # 处理不同的日期格式
    try:
        # 格式1: 20240101 (8位数字)
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        
        # 格式2: 2024/01/01
        elif '/' in date_str:
            parts = date_str.split('/')
            if len(parts) == 3:
                return f"{parts[0].strip()}-{parts[1].strip().zfill(2)}-{parts[2].strip().zfill(2)}"
        
        # 格式3: 2024-01-01
        elif '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3:
                return f"{parts[0].strip()}-{parts[1].strip().zfill(2)}-{parts[2].strip().zfill(2)}"
        
        # 如果都无法识别，返回原字符串
        print(f"警告：无法识别的日期格式：{date_str}")
        return date_str
        
    except Exception as e:
        print(f"日期处理错误：{date_str}，错误：{e}")
        return None

# 查找所有分机组 CSV 文件
# 格式：kemen_1.csv, kemen_2.csv, shaowu_3.csv, etc.
csv_files = []
for plant in plant_mapping.keys():
    csv_files.extend(glob.glob(os.path.join(huodian_dir, f'{plant}_*.csv')))

if not csv_files:
    print(f"目录 {huodian_dir} 中未找到分机组 CSV 文件")
    exit(1)

print(f"找到 {len(csv_files)} 个分机组 CSV 文件")

for csv_file in csv_files:
    print(f"\n处理文件：{csv_file}")
    
    # 解析文件名，提取电厂名称和机组号
    # 格式：kemen_1.csv → 电厂：kemen，机组：1
    file_name = os.path.basename(csv_file)
    parts = file_name.split('_')
    if len(parts) < 2:
        print(f"文件名格式不正确：{file_name}")
        continue
    
    plant_code = parts[0]  # 电厂代码
    unit_part = parts[1].split('.')[0]  # 机组部分，去掉 .csv 后缀
    
    # 提取机组号
    unit_number = ''.join(filter(str.isdigit, unit_part))
    if not unit_number:
        print(f"无法提取机组号：{file_name}")
        continue
    
    unit_id = f'unit{unit_number}'  # 机组ID，如 unit1, unit2
    plant_name = plant_mapping.get(plant_code, plant_code)  # 电厂名称
    data_type = f'{plant_name}_power'  # 数据类型
    
    print(f"解析结果：电厂代码={plant_code}，机组号={unit_number}，机组ID={unit_id}，电厂名称={plant_name}，数据类型={data_type}")
    
    # 读取 CSV 文件
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f"使用 utf-8 编码读取文件成功，共 {len(rows)} 行")
    except UnicodeDecodeError:
        # 尝试使用 gbk 编码
        try:
            with open(csv_file, 'r', encoding='gbk') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            print(f"使用 gbk 编码读取文件成功，共 {len(rows)} 行")
        except Exception as e:
            print(f"读取文件 {csv_file} 失败：{e}")
            continue
    
    if not rows:
        print(f"文件 {csv_file} 为空")
        continue
    
    # 查看文件的列名称
    print(f"文件列名称：{list(rows[0].keys())}")
    
    # 获取日期列和发电量列
    # 尝试不同的日期列名称
    date_col = None
    possible_date_cols = ['date', '日期', 'Date', 'DATE', 'ds']
    for col in possible_date_cols:
        if col in rows[0]:
            date_col = col
            break
    
    if not date_col:
        # 如果没有找到常见的日期列名称，使用第一列
        date_col = list(rows[0].keys())[0]
    
    # 获取发电量列
    power_col = None
    possible_power_cols = ['value', '发电量', 'power', 'y', 'yhat', 'yhat_lower', 'yhat_upper']
    for col in possible_power_cols:
        if col in rows[0]:
            power_col = col
            break
    
    if not power_col:
        # 如果没有找到常见的发电量列名称，使用最后一列
        power_col = list(rows[0].keys())[-1]
    
    print(f"使用的日期列：{date_col}，发电量列：{power_col}")
    
    # 遍历数据
    imported_count = 0
    skipped_count = 0
    
    for i, row in enumerate(rows):
        # 获取日期并清理
        date_str = row.get(date_col, '')
        if not date_str:
            print(f"第 {i+1} 行：日期为空")
            skipped_count += 1
            continue
        
        # 使用清理函数处理日期
        date = clean_date_string(date_str)
        if not date:
            print(f"第 {i+1} 行：日期处理失败：{date_str}")
            skipped_count += 1
            continue
        
        # 获取发电量
        power_value = row.get(power_col, '')
        if power_value == '':
            print(f"第 {i+1} 行：发电量为空")
            skipped_count += 1
            continue
        
        # 转换发电量为浮点数
        try:
            # 先转换为字符串，再转换为浮点数
            value = float(str(power_value).strip())
        except Exception as e:
            print(f"第 {i+1} 行：发电量转换失败：{power_value}，错误：{e}")
            skipped_count += 1
            continue
        
        # 插入数据到 real_data 表
        try:
            cursor.execute('''
            INSERT OR IGNORE INTO real_data (date, data_type, value, unit_id, is_total)
            VALUES (?, ?, ?, ?, ?)
            ''', (date, data_type, value, unit_id, 0))
            imported_count += 1
        except Exception as e:
            print(f"第 {i+1} 行：插入数据失败：{date}，{value}，错误：{e}")
            skipped_count += 1
            continue
    
    # 提交事务
    conn.commit()
    print(f"文件 {csv_file} 处理完成，导入了 {imported_count} 条记录，跳过了 {skipped_count} 条记录")

# 关闭数据库连接
conn.close()
print("\n所有文件处理完成！")