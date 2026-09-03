# -*- coding: utf-8 -*-
import sys
import os

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

from chat_entry import chat_with_tools

def test_procurement_plan():
    # The specific input string provided
    # 使用 price_file 加载价格，并配置煤种参数   "sulfur_pct": 0.8，1.2，1.0，0.9，1.0
    with open("input/user_input.json", "r", encoding="utf-8") as f:
        user_input = f.read()

    print("=== Starting Test: Procurement Plan Generation ===")
    print(f"Input length: {len(user_input)} characters")
    
    try:
        # Call the main chat function
        response = chat_with_tools(user_input)
        
        print("\n=== Test Complete. Response: ===")
        print(response)
    except Exception as e:
        print(f"\n!!! Test Failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_procurement_plan()
