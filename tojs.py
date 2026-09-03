import pandas as pd
import json
import requests
import os
from datetime import datetime, timedelta
import chinese_calendar as cc  # pip install chinese-calendar
#import holidays as hc


TARGET_URL = os.environ.get(
    "INFER_RESULT_URL",
    "https://crm.zhaomei.com/crm/called/v1/aiapi/infer-result",
)
SEND_INFER_RESULT = os.environ.get("SEND_INFER_RESULT", "1") != "0"
INFER_SEND_STRICT = os.environ.get("INFER_SEND_STRICT", "0") == "1"
INFER_RESULT_TIMEOUT = float(os.environ.get("INFER_RESULT_TIMEOUT", "30"))

COAL_PRICE_KEYS = [
    'CCI3800outinfer',
    'CCI4500infer',
    'CCI4700outinfer',
    'CCI5000infer',
    'CCI5500infer',
    'CCI5500outinfer'
]
FREIGHT_RATE_KEYS = ['insideinfer', 'outsideinfer']
TARGET_KEYS = COAL_PRICE_KEYS + FREIGHT_RATE_KEYS


def get_next_workdays(start_date, n_days):
    workdays = []
    current_date = start_date
    while len(workdays) < n_days:
        # 如果年份在支持范围内，用 chinese_calendar 判断
        if 2004 <= current_date.year <= 2026:
            is_work = cc.is_workday(current_date)
        else:
            # 否则简单判断：周一到周五为工作日
            is_work = current_date.weekday() < 5
        
        if is_work:
            workdays.append(current_date)
        current_date += timedelta(days=1)
    return workdays

def build_headers():
    headers = {"Content-Type": "application/json"}
    bearer_token = os.environ.get("INFER_RESULT_AUTH_TOKEN")
    api_key = os.environ.get("INFER_RESULT_API_KEY")

    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    if api_key:
        headers["X-API-Key"] = api_key

    return headers

def send_infer_result(data):
    if not SEND_INFER_RESULT:
        print("已跳过外部接口发送：SEND_INFER_RESULT=0")
        return

    print(f"开始发送预测结果到外部接口：{TARGET_URL}")
    try:
        resp = requests.post(
            TARGET_URL,
            json=data,
            headers=build_headers(),
            timeout=INFER_RESULT_TIMEOUT,
        )
        print("外部接口状态码:", resp.status_code)
        print("外部接口响应:", resp.text[:1000])
        resp.raise_for_status()
        print("预测结果发送成功")
    except requests.RequestException as exc:
        print(f"预测结果发送失败: {exc}")
        if INFER_SEND_STRICT:
            raise

def main():
    # === 参数部分 ===
    csv_dir = "./autoinfer"        # 你的 CSV 存放目录
    
    # === 获取今天日期 ===
    #infer_date = datetime.today().strftime("%Y-%m-%d")-timedelta(days=5)
    infer_date = (datetime.today()-timedelta(days=0)).strftime("%Y-%m-%d")
    today = datetime.today().date()-timedelta(days=0)
    print(today)
    if not cc.is_workday(today):
        print("today is not workday")
        os._exit(0)
    output_file = "autoinfer/json/" + infer_date + "_data.json"
     
    # === 获取未来 120 个工作日 ===
    future_dates = get_next_workdays(today, 120)

    # === 只读取对外需要的煤价/运费 CSV，跳过同步模型中间文件 ===
    csv_files = [os.path.join(csv_dir, f"{key}.csv") for key in TARGET_KEYS]
    missing_files = [csv_file for csv_file in csv_files if not os.path.exists(csv_file)]
    if missing_files:
        raise FileNotFoundError(f"缺少预测 CSV 文件: {missing_files}")

    result = {"inferDate": infer_date, "data": {}}

    for csv_file in csv_files:
        name = os.path.splitext(os.path.basename(csv_file))[0]
        df = pd.read_csv(csv_file, header=None)  # 一列，无表头

        if len(df) < 120:
            raise ValueError(f"{name} 文件不足 120 行（仅 {len(df)} 行）")

        preds = df.iloc[:120, 0].tolist()

        records = [
            {"date": future_dates[i], "predict": float(preds[i])}
            for i in range(120)
        ]

        result["data"][name] = records
        print(f"✅ 已读取 {name}, 共 {len(records)} 条记录")

    # === 导出 JSON ===
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4,default=str)
    
    print(f"\n🎯 已生成文件：{output_file}")
    print(f"推理日期 inferDate = {infer_date}")

    # 读取本地 JSON 文件
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    send_infer_result(data)
    return output_file

def separate_data(input_file):
    """分离煤价和运费数据"""  
    # 提取日期部分
    filename = os.path.basename(input_file)
    date_str = filename.split('_')[0]
    print(f"\n开始分离数据，日期：{date_str}")
    
    # 加载原始数据
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 分离煤价和运费数据
    coal_prices = {}
    freight_rates = {}
    
    # 处理煤价数据
    for key in COAL_PRICE_KEYS:
        if key in data['data']:
            # 提取预测价格列表
            prices = [item['predict'] for item in data['data'][key]]
            coal_prices[key] = prices
    
    # 处理运费数据
    for key in FREIGHT_RATE_KEYS:
        if key in data['data']:
            # 提取预测运费列表
            rates = [item['predict'] for item in data['data'][key]]
            freight_rates[key] = rates
    
    # 保存分离后的数据
    output_dir = 'Qwen/data'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    coal_output_file = os.path.join(output_dir, f'coal_prices.json')
    freight_output_file = os.path.join(output_dir, f'freight_rates.json')
    
    with open(coal_output_file, 'w', encoding='utf-8') as f:
        json.dump(coal_prices, f, ensure_ascii=False, indent=2)
    
    with open(freight_output_file, 'w', encoding='utf-8') as f:
        json.dump(freight_rates, f, ensure_ascii=False, indent=2)
    
    print("数据分离完成：")
    print(f"- 煤价数据已保存为 {coal_output_file}")
    print(f"- 运费数据已保存为 {freight_output_file}")
    print(f"煤价数据包含 {len(coal_prices)} 个煤种")
    print(f"运费数据包含 {len(freight_rates)} 个类别")


if __name__ == "__main__":
    output_file = main()
    # 运行完main后，自动分离数据
    if os.path.exists(output_file):
        separate_data(output_file)
    else:
        # 如果autoinfer/json目录不存在，检查当前目录
        current_dir_output = datetime.today().strftime("%Y-%m-%d") + "_data.json"
        if os.path.exists(current_dir_output):
            separate_data(current_dir_output)
        else:
            print("未找到生成的数据文件，跳过数据分离步骤")
