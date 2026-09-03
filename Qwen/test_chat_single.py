# -*- coding: utf-8 -*-
import sys
import os

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

from chat_entry import chat_with_tools
from tools2 import run_inventory_strategy, run_emergency_strategy, execute_tool

def test_emergency_strategy():
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
    # The specific input string provided
    # 使用 price_file 加载价格，并配置煤种参数   "sulfur_pct": 0.8，1.2，1.0，0.9，1.0
    with open(input_file, "r", encoding="utf-8") as f:
        user_input = f.read()

    print("=== Starting Test: Procurement Plan Generation (User Input) ===")
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

def test_emergency_procurement_plan():
    print("\n=== Starting Test: Emergency Procurement Plan Generation ===")
    import json
    with open("input/user_input.json", "r", encoding="utf-8") as f:
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
        if input_file:
             # 从输入文件名中提取电厂名称
            print("修改文件名")
            if "邵武" in input_file:
                output_file = "../autoinfer/html1/procure_plan/shaowu_procurement_plan.json"
            elif "可门" in input_file:
                output_file = "../autoinfer/html1/procure_plan/kemen_procurement_plan.json"
            elif "永安" in input_file:
                output_file = "../autoinfer/html1/procure_plan/yongan_procurement_plan.json"
            elif "漳平" in input_file:
                output_file = "../autoinfer/html1/procure_plan/zhangping_procurement_plan.json"
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                plan = json.load(f)
                print("JSON is_emergency:", plan.get("is_emergency"))
    except Exception as e:
        print(f"\n!!! Test Failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # test_emergency_strategy()
    # 电厂名称映射
    plant_map = {
        "kemen": "input/user_input_可门.json",
        "shaowu": "input/user_input_邵武.json",
        "yongan": "input/user_input_永安.json",
        "zhangping": "input/user_input_漳平.json"
    }
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
    test_procurement_plan(input_file)
    # test_emergency_procurement_plan()