import pandas as pd
import json
import requests
import os
import glob
from datetime import datetime, timedelta
#import holidays as hc

import pkg_resources



def get_next_days(start_date, n_days):
    return [start_date + timedelta(days=i) for i in range(n_days)]

def main():
    # === 参数部分 ===
    csv_dir = "./autoinfer/elecdata"        # 你的 CSV 存放目录
    
    # === 获取今天日期 ===
    infer_date = (datetime.today()-timedelta(days=11)).strftime("%Y-%m-%d")  # 推理日期为昨天
    today = datetime.today().date()-timedelta(days=11)  # 获取昨天的日期对象
    print(today)
    
    output_file = "autoinfer/elecjson/" + infer_date + "_data.json"
     
    # === 获取未来 90 天（包含周末） ===
    future_dates = get_next_days(today, 90)

    # === 读取所有 CSV ===
    csv_files = sorted(glob.glob(os.path.join(csv_dir, "*.csv")))
    if not csv_files:
        raise FileNotFoundError(f"目录 {csv_dir} 中未找到 CSV 文件")

    result = {"inferDate": infer_date, "data": {}}

    for csv_file in csv_files:
        name = os.path.splitext(os.path.basename(csv_file))[0]
        df = pd.read_csv(csv_file, header=None)  # 一列，无表头

        if len(df) < 90:
            raise ValueError(f"{name} 文件不足 90 行（仅 {len(df)} 行）")

        preds = df.iloc[:90, 0].tolist()

        records = [
            {"date": future_dates[i], "predict": float(preds[i])}
            for i in range(90)
        ]

        result["data"][name] = records
        print(f"✅ 已读取 {name}, 共 {len(records)} 条记录")

    # === 导出 JSON ===
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4,default=str)
    
    print(f"\n🎯 已生成文件：{output_file}")
    print(f"推理日期 inferDate = {infer_date}")
    # 目标回传地址
    TARGET_URL = "https://crm.zhaomei.com/crm/called/v1/aiapi/infer-result"   # ← 改成你的地址
    # 读取本地 JSON 文件
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 只在工作日发送 POST 请求
    '''
    if  cc.is_workway(today):
        resp = requests.post(TARGET_URL, json=data)

        print("状态码:", resp.status_code)
        print("响应内容:", resp.text)
    '''
    '''
    if  today.weekday() < 5:
        resp = requests.post(TARGET_URL, json=data)

        print("状态码:", resp.status_code)
        print("响应内容:", resp.text)
    '''

if __name__ == "__main__":
    main()
