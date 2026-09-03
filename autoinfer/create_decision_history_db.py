#!/usr/bin/env python3
"""
创建决策历史数据数据库
基于 zhangping_procurement_plan.json 的结构设计
"""

import sqlite3
import json
import os

# 数据库文件路径
DB_FILE = 'decision_history.db'

def create_database():
    """创建决策历史数据库及表结构"""
    # 连接数据库（如果不存在则创建）
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 创建决策表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_date TEXT NOT NULL,
        is_emergency INTEGER DEFAULT 0,
        duration_days INTEGER,
        total_purchase_quantity REAL,
        decision_analysis TEXT,
        plant_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建采购计划表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS procurement_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_id INTEGER,
        plan_date TEXT NOT NULL,
        total_quantity REAL,
        FOREIGN KEY (decision_id) REFERENCES decisions(id) ON DELETE CASCADE
    )
    ''')
    
    # 创建采购项目表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS procurement_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plan_id INTEGER,
        coal_name TEXT NOT NULL,
        quantity REAL,
        price REAL,
        coal_price REAL,
        freight REAL,
        delivered_unit_cost REAL,
        latest_delivery_date TEXT,
        FOREIGN KEY (plan_id) REFERENCES procurement_plans(id) ON DELETE CASCADE
    )
    ''')
    
    # 提交并关闭连接
    conn.commit()
    conn.close()
    print(f"数据库 {DB_FILE} 创建成功")

def insert_decision_from_json(json_file, plant_name):
    """从JSON文件插入决策数据"""
    try:
        # 读取JSON文件
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 连接数据库
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 开始事务
        conn.execute('BEGIN TRANSACTION')
        
        # 插入决策数据
        cursor.execute('''
        INSERT INTO decisions (decision_date, is_emergency, duration_days, total_purchase_quantity, decision_analysis, plant_name)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data.get('decision_date'),
            1 if data.get('is_emergency', False) else 0,
            data.get('duration_days'),
            data.get('total_purchase_quantity'),
            data.get('decision_analysis'),
            plant_name
        ))
        
        # 获取决策ID
        decision_id = cursor.lastrowid
        
        # 插入采购计划数据
        for plan in data.get('procurement_plan', []):
            cursor.execute('''
            INSERT INTO procurement_plans (decision_id, plan_date, total_quantity)
            VALUES (?, ?, ?)
            ''', (
                decision_id,
                plan.get('date'),
                plan.get('total_quantity')
            ))
            
            # 获取采购计划ID
            plan_id = cursor.lastrowid
            
            # 插入采购项目数据
            for item in plan.get('items', []):
                cursor.execute('''
                INSERT INTO procurement_items (plan_id, coal_name, quantity, price, coal_price, freight, delivered_unit_cost, latest_delivery_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    plan_id,
                    item.get('coal_name'),
                    item.get('quantity'),
                    item.get('price'),
                    item.get('coal_price'),
                    item.get('freight'),
                    item.get('delivered_unit_cost'),
                    item.get('latest_delivery_date')
                ))
        
        # 提交事务
        conn.commit()
        print(f"成功从 {json_file} 插入数据到数据库")
        
    except Exception as e:
        # 回滚事务
        conn.rollback()
        print(f"插入数据失败: {e}")
    finally:
        # 关闭连接
        if 'conn' in locals():
            conn.close()

def query_decisions():
    """查询所有决策数据"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 查询所有决策
    cursor.execute('SELECT * FROM decisions ORDER BY decision_date DESC')
    decisions = cursor.fetchall()
    
    print(f"共找到 {len(decisions)} 条决策记录")
    for decision in decisions:
        print(f"\n决策ID: {decision['id']}")
        print(f"决策日期: {decision['decision_date']}")
        print(f"电厂: {decision['plant_name']}")
        print(f"是否紧急: {'是' if decision['is_emergency'] else '否'}")
        print(f"持续天数: {decision['duration_days']}")
        print(f"总采购量: {decision['total_purchase_quantity']}")
        
        # 查询该决策的采购计划
        cursor.execute('SELECT * FROM procurement_plans WHERE decision_id = ?', (decision['id'],))
        plans = cursor.fetchall()
        print(f"采购计划数量: {len(plans)}")
        
        for plan in plans:
            print(f"  计划日期: {plan['plan_date']}, 总数量: {plan['total_quantity']}")
    
    conn.close()

def main():
    """主函数"""
    # 创建数据库
    create_database()
    
    # 插入示例数据
    json_files = [
        ('zhangping_procurement_plan.json', '漳平电厂'),
        ('kemen_procurement_plan.json', '可门电厂'),
        ('shaowu_procurement_plan.json', '邵武电厂'),
        ('yongan_procurement_plan.json', '永安电厂')
    ]
    
    for json_file, plant_name in json_files:
        if os.path.exists(json_file):
            insert_decision_from_json(json_file, plant_name)
        else:
            print(f"文件 {json_file} 不存在，跳过")
    
    # 查询数据
    query_decisions()

if __name__ == '__main__':
    main()