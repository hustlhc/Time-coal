import sqlite3
import json
import os
import sys

def update_database(json_file):
    """更新数据库，导入新的采购计划数据"""
    # 读取JSON文件
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    decision_date = data['decision_date']
    print(f"正在处理决策日期: {decision_date} 的采购计划")
    
    # 连接到数据库
    conn = sqlite3.connect('procurement.db')
    cursor = conn.cursor()
    
    # 检查是否已存在相同决策日期的计划
    cursor.execute('''
    SELECT id FROM procurement_plans WHERE decision_date = ?
    ''', (decision_date,))
    existing_plan = cursor.fetchone()
    
    if existing_plan:
        print(f"发现已存在相同决策日期的计划，ID: {existing_plan[0]}")
        print("正在更新现有计划...")
        
        # 更新采购计划
        plan_id = existing_plan[0]
        cursor.execute('''
        UPDATE procurement_plans
        SET is_emergency = ?, duration_days = ?, total_purchase_quantity = ?
        WHERE id = ?
        ''', (data['is_emergency'], data['duration_days'], data['total_purchase_quantity'], plan_id))
        
        # 删除相关的采购周期和项目
        cursor.execute('DELETE FROM procurement_items WHERE cycle_id IN (SELECT id FROM procurement_cycles WHERE plan_id = ?)', (plan_id,))
        cursor.execute('DELETE FROM procurement_cycles WHERE plan_id = ?', (plan_id,))
    else:
        print("未发现现有计划，正在插入新计划...")
        # 插入新的采购计划
        cursor.execute('''
        INSERT INTO procurement_plans (decision_date, is_emergency, duration_days, total_purchase_quantity)
        VALUES (?, ?, ?, ?)
        ''', (decision_date, data['is_emergency'], data['duration_days'], data['total_purchase_quantity']))
        plan_id = cursor.lastrowid
    
    # 插入采购周期和项目
    for cycle in data['procurement_plan']:
        cursor.execute('''
        INSERT INTO procurement_cycles (plan_id, cycle_index, date, total_quantity)
        VALUES (?, ?, ?, ?)
        ''', (plan_id, cycle['cycle_index'], cycle['date'], cycle['total_quantity']))
        
        cycle_id = cursor.lastrowid
        
        for item in cycle['items']:
            cursor.execute('''
            INSERT INTO procurement_items (cycle_id, coal_name, quantity, price, latest_delivery_date)
            VALUES (?, ?, ?, ?, ?)
            ''', (cycle_id, item['coal_name'], item['quantity'], item['price'], item['latest_delivery_date']))
    
    conn.commit()
    conn.close()
    print(f"数据已从 {json_file} 成功更新到数据库")

def check_latest_data():
    """检查数据库中的最新数据"""
    conn = sqlite3.connect('procurement.db')
    cursor = conn.cursor()
    
    # 检查最新的采购计划
    cursor.execute('SELECT * FROM procurement_plans ORDER BY decision_date DESC LIMIT 1')
    latest_plan = cursor.fetchone()
    if latest_plan:
        print(f"\n最新采购计划:")
        print(f"计划ID: {latest_plan[0]}, 决策日期: {latest_plan[1]}, 总采购量: {latest_plan[4]}")
        
        # 检查该计划的采购周期
        cursor.execute('SELECT * FROM procurement_cycles WHERE plan_id = ?', (latest_plan[0],))
        cycles = cursor.fetchall()
        print(f"该计划包含 {len(cycles)} 个采购周期")
        for cycle in cycles:
            print(f"  周期 {cycle[2]}: 日期 {cycle[3]}, 采购量 {cycle[4]}")
    else:
        print("数据库中没有采购计划数据")
    
    conn.close()

def main():
    # 检查是否提供了JSON文件路径
    if len(sys.argv) > 1:
        json_file = sys.argv[1]
    else:
        # 默认使用procure_plan目录下的procurement_plan.json
        json_file = 'procure_plan/procurement_plan.json'
    
    if not os.path.exists(json_file):
        print(f"错误：找不到文件 {json_file}")
        return
    
    # 确保数据库表结构存在
    conn = sqlite3.connect('procurement.db')
    cursor = conn.cursor()
    
    # 创建采购计划表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS procurement_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_date TEXT,
        is_emergency BOOLEAN,
        duration_days INTEGER,
        total_purchase_quantity REAL
    )
    ''')
    
    # 创建采购周期表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS procurement_cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id INTEGER,
        cycle_index INTEGER,
        date TEXT,
        total_quantity REAL,
        FOREIGN KEY (plan_id) REFERENCES procurement_plans(id)
    )
    ''')
    
    # 创建采购项目表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS procurement_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle_id INTEGER,
        coal_name TEXT,
        quantity REAL,
        price REAL,
        latest_delivery_date TEXT,
        FOREIGN KEY (cycle_id) REFERENCES procurement_cycles(id)
    )
    ''')
    
    conn.commit()
    conn.close()
    
    # 更新数据库
    update_database(json_file)
    
    # 检查最新数据
    check_latest_data()

if __name__ == "__main__":
    main()
