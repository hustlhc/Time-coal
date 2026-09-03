import sqlite3

# 连接数据库
conn = sqlite3.connect('coal_prediction.db')
cursor = conn.cursor()

# 添加唯一约束
try:
    # 处理 prediction_data 表
    print("处理 prediction_data 表...")
    # 先删除已存在的重复记录
    print("删除重复记录...")
    cursor.execute('''
    DELETE FROM prediction_data
    WHERE id NOT IN (
        SELECT MIN(id)
        FROM prediction_data
        GROUP BY infer_date, data_type, pred_date
    )
    ''')
    deleted_count = cursor.rowcount
    print(f"删除了 {deleted_count} 条重复记录")
    
    # 创建唯一约束
    print("添加唯一约束...")
    cursor.execute('''
    CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_prediction
    ON prediction_data (infer_date, data_type, pred_date)
    ''')
    print("唯一约束添加成功")
    
    # 处理 real_data 表
    print("\n处理 real_data 表...")
    # 先删除已存在的重复记录
    print("删除重复记录...")
    cursor.execute('''
    DELETE FROM real_data
    WHERE id NOT IN (
        SELECT MIN(id)
        FROM real_data
        GROUP BY date, data_type
    )
    ''')
    deleted_count_real = cursor.rowcount
    print(f"删除了 {deleted_count_real} 条重复记录")
    
    # 创建唯一约束
    print("添加唯一约束...")
    cursor.execute('''
    CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_real
    ON real_data (date, data_type)
    ''')
    print("唯一约束添加成功")
    
    # 提交更改
    conn.commit()
    print("\n操作完成！")
    
    # 打印统计信息
    print(f"总计删除了 {deleted_count + deleted_count_real} 条重复记录")
    
except Exception as e:
    print(f"错误: {str(e)}")
    conn.rollback()
finally:
    # 关闭连接
    conn.close()