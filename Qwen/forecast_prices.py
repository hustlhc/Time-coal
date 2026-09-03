import os
import csv
import json
import copy
#输入csv源表24、25各电厂存煤量_已补充CCI.csv，输出月拆分文件与存煤量

# ==========================
# 用户配置区域
# ==========================

# 需要提取的煤种（示例：请按实际表头替换）
coal_types = ["CCI4500", "CCI5000", "CCI5500", "CCI进口3800", "CCI进口4700", "CCI进口5500"]

# 输出 CSV 文件所在目录
input_folder = r"data/25各电厂存煤量_已补充CCI.csv"

# 月度拆分文件输出目录（生成 coal_output_YYYYMM.json）
monthly_split_dir = r"data/coal_output_monthly"
# 日期->存煤量输出
stock_output_file = r"data/stock_by_date.json"

# ==========================
# 用户输入 JSON 生成配置
# ==========================
TEMPLATE_FILE = "input/user_input.json"
INPUT_MONTHLY_DIR = "input/monthly"


# ==========================
# 数据处理脚本
# ==========================

def _open_csv(csv_file):
    """Robust CSV opener that tries utf-8-sig, then gbk."""
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb18030"]
    last_err = None
    for enc in encodings:
        try:
            return open(csv_file, "r", encoding=enc)
        except Exception as e:
            last_err = e
            continue
    raise last_err


def extract_coal_data(csv_file, coal_types):
    coal_data = {coal: [] for coal in coal_types}

    with _open_csv(csv_file) as f:
        reader = csv.DictReader(f)
        available_columns = reader.fieldnames

        for row in reader:
            for coal in coal_types:
                if coal in available_columns:
                    value = row.get(coal)
                    if value not in (None, ""):
                        coal_data[coal].append(value)

    return coal_data


def extract_stock_data(csv_file, date_col="date", stock_col="存煤量"):
    """输出日期到存煤量的映射，便于决策日直接取值。"""
    stock_map = {}

    with _open_csv(csv_file) as f:
        reader = csv.DictReader(f)
        available_columns = reader.fieldnames or []
        if date_col not in available_columns or stock_col not in available_columns:
            raise ValueError(f"缺少列: {date_col} 或 {stock_col}")

        for row in reader:
            date_raw = row.get(date_col)
            stock_raw = row.get(stock_col)
            if not date_raw or stock_raw in (None, ""):
                continue
            try:
                stock_val = float(stock_raw)
            except Exception:
                continue
            stock_map[str(date_raw)] = stock_val

    return stock_map


def normalize_prices(prices, target_len=20):
    if not prices:
        return [0.0] * target_len

    vals = []
    for p in prices:
        try:
            vals.append(float(p))
        except Exception:
            continue

    if not vals:
        return [0.0] * target_len

    if len(vals) >= target_len:
        return vals[:target_len]

    padded = vals + [vals[-1]] * (target_len - len(vals))
    return padded[:target_len]


def extract_monthly_coal_data(csv_file, coal_types, date_col="date", target_len=20):
    """将日级表按月聚合为 4 周×5 天=20 个价位的月度序列。"""
    monthly = {}

    with _open_csv(csv_file) as f:
        reader = csv.DictReader(f)
        available_columns = reader.fieldnames or []
        if date_col not in available_columns:
            raise ValueError(f"缺少日期列 {date_col}，无法按月聚合")

        for row in reader:
            date_raw = row.get(date_col)
            if not date_raw:
                continue
            month = str(date_raw)[:6]  # 20240101 -> 202401
            bucket = monthly.setdefault(month, {coal: [] for coal in coal_types})

            for coal in coal_types:
                if coal not in available_columns:
                    continue
                value = row.get(coal)
                if value in (None, ""):
                    continue
                try:
                    bucket[coal].append(float(value))
                except Exception:
                    continue

    for month, coal_map in monthly.items():
        for coal in coal_types:
            coal_prices = coal_map.get(coal, [])
            monthly[month][coal] = normalize_prices(coal_prices, target_len=target_len)

    return monthly



def save_as_json(data, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def save_monthly_split(monthly_data, output_dir):
    """把 monthly_data 拆成单月文件，命名为 coal_output_YYYYMM.json。"""
    base_dir = output_dir or "."
    os.makedirs(base_dir, exist_ok=True)

    for month, payload in monthly_data.items():
        fname = f"coal_output_{str(month)}.json"
        out_path = os.path.join(base_dir, fname)
        save_as_json(payload, out_path)
        print("处理完成，已生成单月 JSON 文件:", out_path)


# ==========================
# 自动生成用户输入 JSON 逻辑 
# ==========================
def normalize_month(month_key):
    month_key = str(month_key)
    if len(month_key) >= 6:
        return month_key[:6]
    raise ValueError(f"Invalid month key: {month_key}")

def month_to_decision_date(month_key):
    month_key = normalize_month(month_key)
    year = int(month_key[:4])
    month = int(month_key[4:])
    return f"{year}/{month}/1"

def first_stock_for_month(stock_map, month_key):
    month_key = normalize_month(month_key)
    day_keys = sorted(k for k in stock_map.keys() if str(k).startswith(month_key))
    if not day_keys:
        raise ValueError(f"Missing stock data for month {month_key}")
    first_key = str(day_keys[0])
    return float(stock_map[first_key])

def first_price_for_coal(month_prices, coal_name):
    prices_raw = month_prices.get(coal_name, [])
    if isinstance(prices_raw, list) and prices_raw:
        try:
            return float(prices_raw[0])
        except Exception:
            return None
    return None

def build_coal_config(template_config, month_prices):
    new_config = {}
    for coal_name, base_cfg in template_config.items():
        cfg = copy.deepcopy(base_cfg)
        first_price = first_price_for_coal(month_prices, coal_name)
        if first_price is not None:
            cfg["current_price"] = first_price
        new_config[coal_name] = cfg

    for coal_name, prices_raw in month_prices.items():
        if coal_name in new_config:
            continue
        first_price = first_price_for_coal(month_prices, coal_name)
        new_config[coal_name] = {
            "current_price": first_price if first_price is not None else 0,
            "heat_value": template_config.get(coal_name, {}).get("heat_value", 0)
        }
    return new_config

def build_month_input(month_key, template, month_prices, stock_map, split_base_dir):
    month_key = normalize_month(month_key)
    data = copy.deepcopy(template)
    
    split_path = os.path.join(split_base_dir, f"coal_output_{month_key}.json")
    data["price_file"] = f"./{split_path}"
    
    data["decision_date"] = month_to_decision_date(month_key)
    try:
        data["prev_stock"] = first_stock_for_month(stock_map, month_key)
    except Exception as e:
        print(f"Warning: Could not set prev_stock for {month_key} - {e}")
        
    template_config = template.get("coal_config", {})
    data["coal_config"] = build_coal_config(template_config, month_prices)
    return data

def generate_all_inputs(monthly_data, stock_data, template_file, output_dir, split_base_dir):
    if not os.path.exists(template_file):
        print(f"Template file {template_file} not found, skipping input generation.")
        return
        
    with open(template_file, "r", encoding="utf-8") as f:
        template = json.load(f)
        
    os.makedirs(output_dir, exist_ok=True)
    
    output_paths = []
    month_keys = sorted(k for k in monthly_data.keys())
    for month_key in month_keys:
        month_prices = monthly_data[month_key]
        month_input = build_month_input(month_key, template, month_prices, stock_data, split_base_dir)
        out_path = os.path.join(output_dir, f"user_input_{normalize_month(month_key)}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(month_input, f, ensure_ascii=False, indent=2)
        output_paths.append(out_path)
        print(f"Generated input file: {out_path}")

if __name__ == "__main__":
    monthly_data = {}
    stock_data = {}
    
    # 仅生成：1) 月度拆分文件；2) 日期->存煤量映射
    try:
        monthly_data = extract_monthly_coal_data(input_folder, coal_types)
        save_monthly_split(monthly_data, monthly_split_dir)
    except Exception as e:
        print("按月聚合失败，可忽略：", e)

    # 3) 新增：日期->存煤量映射
    try:
        stock_data = extract_stock_data(input_folder)
        save_as_json(stock_data, stock_output_file)
        print("处理完成，已生成存煤量 JSON 文件:", stock_output_file)
    except Exception as e:
        print("存煤量提取失败，可忽略：", e)
        
    # 4) 将生成 user inputs 的逻辑整合到这里
    try:
        if monthly_data:
            print("\n开始生成各月度用户采购决策输入 JSON(user_input_YYYYMM.json)...")
            generate_all_inputs(monthly_data, stock_data, TEMPLATE_FILE, INPUT_MONTHLY_DIR, monthly_split_dir)
            print(f"处理完成，已生成所有月度输入到: {INPUT_MONTHLY_DIR}")
    except Exception as e:
        print("生成月度输入 JSON 失败：", e)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     