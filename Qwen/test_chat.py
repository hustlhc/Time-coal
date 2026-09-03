# -*- coding: utf-8 -*-
import sys
import os
import json
from pathlib import Path

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

try:
    # chat_entry 会依赖 transformers/torch 等大模型相关包
    from chat_entry import chat_with_tools
except ModuleNotFoundError as e:
    chat_with_tools = None
    print("\n[ERROR] 无法导入 chat_entry 相关依赖：", repr(e))
    print("你现在很可能在 (base) 环境运行，缺少 transformers 等依赖。\n")
    print("解决方法（任选其一）：")
    print("1) 使用项目环境运行（推荐）：")
    print("   /opt/anaconda3/bin/conda run -p /home/czx/.conda/envs/torch221_cpu --no-capture-output python test_chat.py")
    print("2) 或者在当前环境安装依赖：")
    print("   python -m pip install -r requirements.txt")
try:
    from tools2 import run_inventory_strategy, run_emergency_strategy, execute_tool, ACCURACY_STATE_FILE
except ModuleNotFoundError as e:
    run_inventory_strategy = None
    run_emergency_strategy = None
    execute_tool = None
    ACCURACY_STATE_FILE = "state/accuracy_state.json"
    print("\n[ERROR] 无法导入 tools2 相关依赖：", repr(e))
    print("这通常是当前 Python 环境缺少 pulp/numpy 等包。\n")
    print("解决方法（任选其一）：")
    print("1) 使用项目环境运行（推荐）：")
    print("   /opt/anaconda3/bin/conda run -p /home/czx/.conda/envs/torch221_cpu --no-capture-output python test_chat.py")
    print("2) 或者在当前环境安装依赖：")
    print("   python -m pip install -r requirements.txt")


def test_dynamic_accuracy_persistence():
    """回归测试：accuracy_t 能按公式跨调用滚动更新并持久化。"""
    if run_inventory_strategy is None:
        raise RuntimeError("工具函数未能导入：请先切换到正确环境或安装依赖（见启动提示）。")
    print("\n=== Starting Test: Dynamic Accuracy Persistence ===")

    # reset state
    Path(ACCURACY_STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    if os.path.exists(ACCURACY_STATE_FILE):
        os.remove(ACCURACY_STATE_FILE)

    coal_infos = [
        {
            "forecast_prices": [742] * 20,
            "current_price": 740,
            "sulfur_pct": 0.8,
            "heat_value": 5500,
        }
    ]

    decay = 0.7
    args = {
        "coal_infos": coal_infos,
        "prev_acc": 0.8,  # 第一次会用这个，第二次会被 state 覆盖
        "real_acc": 0.85,
        "lambda_base": 0.5,
        "cv_t": 0.06,
        "beta1": 0.6,
        "beta2": 0.4,
        "decay": decay,
        "base_demand": 60,
        "max_stock": 120,
        "prev_stock": 20,
        "extra_factor": 0.05,
        "weekly_accuracy": [0.75, 0.8, 0.78, 0.77],
        "target_heat": 5000,
        "min_ship_qty": 5,
        "use_dynamic_accuracy": True,
    }

    # 1st call
    res1 = run_inventory_strategy(**args)
    acc1 = float(res1["step2"]["accuracy_t"])
    with open(ACCURACY_STATE_FILE, "r", encoding="utf-8") as f:
        state1 = json.load(f)
    saved1 = float(state1["prev_acc"])
    assert abs(acc1 - saved1) < 1e-9, "First call should persist accuracy_t to state"

    # 2nd call: change real_acc and verify rolling update uses saved1
    real_acc2 = 0.65
    args["real_acc"] = real_acc2
    res2 = run_inventory_strategy(**args)
    acc2 = float(res2["step2"]["accuracy_t"])
    expected2 = decay * saved1 + (1.0 - decay) * real_acc2

    assert abs(acc2 - expected2) < 1e-9, (
        f"Second call accuracy_t mismatch: got {acc2}, expected {expected2}"
    )
    with open(ACCURACY_STATE_FILE, "r", encoding="utf-8") as f:
        state2 = json.load(f)
    saved2 = float(state2["prev_acc"])
    assert abs(acc2 - saved2) < 1e-9, "Second call should persist accuracy_t to state"

    print(f"State file: {ACCURACY_STATE_FILE}")
    print(f"acc1={acc1:.6f} saved1={saved1:.6f}")
    print(f"acc2={acc2:.6f} expected2={expected2:.6f} saved2={saved2:.6f}")
    print("=== Dynamic Accuracy Persistence Test Complete ===\n")

def test_emergency_strategy():
    if run_inventory_strategy is None or run_emergency_strategy is None:
        raise RuntimeError("工具函数未能导入：请先切换到正确环境或安装依赖（见启动提示）。")
    print("\n=== Starting Test: Emergency Strategy ===")
    coal_infos = [
        {
            "forecast_prices": [742]*20,
            "current_price": 740,
            "sulfur_pct": 0.8,
            "heat_value": 5500
        }
    ]

    args = {
        "coal_infos": coal_infos,
        "prev_acc": 0.8,
        "real_acc": 0.85,
        "lambda_base": 0.5,
        "cv_t": 0.06,
        "beta1": 0.6,
        "beta2": 0.4,
        "decay": 0.7,
        "base_demand": 60, # daily_use = 2.0
        "max_stock": 120,
        "prev_stock": 10, # < 16 -> Emergency
        "extra_factor": 0.05,
        "weekly_accuracy": [0.75, 0.8, 0.78, 0.77],
        "target_heat": 5000,
        "min_ship_qty": 5
    }

    print("--- Test 1: run_inventory_strategy (Emergency) ---")
    res = run_inventory_strategy(**args)
    print("Emergency Triggered:", res["step3"]["components"].get("note") == "Emergency Strategy Triggered")
    print("Monthly Qty:", res["step3"]["monthly_qty"])

    print("\n--- Test 2: run_emergency_strategy (Direct Call) ---")
    emer_args = {
        "prev_stock": 10,
        "base_demand": 60,
        "min_ship_qty": 5,
        "max_stock": 120
    }
    res_emer = run_emergency_strategy(**emer_args)
    print("Is Emergency:", res_emer["is_emergency"])
    print("Monthly Qty:", res_emer["monthly_qty"])

    print("\n--- Test 3: execute_tool (run_emergency_strategy) - SKIPPED (Internal Only) ---")
    # res_tool = execute_tool("run_emergency_strategy", emer_args)
    # print("Is Emergency:", res_tool["is_emergency"])

    print("\n--- Test 4: Normal Case ---")
    args["prev_stock"] = 20
    res_norm = run_inventory_strategy(**args)
    print("Emergency Triggered:", res_norm["step3"]["components"].get("note") == "Emergency Strategy Triggered")
    print("=== Emergency Strategy Test Complete ===\n")

def test_procurement_plan(input_file):
    if chat_with_tools is None:
        raise RuntimeError(
            "chat_with_tools 未能导入：请先按启动提示切换到正确的 Python 环境或安装依赖。"
        )
    # The specific input string provided
    # 使用 price_file 加载价格，并配置煤种参数   "sulfur_pct": 0.8，1.2，1.0，0.9，1.0
    with open(input_file, "r", encoding="utf-8") as f:
        user_input = f.read()

    print(f"=== Starting Test: Procurement Plan Generation (User Input) ===")
    print(f"Using input file: {input_file}")
    print(f"Input length: {len(user_input)} characters")
    
    try:
        # Call the main chat function
        response = chat_with_tools(user_input,None,input_file)
        
        print("\n=== Test Complete. Response: ===")
        print(response)
    except Exception as e:
        print(f"\n!!! Test Failed with error: {e}")
        import traceback
        traceback.print_exc()

def test_emergency_procurement_plan(input_file):
    if chat_with_tools is None:
        raise RuntimeError(
            "chat_with_tools 未能导入：请先按启动提示切换到正确的 Python 环境或安装依赖。"
        )
    print(f"\n=== Starting Test: Emergency Procurement Plan Generation ===")
    print(f"Using input file: {input_file}")
    import json
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Modify to trigger emergency
    # daily_use = 905483 / 30 = 30182
    # safety_stock = 8 * 30182 = 241456
    data["prev_stock"] = 1000 
    user_input = json.dumps(data, ensure_ascii=False)
    
    try:
        response = chat_with_tools(user_input,None,input_file)
        print("\n=== Emergency Test Complete. Response: ===")
        print(response)
        
        # Check generated JSON
        if os.path.exists("procure_plan/procurement_plan.json"):
            with open("procure_plan/procurement_plan.json", "r") as f:
                plan = json.load(f)
                print("JSON is_emergency:", plan.get("is_emergency"))
    except Exception as e:
        print(f"\n!!! Test Failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 解析命令行参数
    import sys
    
    # 电厂名称映射
    plant_map = {
        "kemen": "input/user_input_可门.json",
        "shaowu": "input/user_input_邵武.json",
        "yongan": "input/user_input_永安.json",
        "zhangping": "input/user_input_漳平.json"
    }
    
    # 默认使用可门的输入文件
    #input_file = plant_map["kemen"]
    input_file='input/monthly/user_input_202501.json'
    
    # 处理命令行参数
    if len(sys.argv) > 1:
        plant_name = sys.argv[1]
        if plant_name in plant_map:
            input_file = plant_map[plant_name]
        else:
            # 尝试匹配电厂名称的部分
            for key in plant_map:
                if plant_name in key:
                    input_file = plant_map[key]
                    break
            else:
                print(f"警告：未找到对应的电厂名称 '{plant_name}'，使用默认的可门输入文件")
    
    print(f"使用输入文件: {input_file}")
    
    # test_emergency_strategy()
    test_procurement_plan(input_file)
    # test_emergency_procurement_plan(input_file)

    # 需要时再跑：避免默认流程加载大模型时被打断
    # RUN_DYNAMIC_ACC_TEST=1 python test_chat.py
    if os.environ.get("RUN_DYNAMIC_ACC_TEST") == "1":
        test_dynamic_accuracy_persistence()
