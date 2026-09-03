import json
import requests

# 目标回传地址
TARGET_URL = "http://183.192.158.102:50202/crm/called/v1/aiapi/infer-result"   # ← 改成你的地址
JSON_FILE = "data20251021.json"                           # ← 你的 JSON 文件路径

# 读取本地 JSON 文件
with open(JSON_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# 直接发送 POST 请求
resp = requests.post(TARGET_URL, json=data)

print("状态码:", resp.status_code)
print("响应内容:", resp.text)
