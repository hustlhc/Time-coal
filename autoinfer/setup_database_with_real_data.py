import sqlite3

# 连接数据库（如果不存在会自动创建）
conn = sqlite3.connect('elec_prediction.db')
cursor = conn.cursor()

# 创建表结构（包含预测数据和真实数据）
cursor.execute('''
CREATE TABLE IF NOT EXISTS prediction_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    infer_date DATE,
    data_type TEXT,
    pred_date DATE,
    predict REAL
)
''')

# 创建真实数据表
cursor.execute('''
CREATE TABLE IF NOT EXISTS real_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE,
    data_type TEXT,
    value REAL
)
''')

# 创建索引以提高查询速度
cursor.execute('''
CREATE INDEX IF NOT EXISTS idx_pred_data_type ON prediction_data(data_type)
''')

cursor.execute('''
CREATE INDEX IF NOT EXISTS idx_pred_pred_date ON prediction_data(pred_date)
''')

cursor.execute('''
CREATE INDEX IF NOT EXISTS idx_real_date ON real_data(date)
''')

cursor.execute('''
CREATE INDEX IF NOT EXISTS idx_real_data_type ON real_data(data_type)
''')

# 提交并关闭
conn.commit()
conn.close()
print("数据库初始化完成！")
print("创建了两个表：")
print("1. prediction_data - 存储预测数据")
print("2. real_data - 存储真实数据")
print("\nreal_data表结构：")
print("- id: 主键，自增")
print("- date: 日期")
print("- data_type: 数据类型（如CCI4500、inside_freight等）")
print("- value: 真实数据值")
