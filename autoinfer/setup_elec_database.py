import sqlite3

# 连接数据库（如果不存在会自动创建）
conn = sqlite3.connect('elec_prediction.db')
cursor = conn.cursor()

# 创建表结构（包含预测数据和真实数据）
# 注意：总发电量由触发器自动计算，等于分机组相加之和
cursor.execute('''
CREATE TABLE IF NOT EXISTS prediction_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    infer_date DATE,
    data_type TEXT,
    pred_date DATE,
    predict REAL,
    unit_id TEXT,  -- 机组ID，NULL表示总发电量，其他如'unit1'、'unit2'等表示分机组
    is_total BOOLEAN DEFAULT 0  -- 标记是否为总发电量（0=分机组，1=总发电量）
)
''')

# 创建真实数据表
# 注意：总发电量由触发器自动计算，等于分机组相加之和
cursor.execute('''
CREATE TABLE IF NOT EXISTS real_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE,
    data_type TEXT,
    value REAL,
    unit_id TEXT,  -- 机组ID，NULL表示总发电量，其他如'unit1'、'unit2'等表示分机组
    is_total BOOLEAN DEFAULT 0  -- 标记是否为总发电量（0=分机组，1=总发电量）
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

# 创建唯一约束（包含机组ID）
cursor.execute('''
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_prediction
ON prediction_data (infer_date, data_type, pred_date, unit_id)
''')

cursor.execute('''
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_real
ON real_data (date, data_type, unit_id)
''')

# 创建触发器：当插入分机组预测数据时，自动更新总发电量
cursor.execute('''
CREATE TRIGGER IF NOT EXISTS trg_update_total_prediction
AFTER INSERT ON prediction_data
WHEN NEW.is_total = 0
BEGIN
    -- 删除旧的总发电量记录
    DELETE FROM prediction_data 
    WHERE infer_date = NEW.infer_date 
    AND data_type = NEW.data_type 
    AND pred_date = NEW.pred_date 
    AND is_total = 1;
    
    -- 插入新的总发电量记录（分机组之和）
    INSERT INTO prediction_data (infer_date, data_type, pred_date, predict, unit_id, is_total)
    SELECT 
        NEW.infer_date,
        NEW.data_type,
        NEW.pred_date,
        SUM(predict),
        NULL,
        1
    FROM prediction_data
    WHERE infer_date = NEW.infer_date 
    AND data_type = NEW.data_type 
    AND pred_date = NEW.pred_date 
    AND is_total = 0;
END
''')

# 创建触发器：当更新分机组预测数据时，自动更新总发电量
cursor.execute('''
CREATE TRIGGER IF NOT EXISTS trg_update_total_prediction_update
AFTER UPDATE ON prediction_data
WHEN NEW.is_total = 0
BEGIN
    -- 删除旧的总发电量记录
    DELETE FROM prediction_data 
    WHERE infer_date = NEW.infer_date 
    AND data_type = NEW.data_type 
    AND pred_date = NEW.pred_date 
    AND is_total = 1;
    
    -- 插入新的总发电量记录（分机组之和）
    INSERT INTO prediction_data (infer_date, data_type, pred_date, predict, unit_id, is_total)
    SELECT 
        NEW.infer_date,
        NEW.data_type,
        NEW.pred_date,
        SUM(predict),
        NULL,
        1
    FROM prediction_data
    WHERE infer_date = NEW.infer_date 
    AND data_type = NEW.data_type 
    AND pred_date = NEW.pred_date 
    AND is_total = 0;
END
''')

# 创建触发器：当插入分机组真实数据时，自动更新总发电量
cursor.execute('''
CREATE TRIGGER IF NOT EXISTS trg_update_total_real
AFTER INSERT ON real_data
WHEN NEW.is_total = 0
BEGIN
    -- 删除旧的总发电量记录
    DELETE FROM real_data 
    WHERE date = NEW.date 
    AND data_type = NEW.data_type 
    AND is_total = 1;
    
    -- 插入新的总发电量记录（分机组之和）
    INSERT INTO real_data (date, data_type, value, unit_id, is_total)
    SELECT 
        NEW.date,
        NEW.data_type,
        SUM(value),
        NULL,
        1
    FROM real_data
    WHERE date = NEW.date 
    AND data_type = NEW.data_type 
    AND is_total = 0;
END
''')

# 创建触发器：当更新分机组真实数据时，自动更新总发电量
cursor.execute('''
CREATE TRIGGER IF NOT EXISTS trg_update_total_real_update
AFTER UPDATE ON real_data
WHEN NEW.is_total = 0
BEGIN
    -- 删除旧的总发电量记录
    DELETE FROM real_data 
    WHERE date = NEW.date 
    AND data_type = NEW.data_type 
    AND is_total = 1;
    
    -- 插入新的总发电量记录（分机组之和）
    INSERT INTO real_data (date, data_type, value, unit_id, is_total)
    SELECT 
        NEW.date,
        NEW.data_type,
        SUM(value),
        NULL,
        1
    FROM real_data
    WHERE date = NEW.date 
    AND data_type = NEW.data_type 
    AND is_total = 0;
END
''')

# 提交并关闭
conn.commit()
conn.close()
print("数据库初始化完成！")
print("创建了两个表：")
print("1. prediction_data - 存储预测数据")
print("2. real_data - 存储真实数据")
print("\n说明：")
print("- 总发电量由触发器自动计算，等于分机组相加之和")
print("- 导入数据时只需导入分机组数据（is_total=0）")
print("- 总发电量会自动生成（is_total=1, unit_id=NULL）")
print("\nprediction_data表结构：")
print("- id: 主键，自增")
print("- infer_date: 预测日期")
print("- data_type: 数据类型（如kemeng、shaowu等电厂名称）")
print("- pred_date: 预测目标日期")
print("- predict: 预测值")
print("- unit_id: 机组ID（NULL表示总发电量，如'unit1'、'unit2'等表示分机组）")
print("- is_total: 是否为总发电量（0=分机组，1=总发电量）")
print("\nreal_data表结构：")
print("- id: 主键，自增")
print("- date: 日期")
print("- data_type: 数据类型（如kemeng_power、shaowu_power等）")
print("- value: 真实数据值")
print("- unit_id: 机组ID（NULL表示总发电量，如'unit1'、'unit2'等表示分机组）")
print("- is_total: 是否为总发电量（0=分机组，1=总发电量）")
print("\n触发器：")
print("- trg_update_total_prediction: 插入分机组预测数据时自动更新总发电量")
print("- trg_update_total_prediction_update: 更新分机组预测数据时自动更新总发电量")
print("- trg_update_total_real: 插入分机组真实数据时自动更新总发电量")
print("- trg_update_total_real_update: 更新分机组真实数据时自动更新总发电量")
