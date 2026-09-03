import sqlite3
import os

def check_database():
    """检查数据库是否建立正确"""
    print("开始检查数据库...")
    print("=" * 60)
    
    # 检查数据库文件是否存在
    db_file = 'coal_prediction.db'
    if not os.path.exists(db_file):
        print(f"❌ 错误：数据库文件 '{db_file}' 不存在")
        print("请先运行 setup_database_with_real_data.py 初始化数据库")
        return False
    
    print(f"✅ 数据库文件 '{db_file}' 存在")
    
    try:
        # 连接数据库
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        print("✅ 成功连接到数据库")
        
        # 检查 prediction_data 表
        print("\n检查 prediction_data 表...")
        cursor.execute('''
        PRAGMA table_info(prediction_data)
        ''')
        pred_columns = cursor.fetchall()
        
        if not pred_columns:
            print("❌ 错误：prediction_data 表不存在或为空")
        else:
            print(f"✅ prediction_data 表存在，包含 {len(pred_columns)} 个字段：")
            for col in pred_columns:
                print(f"  - {col[1]} ({col[2]})")
            
            # 检查数据数量
            cursor.execute('SELECT COUNT(*) FROM prediction_data')
            pred_count = cursor.fetchone()[0]
            print(f"  数据行数: {pred_count}")
        
        # 检查 real_data 表
        print("\n检查 real_data 表...")
        cursor.execute('''
        PRAGMA table_info(real_data)
        ''')
        real_columns = cursor.fetchall()
        
        if not real_columns:
            print("❌ 错误：real_data 表不存在或为空")
        else:
            print(f"✅ real_data 表存在，包含 {len(real_columns)} 个字段：")
            for col in real_columns:
                print(f"  - {col[1]} ({col[2]})")
            
            # 检查数据数量
            cursor.execute('SELECT COUNT(*) FROM real_data')
            real_count = cursor.fetchone()[0]
            print(f"  数据行数: {real_count}")
        
        # 检查数据类型
        print("\n检查数据类型...")
        
        # 检查 prediction_data 的数据类型
        cursor.execute('SELECT DISTINCT data_type FROM prediction_data')
        pred_types = [row[0] for row in cursor.fetchall()]
        if pred_types:
            print("✅ prediction_data 包含以下数据类型：")
            for i, data_type in enumerate(pred_types, 1):
                print(f"  {i}. {data_type}")
        else:
            print("⚠️  warning: prediction_data 中没有数据类型")
        
        # 检查 real_data 的数据类型
        cursor.execute('SELECT DISTINCT data_type FROM real_data')
        real_types = [row[0] for row in cursor.fetchall()]
        if real_types:
            print("✅ real_data 包含以下数据类型：")
            for i, data_type in enumerate(real_types, 1):
                print(f"  {i}. {data_type}")
        else:
            print("⚠️  warning: real_data 中没有数据类型")
        
        # 检查数据分布
        print("\n检查数据分布...")
        
        # 检查 prediction_data 各类型数据数量
        if pred_types:
            print("prediction_data 各类型数据数量：")
            for data_type in pred_types:
                cursor.execute('SELECT COUNT(*) FROM prediction_data WHERE data_type = ?', (data_type,))
                count = cursor.fetchone()[0]
                print(f"  {data_type}: {count} 条")
        
        # 检查 real_data 各类型数据数量
        if real_types:
            print("\nreal_data 各类型数据数量：")
            for data_type in real_types:
                cursor.execute('SELECT COUNT(*) FROM real_data WHERE data_type = ?', (data_type,))
                count = cursor.fetchone()[0]
                print(f"  {data_type}: {count} 条")
        
        # 检查索引
        print("\n检查索引...")
        cursor.execute('SELECT name FROM sqlite_master WHERE type="index"')
        indexes = cursor.fetchall()
        if indexes:
            print("✅ 数据库包含以下索引：")
            for idx in indexes:
                print(f"  - {idx[0]}")
        else:
            print("⚠️  warning: 数据库中没有索引")
        
        # 检查数据质量
        print("\n检查数据质量...")
        
        # 检查 prediction_data 是否有缺失值
        cursor.execute('SELECT COUNT(*) FROM prediction_data WHERE predict IS NULL')
        pred_null = cursor.fetchone()[0]
        print(f"prediction_data 中 predict 字段的空值数量: {pred_null}")
        
        # 检查 real_data 是否有缺失值
        cursor.execute('SELECT COUNT(*) FROM real_data WHERE value IS NULL')
        real_null = cursor.fetchone()[0]
        print(f"real_data 中 value 字段的空值数量: {real_null}")
        
        # 检查日期字段格式
        cursor.execute('SELECT COUNT(*) FROM prediction_data WHERE pred_date IS NULL')
        pred_date_null = cursor.fetchone()[0]
        print(f"prediction_data 中 pred_date 字段的空值数量: {pred_date_null}")
        
        cursor.execute('SELECT COUNT(*) FROM real_data WHERE date IS NULL')
        real_date_null = cursor.fetchone()[0]
        print(f"real_data 中 date 字段的空值数量: {real_date_null}")
        
        # 关闭连接
        conn.close()
        print("✅ 数据库连接已关闭")
        
        print("\n" + "=" * 60)
        print("数据库检查完成！")
        
        # 总结
        print("\n总结：")
        if (pred_columns and real_columns and 
            pred_count > 0 and real_count > 0 and 
            len(pred_types) > 0 and len(real_types) > 0):
            print("✅ 数据库建立正确，数据导入成功！")
            print(f"  - prediction_data 表：{pred_count} 条数据")
            print(f"  - real_data 表：{real_count} 条数据")
            print(f"  - 预测数据类型：{len(pred_types)} 种")
            print(f"  - 真实数据类型：{len(real_types)} 种")
            return True
        else:
            print("❌ 数据库存在问题，请检查上述警告和错误")
            return False
            
    except Exception as e:
        print(f"❌ 错误：{str(e)}")
        return False

def check_api_readiness():
    """检查API服务是否准备就绪"""
    print("\n" + "=" * 60)
    print("检查API服务准备情况...")
    
    # 检查必要的文件
    required_files = [
        'coal_prediction.db',
        'app_with_real_data.py',
        'import_data.py',
        'import_real_data.py'
    ]
    
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("❌ 缺少以下文件：")
        for file in missing_files:
            print(f"  - {file}")
        return False
    else:
        print("✅ 所有必要文件都存在")
        return True

if __name__ == '__main__':
    print("数据库检查工具")
    print("功能：检查数据库结构、数据导入情况和API服务准备状态")
    print("\n运行环境：")
    print(f"  当前目录：{os.getcwd()}")
    print(f"  Python 版本：{os.sys.version}")
    
    # 执行数据库检查
    db_ok = check_database()
    
    # 执行API服务准备检查
    api_ready = check_api_readiness()
    
    print("\n" + "=" * 60)
    print("最终状态：")
    if db_ok and api_ready:
        print("✅ 数据库和API服务准备就绪！")
        print("\n可以运行以下命令启动服务：")
        print("  python app_with_real_data.py")
        print("\n然后访问：http://localhost:5000")
    else:
        print("❌ 数据库或API服务未准备就绪")
        print("请根据上述检查结果修复问题")
