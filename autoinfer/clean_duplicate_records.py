#!/usr/bin/env python3
"""
清理数据库中的重复记录
确保一个电厂在一个决策日只有一个决策
"""

import sqlite3

# 数据库文件路径
DB_FILE = 'decision_history.db'

def clean_duplicate_records():
    """清理重复记录"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # 开始事务
        conn.execute('BEGIN TRANSACTION')
        
        # 查找重复记录
        cursor.execute('''
        SELECT plant_name, decision_date, MIN(id) as keep_id
        FROM decisions
        GROUP BY plant_name, decision_date
        HAVING COUNT(*) > 1
        ''')
        duplicates = cursor.fetchall()
        
        if duplicates:
            print(f"发现 {len(duplicates)} 组重复记录")
            
            for plant, date, keep_id in duplicates:
                # 找到要删除的记录
                cursor.execute('''
                SELECT id FROM decisions 
                WHERE plant_name = ? AND decision_date = ? AND id != ?
                ''', (plant, date, keep_id))
                delete_ids = [row[0] for row in cursor.fetchall()]
                
                if delete_ids:
                    print(f"  {plant} - {date}: 保留 ID {keep_id}, 删除 ID {delete_ids}")
                    
                    # 删除重复记录
                    for delete_id in delete_ids:
                        cursor.execute('DELETE FROM decisions WHERE id = ?', (delete_id,))
        else:
            print("未发现重复记录")
        
        # 提交事务
        conn.commit()
        print("✅ 重复记录清理完成")
        
    except Exception as e:
        # 回滚事务
        conn.rollback()
        print(f"❌ 清理重复记录失败: {e}")
        raise e
    finally:
        # 关闭连接
        conn.close()

def main():
    """主函数"""
    print("=" * 60)
    print("重复记录清理工具")
    print("=" * 60)
    
    # 清理重复记录
    clean_duplicate_records()
    
    # 再次检查
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT plant_name, decision_date, COUNT(*) as count
    FROM decisions
    GROUP BY plant_name, decision_date
    HAVING COUNT(*) > 1
    ''')
    remaining_duplicates = cursor.fetchall()
    
    if remaining_duplicates:
        print("\n⚠️  仍有重复记录:")
        for duplicate in remaining_duplicates:
            plant, date, count = duplicate
            print(f"  {plant} - {date}: {count} 条记录")
    else:
        print("\n✅ 所有重复记录已清理")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("操作完成！")
    print("现在可以添加唯一约束了。")
    print("=" * 60)

if __name__ == '__main__':
    main()