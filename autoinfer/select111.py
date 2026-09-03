import pandas as pd
import numpy as np
import glob
import os
import argparse

def calculate_mape(predictions, actuals):
    """
    计算MAPE（平均绝对百分比误差）
    predictions: 预测值列表（前10个预测值）
    actuals: 真实值列表（对应的10个真实值）
    """
    predictions = np.array(predictions)
    actuals = np.array(actuals)
    
    # 避免除零错误，将实际值为0的位置替换为很小的数
    actuals = np.where(actuals == 0, 1e-10, actuals)
    
    # 计算MAPE
    mape = np.mean(np.abs((actuals - predictions) / actuals)) * 100
    return mape

def calculate_direction_accuracy(predictions, actuals):
    """
    计算涨跌预测正确率
    比较预测值的涨跌方向与真实值的涨跌方向
    10天数据只能计算9天的涨跌结果
    """
    if len(actuals) < 2:
        return 0.0, 0, 0
    
    correct_count = 0
    total_count = 0
    
    # 从第2天开始计算涨跌（第1天没有前一天的基准）
    for i in range(1, len(predictions)):
        # 前一天的基准值（真实值）
        prev_actual = actuals[i-1]
        current_pred = predictions[i]
        current_actual = actuals[i]
        
        # 预测涨跌方向
        pred_direction = 1 if current_pred > prev_actual else (-1 if current_pred < prev_actual else 0)
        
        # 实际涨跌方向
        actual_direction = 1 if current_actual > prev_actual else (-1 if current_actual < prev_actual else 0)
        
        # 只有当两个方向都明确时才计数
        if pred_direction != 0 and actual_direction != 0:
            if pred_direction == actual_direction:
                correct_count += 1
            total_count += 1
    
    # 如果没有有效比较，返回0
    if total_count == 0:
        return 0.0, 0, 0
    
    accuracy = correct_count / total_count * 100
    return accuracy, correct_count, total_count

def calculate_scores(mape, direction_accuracy, correct_count, total_count):
    """
    计算各项得分
    MAPE得分 = 1 / (MAPE × 100)
    趋势正确率得分 = 正确率 × 1.5
    """
    # 计算MAPE得分
    # MAPE为2%时：1 / (2% × 100) = 1 / (0.02 × 100) = 1 / 2 = 0.5
    if mape > 0:
        mape_score = 1 / (mape / 100 * 100)  # mape/100 将百分比转为小数
    else:
        mape_score = 10  # 如果MAPE为0，给一个很高的分数
    
    # 计算趋势正确率得分
    direction_score = (correct_count / total_count) * 1.5 if total_count > 0 else 0
    
    # 综合得分 = MAPE得分 + 趋势正确率得分
    comprehensive_score = mape_score + direction_score
    
    return mape_score, direction_score, comprehensive_score

def main():
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='计算预测值与真实值的MAPE和涨跌正确率并排序')
    parser.add_argument('--true_col', type=int, default=-1, 
                       help='真实值所在列索引（从0开始，-1表示最后一列，-2表示倒数第二列，依此类推）')
    parser.add_argument('--data_file', type=str, default='/home/chenty/Time-Series-Library/dataset/pre_coal/coal_new.csv',
                       help='真实值数据文件名，默认为data.csv')
    parser.add_argument('--sort_by', type=str, default='comprehensive', 
                       choices=['mape', 'direction', 'comprehensive'],
                       help='排序依据：mape（MAPE升序）、direction（涨跌正确率降序）或 comprehensive（综合评分）')
    
    args = parser.parse_args()
    
    # 读取真实值数据
    try:
        actual_data = pd.read_csv(args.data_file)
        
        # 根据列索引获取真实值列
        if args.true_col < 0:
            # 负索引：从后往前数
            col_index = actual_data.shape[1] + args.true_col
        else:
            # 正索引：从前往后数
            col_index = args.true_col
        
        # 检查列索引是否有效
        if col_index < 0 or col_index >= actual_data.shape[1]:
            print(f"错误：列索引 {args.true_col} 超出范围（可用列数：{actual_data.shape[1]}）")
            print(f"可用列名: {list(actual_data.columns)}")
            return
        
        # 获取指定列的最后10行作为真实值
        true_column = actual_data.iloc[:, col_index]
        actual_values = true_column.iloc[-10:].values  # 取最后10个值
        
        print(f"使用列 '{actual_data.columns[col_index]}' 的最后10行作为真实值")
        print(f"真实值范围: {actual_values.min():.4f} ~ {actual_values.max():.4f}")
        
    except FileNotFoundError:
        print(f"错误：找不到文件 {args.data_file}")
        return
    except Exception as e:
        print(f"读取 {args.data_file} 文件时出错: {e}")
        return
    
    # 获取所有CSV文件（排除data_file）
    csv_files = glob.glob("*.csv")
    csv_files = [f for f in csv_files if f != args.data_file]
    
    if not csv_files:
        print("未找到预测文件")
        return
    
    results = []
    best_predictions = None
    best_file = None
    best_param_name = None
    best_comprehensive_score = -float('inf')
    
    # 处理每个预测文件
    for file in csv_files:
        try:
            # 读取预测数据
            pred_data = pd.read_csv(file)
            
            # 检查数据行数
            if len(pred_data) < 10:
                print(f"警告：文件 {file} 数据行数不足10行")
                continue
            
            # 获取前10行预测值（使用第一列）
            predictions = pred_data.iloc[:10, 0].values.flatten()
            
            # 检查数据长度匹配
            if len(predictions) != 10:
                print(f"警告：文件 {file} 预测值数量({len(predictions)})不等于10")
                continue
            
            # 计算MAPE（使用全部10天数据）
            mape = calculate_mape(predictions, actual_values)
            
            # 计算涨跌正确率（使用9天数据，从第2天开始）
            direction_accuracy, correct_count, total_count = calculate_direction_accuracy(predictions, actual_values)
            
            # 计算各项得分
            mape_score, direction_score, comprehensive_score = calculate_scores(
                mape, direction_accuracy, correct_count, total_count
            )
            
            # 获取文件名（不含扩展名）作为参数标识
            param_name = os.path.splitext(file)[0]
            
            results.append({
                '参数组': param_name,
                'MAPE(%)': mape,
                '涨跌正确率(%)': direction_accuracy,
                '正确数/总数': f"{correct_count}/{total_count}",
                'MAPE得分': mape_score,
                '趋势得分': direction_score,
                '综合评分': comprehensive_score,
                '预测文件': file,
                '预测值范围': f"{predictions.min():.4f}~{predictions.max():.4f}"
            })
            
            # 更新最优结果（基于综合评分）
            if comprehensive_score > best_comprehensive_score:
                best_comprehensive_score = comprehensive_score
                best_predictions = predictions
                best_file = file
                best_param_name = param_name
                best_mape = mape
                best_direction_accuracy = direction_accuracy
                best_correct_count = correct_count
                best_total_count = total_count
                best_mape_score = mape_score
                best_direction_score = direction_score
            
        except Exception as e:
            print(f"处理文件 {file} 时出错: {e}")
            continue
    
    if not results:
        print("没有成功处理任何文件")
        return
    
    # 根据排序依据进行排序
    if args.sort_by == 'mape':
        results_df = pd.DataFrame(results).sort_values('MAPE(%)', ascending=True)
        sort_info = "MAPE升序"
    elif args.sort_by == 'direction':
        results_df = pd.DataFrame(results).sort_values('涨跌正确率(%)', ascending=False)
        sort_info = "涨跌正确率降序"
    else:  # comprehensive
        results_df = pd.DataFrame(results).sort_values('综合评分', ascending=False)
        sort_info = "综合评分降序"
    
    # 重置索引并显示漂亮的序号
    results_df = results_df.reset_index(drop=True)
    results_df.index = results_df.index + 1
    
    # 输出总体排序结果
    print("\n" + "=" * 120)
    print(f"模型评估结果 - {sort_info}")
    print("=" * 120)
    print(f"{'排名':<6} {'参数组':<20} {'MAPE(%)':<10} {'涨跌正确率(%)':<15} {'正确数/总数':<12} {'MAPE得分':<10} {'趋势得分':<10} {'综合评分':<10} {'预测文件':<20}")
    print("-" * 120)
    
    for idx, row in results_df.iterrows():
        print(f"{idx:<6} {row['参数组']:<20} {row['MAPE(%)']:<10.4f} {row['涨跌正确率(%)']:<15.2f} {row['正确数/总数']:<12} {row['MAPE得分']:<10.4f} {row['趋势得分']:<10.4f} {row['综合评分']:<10.4f} {row['预测文件']:<20}")
    
    # 显示最优参数组的详细对比
    print("\n" + "=" * 95)
    print(f"最优参数组详细对比 - {best_param_name}")
    print(f"(MAPE: {best_mape:.4f}% [得分:{best_mape_score:.4f}], 涨跌正确率: {best_direction_accuracy:.2f}% ({best_correct_count}/{best_total_count}) [得分:{best_direction_score:.4f}], 综合评分: {best_comprehensive_score:.4f})")
    print("=" * 95)
    
    # 创建详细对比表格
    comparison_data = []
    
    for i in range(len(best_predictions)):
        pred_val = best_predictions[i]
        actual_val = actual_values[i]
        abs_error = abs(pred_val - actual_val)
        point_mape = abs((pred_val - actual_val) / actual_val) * 100 if actual_val != 0 else 0
        
        # 计算涨跌方向（第1天没有涨跌，从第2天开始）
        if i == 0:
            pred_direction = "-"
            actual_direction = "-"
            direction_correct = "-"
        else:
            prev_actual = actual_values[i-1]  # 前一天的基准值
            pred_direction = "↑" if pred_val > prev_actual else ("↓" if pred_val < prev_actual else "→")
            actual_direction = "↑" if actual_val > prev_actual else ("↓" if actual_val < prev_actual else "→")
            direction_correct = "✓" if pred_direction == actual_direction else "✗"
        
        comparison_data.append({
            '预测日': i + 1,
            '预测值': pred_val,
            '真实值': actual_val,
            '绝对误差': abs_error,
            'MAPE(%)': point_mape,
            '预测方向': pred_direction,
            '真实方向': actual_direction,
            '方向正确': direction_correct
        })
    
    comparison_df = pd.DataFrame(comparison_data)
    
    # 使用制表符和固定宽度格式化表格
    # 计算每列的实际宽度
    col_widths = {
        '预测日': 10,
        '预测值': 14,
        '真实值': 14,
        '绝对误差': 14,
        'MAPE(%)': 14,
        '预测方向': 12,
        '真实方向': 12,
        '方向正确': 12
    }
    
    # 打印表头
    header = (f"{'预测日':<{col_widths['预测日']}} "
              f"{'预测值':<{col_widths['预测值']}} "
              f"{'真实值':<{col_widths['真实值']}} "
              f"{'绝对误差':<{col_widths['绝对误差']}} "
              f"{'MAPE(%)':<{col_widths['MAPE(%)']}} "
              f"{'预测方向':<{col_widths['预测方向']}} "
              f"{'真实方向':<{col_widths['真实方向']}} "
              f"{'方向正确':<{col_widths['方向正确']}}")
    
    print(header)
    print("-" * len(header))
    
    # 打印数据行
    for _, row in comparison_df.iterrows():
        row_str = (f"{row['预测日']:<{col_widths['预测日']}} "
                   f"{row['预测值']:<{col_widths['预测值']}.4f} "
                   f"{row['真实值']:<{col_widths['真实值']}.4f} "
                   f"{row['绝对误差']:<{col_widths['绝对误差']}.4f} "
                   f"{row['MAPE(%)']:<{col_widths['MAPE(%)']}.4f} "
                   f"{row['预测方向']:<{col_widths['预测方向']}} "
                   f"{row['真实方向']:<{col_widths['真实方向']}} "
                   f"{row['方向正确']:<{col_widths['方向正确']}}")
        print(row_str)
    
    # 添加汇总统计
    print("-" * len(header))
    pred_mean = comparison_df['预测值'].mean()
    actual_mean = comparison_df['真实值'].mean()
    error_mean = comparison_df['绝对误差'].mean()
    mape_mean = comparison_df['MAPE(%)'].mean()
    
    summary_str = (f"{'汇总':<{col_widths['预测日']}} "
                   f"{pred_mean:<{col_widths['预测值']}.4f} "
                   f"{actual_mean:<{col_widths['真实值']}.4f} "
                   f"{error_mean:<{col_widths['绝对误差']}.4f} "
                   f"{mape_mean:<{col_widths['MAPE(%)']}.4f} "
                   f"{'-':<{col_widths['预测方向']}} "
                   f"{'-':<{col_widths['真实方向']}} "
                   f"{'-':<{col_widths['方向正确']}}")
    print(summary_str)
    
    # 保存结果到CSV文件
    output_file = 'model_evaluation_results.csv'
    results_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    # 保存最优参数组的详细对比
    best_comparison_file = f'best_comparison_{best_param_name}.csv'
    comparison_df.to_csv(best_comparison_file, index=False, encoding='utf-8-sig')
    
    print(f"\n结果已保存到: {output_file}")
    print(f"最优参数组详细对比已保存到: {best_comparison_file}")
    
    # 显示统计信息
    print(f"\n统计信息:")
    print(f"处理文件总数: {len(csv_files)}")
    print(f"成功处理文件数: {len(results)}")
    print(f"最佳MAPE: {results_df['MAPE(%)'].min():.4f}%")
    print(f"最佳涨跌正确率: {results_df['涨跌正确率(%)'].max():.2f}%")
    print(f"最佳综合评分: {results_df['综合评分'].max():.4f}")

if __name__ == "__main__":
    main()