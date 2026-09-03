import pandas as pd

# 读取两个CSV文件（只有一列）
df5 = pd.read_csv('zhangping_5.csv', header=None)  # 如果没有列名，用header=None
df6 = pd.read_csv('zhangping_6.csv', header=None)

# 或者如果有列名，可以指定列名
# df5 = pd.read_csv('zhangping_5.csv', names=['value'])
# df6 = pd.read_csv('zhangping_6.csv', names=['value'])

# 两列对应相加
result = df5 + df6

# 保存结果
result.to_csv('zhangping.csv', index=False, header=False)  # 不保存索引和列名

print("数据已成功相加并保存到 zhangping.csv")
print(f"第一个文件行数: {len(df5)}")
print(f"第二个文件行数: {len(df6)}")
print(f"结果文件行数: {len(result)}")

# 显示前几行预览
print("\n预览（前5行）:")
print(result.head())