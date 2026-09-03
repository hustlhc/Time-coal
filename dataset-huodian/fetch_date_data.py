import requests
import json
import os
from datetime import datetime, timedelta

def fetch_data_by_date(period_id):
    """根据日期获取数据"""
    url = 'http://10.104.243.34:8091/api/dic/crewtype2'
    headers = {
        'accept': 'application/json',
        'Authorization': 'Bearer f0b783535c19a9a9a1656a6f9f88de7b'
    }
    
    all_data = []
    page = 1
    page_size = 100
    
    while True:
        params = {
            'periodId': period_id,
            'apiPageNum': page,
            'apiPageSize': page_size
        }
        
        try:
            print(f"获取 {period_id} 第 {page} 页数据...")
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                data = result.get('data', [])
                print(f"获取到 {len(data)} 条数据")
                
                if not data:
                    break
                
                all_data.extend(data)
                
                if len(data) < page_size:
                    break
                
                page += 1
            else:
                print(f"API错误: {result.get('message')}")
                break
        
        except Exception as e:
            print(f"请求失败: {e}")
            break
    
    return {
        'code': 0,
        'message': 'success',
        'periodId': period_id,
        'data': all_data
    }

def fetch_last_n_days(n):
    """获取过去n天的数据"""
    all_data = []
    end_date = datetime.now()
    
    for i in range(n):
        current_date = end_date - timedelta(days=i)
        period_id = current_date.strftime('%Y%m%d')
        
        print(f"\n{'='*50}")
        print(f"正在获取 {period_id} 的数据...")
        print(f"{'='*50}")
        
        result = fetch_data_by_date(period_id)
        if result and result.get('data'):
            daily_data = result.get('data', [])
            print(f"{period_id}: 获取到 {len(daily_data)} 条数据")
            
            # 为每条数据添加日期字段
            for item in daily_data:
                item['query_date'] = period_id
            
            all_data.extend(daily_data)
        else:
            print(f"{period_id}: 未获取到数据")
    
    return {
        'code': 0,
        'message': 'success',
        'start_date': (end_date - timedelta(days=n-1)).strftime('%Y%m%d'),
        'end_date': end_date.strftime('%Y%m%d'),
        'days': n,
        'data': all_data
    }

def save_to_json(data, filename=None):
    """保存数据到JSON文件"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        #filename = f'last_{data.get("days")}_days_data_{timestamp}.json'
        filename="huodian.json"
    
    try:
        output_dir = 'data_json'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 数据已保存到: {filepath}")
        return filepath
    except Exception as e:
        print(f"❌ 保存文件失败: {e}")
        return None

def main():
    import sys
    
    # 获取参数n
    if len(sys.argv) > 1:
        try:
            n = int(sys.argv[1])
            if n <= 0:
                print("错误: n必须是正整数")
                return
        except ValueError:
            print("错误: n必须是整数")
            return
    else:
        n = 7  # 默认获取7天数据
    
    print(f"获取过去 {n} 天的数据...")
    result = fetch_last_n_days(n)
    
    if result and result.get('data'):
        print(f"\n{'='*50}")
        print(f"总计获取 {len(result['data'])} 条数据")
        print(f"日期范围: {result['start_date']} 到 {result['end_date']}")
        print(f"总天数: {result['days']} 天")
        print(f"{'='*50}")
        
        # 保存数据
        save_to_json(result)
    else:
        print("\n❌ 未获取到任何数据")

if __name__ == "__main__":
    main()
