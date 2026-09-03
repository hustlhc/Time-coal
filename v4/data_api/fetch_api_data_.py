import time
import base64
import hashlib
import hmac
from urllib.parse import urlencode, quote
import requests


def fetch_data(params):
    api_key = "ak_f6ec693a047f48ea8de4"
    secret_key = "sk_32f3612f28c54c2e9f1663ea5afc1629191496ed16b44212b132"

    # params = {
    #     "source": "500plus",
    #     "tableName": "输入00000356-CCTD-港口煤炭数据_港口库存及调度_港口库存及调度(日)_环渤海四港货船比",
    #     "columns": "时间,数值",
    #     "dateColumn": "时间",
    #     "startDate": "2015-01-09",
    #     "endDate": "2025-09-11",
    #     # "limit": "20",
    #     # "cursor": "1"
    # }

    timestamp = int(time.time() * 1000)
    signature = generate_signature(timestamp, secret_key)

    url = "https://aiapi.zhaomei.cn/api/v1/query-data"
    param_url = build_url_with_params(url, params)

    headers = {
        "X-API-Key": api_key,
        "X-Timestamp": str(timestamp),
        "X-Signature": signature,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    response = requests.get(param_url, headers=headers)
    response.raise_for_status()  # 出错直接抛异常
    return response.json()
    # print(f"{response.status_code}  {response.text}")


def build_url_with_params(url, params):
    if not params:
        return url
    encoded_params = urlencode(params, quote_via=quote)
    return f"{url}?{encoded_params}"


def generate_signature(timestamp, secret_key):
    try:
        # 构建签名字符串：时间戳
        data_to_sign = str(timestamp)

        # 使用HMAC-SHA256生成签名
        signature = hmac.new(
            secret_key.encode('utf-8'),
            data_to_sign.encode('utf-8'),
            hashlib.sha256
        ).digest()

        return base64.b64encode(signature).decode('utf-8')

    except Exception as e:
        raise RuntimeError("生成签名失败") from e


def main():
    """测试用"""
    params = {
        "source": "60plus",
        "tableName": "输入00000019-CCI指数_处理后",
        "columns": "发布日期,CCI5500,CCI5000,CCI4500,CCI进口3800,CCI进口4700,CCI进口5500,内蒙古鄂尔多斯5500,山西大同5500,陕西榆林5800",
        "dateColumn": "发布日期",
        "startDate": "2025-09-27",
        "endDate": "2025-09-27",
    }
    data = fetch_data(params)
    print(data)


if __name__ == "__main__":
    main()
