#!/usr/bin/env python3
"""
决策历史数据API服务器
提供决策历史数据的查询接口
"""

import sqlite3
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 数据库文件路径
DB_FILE = 'decision_history.db'

class DecisionHistoryAPI(BaseHTTPRequestHandler):
    def do_GET(self):
        """处理GET请求"""
        # 解析路径和查询参数
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)
        
        if path == '/api/decision_history':
            # 获取电厂参数
            plant = query_params.get('plant', [None])[0]
            self.handle_decision_history(plant)
        elif path.startswith('/api/decision_history/'):
            # 处理单个决策详情
            parts = path.split('/')
            if len(parts) == 4 and parts[3].isdigit():
                decision_id = int(parts[3])
                self.handle_decision_detail(decision_id)
            else:
                self.send_error(404, "Not Found")
        else:
            self.send_error(404, "Not Found")
    
    def send_json_response(self, data):
        """发送JSON响应"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def handle_decision_history(self, plant=None):
        """处理决策历史列表请求"""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 构建查询
        if plant:
            # 将plant参数映射到电厂名称
            plant_name_map = {
                'kemen': '可门电厂',
                'shaowu': '邵武电厂',
                'yongan': '永安电厂',
                'zhangping': '漳平电厂'
            }
            plant_name = plant_name_map.get(plant, plant)
            cursor.execute('SELECT * FROM decisions WHERE plant_name = ? ORDER BY decision_date DESC', (plant_name,))
        else:
            cursor.execute('SELECT * FROM decisions ORDER BY decision_date DESC')
        
        decisions = cursor.fetchall()
        
        # 转换为JSON格式
        result = []
        for decision in decisions:
            result.append({
                'id': decision['id'],
                'decision_date': decision['decision_date'],
                'plant_name': decision['plant_name'],
                'is_emergency': bool(decision['is_emergency']),
                'duration_days': decision['duration_days'],
                'total_purchase_quantity': decision['total_purchase_quantity'],
                'created_at': decision['created_at']
            })
        
        conn.close()
        self.send_json_response(result)
    
    def handle_decision_detail(self, decision_id):
        """处理单个决策详情请求"""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 查询决策基本信息
        cursor.execute('SELECT * FROM decisions WHERE id = ?', (decision_id,))
        decision = cursor.fetchone()
        
        if not decision:
            conn.close()
            self.send_error(404, "Decision not found")
            return
        
        # 查询采购计划
        cursor.execute('SELECT * FROM procurement_plans WHERE decision_id = ? ORDER BY plan_date', (decision_id,))
        plans = cursor.fetchall()
        
        # 构建响应数据
        result = {
            'id': decision['id'],
            'decision_date': decision['decision_date'],
            'plant_name': decision['plant_name'],
            'is_emergency': bool(decision['is_emergency']),
            'duration_days': decision['duration_days'],
            'total_purchase_quantity': decision['total_purchase_quantity'],
            'decision_analysis': decision['decision_analysis'],
            'created_at': decision['created_at'],
            'procurement_plan': []
        }
        
        # 添加采购计划详情
        for plan in plans:
            # 查询采购项目
            cursor.execute('SELECT * FROM procurement_items WHERE plan_id = ?', (plan['id'],))
            items = cursor.fetchall()
            
            plan_data = {
                'date': plan['plan_date'],
                'total_quantity': plan['total_quantity'],
                'items': []
            }
            
            # 添加采购项目详情
            for item in items:
                plan_data['items'].append({
                    'coal_name': item['coal_name'],
                    'quantity': item['quantity'],
                    'price': item['price'],
                    'coal_price': item['coal_price'],
                    'freight': item['freight'],
                    'delivered_unit_cost': item['delivered_unit_cost'],
                    'latest_delivery_date': item['latest_delivery_date']
                })
            
            result['procurement_plan'].append(plan_data)
        
        conn.close()
        self.send_json_response(result)
    
    def log_message(self, format, *args):
        """自定义日志输出"""
        print(f"[DecisionHistoryAPI] {args[0]}")

def run_server(port=8084):
    """运行API服务器"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, DecisionHistoryAPI)
    print(f"=" * 60)
    print(f"决策历史数据API服务器")
    print(f"=" * 60)
    print(f"服务器运行在: http://localhost:{port}")
    print(f"可用接口:")
    print(f"  GET /api/decision_history?plant={{plant_name}} - 获取决策历史列表")
    print(f"  GET /api/decision_history/{{id}} - 获取单个决策详情")
    print(f"=" * 60)
    print(f"按 Ctrl+C 停止服务器")
    print(f"=" * 60)
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()