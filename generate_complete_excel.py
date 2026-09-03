#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成包含多个子表的Excel预测数据文件

此脚本将生成一个Excel文件，包含以下5个子表：
1. 国内煤价预测
2. 进口煤价预测
3. 国内运费预测
4. 国际运费预测
5. 发电量预测

使用方法：
1. 确保安装了pandas和openpyxl库：pip install pandas openpyxl
2. 将脚本放在项目根目录下运行
3. 生成的Excel文件将保存在项目根目录下的'预测数据.xlsx'
"""

import os
import sys
from datetime import datetime, timedelta

# 尝试导入pandas库
try:
    import pandas as pd
except ImportError:
    print("pandas库未安装，正在尝试安装...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pandas", "openpyxl"])
    import pandas as pd

# 尝试导入chinese_calendar库
try:
    from chinese_calendar import is_workday
except ImportError:
    print("chinese_calendar库未安装，正在尝试安装...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "chinese-calendar"])
    from chinese_calendar import is_workday

# 脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOINFER_DIR = os.path.join(SCRIPT_DIR, 'autoinfer')
ELECDATA_DIR = os.path.join(AUTOINFER_DIR, 'elecdata')
output_dir=("autoinfer/html1/week_report")
# 生成周报文件名
def generate_report_filename():
    """生成周报文件名，格式为：2026年3月第3周周报（3.16-3.22）"""
    today = datetime.now()
    
    # 计算下一周的周一
    # 计算今天距离下一个周一的天数
    days_until_next_monday = (7 - today.weekday()) % 7
    if days_until_next_monday == 0:
        days_until_next_monday = 7  # 如果今天是周一，那么下一周的周一就是7天后
    next_week_monday = today + timedelta(days=days_until_next_monday)
    # 下一周的周日
    next_week_sunday = next_week_monday + timedelta(days=6)
    
    year = next_week_monday.year
    month = next_week_monday.month
    
    # 计算下一周是本月的第几周（从1开始）
    # 获取本月第一天
    first_day = datetime(year, month, 1)
    # 计算本月第一个周一
    first_day_weekday = first_day.weekday()
    if first_day_weekday == 0:  # 第一天就是周一
        first_monday = first_day
    else:
        first_monday = first_day + timedelta(days=(7 - first_day_weekday))
    
    # 计算下一周是第几周
    if next_week_monday < first_monday:
        # 如果下一周的周一在本月第一个周一之前，那么是第1周
        week_number = 1
    else:
        weeks_since_first = (next_week_monday - first_monday).days // 7
        week_number = weeks_since_first + 1
    
    # 下一周的周一和周日
    monday = next_week_monday
    sunday = next_week_sunday
    
    # 格式化日期范围：3.16-3.22
    date_range = f"{monday.month}.{monday.day}-{sunday.month}.{sunday.day}"
    
    # 生成文件名
    filename = f"{year}年{month}月第{week_number}周周报（{date_range}）"
    return filename

# 生成煤价和运费预测的工作日日期列表
def generate_workday_dates():
    """生成下一周的工作日日期"""
    dates = []
    # 计算下一周的周一
    today = datetime.now()
    days_until_next_monday = (7 - today.weekday()) % 7
    if days_until_next_monday == 0:
        days_until_next_monday = 7  # 如果今天是周一，那么下一周的周一就是7天后
    next_week_monday = today + timedelta(days=days_until_next_monday)
    
    # 生成下一周的日期（周一到周日）
    for i in range(7):
        current = next_week_monday + timedelta(days=i)
        if is_workday(current):
            dates.append(current.strftime('%Y-%m-%d'))
    return dates

# 生成发电量预测的一周七天日期列表
def generate_weekly_dates():
    """生成下一周七天的日期"""
    dates = []
    # 计算下一周的周一
    today = datetime.now()
    days_until_next_monday = (7 - today.weekday()) % 7
    if days_until_next_monday == 0:
        days_until_next_monday = 7  # 如果今天是周一，那么下一周的周一就是7天后
    next_week_monday = today + timedelta(days=days_until_next_monday)
    
    # 生成下一周的日期（周一到周日）
    for i in range(7):
        current = next_week_monday + timedelta(days=i)
        dates.append(current.strftime('%Y-%m-%d'))
    return dates

# 读取CSV文件的数据
def read_csv_values(csv_path, count):
    """读取CSV文件的指定数量的数据值"""
    values = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= count:
                    break
                # 提取数值部分
                value_str = line.strip().split('→')[-1]
                try:
                    value = float(value_str)
                    values.append(value)
                except:
                    values.append(0.0)
    except FileNotFoundError:
        print(f"警告：文件 {csv_path} 未找到，使用默认值0")
    # 确保有指定数量的值
    while len(values) < count:
        values.append(0.0)
    return values

# 生成国内煤价预测数据
def generate_domestic_coal_price_data():
    """生成国内煤价预测数据"""
    dates = generate_workday_dates()
    count = len(dates)
    # 读取三个国内煤价文件
    cci4500 = read_csv_values(os.path.join(AUTOINFER_DIR, 'CCI4500infer.csv'), count)
    cci5000 = read_csv_values(os.path.join(AUTOINFER_DIR, 'CCI5000infer.csv'), count)
    cci5500 = read_csv_values(os.path.join(AUTOINFER_DIR, 'CCI5500infer.csv'), count)
    
    data = {
        '日期': dates,
        'CCI4500': cci4500,
        'CCI5000': cci5000,
        'CCI5500': cci5500
    }
    return pd.DataFrame(data)

# 生成进口煤价预测数据
def generate_import_coal_price_data():
    """生成进口煤价预测数据"""
    dates = generate_workday_dates()
    count = len(dates)
    # 读取三个进口煤价文件
    cci3800out = read_csv_values(os.path.join(AUTOINFER_DIR, 'CCI3800outinfer.csv'), count)
    cci4700out = read_csv_values(os.path.join(AUTOINFER_DIR, 'CCI4700outinfer.csv'), count)
    cci5500out = read_csv_values(os.path.join(AUTOINFER_DIR, 'CCI5500outinfer.csv'), count)
    
    data = {
        '日期': dates,
        'CCI3800out': cci3800out,
        'CCI4700out': cci4700out,
        'CCI5500out': cci5500out
    }
    return pd.DataFrame(data)

# 生成国内运费预测数据
def generate_domestic_freight_data():
    """生成国内运费预测数据"""
    dates = generate_workday_dates()
    count = len(dates)
    # 读取国内运费文件
    insideinfer = read_csv_values(os.path.join(AUTOINFER_DIR, 'insideinfer.csv'), count)
    
    data = {
        '日期': dates,
        '国内运费': insideinfer
    }
    return pd.DataFrame(data)

# 生成国际运费预测数据
def generate_international_freight_data():
    """生成国际运费预测数据"""
    dates = generate_workday_dates()
    count = len(dates)
    # 读取国际运费文件
    outsideinfer = read_csv_values(os.path.join(AUTOINFER_DIR, 'outsideinfer.csv'), count)
    
    data = {
        '日期': dates,
        '国际运费': outsideinfer
    }
    return pd.DataFrame(data)

# 生成发电量预测数据
def generate_power_generation_data():
    """生成发电量预测数据"""
    dates = generate_weekly_dates()
    count = len(dates)  # 固定为7
    
    # 电厂和机组映射
    power_plants = {
        '可门': ['kemen_1.csv', 'kemen_2.csv', 'kemen_3.csv', 'kemen_4.csv', 'kemen_5.csv', 'kemen_6.csv'],
        '永安': ['yongan_7.csv', 'yongan_8.csv'],
        '邵武': ['shaowu_3.csv', 'shaowu_4.csv'],
        '漳平': ['zhangping_5.csv', 'zhangping_6.csv']
    }
    
    # 构建数据结构
    data = {'日期': dates}
    
    # 读取每个电厂的每个机组数据
    for plant, units in power_plants.items():
        total = [0] * count
        for i, unit_file in enumerate(units):
            unit_name = f'{plant}机组{i+1}'
            unit_data = read_csv_values(os.path.join(ELECDATA_DIR, unit_file), count)
            data[unit_name] = unit_data
            # 计算总发电量
            for j in range(count):
                total[j] += unit_data[j]
        # 添加总发电量
        total_name = f'{plant}总发电量'
        data[total_name] = total
    
    return pd.DataFrame(data)

# 主函数
def main():
    """主函数，生成Excel文件"""
    print("开始生成预测数据Excel文件...")
    
    # 生成各个预测数据
    print("1. 生成国内煤价预测数据...")
    domestic_coal_df = generate_domestic_coal_price_data()
    
    print("2. 生成进口煤价预测数据...")
    import_coal_df = generate_import_coal_price_data()
    
    print("3. 生成国内运费预测数据...")
    domestic_freight_df = generate_domestic_freight_data()
    
    print("4. 生成国际运费预测数据...")
    international_freight_df = generate_international_freight_data()
    
    print("5. 生成发电量预测数据...")
    power_generation_df = generate_power_generation_data()
    
    # 生成Excel文件
    report_filename = generate_report_filename()
    output_file = os.path.join(output_dir, f'{report_filename}.xlsx')
    print(f"\n正在写入Excel文件: {output_file}")
    
    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            # 生成国内煤价预测子表
            domestic_coal_df.to_excel(writer, sheet_name='国内煤价预测', index=False)
            
            # 生成进口煤价预测子表
            import_coal_df.to_excel(writer, sheet_name='进口煤价预测', index=False)
            
            # 生成国内运费预测子表
            domestic_freight_df.to_excel(writer, sheet_name='国内运费预测', index=False)
            
            # 生成国际运费预测子表
            international_freight_df.to_excel(writer, sheet_name='国际运费预测', index=False)
            
            # 生成发电量预测子表
            power_generation_df.to_excel(writer, sheet_name='发电量预测', index=False)
        
        print(f"\nExcel文件生成成功: {output_file}")
        print("文件包含以下子表:")
        print("1. 国内煤价预测")
        print("2. 进口煤价预测")
        print("3. 国内运费预测")
        print("4. 国际运费预测")
        print("5. 发电量预测")
    except Exception as e:
        print(f"生成Excel文件时出错: {e}")
        print("尝试使用xlwt库生成.xls文件...")
        
        # 尝试使用xlwt库
        try:
            import xlwt
            workbook = xlwt.Workbook()
            
            # 生成国内煤价预测子表
            sheet1 = workbook.add_sheet('国内煤价预测')
            for i, row in enumerate(domestic_coal_df.values.tolist()):
                for j, cell in enumerate([domestic_coal_df.columns[j]] + row):
                    sheet1.write(0, j, domestic_coal_df.columns[j])
                    sheet1.write(i+1, j, cell)
            
            # 生成进口煤价预测子表
            sheet2 = workbook.add_sheet('进口煤价预测')
            for i, row in enumerate(import_coal_df.values.tolist()):
                for j, cell in enumerate([import_coal_df.columns[j]] + row):
                    sheet2.write(0, j, import_coal_df.columns[j])
                    sheet2.write(i+1, j, cell)
            
            # 生成国内运费预测子表
            sheet3 = workbook.add_sheet('国内运费预测')
            for i, row in enumerate(domestic_freight_df.values.tolist()):
                for j, cell in enumerate([domestic_freight_df.columns[j]] + row):
                    sheet3.write(0, j, domestic_freight_df.columns[j])
                    sheet3.write(i+1, j, cell)
            
            # 生成国际运费预测子表
            sheet4 = workbook.add_sheet('国际运费预测')
            for i, row in enumerate(international_freight_df.values.tolist()):
                for j, cell in enumerate([international_freight_df.columns[j]] + row):
                    sheet4.write(0, j, international_freight_df.columns[j])
                    sheet4.write(i+1, j, cell)
            
            # 生成发电量预测子表
            sheet5 = workbook.add_sheet('发电量预测')
            for i, row in enumerate(power_generation_df.values.tolist()):
                for j, cell in enumerate([power_generation_df.columns[j]] + row):
                    sheet5.write(0, j, power_generation_df.columns[j])
                    sheet5.write(i+1, j, cell)
            
            output_file_xls = os.path.join(output_dir, f'{report_filename}.xls')
            workbook.save(output_file_xls)
            print(f"Excel文件生成成功: {output_file_xls}")
        except Exception as e2:
            print(f"使用xlwt库生成文件时也出错: {e2}")
            print("生成CSV文件作为替代...")
            
            # 生成CSV文件
            output_file_csv = os.path.join(output_dir, f'{report_filename}.csv')
            with open(output_file_csv, 'w', newline='', encoding='utf-8') as f:
                # 写入国内煤价预测
                f.write('国内煤价预测,,,\n')
                f.write('日期,CCI4500,CCI5000,CCI5500\n')
                for _, row in domestic_coal_df.iterrows():
                    f.write(f"{row['日期']},{row['CCI4500']},{row['CCI5000']},{row['CCI5500']}\n")
                f.write('\n')
                
                # 写入进口煤价预测
                f.write('进口煤价预测,,,\n')
                f.write('日期,CCI3800out,CCI4700out,CCI5500out\n')
                for _, row in import_coal_df.iterrows():
                    f.write(f"{row['日期']},{row['CCI3800out']},{row['CCI4700out']},{row['CCI5500out']}\n")
                f.write('\n')
                
                # 写入国内运费预测
                f.write('国内运费预测,,\n')
                f.write('日期,国内运费\n')
                for _, row in domestic_freight_df.iterrows():
                    f.write(f"{row['日期']},{row['国内运费']}\n")
                f.write('\n')
                
                # 写入国际运费预测
                f.write('国际运费预测,,\n')
                f.write('日期,国际运费\n')
                for _, row in international_freight_df.iterrows():
                    f.write(f"{row['日期']},{row['国际运费']}\n")
                f.write('\n')
                
                # 写入发电量预测
                f.write('发电量预测,,,,,,,,,,,,,,,,\n')
                headers = list(power_generation_df.columns)
                f.write(','.join(headers) + '\n')
                for _, row in power_generation_df.iterrows():
                    row_values = [str(row[col]) for col in headers]
                    f.write(','.join(row_values) + '\n')
            
            print(f"CSV文件生成成功: {output_file_csv}")
            print("请在Excel中打开此文件，然后手动将不同部分的数据复制到新的工作表中。")

if __name__ == '__main__':
    main()
