import pandas as pd

# 1. 读文件
file = 'attention_predictions_1.csv'          # 原始文件
df = pd.read_csv(file)

# 2. 只保留数值列的小数点后 2 位
decimal_places = 0
numeric_cols = df.select_dtypes(include='number').columns
df[numeric_cols] = df[numeric_cols].round(decimal_places)

# 3. 写回（覆盖保存，想另存就改文件名）
df.to_csv(file, index=False)

print('Done！所有数值列已保留 2 位小数。')