#!/usr/bin/env python3
"""
将决策数据保存到数据库
支持从JSON文件或直接从数据结构保存
"""

import sqlite3
import json
import os
from datetime import datetime

# 数据库文件路径
DB_FILE = 'decision_history.db'


def save_decision_to_db(decision_data, plant_name):
    """
    将决策数据保存到数据库
    
    参数:
        decision_data: 决策数据字典，格式与JSON文件相同
        plant_name: 电厂名称（如：可门电厂、漳平电厂等）
    
    返回:
        decision_id: 保存的决策记录ID
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # 开始事务
        conn.execute('BEGIN TRANSACTION')
        
        # 检查是否已存在相同电厂和决策日期的记录
        decision_date = decision_data.get('decision_date')
        if decision_date:
            # 查找已存在的决策ID
            cursor.execute('''
            SELECT id FROM decisions WHERE plant_name = ? AND decision_date = ?
            ''', (plant_name, decision_date))
            existing_decision = cursor.fetchone()
            
            if existing_decision:
                # 如果存在，删除旧记录（级联删除会自动删除相关的采购计划和采购项目）
                existing_id = existing_decision[0]
                print(f"⚠️ 发现相同电厂和决策日期的记录，正在更新... (ID: {existing_id})")
                
                # 删除旧的决策记录（级联删除会自动处理关联数据）
                cursor.execute('DELETE FROM decisions WHERE id = ?', (existing_id,))
        
        # 插入决策数据
        cursor.execute('''
        INSERT INTO decisions (decision_date, is_emergency, duration_days, total_purchase_quantity, decision_analysis, plant_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            decision_date,
            1 if decision_data.get('is_emergency', False) else 0,
            decision_data.get('duration_days'),
            decision_data.get('total_purchase_quantity'),
            decision_data.get('decision_analysis'),
            plant_name,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        
        # 获取决策ID
        decision_id = cursor.lastrowid
        
        # 插入采购计划数据
        for plan in decision_data.get('procurement_plan', []):
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
        print(f"✅ 决策数据保存成功！决策ID: {decision_id}")
        return decision_id
        
    except Exception as e:
        # 回滚事务
        conn.rollback()
        print(f"❌ 保存决策数据失败: {e}")
        raise e
    finally:
        # 关闭连接
        conn.close()


def save_decision_from_json(json_file, plant_name):
    """
    从JSON文件读取决策数据并保存到数据库
    
    参数:
        json_file: JSON文件路径
        plant_name: 电厂名称
    
    返回:
        decision_id: 保存的决策记录ID
    """
    try:
        # 读取JSON文件
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 保存到数据库
        decision_id = save_decision_to_db(data, plant_name)
        return decision_id
        
    except FileNotFoundError:
        print(f"❌ 文件不存在: {json_file}")
        raise
    except json.JSONDecodeError as e:
        print(f"❌ JSON解析错误: {e}")
        raise


def create_sample_decision_data():
    """
    创建示例决策数据（用于测试）
    """
    return {
        "decision_date": "2026-03-12",
        "is_emergency": False,
        "duration_days": 30,
        "total_purchase_quantity": 50000.0,
        "decision_analysis": "根据当前库存和预测需求，建议在未来30天内分批次采购煤炭，确保库存充足。",
        "procurement_plan": [
            {
                "date": "2026/03/15",
                "total_quantity": 15000.0,
                "items": [
                    {
                        "coal_name": "CCI5500",
                        "quantity": 10000.0,
                        "price": 750.0,
                        "coal_price": 700.0,
                        "freight": 50.0,
                        "delivered_unit_cost": 750.0,
                        "latest_delivery_date": "2026-03-20"
                    },
                    {
                        "coal_name": "CCI5000",
                        "quantity": 5000.0,
                        "price": 650.0,
                        "coal_price": 600.0,
                        "freight": 50.0,
                        "delivered_unit_cost": 650.0,
                        "latest_delivery_date": "2026-03-20"
                    }
                ]
            },
            {
                "date": "2026/03/25",
                "total_quantity": 20000.0,
                "items": [
                    {
                        "coal_name": "CCI5500",
                        "quantity": 12000.0,
                        "price": 745.0,
                        "coal_price": 695.0,
                        "freight": 50.0,
                        "delivered_unit_cost": 745.0,
                        "latest_delivery_date": "2026-03-30"
                    },
                    {
                        "coal_name": "CCI4500",
                        "quantity": 8000.0,
                        "price": 550.0,
                        "coal_price": 500.0,
                        "freight": 50.0,
                        "delivered_unit_cost": 550.0,
                        "latest_delivery_date": "2026-03-30"
                    }
                ]
            },
            {
                "date": "2026/04/05",
                "total_quantity": 15000.0,
                "items": [
                    {
                        "coal_name": "CCI5500",
                        "quantity": 15000.0,
                        "price": 740.0,
                        "coal_price": 690.0,
                        "freight": 50.0,
                        "delivered_unit_cost": 740.0,
                        "latest_delivery_date": "2026-04-10"
                    }
                ]
            }
        ]
    }


def main():
    """主函数 - 示例用法"""
    print("=" * 60)
    print("决策数据保存工具")
    print("=" * 60)
    
    # 示例1: 从JSON文件保存
    json_files = [
        ('html1/procure_plan/zhangping_procurement_plan.json', '漳平电厂'),
        ('html1/procure_plan/kemen_procurement_plan.json', '可门电厂'),
        ('html1/procure_plan/shaowu_procurement_plan.json', '邵武电厂'),
        ('html1/procure_plan/yongan_procurement_plan.json', '永安电厂')
    ]
    
    for json_file, plant_name in json_files:
        if os.path.exists(json_file):
            print(f"\n📁 正在从文件 {json_file} 导入数据...")
            try:
                decision_id = save_decision_from_json(json_file, plant_name)
                print(f"✅ {plant_name} 数据导入成功，决策ID: {decision_id}")
            except Exception as e:
                print(f"❌ {plant_name} 数据导入失败: {e}")
        else:
            print(f"⚠️ 文件 {json_file} 不存在，跳过")
    
    # 示例2: 直接保存数据（用于程序生成决策后保存）
    print("\n" + "=" * 60)
    print("示例2: 直接保存程序生成的决策数据")
    print("=" * 60)
    
    sample_data = create_sample_decision_data()
    try:
        decision_id = save_decision_to_db(sample_data, '示例电厂')
        print(f"✅ 示例数据保存成功，决策ID: {decision_id}")
    except Exception as e:
        print(f"❌ 示例数据保存失败: {e}")
    
    print("\n" + "=" * 60)
    print("使用说明:")
    print("=" * 60)
    print("1. 从JSON文件导入:")
    print("   save_decision_from_json('filename.json', '电厂名称')")
    print("")
    print("2. 直接保存数据:")
    print("   save_decision_to_db(decision_data_dict, '电厂名称')")
    print("")
    print("3. 在你的决策生成代码中使用:")
    print("   from save_decision_to_db import save_decision_to_db")
    print("   # 生成决策数据后...")
    print("   decision_id = save_decision_to_db(decision_result, plant_name)")
    print("=" * 60)


if __name__ == '__main__':
    main()