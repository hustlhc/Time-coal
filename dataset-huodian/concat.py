import pandas as pd

# 读取天气数据
weather_df = pd.read_csv('/home/chenty/Time-Series-Library/dataset/huodian/weather/漳平_天气.csv')
# 读取漳平数据
zhangping_df = pd.read_csv('/home/chenty/Time-Series-Library/dataset/huodian/dianchang/漳平.csv')

# 确保日期列格式一致
weather_df['fxDate'] = weather_df['fxDate'].astype(str)
zhangping_df['period_id'] = zhangping_df['period_id'].astype(str)

# 找到要插入的位置
columns = zhangping_df.columns.tolist()
target_index = columns.index('漳平_漳平#6_运行小时') + 1

# 获取天气特征列（排除日期列）
weather_features = ['tempMax', 'tempMin', 'textDay', 'textNight', 'windDirDay', 'windScaleDay']

# 合并数据
merged_df = zhangping_df.merge(weather_df, left_on='period_id', right_on='fxDate', how='left')

# 重新排列列的顺序
new_columns = columns[:target_index] + weather_features + columns[target_index:]

# 创建最终的数据框
final_df = merged_df[new_columns]

# 保存结果
final_df.to_csv('zhangping.csv', index=False)

print("合并完成！新文件已保存为 'zhangping.csv'")
print(f"新增的天气特征列：{weather_features}")
print(f"插入位置：在 '漳平_漳平#6_运行小时' 之后")