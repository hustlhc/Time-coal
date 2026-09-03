from flask import Flask, jsonify, request
import sqlite3
from flask_cors import CORS  # 解决跨域问题

app = Flask(__name__)
CORS(app)  # 启用CORS，允许前端跨域请求

def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect('coal_prediction.db')
    conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
    return conn

@app.route('/api/prediction', methods=['GET'])
def get_prediction():
    """获取预测数据的API接口"""
    # 获取查询参数
    data_type = request.args.get('type')  # 数据类型
    days = request.args.get('days', 5, type=int)  # 天数，默认5天
    
    # 验证参数
    if not data_type:
        return jsonify({'error': '缺少type参数'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询数据（按预测日期排序，取前N天）
        cursor.execute('''
        SELECT pred_date, predict FROM prediction_data
        WHERE data_type = ?
        ORDER BY pred_date ASC
        LIMIT ?
        ''', (data_type, days))
        
        rows = cursor.fetchall()
        conn.close()
        
        # 格式化返回数据
        result = []
        for row in rows:
            result.append({
                'date': row['pred_date'],
                'predict': row['predict']
            })
        
        # 返回JSON数据
        return jsonify(result)
        
    except Exception as e:
        print(f"API错误: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500

@app.route('/api/real_data', methods=['GET'])
def get_real_data():
    """获取真实数据的API接口"""
    # 获取查询参数
    data_type = request.args.get('type')  # 数据类型
    days = request.args.get('days', 30, type=int)  # 天数，默认30天
    
    # 验证参数
    if not data_type:
        return jsonify({'error': '缺少type参数'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询数据（按日期排序，取最近N天）
        cursor.execute('''
        SELECT date, value FROM real_data
        WHERE data_type = ?
        ORDER BY date DESC
        LIMIT ?
        ''', (data_type, days))
        
        rows = cursor.fetchall()
        conn.close()
        
        # 格式化返回数据并按日期正序排列
        result = []
        for row in reversed(rows):  # 反转顺序，使日期从小到大
            result.append({
                'date': row['date'],
                'value': row['value']
            })
        
        # 返回JSON数据
        return jsonify(result)
        
    except Exception as e:
        print(f"API错误: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500

@app.route('/api/data_types', methods=['GET'])
def get_data_types():
    """获取所有数据类型的API接口"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询所有不重复的数据类型（预测数据）
        cursor.execute('''
        SELECT DISTINCT data_type FROM prediction_data
        ORDER BY data_type
        ''')
        
        pred_types = [row['data_type'] for row in cursor.fetchall()]
        
        # 查询所有不重复的数据类型（真实数据）
        cursor.execute('''
        SELECT DISTINCT data_type FROM real_data
        ORDER BY data_type
        ''')
        
        real_types = [row['data_type'] for row in cursor.fetchall()]
        
        conn.close()
        
        # 返回JSON数据
        return jsonify({
            'prediction_types': pred_types,
            'real_types': real_types
        })
        
    except Exception as e:
        print(f"API错误: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500

@app.route('/api/compare', methods=['GET'])
def get_compare_data():
    """获取预测数据和真实数据对比的API接口"""
    # 获取查询参数
    pred_type = request.args.get('pred_type')  # 预测数据类型
    real_type = request.args.get('real_type')  # 真实数据类型
    days = request.args.get('days', 5, type=int)  # 天数，默认5天
    
    # 验证参数
    if not pred_type or not real_type:
        return jsonify({'error': '缺少pred_type或real_type参数'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询预测数据
        cursor.execute('''
        SELECT pred_date, predict FROM prediction_data
        WHERE data_type = ?
        ORDER BY pred_date ASC
        LIMIT ?
        ''', (pred_type, days))
        
        pred_rows = cursor.fetchall()
        
        # 查询真实数据（最近N天）
        cursor.execute('''
        SELECT date, value FROM real_data
        WHERE data_type = ?
        ORDER BY date DESC
        LIMIT ?
        ''', (real_type, days))
        
        real_rows = cursor.fetchall()
        conn.close()
        
        # 格式化预测数据
        prediction_data = []
        for row in pred_rows:
            prediction_data.append({
                'date': row['pred_date'],
                'value': row['predict']
            })
        
        # 格式化真实数据并按日期正序排列
        real_data_list = []
        for row in reversed(real_rows):  # 反转顺序，使日期从小到大
            real_data_list.append({
                'date': row['date'],
                'value': row['value']
            })
        
        # 返回JSON数据
        return jsonify({
            'prediction': prediction_data,
            'real': real_data_list
        })
        
    except Exception as e:
        print(f"API错误: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500

@app.route('/', methods=['GET'])
def index():
    """根路径，返回API说明"""
    return '''
    <h1>煤价预测数据API</h1>
    <p>API接口说明：</p>
    <ul>
        <li><strong>GET /api/prediction</strong> - 获取预测数据</li>
        <li>参数：</li>
        <ul>
            <li><code>type</code> - 数据类型（如CCI4500infer、insideinfer等）</li>
            <li><code>days</code> - 天数（默认5天）</li>
        </ul>
        <li>示例：<code>/api/prediction?type=CCI4500infer&days=10</code></li>
        
        <li><strong>GET /api/real_data</strong> - 获取真实数据</li>
        <li>参数：</li>
        <ul>
            <li><code>type</code> - 数据类型（如CCI4500、inside_freight等）</li>
            <li><code>days</code> - 天数（默认30天）</li>
        </ul>
        <li>示例：<code>/api/real_data?type=CCI4500&days=30</code></li>
        
        <li><strong>GET /api/data_types</strong> - 获取所有数据类型</li>
        
        <li><strong>GET /api/compare</strong> - 获取预测数据和真实数据对比</li>
        <li>参数：</li>
        <ul>
            <li><code>pred_type</code> - 预测数据类型</li>
            <li><code>real_type</code> - 真实数据类型</li>
            <li><code>days</code> - 天数（默认5天）</li>
        </ul>
        <li>示例：<code>/api/compare?pred_type=CCI4500infer&real_type=CCI4500&days=10</code></li>
    </ul>
    <p>数据类型说明：</p>
    <ul>
        <li><strong>预测数据类型</strong>：</li>
        <ul>
            <li>CCI3800outinfer (进口煤价)</li>
            <li>CCI4500infer (国内煤价)</li>
            <li>CCI4700outinfer (进口煤价)</li>
            <li>CCI5000infer (国内煤价)</li>
            <li>CCI5500infer (国内煤价)</li>
            <li>CCI5500outinfer (进口煤价)</li>
            <li>insideinfer (国内运费)</li>
            <li>outsideinfer (国际运费)</li>
        </ul>
        <li><strong>真实数据类型</strong>：</li>
        <ul>
            <li>CCI3800, CCI4500, CCI4700, CCI5000, CCI5500, CCI5800 (煤价)</li>
            <li>inside_freight (国内运费)</li>
            <li>outside_freight (国际运费)</li>
        </ul>
    </ul>
    '''

if __name__ == '__main__':
    print("启动煤价预测数据API服务...")
    print("服务地址: http://localhost:5000")
    print("API接口:")
    print("- GET /api/prediction?type=数据类型&days=天数")
    print("- GET /api/real_data?type=数据类型&days=天数")
    print("- GET /api/data_types")
    print("- GET /api/compare?pred_type=预测类型&real_type=真实类型&days=天数")
    print("- GET / (API说明)")
    print("\n按 Ctrl+C 停止服务")
    app.run(debug=True, host='localhost', port=5000)
