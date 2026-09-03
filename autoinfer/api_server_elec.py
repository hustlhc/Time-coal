import http.server
import socketserver
import sqlite3
import json
import urllib.parse
import sys
import os

# 尝试导入 SSL 模块
try:
    import ssl
    has_ssl = True
except ImportError:
    has_ssl = False
    print("警告: SSL 模块不可用，将使用 HTTP 服务器")

PORT = 8083  # 使用不同的端口，避免与现有服务冲突

# 获取数据库路径（相对于脚本文件所在目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, 'elec_prediction.db')

class APIRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义API请求处理器"""
    
    def do_GET(self):
        """处理GET请求"""
        # 解析URL路径
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        # 处理CORS
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        # 处理不同的API路径
        if path == '/api/elec_prediction':
            self.handle_elec_prediction(query_params)
        elif path == '/api/elec_real_data':
            self.handle_elec_real_data(query_params)
        elif path == '/api/elec_data_types':
            self.handle_elec_data_types()
        elif path == '/':
            self.handle_index()
        else:
            self.handle_not_found()
    
    def handle_elec_prediction(self, params):
        """处理发电量预测数据请求"""
        try:
            # 获取参数
            type_param = params.get('type', [''])[0]
            days = int(params.get('days', ['60'])[0])
            infer_date = params.get('infer_date', [''])[0]  # 获取推理日期参数
            unit = params.get('unit', ['total'])[0]  # 获取显示模式参数，默认为total
            
            if not type_param:
                self.send_error_json(400, '缺少type参数')
                return
            
            if not infer_date:
                self.send_error_json(400, '缺少infer_date参数')
                return
            
            # 连接数据库（使用相对于脚本的路径）
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 映射数据类型
            type_map = {
                'kemen': 'kemen',
                'shaowu': 'shaowu',
                'yongan': 'yongan',
                'zhangping': 'zhangping'
            }
            mapped_type = type_map.get(type_param, type_param)
            
            # 根据unit参数决定查询总发电量还是分机组发电量
            if unit == 'units':
                # 为每个电厂定义对应的机组ID
                plant_units = {
                    'kemen': ['unit1', 'unit2', 'unit3', 'unit4','unit5','unit6'],
                    'shaowu': ['unit3', 'unit4'],
                    'yongan': ['unit7', 'unit8'],
                    'zhangping': ['unit5', 'unit6']
                }
                
                # 获取当前电厂的机组ID列表
                units = plant_units.get(mapped_type, [])
                
                # 构建查询语句
                if units:
                    # 有指定机组ID，使用IN子句
                    cursor.execute('''
                    SELECT pred_date, predict, unit_id FROM prediction_data
                    WHERE data_type = ? and infer_date = ? and is_total = 0 and unit_id IN ({})
                    ORDER BY pred_date ASC, unit_id
                    LIMIT ?
                    '''.format(','.join(['?'] * len(units))), (mapped_type, infer_date) + tuple(units) + (days * 10,))
                else:
                    # 无指定机组ID，返回空数据
                    result = []
            else:
                # 查询总发电量数据（默认）
                cursor.execute('''
                SELECT pred_date, predict FROM prediction_data
                WHERE data_type = ? and infer_date = ? and is_total = 1
                ORDER BY pred_date ASC
                LIMIT ?
                ''', (mapped_type, infer_date, days))
            
            rows = cursor.fetchall()
            conn.close()
            
            # 格式化数据
            result = []
            if unit == 'units' and units:
                # 按日期分组，将每个机组的数据作为一个字段
                date_map = {}
                for row in rows:
                    date = row['pred_date']
                    if date not in date_map:
                        date_map[date] = {'date': date}
                    date_map[date][row['unit_id']] = row['predict']
                
                # 转换为列表
                for date in sorted(date_map.keys()):
                    result.append(date_map[date])
            else:
                # 总发电量模式
                for row in rows:
                    result.append({
                        'date': row['pred_date'],
                        'predict': row['predict']
                    })
            
            # 返回JSON
            self.wfile.write(json.dumps(result).encode('utf-8'))
            
        except Exception as e:
            self.send_error_json(500, f'服务器内部错误: {str(e)}')
    
    def handle_elec_real_data(self, params):
        """处理发电量真实数据请求"""
        try:
            # 获取参数
            type_param = params.get('type', [''])[0]
            days = int(params.get('days', ['30'])[0])
            start_date = params.get('start_date', [''])[0]  # 获取开始日期参数
            unit = params.get('unit', ['total'])[0]  # 获取显示模式参数，默认为total
            
            if not type_param:
                self.send_error_json(400, '缺少type参数')
                return
            
            # 连接数据库（使用相对路径）
            conn = sqlite3.connect('elec_prediction.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 映射数据类型
            type_map = {
                'kemen_power': 'kemen_power',
                'shaowu_power': 'shaowu_power',
                'yongan_power': 'yongan_power',
                'zhangping_power': 'zhangping_power'
            }
            mapped_type = type_map.get(type_param, type_param)
            
            # 根据unit参数决定查询总发电量还是分机组发电量
            if unit == 'units':
                # 为每个电厂定义对应的机组ID
                plant_units = {
                    'kemen_power': ['unit1', 'unit2', 'unit3', 'unit4','unit5','unit6'],
                    'shaowu_power': ['unit3', 'unit4'],
                    'yongan_power': ['unit7', 'unit8'],
                    'zhangping_power': ['unit5', 'unit6']
                }
                
                # 获取当前电厂的机组ID列表
                units = plant_units.get(mapped_type, [])
                
                # 构建查询语句
                if units:
                    # 查询分机组数据
                    if start_date:
                        cursor.execute('''
                        SELECT date, value, unit_id FROM real_data
                        WHERE data_type = ? and date >= ? and is_total = 0 and unit_id IN ({})
                        ORDER BY date ASC, unit_id
                        LIMIT ?
                        '''.format(','.join(['?'] * len(units))), (mapped_type, start_date) + tuple(units) + (days * 10,))
                    else:
                        cursor.execute('''
                        SELECT date, value, unit_id FROM real_data
                        WHERE data_type = ? and is_total = 0 and unit_id IN ({})
                        ORDER BY date DESC, unit_id
                        LIMIT ?
                        '''.format(','.join(['?'] * len(units))), (mapped_type,) + tuple(units) + (days * 10,))
                    
                    rows = cursor.fetchall()
                    conn.close()
                    
                    # 按日期分组，将每个机组的数据作为一个字段
                    date_map = {}
                    for row in rows:
                        date = row['date']
                        if date not in date_map:
                            date_map[date] = {'date': date}
                        date_map[date][row['unit_id']] = row['value']
                    
                    # 转换为列表并按日期排序
                    result = []
                    for date in sorted(date_map.keys()):
                        result.append(date_map[date])
                    
                    # 限制返回天数
                    if len(result) > days:
                        result = result[:days]
                else:
                    result = []
            else:
                # 查询总发电量数据（默认，is_total=1）
                if start_date:
                    cursor.execute('''
                    SELECT date, value FROM real_data
                    WHERE data_type = ? and date >= ? and is_total = 1
                    ORDER BY date ASC
                    LIMIT ?
                    ''', (mapped_type, start_date, days))
                else:
                    cursor.execute('''
                    SELECT date, value FROM real_data
                    WHERE data_type = ? and is_total = 1
                    ORDER BY date DESC
                    LIMIT ?
                    ''', (mapped_type, days))

                rows = cursor.fetchall()
                conn.close()
                
                # 格式化数据（按日期正序）
                result = []
                for row in rows:
                    result.append({
                        'date': row['date'],
                        'value': row['value']
                    })
            
            # 返回JSON
            self.wfile.write(json.dumps(result).encode('utf-8'))
            
        except Exception as e:
            self.send_error_json(500, f'服务器内部错误: {str(e)}')
    
    def handle_elec_data_types(self):
        """处理发电量数据类型请求"""
        try:
            # 连接数据库（使用相对路径）
            conn = sqlite3.connect('elec_prediction.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 查询预测数据类型
            cursor.execute('SELECT DISTINCT data_type FROM prediction_data ORDER BY data_type')
            pred_types = [row['data_type'] for row in cursor.fetchall()]
            
            # 查询真实数据类型
            cursor.execute('SELECT DISTINCT data_type FROM real_data ORDER BY data_type')
            real_types = [row['data_type'] for row in cursor.fetchall()]
            
            conn.close()
            
            # 返回JSON
            result = {
                'prediction_types': pred_types,
                'real_types': real_types
            }
            self.wfile.write(json.dumps(result).encode('utf-8'))
            
        except Exception as e:
            self.send_error_json(500, f'服务器内部错误: {str(e)}')
    
    def handle_index(self):
        """处理根路径请求"""
        html_content = '''
        <h1>发电量预测数据API</h1>
        <p>API接口说明：</p>
        <ul>
            <li><strong>GET /api/elec_prediction</strong> - 获取发电量预测数据</li>
            <li>参数：</li>
            <ul>
                <li><code>type</code> - 数据类型（如zhangping）</li>
                <li><code>days</code> - 天数（默认60天）</li>
                <li><code>infer_date</code> - 推理日期（格式：YYYY-MM-DD）</li>
                <li><code>unit</code> - 显示模式：total（总发电量，默认）或 units（分机组）</li>
            </ul>
            <li><strong>GET /api/elec_real_data</strong> - 获取发电量真实数据</li>
            <li>参数：</li>
            <ul>
                <li><code>type</code> - 数据类型（如zhangping_power）</li>
                <li><code>days</code> - 天数（默认30天）</li>
                <li><code>start_date</code> - 开始日期（格式：YYYY-MM-DD）</li>
            </ul>
            <li><strong>GET /api/elec_data_types</strong> - 获取所有数据类型</li>
        </ul>
        '''
        self.wfile.write(html_content.encode('utf-8'))
    
    def handle_not_found(self):
        """处理404请求"""
        self.send_error_json(404, '接口不存在')
    
    def send_error_json(self, code, message):
        """发送错误JSON响应"""
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        error_response = {'error': message}
        self.wfile.write(json.dumps(error_response).encode('utf-8'))

def run_server():
    """启动服务器"""
    with socketserver.TCPServer(("", PORT), APIRequestHandler) as httpd:
        print(f"启动发电量预测数据API服务...")
        print(f"服务地址: http://localhost:{PORT}")
        print(f"API接口:")
        print(f"- GET /api/elec_prediction?type=数据类型&days=天数&infer_date=推理日期&unit=显示模式")
        print(f"- GET /api/elec_real_data?type=数据类型&days=天数&start_date=开始日期")
        print(f"- GET /api/elec_data_types")
        print(f"- GET / (API说明)")
        print(f"\n按 Ctrl+C 停止服务")
        httpd.serve_forever()

if __name__ == '__main__':
    run_server()
