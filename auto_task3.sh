#!/bin/bash
# auto_task3.sh - 数据导入任务

echo "===== Task3 开始执行: $(date '+%Y-%m-%d %H:%M:%S') ====="

# 切换到正确目录
cd /home/coal/Time-coal/autoinfer || {
    echo "错误: 无法切换到目录 /home/coal/Time-coal/autoinfer"
    exit 1
}

# 记录当前目录
echo "当前目录: $(pwd)"

# 执行Python脚本
echo "执行 import_real_data.py..."
/usr/bin/python3 import_real_data.py
if [ $? -eq 0 ]; then
    echo "✓ import_real_data.py 执行成功"
else
    echo "✗ import_real_data.py 执行失败"
fi

echo "执行 import_data.py..."
/usr/bin/python3 import_data.py
if [ $? -eq 0 ]; then
    echo "✓ import_data.py 执行成功"
else
    echo "✗ import_data.py 执行失败"
fi

echo "执行 add_unique_constraint.py..."
/usr/bin/python3 add_unique_constraint.py
if [ $? -eq 0 ]; then
    echo "✓ add_unique_constraint.py 执行成功"
else
    echo "✗ add_unique_constraint.py 执行失败"
fi

/usr/bin/python3 import_real_elec_data.py

/usr/bin/python3 import_elec_prediction_data.py

/usr/bin/python3 save_decision_to_db.py


# 写入日志
echo "$(date '+%Y-%m-%d %H:%M:%S') Task3 finished." >> /home/coal/Time-coal/auto_task3.log

echo "===== Task3 执行完成: $(date '+%Y-%m-%d %H:%M:%S') ====="
echo ""

