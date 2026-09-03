import re
import os
from collections import defaultdict

def parse_log_file(log_file_path):
    """
    解析单个日志文件，提取参数和最终得分
    """
    with open(log_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取模型参数
    params = {}
    
    # 提取基础配置
    basic_config_match = re.search(r'Basic Config(.*?)Data Loader', content, re.DOTALL)
    if basic_config_match:
        basic_config = basic_config_match.group(1)
        params.update(extract_key_value_pairs(basic_config))
    
    # 提取数据加载器配置
    data_loader_match = re.search(r'Data Loader(.*?)Forecasting Task', content, re.DOTALL)
    if data_loader_match:
        data_loader = data_loader_match.group(1)
        params.update(extract_key_value_pairs(data_loader))
    
    # 提取预测任务配置
    forecasting_match = re.search(r'Forecasting Task(.*?)Model Parameters', content, re.DOTALL)
    if forecasting_match:
        forecasting = forecasting_match.group(1)
        params.update(extract_key_value_pairs(forecasting))
    
    # 提取模型参数
    model_params_match = re.search(r'Model Parameters(.*?)Run Parameters', content, re.DOTALL)
    if model_params_match:
        model_params = model_params_match.group(1)
        params.update(extract_key_value_pairs(model_params))
    
    # 提取运行参数
    run_params_match = re.search(r'Run Parameters(.*?)GPU', content, re.DOTALL)
    if run_params_match:
        run_params = run_params_match.group(1)
        params.update(extract_key_value_pairs(run_params))
    
    # 提取最终得分
    score_match = re.search(r'小模型一.*?得分为：(\d+\.\d+)', content)
    score1 = float(score_match.group(1)) if score_match else 0
    
    score_match = re.search(r'小模型二.*?得分为：(\d+\.\d+)', content)
    score2 = float(score_match.group(1)) if score_match else 0
    
    total_score = score1 + score2
    
    return {
        'file_name': os.path.basename(log_file_path),
        'params': params,
        'score1': score1,
        'score2': score2,
        'total_score': total_score
    }

def extract_key_value_pairs(text):
    """
    从文本中提取键值对
    """
    pairs = {}
    # 匹配键值对模式
    pattern = r'(\w[\w\s]*):\s*([^\n]+)'
    matches = re.findall(pattern, text)
    
    for key, value in matches:
        # 清理键名（去除多余空格）
        key = re.sub(r'\s+', ' ', key.strip())
        # 清理值（去除尾部空格）
        value = value.strip()
        pairs[key] = value
    
    return pairs

def find_log_files(directory):
    """
    查找目录中的所有log文件
    """
    log_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.log') or file.endswith('.txt'):
                log_files.append(os.path.join(root, file))
    return log_files

def main(directory='.'):
    """
    主函数：解析所有日志文件并按得分排序展示
    """
    log_files = find_log_files(directory)
    results = []
    
    print(f"找到 {len(log_files)} 个日志文件")
    print("=" * 100)
    
    for log_file in log_files:
        try:
            result = parse_log_file(log_file)
            results.append(result)
            print(f"已解析: {result['file_name']} - 总分: {result['total_score']:.2f}")
        except Exception as e:
            print(f"解析文件 {log_file} 时出错: {e}")
    
    # 按总分降序排序
    results.sort(key=lambda x: x['total_score'], reverse=True)
    
    print("\n" + "=" * 100)
    print("结果排名（按总分降序）:")
    print("=" * 100)
    
    for i, result in enumerate(results, 1):
        if i < 30: 
            print(f"\n第{i}名: {result['file_name']}")
            print(f"总分: {result['total_score']:.2f} (模型一: {result['score1']:.2f}, 模型二: {result['score2']:.2f})")
            print("关键参数:")
            
            # 显示重要参数
            important_params = [
                'Model', 'Seq Len', 'Label Len', 'Pred Len', 
                'd model', 'n heads', 'e layers', 'd layers'
            ]
            
            for param in important_params:
                if param in result['params']:
                    print(f"  {param}: {result['params'][param]}")
            
            print("-" * 50)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()