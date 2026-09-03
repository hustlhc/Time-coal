import json
import csv
from datetime import datetime

# 配置4个电厂的信息，包括orgzCode和文件名
power_plants = [
    {"name": "邵武", "orgzCode": "17E7", "file": "input/user_input_邵武.json"},
    {"name": "可门", "orgzCode": "383", "file": "input/user_input_可门.json"},
    {"name": "永安", "orgzCode": "384", "file": "input/user_input_永安.json"},
    {"name": "漳平", "orgzCode": "484", "file": "input/user_input_漳平.json"}
]

# 从huodian.csv获取最新库存数据
def get_latest_stock():
    stock_data = []
    with open("../dataset-huodian/data_json/huodian.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['measureCode'] == "DL03004":  # 存煤量
                stock_data.append(row)
    
    # 获取最新日期
    latest_date = max([row['query_date'] for row in stock_data])
    
    # 筛选最新日期的数据
    latest_stock_data = [row for row in stock_data if row['query_date'] == latest_date]
    
    # 转换为字典，键为orgzCode，值为measureValue
    stock_dict = {row['orgzCode']: row['measureValue'] for row in latest_stock_data}
    return stock_dict

# 从coal_new.csv获取最新煤价数据
def get_latest_coal_prices():
    with open("../dataset/pre_coal/coal_new.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    
    # 获取最后一行数据
    last_row = rows[-1]
    
    # 提取最后6列作为煤价数据
    prices = last_row[-6:]
    
    # 转换为浮点数
    prices = [float(price) for price in prices]
    
    # 构建煤价字典
    coal_prices = {
        "CCI4500": {"current_price": prices[0], "heat_value": 4500},
        "CCI5000": {"current_price": prices[1], "heat_value": 5000},
        "CCI5500": {"current_price": prices[2], "heat_value": 5500},
        "CCI进口3800": {"current_price": prices[3], "heat_value": 3800},
        "CCI进口4700": {"current_price": prices[4], "heat_value": 4700},
        "CCI进口5500": {"current_price": prices[5], "heat_value": 5500}
    }
    return coal_prices

# 获取最新数据
stock_dict = get_latest_stock()
coal_prices = get_latest_coal_prices()
today = datetime.now().strftime("%Y/%m/%d")

# 更新每个电厂的文件
for plant in power_plants:
    # 读取文件
    with open(plant['file'], "r", encoding="utf-8") as f:
        user_input = json.load(f)
    
    # 更新日期
    user_input['decision_date'] = today
    
    # 更新煤价
    user_input['coal_config'] = coal_prices
    
    # 更新库存
    if plant['orgzCode'] in stock_dict:
        user_input['prev_stock'] = float(stock_dict[plant['orgzCode']])
    
    # 写回文件
    with open(plant['file'], "w", encoding="utf-8") as f:
        json.dump(user_input, f, ensure_ascii=False, indent=2)
    
    print(f"已更新文件: {plant['file']}")

print("所有文件更新完成！")
