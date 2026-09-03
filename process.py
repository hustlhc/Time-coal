import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys

def load_workdays_from_txt(txt_file):
    """从txt文件加载非节假日日期"""
    workdays = []
    try:
        with open(txt_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '正常工作日' in line:
                    # 提取日期部分，格式如：2025-10-17
                    date_str = line.split(' ')[1]
                    workdays.append(date_str)
        # print(f"从 {txt_file} 加载了 {len(workdays)} 个工作日")
        return workdays
    except Exception as e:
        print(f"加载工作日文件失败: {str(e)}")
        return []

def update_result_file(result_file, predict_file, data_file, index, workdays):
    
    try:
        # 读取三个文件
        result_df = pd.read_csv(result_file, keep_default_na=False)
        predict_df = pd.read_csv(predict_file, header=None)
        data_df = pd.read_csv(data_file, keep_default_na=False)
        
        # print(f"读取文件成功:")
        print(f"  result.csv: {len(result_df)} 行")
        print(f"  predict.csv: {len(predict_df)} 行")
        print(f"  data.csv: {len(data_df)} 行, {len(data_df.columns)} 列")
        
        # 检查result.csv的列名
        expected_columns = ['date', '真实值', '预测值']
        if not all(col in result_df.columns for col in expected_columns):
            print("错误: result.csv 必须包含 'date', '真实值', '预测值' 三列")
            return False
        
        # 创建data.csv的日期到真实值的映射字典
        data_date_to_value = {}
        for data_idx, data_row in data_df.iterrows():
            data_date = str(data_row.iloc[0])  # data.csv的日期（第一列）
            real_value = data_row.iloc[index]   # 指定索引的真实值
            data_date_to_value[data_date] = real_value
        
        # print(f"创建了 {len(data_date_to_value)} 个日期到真实值的映射")
        
        # 只更新result.csv中有日期的行的真实值
        updated_count = 0
        skipped_count = 0
        
        for result_idx, result_row in result_df.iterrows():
            result_date = str(result_row['date'])
            
            # 跳过空日期行（保持为空）
            if result_date == 'nan' or result_date == '' or result_date == 'None':
                skipped_count += 1
                continue
                
            # 检查该日期是否在data.csv中存在
            if result_date in data_date_to_value:
                real_value = data_date_to_value[result_date]
                current_real_value = result_row['真实值']
                
                # 如果真实值为空或者为NaN，进行更新
                if current_real_value == '' or current_real_value == 'nan' or pd.isna(current_real_value):
                    result_df.at[result_idx, '真实值'] = real_value
                    # print(f"更新日期 {result_date} 的真实值: {real_value}")
                    updated_count += 1
        
        # print(f"真实值更新统计: 更新了 {updated_count} 行，跳过了 {skipped_count} 行空日期")
        
        # 更新预测值 - 分为两个阶段
        
        # 第一阶段：填充真实值为空的行
        predict_index = 0
        filled_count = 0
        
        # 找到所有真实值为空的行
        empty_real_rows = result_df[
            (result_df['真实值'] == '') | 
            (result_df['真实值'] == 'nan') | 
            (pd.isna(result_df['真实值']))
        ]
        
        # print(f"找到 {len(empty_real_rows)} 行真实值为空的行")
        
        # 按顺序为真实值为空的行填入预测值
        for idx in empty_real_rows.index:
            if predict_index < len(predict_df):
                new_predict = predict_df.iloc[predict_index, 0]
                result_df.at[idx, '预测值'] = new_predict
                # print(f"第一阶段 - 更新第 {idx} 行预测值: {new_predict} (真实值为空)")
                predict_index += 1
                filled_count += 1
            else:
                break
        
        # print(f"第一阶段填充了 {filled_count} 个预测值")
        
        # 第二阶段：如果还有剩余的预测值，添加到末尾
        if predict_index < len(predict_df):
            remaining_count = len(predict_df) - predict_index
            # print(f"开始第二阶段: 将剩余的 {remaining_count} 个预测值添加到末尾")
            
            for i in range(predict_index, len(predict_df)):
                new_predict = predict_df.iloc[i, 0]
                new_row = {
                    'date': '',  # 日期为空
                    '真实值': '',  # 真实值为空
                    '预测值': new_predict
                }
                result_df = pd.concat([result_df, pd.DataFrame([new_row])], ignore_index=True)
        
        # 为有预测值的空日期行填入工作日日期
        fill_dates_for_predictions(result_df, workdays)
        
        # 保存更新后的result.csv，保持空值为空
        result_df.to_csv(result_file, index=False, encoding='utf-8-sig', na_rep='')
        print(f"更新完成! 结果已保存到 {result_file}")
        print(f"最终result.csv: {len(result_df)} 行")
        # print(f"总共使用了 {len(predict_df)} 个预测值")
        
        return True
        
    except Exception as e:
        print(f"处理过程中出现错误: {str(e)}")
        return False

def fill_dates_for_predictions(result_df, workdays):
    """为有预测值的空日期行填入工作日日期（仅限txt文件中存在的日期）"""
    # 找到有预测值且日期为空的行的索引
    prediction_indices = result_df[
        (result_df['预测值'] != '') & 
        (result_df['预测值'] != 'nan') & 
        (~pd.isna(result_df['预测值'])) &
        (result_df['date'] == '')
    ].index
    
    if len(prediction_indices) == 0:
        # print("没有找到有预测值且日期为空的行的索引")
        return
    
    # print(f"找到 {len(prediction_indices)} 行有预测值且日期为空的行的索引")
    
    # 找到最后一个有日期的行
    dated_rows = result_df[result_df['date'] != '']
    if len(dated_rows) == 0:
        # print("没有找到有日期的行，无法确定起始日期")
        return
    
    last_date = dated_rows['date'].iloc[-1]
    # print(f"最后一个日期: {last_date}")
    
    # 在workdays中找到最后一个日期的位置
    try:
        last_date_index = workdays.index(last_date)
        # print(f"在workdays中找到 {last_date}，索引: {last_date_index}")
    except ValueError:
        print(f"在workdays中未找到 {last_date}，使用workdays的第一个日期")
        last_date_index = -1  # 如果没找到，从第一个工作日开始
    
    # 为有预测值但无日期的行填入日期（仅当workdays中有足够的日期时）
    date_index = last_date_index + 1
    filled_count = 0
    
    for idx in prediction_indices:
        if date_index < len(workdays):
            result_df.at[idx, 'date'] = workdays[date_index]
            # print(f"为第 {idx} 行填入日期: {workdays[date_index]}")
            date_index += 1
            filled_count += 1
        else:
            # print(f"workdays中的日期已用完，第 {idx} 行及后续行保持日期为空")
            break
    
    # print(f"成功为 {filled_count} 行填入工作日日期")

def main():
    # 从txt文件加载工作日
    workdays = load_workdays_from_txt("workdays.txt")  # 修改为实际的txt文件名
    
    coal_file = [
        "CCI4500infer.csv", "CCI5000infer.csv", "CCI5500infer.csv", 
        "CCI3800outinfer.csv", "CCI4700outinfer.csv", "CCI5500outinfer.csv"
    ]
    trans_file = ["insideinfer.csv", "outsideinfer.csv"]
    
    i = 7
    for file_path in coal_file:
        i = i - 1
        result_file = "output/" + file_path
        success = update_result_file(result_file, "autoinfer/" + file_path, "dataset/pre_coal/coal_new.csv", -i, workdays)
        if success:
            print("脚本执行成功!")
        else:
            print("脚本执行失败!")
            sys.exit(1)
    
    i = 0
    for file_path in trans_file:
        i = i + 1
        result_file = "output/" + file_path
        success = update_result_file(result_file, "autoinfer/" + file_path, "dataset/pre_coal/coal_freight.csv", -i, workdays)
        if success:
            print("脚本执行成功!")
        else:
            print("脚本执行失败!")
            sys.exit(1)

if __name__ == "__main__":
    main()