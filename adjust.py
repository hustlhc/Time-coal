import pandas as pd
import numpy as np
import os
import argparse
import subprocess
import glob
import re
import shutil
import time
import sys
from datetime import datetime

class Logger:
    def __init__(self):
        self.log_dir = "adjust_logs"
        self.ensure_log_dir()
        self.log_file = self.create_log_file()
        self.console_output = True
        
    def ensure_log_dir(self):
        """确保日志目录存在"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def create_log_file(self):
        """创建带时间戳的日志文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"adjust_log_{timestamp}.txt"
        log_path = os.path.join(self.log_dir, log_filename)
        return log_path
    
    def log(self, message, console=True):
        """记录日志信息"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        
        # 写入文件
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + '\n')
        
        # 控制台输出
        if console and self.console_output:
            print(log_message)
    
    def log_table(self, table_lines, console=True):
        """记录表格数据"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 写入文件
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}]\n")
            for line in table_lines:
                f.write(line + '\n')
            f.write('\n')
        
        # 控制台输出
        if console and self.console_output:
            for line in table_lines:
                print(line)
            print()

# 创建全局logger实例
logger = Logger()

def calculate_mape(predictions, actuals):
    """
    计算MAPE（平均绝对百分比误差）
    predictions: 预测值列表（第1-10条）
    actuals: 真实值列表（第2-11条，对应预测的10个实际值）
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
    计算涨跌预测正确率（包含平盘情况）
    使用11条真实值计算10个方向
    predictions: 第1-10条预测值
    actuals: 第1-11条真实值
    """
    if len(actuals) < 11 or len(predictions) < 10:
        return 0.0, 0, 0
    
    correct_count = 0
    total_count = 0
    
    # 计算10个方向（使用11条真实值）
    for i in range(10):  # 0-9，共10个方向
        # 第i天的基准值（真实值）
        prev_actual = actuals[i]  # 第i个真实值作为基准
        current_pred = predictions[i]  # 第i个预测值
        current_actual = actuals[i+1]  # 第i+1个真实值作为当前实际值
        
        # 预测涨跌方向（包含平盘）
        if current_pred > prev_actual:
            pred_direction = 1  # 上涨
        elif current_pred < prev_actual:
            pred_direction = -1  # 下跌
        else:
            pred_direction = 0  # 平盘
        
        # 实际涨跌方向（包含平盘）
        if current_actual > prev_actual:
            actual_direction = 1  # 上涨
        elif current_actual < prev_actual:
            actual_direction = -1  # 下跌
        else:
            actual_direction = 0  # 平盘
        
        # 所有情况都纳入统计（包括平盘）
        total_count += 1
        if pred_direction == actual_direction:
            correct_count += 1
    
    # 如果没有有效比较，返回0
    if total_count == 0:
        return 0.0, 0, 0
    
    accuracy = correct_count / total_count * 100
    return accuracy, correct_count, total_count

def calculate_scores(mape, correct_count, total_count):
    """
    计算各项得分
    MAPE得分 = 1 / MAPE
    趋势正确率得分 = 正确率 × 1.5
    """
    # 计算MAPE得分
    if mape > 0:
        mape_score = 1 / mape
    else:
        mape_score = 10  # 如果MAPE为0，给一个很高的分数
    
    # 计算趋势正确率得分
    direction_score = (correct_count / total_count) * 1.5 if total_count > 0 else 0
    
    # 综合得分 = MAPE得分 + 趋势正确率得分
    comprehensive_score = mape_score + direction_score
    
    return mape_score, direction_score, comprehensive_score

def parse_parameters_from_filename(filename):
    """
    从文件名解析参数
    格式：infer_${seq_len}_${down_sampling_window}_${down_sampling_layers}_${moving_avg}_${decomp_method}.csv
    """
    try:
        # 移除扩展名和infer_前缀
        base_name = filename.replace('.csv', '').replace('infer_', '')
        parts = base_name.split('_')
        
        # 处理分解方法参数（可能包含下划线）
        if len(parts) >= 5:
            # 前4个参数是固定的，剩下的部分合并为decomp_method
            params = {
                'seq_len': parts[0],
                'down_sampling_window': parts[1],
                'down_sampling_layers': parts[2],
                'moving_avg': parts[3],
                'decomp_method': '_'.join(parts[4:])  # 合并剩余部分
            }
        else:
            params = {
                'seq_len': 'unknown',
                'down_sampling_window': 'unknown',
                'down_sampling_layers': 'unknown',
                'moving_avg': 'unknown',
                'decomp_method': 'unknown'
            }
        
        return params
    except Exception as e:
        return None

def load_predictions_from_file(file_path):
    """
    从单个文件加载预测数据
    返回前10条预测值（第1-10条）
    """
    try:
        df = pd.read_csv(file_path, header=None)
        # 假设预测值在第一列，取前10条
        predictions = df.iloc[:10, 0].values  # 只取前10条
        return predictions
    except Exception as e:
        return None

def load_actuals(data_file, true_col):
    """
    加载真实值数据（最后11条）
    """
    try:
        df = pd.read_csv(data_file)
        
        # 根据列索引获取真实值列
        if true_col < 0:
            # 负索引：从后往前数
            col_index = df.shape[1] + true_col
        else:
            # 正索引：从前往后数
            col_index = true_col
        
        # 检查列索引是否有效
        if col_index < 0 or col_index >= df.shape[1]:
            return None
        
        # 获取最后11行真实值
        true_column = df.iloc[:, col_index]
        actuals = true_column.iloc[-11:].values
        
        return actuals
        
    except Exception as e:
        return None

def evaluate_single_model(model_file, actuals, model_name="当前模型"):
    """
    评估单个模型
    """
    # 加载预测数据（前10条）
    predictions = load_predictions_from_file(model_file)
    if predictions is None:
        return None
    
    # 检查数据长度
    if len(predictions) < 10 or len(actuals) < 11:
        return None
    
    # 使用前10条预测数据
    predictions_10 = predictions[:10]
    # 使用第2-11条真实值进行MAPE计算（对应10个预测值）
    actuals_for_mape = actuals[1:11]
    # 使用全部11条真实值进行方向计算
    actuals_for_direction = actuals
    
    # 计算MAPE
    mape = calculate_mape(predictions_10, actuals_for_mape)
    
    # 计算涨跌正确率（10个方向）
    direction_accuracy, correct_count, total_count = calculate_direction_accuracy(predictions_10, actuals_for_direction)
    
    # 计算各项得分
    mape_score, direction_score, comprehensive_score = calculate_scores(mape, correct_count, total_count)
    
    # 解析参数（如果是网格搜索文件）
    params = {}
    filename = os.path.basename(model_file)
    if filename.startswith('infer_'):
        params = parse_parameters_from_filename(filename)
    
    result = {
        'filename': filename,
        'file_path': model_file,
        'params': params,
        'mape': mape,
        'direction_accuracy': direction_accuracy,
        'correct_count': correct_count,
        'total_count': total_count,
        'mape_score': mape_score,
        'direction_score': direction_score,
        'comprehensive_score': comprehensive_score
    }
    
    return result

def evaluate_all_models(folder_path, actuals):
    """
    评估文件夹中所有CSV文件的模型
    """
    results = []
    
    # 获取所有CSV文件
    csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
    
    if not csv_files:
        return results
    
    for file_path in csv_files:
        filename = os.path.basename(file_path)
        
        # 跳过data.csv（如果是真实值文件）
        if filename == 'data.csv':
            continue
        
        result = evaluate_single_model(file_path, actuals, f"网格模型 {filename}")
        if result is not None:
            results.append(result)
    
    return results

def find_best_model(results):
    """
    找到得分最高的模型
    """
    if not results:
        return None
    
    best_model = max(results, key=lambda x: x['comprehensive_score'])
    return best_model

def run_grid_search(choice_script_path, target=None):
    """
    执行网格搜索脚本生成新的预测模型
    """
    if not os.path.exists(choice_script_path):
        return False
    
    # 构建执行命令
    if target:
        cmd = ['bash', choice_script_path, target]
    else:
        cmd = ['bash', choice_script_path]
    
    try:
        start_time = time.time()
        
        result = subprocess.run(cmd, 
                              capture_output=True, 
                              text=True)
        
        execution_time = time.time() - start_time
        
        if result.returncode == 0:
            logger.log(f"网格搜索执行成功 (耗时: {execution_time:.2f}秒)")
            return True
        else:
            logger.log(f"网格搜索执行失败 (耗时: {execution_time:.2f}秒)")
            return False
            
    except Exception as e:
        logger.log(f"执行网格搜索时出错: {e}")
        return False

def print_model_ranking_table(all_results, current_model_filename):
    """
    打印模型排名表
    """
    if not all_results:
        return
    
    # 按综合评分排序
    sorted_results = sorted(all_results, key=lambda x: x['comprehensive_score'], reverse=True)
    
    table_lines = []
    table_lines.append("=" * 100)
    table_lines.append("模型排名表")
    table_lines.append("=" * 100)
    table_lines.append(f"{'排名':<6} {'模型类型':<10} {'模型文件':<40} {'综合评分':<12} {'MAPE得分':<12} {'趋势得分':<12} {'MAPE(%)':<10} {'正确率(%)':<10}")
    table_lines.append("-" * 100)
    
    for i, result in enumerate(sorted_results, 1):
        model_type = "当前模型" if result['filename'] == current_model_filename else "网格模型"
        table_lines.append(f"{i:<6} {model_type:<10} {result['filename']:<40} {result['comprehensive_score']:<12.4f} "
              f"{result['mape_score']:<12.4f} {result['direction_score']:<12.4f} "
              f"{result['mape']:<10.4f} {result['direction_accuracy']:<10.2f}")
    
    table_lines.append("=" * 100)
    
    logger.log_table(table_lines)

def main():
    # 记录开始信息
    logger.log("=" * 80)
    logger.log("模型评估与优化开始")
    logger.log("=" * 80)
    logger.log(f"日志文件: {logger.log_file}")
    
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='评估当前模型，低于阈值时进行网格搜索选择最佳模型')
    parser.add_argument('--current_model', type=str, default='/home/chenty/Time-Series-Library/teninfer/CCI3800outinfer.csv',
                       help='当前模型预测文件路径')
    parser.add_argument('--grid_folder', type=str, required=True,
                       help='包含网格搜索模型预测CSV文件的文件夹路径')
    parser.add_argument('--data_file', type=str, default='/home/chenty/Time-Series-Library/dataset/pre_coal/coal_new.csv',
                       help='真实值数据文件，默认为data.csv')
    parser.add_argument('--true_col', type=int, default=-3,
                       help='真实值所在列索引（从0开始，-1表示最后一列，-2表示倒数第二列，依此类推）')
    parser.add_argument('--threshold', type=float, default=1.0,
                       help='综合评分阈值，低于此值将进行网格搜索并运行grid.sh脚本')
    parser.add_argument('--mape_threshold', type=float, default=0.5,
                       help='MAPE得分阈值，低于此值将进行网格搜索并运行grid.sh脚本')
    parser.add_argument('--direction_threshold', type=float, default=0.3,
                       help='趋势得分阈值，低于此值将进行网格搜索并运行grid.sh脚本')
    parser.add_argument('--check_all', action='store_true',
                       help='检查所有得分阈值，任一低于阈值都进行网格搜索')
    parser.add_argument('--choice_script', type=str, default='/home/chenty/Time-Series-Library/scripts/long_term_forecast/autocoal/choice.sh',
                       help='网格搜索脚本路径，默认为./choice.sh')
    parser.add_argument('--target', type=str, 
                       help='目标指数名称，例如：CCI进口3800, CCI进口4700等')
    
    args = parser.parse_args()
    
    # 记录参数信息
    logger.log("运行参数:")
    logger.log(f"  当前模型: {args.current_model}")
    logger.log(f"  网格文件夹: {args.grid_folder}")
    logger.log(f"  数据文件: {args.data_file}")
    logger.log(f"  真实值列: {args.true_col}")
    logger.log(f"  综合评分阈值: {args.threshold}")
    logger.log(f"  MAPE得分阈值: {args.mape_threshold}")
    logger.log(f"  趋势得分阈值: {args.direction_threshold}")
    logger.log(f"  检查所有阈值: {args.check_all}")
    logger.log(f"  网格搜索脚本: {args.choice_script}")
    logger.log(f"  目标: {args.target}")
    
    # 检查文件是否存在
    if not os.path.exists(args.current_model):
        logger.log(f"错误：当前模型文件 {args.current_model} 不存在")
        return
    
    if not os.path.exists(args.grid_folder):
        logger.log(f"错误：网格搜索文件夹 {args.grid_folder} 不存在")
        return
    
    if not os.path.exists(args.data_file):
        logger.log(f"错误：真实值文件 {args.data_file} 不存在")
        return
    
    # 加载真实值数据（最后11条）
    logger.log("正在加载真实值数据...")
    actuals = load_actuals(args.data_file, args.true_col)
    if actuals is None:
        logger.log("错误：无法加载真实值数据")
        return
    logger.log(f"成功加载真实值数据，共{len(actuals)}条")
    
    # 第一步：评估当前模型
    logger.log("")
    logger.log("第一步：评估当前模型")
    logger.log("-" * 40)
    
    current_model_result = evaluate_single_model(args.current_model, actuals, "当前模型")
    if current_model_result is None:
        logger.log("当前模型评估失败")
        return
    
    # 输出当前模型结果
    logger.log(f"当前模型: {current_model_result['filename']}")
    logger.log(f"综合评分: {current_model_result['comprehensive_score']:.4f}")
    logger.log(f"MAPE: {current_model_result['mape']:.4f}%")
    logger.log(f"涨跌正确率: {current_model_result['direction_accuracy']:.2f}%")
    
    # 检查当前模型是否达到阈值
    need_grid_search = False
    threshold_reasons = []
    
    if current_model_result['comprehensive_score'] < args.threshold:
        need_grid_search = True
        threshold_reasons.append(f"综合评分 {current_model_result['comprehensive_score']:.4f} < {args.threshold}")
    
    if args.check_all:
        if current_model_result['mape_score'] < args.mape_threshold:
            need_grid_search = True
            threshold_reasons.append(f"MAPE得分 {current_model_result['mape_score']:.4f} < {args.mape_threshold}")
        if current_model_result['direction_score'] < args.direction_threshold:
            need_grid_search = True
            threshold_reasons.append(f"趋势得分 {current_model_result['direction_score']:.4f} < {args.direction_threshold}")
    
    # 收集所有模型结果用于排名
    all_results = [current_model_result]
    
    # 第二步：如果当前模型不达标，进行网格搜索
    best_model = current_model_result
    
    if need_grid_search:
        logger.log("")
        logger.log("第二步：进行网格搜索")
        logger.log("-" * 40)
        logger.log(f"触发网格搜索的原因: {', '.join(threshold_reasons)}")
        
        # 执行网格搜索脚本生成新的模型文件
        grid_search_success = run_grid_search(args.choice_script, args.target)
        
        if grid_search_success:
            # 等待一段时间确保文件生成完成
            logger.log("等待文件生成完成...")
            time.sleep(5)
            
            # 评估所有网格搜索模型
            logger.log("评估网格搜索模型...")
            grid_results = evaluate_all_models(args.grid_folder, actuals)
            
            if grid_results:
                logger.log(f"找到 {len(grid_results)} 个网格模型")
                # 将网格搜索结果添加到总结果中
                all_results.extend(grid_results)
                
                # 找到最佳网格模型
                best_grid_model = find_best_model(grid_results)
                
                # 比较当前模型和最佳网格模型
                if best_grid_model['comprehensive_score'] > current_model_result['comprehensive_score']:
                    best_model = best_grid_model
                    improvement = best_grid_model['comprehensive_score'] - current_model_result['comprehensive_score']
                    logger.log(f"找到更优模型: {best_grid_model['filename']}")
                    logger.log(f"新模型得分: {best_grid_model['comprehensive_score']:.4f} (提升: {improvement:.4f})")
                else:
                    logger.log("当前模型已是最佳")
            else:
                logger.log("网格搜索未找到有效模型")
        else:
            logger.log("网格搜索执行失败")
    else:
        logger.log("当前模型已达到阈值，无需网格搜索")
    
    # 第三步：输出模型排名表
    logger.log("")
    logger.log("第三步：模型排名")
    logger.log("-" * 40)
    print_model_ranking_table(all_results, current_model_result['filename'])
    
    # 第四步：输出最终最佳模型信息
    logger.log("")
    logger.log("第四步：最终结果")
    logger.log("-" * 40)
    logger.log(f"最终最佳模型: {best_model['filename']}")
    logger.log(f"综合评分: {best_model['comprehensive_score']:.4f}")
    logger.log(f"MAPE: {best_model['mape']:.4f}%")
    logger.log(f"涨跌正确率: {best_model['direction_accuracy']:.2f}%")
    
    # 如果是最佳网格模型，显示参数
    if best_model['params'] and best_model['filename'] != current_model_result['filename']:
        logger.log("最佳模型参数:")
        for param_name, param_value in best_model['params'].items():
            logger.log(f"  {param_name}: {param_value}")
    
    # 记录结束信息
    logger.log("")
    logger.log("=" * 80)
    logger.log("模型评估与优化完成")
    logger.log("=" * 80)
    logger.log(f"完整日志请查看: {logger.log_file}")

if __name__ == "__main__":
    main()