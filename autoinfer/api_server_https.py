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

PORT = 8444

# 获取数据库路径（相对于脚本文件所在目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ELEC_DB_PATH = os.path.join(SCRIPT_DIR, 'elec_prediction.db')
ELEC_OVERRIDE_DB_PATH = os.path.join(SCRIPT_DIR, 'elec_prediction_override.db')
COAL_DB_PATH = os.path.join(SCRIPT_DIR, 'coal_prediction.db')
DECISION_DB_PATH = os.path.join(SCRIPT_DIR, 'decision_history.db')

def _ensure_elec_override_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute('PRAGMA database_list')
    attached = {row[1] for row in cursor.fetchall()}
    if 'elec_override' not in attached:
        cursor.execute('ATTACH DATABASE ? AS elec_override', (ELEC_OVERRIDE_DB_PATH,))
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS elec_override.prediction_override_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        data_type TEXT,
        infer_date DATE,
        pred_date DATE,
        unit_id TEXT,
        is_total BOOLEAN,
        override_predict REAL
    )
    ''')
    cursor.execute('''
    CREATE UNIQUE INDEX IF NOT EXISTS elec_override.idx_prediction_override_unique
    ON prediction_override_data(data_type, infer_date, pred_date, unit_id, is_total)
    ''')
    cursor.execute('''
    CREATE UNIQUE INDEX IF NOT EXISTS elec_override.idx_prediction_override_global
    ON prediction_override_data(data_type, pred_date, unit_id, is_total)
    WHERE infer_date IS NULL
    ''')
    cursor.execute('''
    CREATE UNIQUE INDEX IF NOT EXISTS elec_override.idx_prediction_override_infer
    ON prediction_override_data(data_type, infer_date, pred_date, unit_id, is_total)
    WHERE infer_date IS NOT NULL
    ''')

class APIRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义API请求处理器"""
    
    def do_GET(self):
        """处理GET请求"""
        # 解析URL路径
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        # 处理静态文件请求
        if path.startswith('/week_report/'):
            # 处理周报文件请求
            self.handle_static_file(path)
            return
        
        # 处理CORS
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        # 处理不同的API路径
        if path == '/api/prediction':
            self.handle_prediction(query_params)
        elif path == '/api/real_data':
            self.handle_real_data(query_params)
        elif path == '/api/data_types':
            self.handle_data_types()
        elif path == '/api/compare':
            self.handle_compare(query_params)
        elif path == '/api/elec_prediction':
            self.handle_elec_prediction(query_params)
        elif path == '/api/elec_real_data':
            self.handle_elec_real_data(query_params)
        elif path == '/api/elec_data_types':
            self.handle_elec_data_types()
        elif path == '/api/decision_history':
            self.handle_decision_history(query_params)
        elif path.startswith('/api/decision_history/'):
            # 处理单个决策详情
            parts = path.split('/')
            if len(parts) == 4 and parts[3].isdigit():
                decision_id = int(parts[3])
                self.handle_decision_detail(decision_id)
            else:
                self.handle_not_found()
        elif path == '/':
            self.handle_index()
        else:
            self.handle_not_found()
    
    def handle_prediction(self, params):
        """处理预测数据请求"""
        try:
            # 获取参数
            type_param = params.get('type', [''])[0]
            days = int(params.get('days', ['5'])[0])
            base_date = params.get('date', [''])[0]  # 新增：获取日期参数
            
            if not type_param:
                self.send_error_json(400, '缺少type参数')
                return
            
            # 连接数据库
            conn = sqlite3.connect(COAL_DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 查询数据
            cursor.execute('''
            SELECT pred_date, predict FROM prediction_data
            WHERE data_type = ? and infer_date= ? and pred_date>=?
            ORDER BY pred_date ASC
            LIMIT ?
            ''', (type_param, base_date, base_date,days))
            
            rows = cursor.fetchall()
            conn.close()
            
            # 格式化数据
            result = []
            for row in rows:
                result.append({
                    'date': row['pred_date'],
                    'predict': row['predict']
                })
            
            # 返回JSON
            self.wfile.write(json.dumps(result).encode('utf-8'))
            
        except Exception as e:
            self.send_error_json(500, f'服务器内部错误: {str(e)}')
    
    def handle_real_data(self, params):
        """处理真实数据请求"""
        try:
            # 获取参数
            type_param = params.get('type', [''])[0]
            days = int(params.get('days', ['30'])[0])
            base_date = params.get('date', [''])[0]  # 新增：获取日期参数
            
            if not type_param:
                self.send_error_json(400, '缺少type参数')
                return
            
            # 连接数据库
            conn = sqlite3.connect(COAL_DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 查询数据 - 返回指定日期之前的真实数据
            cursor.execute('''
            SELECT date, value FROM real_data
            WHERE data_type = ? and date >= ?
            ORDER BY date asc
            LIMIT ?
            ''', (type_param, base_date, days))

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
    
    def handle_data_types(self):
        """处理数据类型请求"""
        try:
            # 连接数据库
            conn = sqlite3.connect(COAL_DB_PATH)
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
    
    def handle_compare(self, params):
        """处理数据对比请求"""
        try:
            # 获取参数
            pred_type = params.get('pred_type', [''])[0]
            real_type = params.get('real_type', [''])[0]
            days = int(params.get('days', ['5'])[0])
            
            if not pred_type or not real_type:
                self.send_error_json(400, '缺少pred_type或real_type参数')
                return
            
            # 连接数据库
            conn = sqlite3.connect(COAL_DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 查询预测数据
            cursor.execute('''
            SELECT pred_date, predict FROM prediction_data
            WHERE data_type = ?
            ORDER BY pred_date ASC
            LIMIT ?
            ''', (pred_type, days))
            pred_rows = cursor.fetchall()
            
            # 查询真实数据
            cursor.execute('''
            SELECT date, value FROM real_data
            WHERE data_type = ?
            ORDER BY date ASC
            LIMIT ?
            ''', (real_type, days))
            real_rows = cursor.fetchall()
            
            conn.close()
            
            # 格式化数据
            prediction_data = []
            for row in pred_rows:
                prediction_data.append({
                    'date': row['pred_date'],
                    'value': row['predict']
                })
            
            real_data_list = []
            for row in reversed(real_rows):
                real_data_list.append({
                    'date': row['date'],
                    'value': row['value']
                })
            
            # 返回JSON
            result = {
                'prediction': prediction_data,
                'real': real_data_list
            }
            self.wfile.write(json.dumps(result).encode('utf-8'))
            
        except Exception as e:
            self.send_error_json(500, f'服务器内部错误: {str(e)}')
    
    def handle_index(self):
        """处理根路径请求"""
        html_content = '''
        <h1>综合预测数据API</h1>
        <p>API接口说明：</p>
        
        <h2>煤价预测API</h2>
        <ul>
            <li><strong>GET /api/prediction</strong> - 获取煤价预测数据</li>
            <li>参数：</li>
            <ul>
                <li><code>type</code> - 数据类型（如CCI4500infer、insideinfer等）</li>
                <li><code>days</code> - 天数（默认5天）</li>
                <li><code>date</code> - 基准日期</li>
            </ul>
            <li>示例：<code>/api/prediction?type=CCI4500infer&days=10&date=2026-03-01</code></li>
            
            <li><strong>GET /api/real_data</strong> - 获取煤价真实数据</li>
            <li>参数：</li>
            <ul>
                <li><code>type</code> - 数据类型（如CCI4500、inside_freight等）</li>
                <li><code>days</code> - 天数（默认30天）</li>
                <li><code>date</code> - 开始日期</li>
            </ul>
            <li>示例：<code>/api/real_data?type=CCI4500&days=30&date=2026-03-01</code></li>
            
            <li><strong>GET /api/data_types</strong> - 获取所有煤价数据类型</li>
            
            <li><strong>GET /api/compare</strong> - 获取煤价预测数据和真实数据对比</li>
            <li>参数：</li>
            <ul>
                <li><code>pred_type</code> - 预测数据类型</li>
                <li><code>real_type</code> - 真实数据类型</li>
                <li><code>days</code> - 天数（默认5天）</li>
            </ul>
            <li>示例：<code>/api/compare?pred_type=CCI4500infer&real_type=CCI4500&days=10</code></li>
        </ul>
        
        <h2>发电量预测API</h2>
        <ul>
            <li><strong>GET /api/elec_prediction</strong> - 获取发电量预测数据</li>
            <li>参数：</li>
            <ul>
                <li><code>type</code> - 数据类型（如kemen、shaowu等）</li>
                <li><code>days</code> - 天数（默认60天）</li>
                <li><code>infer_date</code> - 推理日期（格式：YYYY-MM-DD）</li>
                <li><code>unit</code> - 显示模式：total（总发电量，默认）或 units（分机组）</li>
            </ul>
            <li>示例：<code>/api/elec_prediction?type=kemen&days=60&infer_date=2026-03-01&unit=units</code></li>
            
            <li><strong>GET /api/elec_real_data</strong> - 获取发电量真实数据</li>
            <li>参数：</li>
            <ul>
                <li><code>type</code> - 数据类型（如kemen_power、shaowu_power等）</li>
                <li><code>days</code> - 天数（默认30天）</li>
                <li><code>start_date</code> - 开始日期（格式：YYYY-MM-DD）</li>
                <li><code>unit</code> - 显示模式：total（总发电量，默认）或 units（分机组）</li>
            </ul>
            <li>示例：<code>/api/elec_real_data?type=kemen_power&days=30&start_date=2026-03-01&unit=units</code></li>
            
            <li><strong>GET /api/elec_data_types</strong> - 获取所有发电量数据类型</li>
        </ul>
        
        <h2>决策历史API</h2>
        <ul>
            <li><strong>GET /api/decision_history</strong> - 获取决策历史列表</li>
            <li>参数：</li>
            <ul>
                <li><code>plant</code> - 电厂名称（可选，如kemen、shaowu等）</li>
            </ul>
            <li>示例：<code>/api/decision_history?plant=kemen</code></li>
            
            <li><strong>GET /api/decision_history/{id}</strong> - 获取单个决策详情</li>
            <li>示例：<code>/api/decision_history/1</code></li>
        </ul>
        '''
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    
    def handle_not_found(self):
        """处理404请求"""
        self.send_error_json(404, '路径不存在')
    
    def send_error_json(self, status_code, message):
        """发送错误响应"""
        error_response = {
            'error': message
        }
        self.wfile.write(json.dumps(error_response).encode('utf-8'))
    
    def handle_static_file(self, path):
        """处理静态文件请求"""
        try:
            # 移除路径前缀，获取相对路径
            relative_path = path[len('/week_report/'):]
            
            # 构建完整的文件路径 - 使用相对路径
            file_path = os.path.join(SCRIPT_DIR, 'html1', 'week_report', relative_path)
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                self.send_error(404, 'File not found')
                return
            
            # 检查是否是文件
            if not os.path.isfile(file_path):
                # 如果是目录，返回目录列表
                self.send_directory_listing(os.path.join(SCRIPT_DIR, 'html1', 'week_report'), relative_path)
                return
            
            # 确定文件的 MIME 类型
            content_type = self.guess_type(file_path)
            
            # 获取文件名
            filename = os.path.basename(file_path)
            
            # 获取文件大小
            file_size = os.path.getsize(file_path)
            
            # 发送文件
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(file_size))
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, Content-Disposition')
            self.end_headers()
            
            # 分块读取文件，避免内存问题
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)  # 8KB chunks
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                
        except Exception as e:
            self.send_error(500, f'Internal server error: {str(e)}')
    
    def send_directory_listing(self, base_dir, relative_path):
        """发送目录列表"""
        try:
            # 构建当前目录路径
            current_dir = os.path.join(base_dir, relative_path)
            
            # 获取目录中的文件和子目录
            entries = os.listdir(current_dir)
            
            # 生成 HTML 目录列表
            html_content = f'''<!DOCTYPE html>
<html>
<head>
    <title>Directory listing for /week_report/{relative_path}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        ul {{ list-style-type: none; padding: 0; }}
        li {{ margin: 10px 0; }}
        a {{ text-decoration: none; color: #1a56db; }}
        a:hover {{ text-decoration: underline; }}
        .back {{ margin-bottom: 20px; }}
    </style>
</head>
<body>
    <h1>Directory listing for /week_report/{relative_path}</h1>
'''
            
            # 添加返回上一级目录的链接
            if relative_path:
                parent_path = os.path.dirname(relative_path)
                if parent_path == '.':
                    parent_path = ''
                html_content += f'    <div class="back"><a href="/week_report/{parent_path}">..</a></div>\n'
            
            # 添加文件和子目录列表
            html_content += '    <ul>\n'
            for entry in entries:
                entry_path = os.path.join(relative_path, entry)
                entry_full_path = os.path.join(current_dir, entry)
                if os.path.isdir(entry_full_path):
                    html_content += f'        <li><a href="/week_report/{entry_path}/">{entry}/</a></li>\n'
                else:
                    html_content += f'        <li><a href="/week_report/{entry_path}">{entry}</a></li>\n'
            html_content += '    </ul>\n</body>\n</html>'
            
            # 发送响应
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))
            
        except Exception as e:
            self.send_error(500, f'Internal server error: {str(e)}')
    
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
            
            # 连接数据库
            conn = sqlite3.connect(ELEC_DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            _ensure_elec_override_schema(conn)
            
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
                    SELECT
                        p.pred_date,
                        COALESCE(o1.override_predict, o0.override_predict, p.predict) AS predict,
                        p.unit_id
                    FROM prediction_data p
                    LEFT JOIN elec_override.prediction_override_data o1
                        ON o1.data_type = p.data_type
                        AND o1.infer_date = p.infer_date
                        AND o1.pred_date = p.pred_date
                        AND o1.is_total = p.is_total
                        AND o1.unit_id IS p.unit_id
                    LEFT JOIN elec_override.prediction_override_data o0
                        ON o0.data_type = p.data_type
                        AND o0.infer_date IS NULL
                        AND o0.pred_date = p.pred_date
                        AND o0.is_total = p.is_total
                        AND o0.unit_id IS p.unit_id
                    WHERE p.data_type = ? and p.infer_date = ? and p.is_total = 0 and p.unit_id IN ({})
                    ORDER BY p.pred_date ASC, p.unit_id
                    LIMIT ?
                    '''.format(','.join(['?'] * len(units))), (mapped_type, infer_date) + tuple(units) + (days * 10,))
                    rows = cursor.fetchall()
                else:
                    # 无指定机组ID，返回空数据
                    rows = []
            else:
                cursor.execute('''
                SELECT
                    p.pred_date,
                    SUM(COALESCE(o1.override_predict, o0.override_predict, p.predict)) AS predict
                FROM prediction_data p
                LEFT JOIN elec_override.prediction_override_data o1
                    ON o1.data_type = p.data_type
                    AND o1.infer_date = p.infer_date
                    AND o1.pred_date = p.pred_date
                    AND o1.is_total = p.is_total
                    AND o1.unit_id IS p.unit_id
                LEFT JOIN elec_override.prediction_override_data o0
                    ON o0.data_type = p.data_type
                    AND o0.infer_date IS NULL
                    AND o0.pred_date = p.pred_date
                    AND o0.is_total = p.is_total
                    AND o0.unit_id IS p.unit_id
                WHERE p.data_type = ? and p.infer_date = ? and p.is_total = 0
                GROUP BY p.pred_date
                ORDER BY p.pred_date ASC
                LIMIT ?
                ''', (mapped_type, infer_date, days))
                rows = cursor.fetchall()

                if not rows:
                    cursor.execute('''
                    SELECT
                        p.pred_date,
                        COALESCE(o1.override_predict, o0.override_predict, p.predict) AS predict
                    FROM prediction_data p
                    LEFT JOIN elec_override.prediction_override_data o1
                        ON o1.data_type = p.data_type
                        AND o1.infer_date = p.infer_date
                        AND o1.pred_date = p.pred_date
                        AND o1.is_total = p.is_total
                        AND o1.unit_id IS p.unit_id
                    LEFT JOIN elec_override.prediction_override_data o0
                        ON o0.data_type = p.data_type
                        AND o0.infer_date IS NULL
                        AND o0.pred_date = p.pred_date
                        AND o0.is_total = p.is_total
                        AND o0.unit_id IS p.unit_id
                    WHERE p.data_type = ? and p.infer_date = ? and p.is_total = 1
                    ORDER BY p.pred_date ASC
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
            
            # 连接数据库
            conn = sqlite3.connect(ELEC_DB_PATH)
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
            # 连接数据库
            conn = sqlite3.connect(ELEC_DB_PATH)
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
    
    def handle_decision_history(self, params):
        """处理决策历史列表请求"""
        try:
            # 获取电厂参数
            plant = params.get('plant', [None])[0]
            
            conn = sqlite3.connect(DECISION_DB_PATH)
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
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            self.send_error_json(500, f'服务器内部错误: {str(e)}')
    
    def handle_decision_detail(self, decision_id):
        """处理单个决策详情请求"""
        try:
            conn = sqlite3.connect(DECISION_DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 查询决策基本信息
            cursor.execute('SELECT * FROM decisions WHERE id = ?', (decision_id,))
            decision = cursor.fetchone()
            
            if not decision:
                conn.close()
                self.send_error_json(404, '决策不存在')
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
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            self.send_error_json(500, f'服务器内部错误: {str(e)}')

def start_server():
    """启动API服务"""
    try:
        # 创建服务器
        httpd = socketserver.TCPServer(("", PORT), APIRequestHandler)
        
        # 尝试包装为HTTPS服务器
        if has_ssl:
            try:
                httpd.socket = ssl.wrap_socket(
                    httpd.socket,
                    keyfile="/home/lhc/Time-coal/services/ssl/server.key",
                    certfile="/home/lhc/Time-coal/services/ssl/server.crt",
                    server_side=True
                )
                protocol = "https"
            except Exception as e:
                print(f"警告: SSL 配置失败，将使用 HTTP 服务器: {str(e)}")
                protocol = "http"
        else:
            protocol = "http"
        
        print(f"启动综合预测数据API服务...")
        print(f"服务地址: {protocol}://localhost:{PORT}")
        print(f"API接口:")
        print(f"\n[煤价预测API]")
        print(f"- GET /api/prediction?type=数据类型&days=天数&date=基准日期")
        print(f"- GET /api/real_data?type=数据类型&days=天数&date=开始日期")
        print(f"- GET /api/data_types")
        print(f"- GET /api/compare?pred_type=预测类型&real_type=真实类型&days=天数")
        print(f"\n[发电量预测API]")
        print(f"- GET /api/elec_prediction?type=数据类型&days=天数&infer_date=推理日期&unit=显示模式")
        print(f"- GET /api/elec_real_data?type=数据类型&days=天数&start_date=开始日期&unit=显示模式")
        print(f"- GET /api/elec_data_types")
        print(f"\n[决策历史API]")
        print(f"- GET /api/decision_history?plant=电厂名称")
        print(f"- GET /api/decision_history/{id}")
        print(f"\n- GET / (API说明)")
        print(f"\n按 Ctrl+C 停止服务")
        # 启动服务
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        sys.exit(0)
    except Exception as e:
        print(f"错误: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    start_server()
