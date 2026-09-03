
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder

# 读取数据
df = pd.read_csv("shaowu.csv")

# 创建处理后的数据框
df_processed = df.copy()

print("开始进行语义连续编码...")
print(f"原始数据形状: {df.shape}")

# 定义天气类型的语义层次和连续性
weather_hierarchy = {
    '晴': 0,
    '多云': 1,
    '阴': 3,
    '雾': 4,
    '小雨': 6,
    '中雨': 7,
    '大雨': 8,
    '暴雨': 9,
    '大暴雨': 10,
    '雪': 11,
    '雷阵雨': 12
}

# 创建语义编码映射
def semantic_weather_encoding(weather_text, hierarchy):
    """根据语义层次进行编码"""
    if weather_text in hierarchy:
        return hierarchy[weather_text]
    else:
        if '雨' in weather_text:
            return 7
        elif '云' in weather_text or '多云' in weather_text:
            return 1
        elif '晴' in weather_text:
            return 0
        elif '阴' in weather_text:
            return 3
        elif '雾' in weather_text:
            return 4
        else:
            return 5

# 应用语义编码
df_processed['textDay_semantic'] = df['textDay'].apply(
    lambda x: semantic_weather_encoding(x, weather_hierarchy)
)

df_processed['textNight_semantic'] = df['textNight'].apply(
    lambda x: semantic_weather_encoding(x, weather_hierarchy)
)

# === 替换原始列 ===
print("\n替换原始天气列...")
# 保存原始列的值（用于后续映射显示）
original_textDay = df_processed['textDay'].copy()
original_textNight = df_processed['textNight'].copy()

# 用编码列替换原始列
df_processed['textDay'] = df_processed['textDay_semantic']
df_processed['textNight'] = df_processed['textNight_semantic']

# 删除临时的语义编码列
df_processed = df_processed.drop(['textDay_semantic', 'textNight_semantic'], axis=1)

# 删除 windDirDay 列
df_processed = df_processed.drop('windDirDay', axis=1)
df_processed['windScaleDay'] = pd.to_numeric(df_processed['windScaleDay'], errors='coerce')

print("✅ 原始天气列已替换为语义编码")

# 保存处理后的文件
output_filename = "shaowu_semantic_continuous.csv"
df_processed.to_csv(output_filename, index=False, encoding='utf-8-sig')

print(f"✅ 语义连续编码完成！文件已保存为: {output_filename}")
print(f"📊 原始列数: {df.shape[1]}, 处理后列数: {df_processed.shape[1]}")

# === 输出编码映射 ===
print(f"\n{'='*50}")
print("📋 编码映射表")
print(f"{'='*50}")

# 获取实际出现的所有编码值
day_codes = sorted(df_processed['textDay'].unique())
night_codes = sorted(df_processed['textNight'].unique())
all_codes = sorted(set(day_codes + night_codes))

# 创建反向映射：编码值 -> 天气类型
code_to_weather = {}
for weather, code in weather_hierarchy.items():
    code_to_weather[code] = weather

# 对于编码5（其他天气），找出对应的原始天气类型
code_5_weathers_day = original_textDay[df_processed['textDay'] == 5].unique()
code_5_weathers_night = original_textNight[df_processed['textNight'] == 5].unique()
code_5_weathers = set(code_5_weathers_day) | set(code_5_weathers_night)

if len(code_5_weathers) > 0:
    code_to_weather[5] = f"其他({', '.join(code_5_weathers)})"

print("\ntextDay 编码映射:")
print("编码 | 天气类型")
print("-" * 20)
for code in day_codes:
    weather = code_to_weather.get(code, "未知")
    print(f"{code:4} | {weather}")

print("\ntextNight 编码映射:")
print("编码 | 天气类型")
print("-" * 20)
for code in night_codes:
    weather = code_to_weather.get(code, "未知")
    print(f"{code:4} | {weather}")

print(f"\n所有出现的编码值: {all_codes}")

# 显示编码统计
print(f"\n{'='*50}")
print("📊 编码统计")
print(f"{'='*50}")

print("\ntextDay 编码分布:")
day_dist = df_processed['textDay'].value_counts().sort_index()
for code, count in day_dist.items():
    weather = code_to_weather.get(code, "未知")
    percentage = (count / len(df_processed)) * 100
    print(f"  编码 {code} ({weather}): {count} 次 ({percentage:.1f}%)")

print("\ntextNight 编码分布:")
night_dist = df_processed['textNight'].value_counts().sort_index()
for code, count in night_dist.items():
    weather = code_to_weather.get(code, "未知")
    percentage = (count / len(df_processed)) * 100
    print(f"  编码 {code} ({weather}): {count} 次 ({percentage:.1f}%)")

# 显示前几行数据示例（替换后的）
print(f"\n{'='*50}")
print("👀 替换后的数据示例（前5行）")
print(f"{'='*50}")
print(f"{'行号':<4} {'textDay':<8} {'textNight':<8} {'windScaleDay':<12}")
print("-" * 40)

for sample_idx in range(5):
    textDay_code = df_processed.iloc[sample_idx]['textDay']
    textNight_code = df_processed.iloc[sample_idx]['textNight']
    windScale = df_processed.iloc[sample_idx]['windScaleDay']
    
    textDay_weather = code_to_weather.get(textDay_code, "未知")
    textNight_weather = code_to_weather.get(textNight_code, "未知")
    
    print(f"{sample_idx:<4} {textDay_code:<8} {textNight_code:<8} {windScale:<12}")
    print(f"      ({textDay_weather:<6})   ({textNight_weather:<6})")

# 显示列变化信息
print(f"\n{'='*50}")
print("🔧 列变化总结")
print(f"{'='*50}")
print("删除的列:")
print("  - windDirDay")
print("\n替换的列:")
print("  - textDay → 语义编码 (整数)")
print("  - textNight → 语义编码 (整数)")
print("\n保留的列:")
print("  - windScaleDay (数值类型)")
print("  - 所有其他原始列")

print(f"\n💡 语义编码说明:")
print("• textDay 和 textNight 列现在包含语义编码数值")
print("• 编码设计让相似天气在数值上接近")
print("• 晴天类: 0-2, 阴天类: 3-5, 雨天类: 6-10, 特殊天气: 11-12")
print("• 编码5代表未在预定义列表中的其他天气类型")

# 验证处理结果
print(f"\n{'='*50}")
print("✅ 处理验证")
print(f"{'='*50}")
print(f"最终数据形状: {df_processed.shape}")
print(f"textDay 数据类型: {df_processed['textDay'].dtype}")
print(f"textNight 数据类型: {df_processed['textNight'].dtype}")
print(f"文件已保存: {output_filename}")