import pandas as pd
import numpy as np
from datetime import datetime
import os
import warnings

def parse_meidian_daily(file_path):
    """
    解析煤电日报文件，支持Excel和CSV格式
    按电厂和机组拆分数据
    """
    print(f"正在读取文件: {file_path}")
    
    # 判断文件类型
    file_ext = os.path.splitext(file_path)[1].lower()
    
    df = None
    
    if file_ext in ['.xlsx', '.xls']:
        # Excel文件处理
        engines = ['openpyxl', 'xlrd', None]
        for engine in engines:
            try:
                if engine:
                    df = pd.read_excel(file_path, sheet_name=0, engine=engine)
                else:
                    df = pd.read_excel(file_path, sheet_name=0)
                print(f"成功使用 {engine or '默认'} 引擎读取Excel文件")
                break
            except Exception as e:
                print(f"使用 {engine or '默认'} 引擎失败: {e}")
                continue
    elif file_ext == '.csv':
        # CSV文件处理
        try:
            # 尝试不同的编码格式
            encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']
            for encoding in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    print(f"成功使用 {encoding} 编码读取CSV文件")
                    break
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    print(f"使用 {encoding} 编码失败: {e}")
                    continue
            
            if df is None:
                # 最后尝试自动检测编码
                import chardet
                with open(file_path, 'rb') as f:
                    raw_data = f.read()
                    result = chardet.detect(raw_data)
                    encoding = result['encoding']
                    df = pd.read_csv(file_path, encoding=encoding)
                    print(f"使用检测到的编码 {encoding} 读取CSV文件")
        except Exception as e:
            print(f"读取CSV文件失败: {e}")
    else:
        raise Exception(f"不支持的文件格式: {file_ext}")
    
    if df is None:
        raise Exception("无法读取文件，请检查文件格式或安装必要的库")
    
    # 检查必要的列是否存在
    required_columns = ['orgzAbbName', 'crewSetAbbName', 'measureAbbName', 
                       'measureValue', 'periodId']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        print(f"警告: 文件中缺少以下列: {missing_columns}")
        print(f"现有列: {list(df.columns)}")
        
        # 尝试匹配可能的列名变体
        column_mapping = {}
        for col in required_columns:
            for df_col in df.columns:
                if col.lower() in df_col.lower() or df_col.lower() in col.lower():
                    column_mapping[col] = df_col
                    break
        
        if column_mapping:
            print(f"将使用列名映射: {column_mapping}")
            df = df.rename(columns=column_mapping)
    
    # 再次检查必要的列
    if not all(col in df.columns for col in required_columns):
        print(f"错误: 仍然缺少必要的列")
        print(f"请确保文件包含以下列: {required_columns}")
        print(f"当前列: {list(df.columns)}")
        return None, None
    
    # 过滤出邵武、可门、永安、漳平的数据
    valid_orgs = ['邵武', '可门', '永安', '漳平']
    df = df[df['orgzAbbName'].isin(valid_orgs)]
    
    # 获取所有唯一的日期
    dates = df['periodId'].unique()
    print(f"找到日期: {dates}")
    
    return df, dates

def get_plant_config(org_name):
    """
    根据电厂名称返回对应的机组配置
    """
    configs = {
        '邵武': {
            'unit_files': {
                '邵武#3': 'shaowu_3.csv',
                '邵武#4': 'shaowu_4.csv'
            },
            'plant_files': ['shaowu_3.csv', 'shaowu_4.csv'],  # 厂级数据需要写入这两个文件
            'total_file': 'shaowu.csv',
            'units': ['邵武#3', '邵武#4'],
            'plant_level': '厂级'
        },
        '可门': {
            'unit_files': {
                '可门#1': 'kemen_1.csv',
                '可门#2': 'kemen_2.csv',
                '可门#3': 'kemen_3.csv',
                '可门#4': 'kemen_4.csv',
                '可门#5': 'kemen_5.csv',
                '可门#6': 'kemen_6.csv'
            },
            'plant_files': ['kemen_1.csv', 'kemen_2.csv', 'kemen_3.csv', 'kemen_4.csv', 'kemen_5.csv', 'kemen_6.csv'],
            'total_file': 'kemen.csv',
            'units': ['可门#1', '可门#2', '可门#3', '可门#4', '可门#5', '可门#6'],
            'plant_level': '厂级'
        },
        '永安': {
            'unit_files': {
                '永安#7': 'yongan_7.csv',
                '永安#8': 'yongan_8.csv'
            },
            'plant_files': ['yongan_7.csv', 'yongan_8.csv'],
            'total_file': 'yongan.csv',
            'units': ['永安#7', '永安#8'],
            'plant_level': '厂级'
        },
        '漳平': {
            'unit_files': {
                '漳平#5': 'zhangping_5.csv',
                '漳平#6': 'zhangping_6.csv'
            },
            'plant_files': ['zhangping_5.csv', 'zhangping_6.csv'],
            'total_file': 'zhangping.csv',
            'units': ['漳平#5', '漳平#6'],
            'plant_level': '厂级'
        }
    }
    return configs.get(org_name)

def get_csv_columns(file_path):
    """
    获取CSV文件中的所有列名
    """
    try:
        df = pd.read_csv(file_path)
        return set(df.columns)
    except FileNotFoundError:
        return set(['date'])  # 新文件只有date列
    except Exception as e:
        print(f"读取文件 {file_path} 列名时出错: {e}")
        return set(['date'])

def map_measure_to_column(measure_name, unit_name, org_name, existing_columns):
    """
    将指标名称映射到CSV中的列名
    只返回CSV中已存在的列
    """
    # 基础映射表（指标名 -> 列名后缀）
    measure_suffix = {
        # 发电相关指标
        '发电量': '发电量',
        '上网电量': '上网电量',
        '综合厂用电量': '综合厂用电量',
        '发电用厂用电量': '发电用厂用电量',
        '供热厂用电量': '供热厂用电量',
        '发电标煤量': '发电标煤量',
        '供电煤耗': '供电煤耗',
        '综合供电煤耗': '综合供电煤耗',
        '负荷率': '负荷率',
        '利用小时': '利用小时',
        '综合厂用电率': '综合厂用电率',
        '发电厂用电率': '发电厂用电率',
        '供热用厂用电率': '供热用厂用电率',
        '开机率': '开机率',
        '运行小时': '运行小时',
        '日电网调度发电量': '日电网调度发电量',
        '发电设备平均容量': '发电设备平均容量',
        '期末运行容量': '期末运行容量',
        '等效运行容量': '等效运行容量',
        '等效运行小时': '等效运行小时',
        '期末运行台数': '期末运行台数',
        
        # 煤炭相关指标
        '耗煤量': '耗煤量',
        '发电耗煤量': '发电耗煤量',
        '供热耗煤量': '供热耗煤量',
        '存煤量': '存煤量',
        '煤炭可用天数': '煤炭可用天数',
        '供煤量': '供煤量',
        '账面库存': '账面库存',
        '库存增长量': '库存增长量',
        
        # 供热相关指标
        '供热量': '供热量',
        '综合供热标煤耗': '综合供热标煤耗',
        
        # 油相关指标
        '库存油量': '库存油量',
        '发电耗油量': '发电耗油量',
        '供热耗油量': '供热耗油量',
        
        # 成本相关指标
        '边际贡献': '边际贡献',
        '边际成本': '边际成本',
        '入炉标煤单价': '入炉标煤单价',
        
        # 机组状态相关指标
        '期末机组运行方式': '期末机组运行方式',
        '改变前状态': '改变前状态',
        '开始时间ZT': '开始时间ZT',
        '原因ZT': '原因ZT',
        '机组状态变化1': '机组状态变化1',
        '开始时间1': '开始时间1',
        '原因1': '原因1',
        '机组状态变化2': '机组状态变化2',
        '开始时间2': '开始时间2',
        '原因2': '原因2',
        '机组状态变化3': '机组状态变化3',
        '开始时间3': '开始时间3',
        '原因3': '原因3',
        '机组状态变化4': '机组状态变化4',
        '开始时间4': '开始时间4',
        '原因4': '原因4',
        '机组状态变化5': '机组状态变化5',
        '开始时间5': '开始时间5',
        '原因5': '原因5',
        '开始检修日期': '开始检修日期',
        '检修结束日期': '检修结束日期',
        '检修延期': '检修延期',
        '检修延期原因': '检修延期原因',
    }
    
    if measure_name not in measure_suffix:
        return None
    
    # 根据机组名称构建列名
    if unit_name == '厂级':
        column_name = f"{org_name}_厂级_{measure_suffix[measure_name]}"
    else:
        # 保持原始格式，不替换#号
        column_name = f"{org_name}_{unit_name}_{measure_suffix[measure_name]}"
    
    # 只返回CSV中已存在的列
    if column_name in existing_columns:
        return column_name
    else:
        return None

def get_existing_data(file_path, date):
    """
    获取指定文件中特定日期的数据
    """
    try:
        df = pd.read_csv(file_path)
        # 过滤出指定日期的数据
        if 'date' in df.columns:
            return df[df['date'] == int(date)]
    except FileNotFoundError:
        return pd.DataFrame()
    except Exception as e:
        print(f"读取文件 {file_path} 出错: {e}")
        return pd.DataFrame()
    
    return pd.DataFrame()

def update_or_create_row(existing_df, date, unit_data, existing_columns):
    """
    更新现有行或创建新行
    只保留CSV中已有的列
    """
    if existing_df.empty:
        # 创建新行，只包含date和unit_data中且在existing_columns中的列
        row = {'date': int(date)}
        for col, value in unit_data.items():
            if col in existing_columns:
                row[col] = value
        return pd.DataFrame([row])
    else:
        # 更新现有行，只更新unit_data中且在existing_columns中的列
        row = existing_df.iloc[0].to_dict()
        for col, value in unit_data.items():
            if col in existing_columns:
                row[col] = value
        return pd.DataFrame([row])

def write_to_file(file_path, date, unit_data, existing_columns, unit_name):
    """
    将数据写入指定的文件
    """
    if not unit_data:
        print(f"    - {unit_name}: 没有需要写入的数据（所有指标在目标文件中都不存在）")
        return
    
    try:
        # 获取现有数据
        existing_df = get_existing_data(file_path, date)
        
        # 创建或更新行
        new_row_df = update_or_create_row(existing_df, date, unit_data, existing_columns)
        
        # 读取整个文件并更新
        try:
            full_df = pd.read_csv(file_path)
            # 删除已存在的该日期数据
            full_df = full_df[full_df['date'] != int(date)]
            # 添加新数据
            full_df = pd.concat([full_df, new_row_df], ignore_index=True)
            # 按日期排序
            full_df = full_df.sort_values('date')
            # 保存
            full_df.to_csv(file_path, index=False, encoding='utf-8-sig')
            print(f"    - 已更新 {file_path} 中 {unit_name} 的数据（共 {len(unit_data)} 个指标）")
        except FileNotFoundError:
            # 文件不存在，直接保存
            new_row_df.to_csv(file_path, index=False, encoding='utf-8-sig')
            print(f"    - 已创建 {file_path} 并写入 {unit_name} 的数据（共 {len(unit_data)} 个指标）")
        except Exception as e:
            print(f"    - 写入 {file_path} 出错: {e}")
    except Exception as e:
        print(f"    - 处理 {unit_name} 数据时出错: {e}")

def process_plant_data(df, date, org_name, config):
    """
    处理单个电厂的数据
    """
    # 过滤出当前电厂和日期的数据
    plant_df = df[(df['orgzAbbName'] == org_name) & 
                  (df['periodId'] == date)]
    
    if plant_df.empty:
        print(f"{org_name} {date} 无数据")
        return
    
    print(f"\n处理 {org_name} {date} 的数据，共 {len(plant_df)} 条记录")
    
    # 先处理厂级数据
    plant_level_df = plant_df[plant_df['crewSetAbbName'] == config['plant_level']]
    if not plant_level_df.empty:
        print(f"  发现厂级数据，共 {len(plant_level_df)} 条记录")
        
        # 构建厂级数据字典
        plant_data = {}
        target_files = list(config['plant_files'])
        if config.get('total_file'):
            target_files.append(config['total_file'])
        for _, row in plant_level_df.iterrows():
            measure_name = row['measureAbbName']
            measureValue = row['measureValue']
            
            if pd.notna(measureValue):
                # 厂级数据需要写入每个机组文件
                for target_file in target_files:
                    existing_columns = get_csv_columns(target_file)
                    col_name = map_measure_to_column(measure_name, config['plant_level'], org_name, existing_columns)
                    if col_name:
                        if target_file not in plant_data:
                            plant_data[target_file] = {}
                        plant_data[target_file][col_name] = measureValue
        
        # 写入厂级数据到每个机组文件
        for target_file, data in plant_data.items():
            existing_columns = get_csv_columns(target_file)
            write_to_file(target_file, date, data, existing_columns, f"{org_name}厂级")
    
    # 处理机组数据
    for unit_name in config['units']:
        # 过滤出当前机组的数据
        unit_data_df = plant_df[plant_df['crewSetAbbName'] == unit_name]
        
        if unit_data_df.empty:
            continue
        
        # 获取机组对应的文件
        file_path = config['unit_files'].get(unit_name)
        if not file_path:
            continue
        
        total_file = config.get('total_file')

        existing_columns_unit = get_csv_columns(file_path)
        existing_columns_total = get_csv_columns(total_file) if total_file else set()

        unit_data_for_unit_file = {}
        unit_data_for_total_file = {}
        for _, row in unit_data_df.iterrows():
            measure_name = row['measureAbbName']
            measureValue = row['measureValue']
            if pd.isna(measureValue):
                continue

            col_name_unit = map_measure_to_column(measure_name, unit_name, org_name, existing_columns_unit)
            if col_name_unit:
                unit_data_for_unit_file[col_name_unit] = measureValue

            if total_file:
                col_name_total = map_measure_to_column(measure_name, unit_name, org_name, existing_columns_total)
                if col_name_total:
                    unit_data_for_total_file[col_name_total] = measureValue

        write_to_file(file_path, date, unit_data_for_unit_file, existing_columns_unit, unit_name)

        if total_file:
            write_to_file(total_file, date, unit_data_for_total_file, existing_columns_total, f"{org_name}总表/{unit_name}")

def main():
    # 煤电日报文件路径（自动检测文件类型）
    daily_file = 'data_json/huodian.csv'  # 或 '煤电日报导出.xlsx'
    
    # 解析文件
    df, dates = parse_meidian_daily(daily_file)
    
    if df is None or dates is None:
        print("文件解析失败，请检查文件格式")
        return
    
    # 处理每个日期
    for date in dates:
        print(f"\n{'='*50}")
        print(f"处理日期: {date}")
        print('='*50)
        
        # 处理每个电厂
        for org_name in ['邵武', '可门', '永安', '漳平']:
            config = get_plant_config(org_name)
            if config:
                process_plant_data(df, date, org_name, config)
    
    print("\n所有数据处理完成！")

def create_template_files():
    """
    创建模板文件（如果不存在）
    """
    plants = {
        '邵武': ['shaowu_3.csv', 'shaowu_4.csv'],
        '可门': ['kemen_1.csv', 'kemen_2.csv', 'kemen_3.csv', 'kemen_4.csv', 'kemen_5.csv', 'kemen_6.csv'],
        '永安': ['yongan_7.csv', 'yongan_8.csv'],
        '漳平': ['zhangping_5.csv', 'zhangping_6.csv']
    }
    
    for plant, files in plants.items():
        for file in files:
            if not os.path.exists(file):
                # 创建空文件，只包含date列
                pd.DataFrame(columns=['date']).to_csv(file, index=False, encoding='utf-8-sig')
                print(f"已创建模板文件: {file}")

    total_files = ['kemen.csv', 'shaowu.csv', 'yongan.csv', 'zhangping.csv']
    for file in total_files:
        if not os.path.exists(file):
            pd.DataFrame(columns=['date']).to_csv(file, index=False, encoding='utf-8-sig')
            print(f"已创建模板文件: {file}")

if __name__ == "__main__":
    # 先创建模板文件
    create_template_files()
    
    # 执行主程序
    main()
