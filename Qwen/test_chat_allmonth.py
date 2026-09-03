# -*- coding: utf-8 -*-
import sys
import os
import glob
import re
import shutil
import json

# Ensure we can import from the current directory
sys.path.append(os.getcwd())

from chat_entry import chat_with_tools
from tools2 import (
    run_inventory_strategy,
    run_emergency_strategy,
    execute_tool,
    compute_drop_rise_probs,
    compute_accuracy_and_lambda,
)

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

def run_one(input_path: str, user_data: dict | None = None):
    """Load a user_input JSON and invoke chat_with_tools.

    If user_data is provided, it will be serialized and used instead of reading input_path.
    """
    if user_data is None:
        with open(input_path, "r", encoding="utf-8") as f:
            user_input = f.read()
    else:
        user_input = json.dumps(user_data, ensure_ascii=False)

    print("=== Starting Procurement Plan Generation ===")
    print(f"Input file: {input_path}  length: {len(user_input)} characters")

    response = chat_with_tools(user_input)
    print("\n=== Generation Complete. Response: ===")
    print(response)
    return response

def test_emergency_procurement_plan():
    print("\n=== Starting Test: Emergency Procurement Plan Generation ===")
    import json
    with open("input/monthly/user_input_202401.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Modify to trigger emergency
    # daily_use = 905483 / 30 = 30182
    # safety_stock = 8 * 30182 = 241456
    data["prev_stock"] = 1000 
    user_input = json.dumps(data, ensure_ascii=False)
    
    try:
        response = chat_with_tools(user_input)
        print("\n=== Emergency Test Complete. Response: ===")
        print(response)
        
        # Check generated JSON
        if os.path.exists("procure_plan/procurement_plan_202401.json"):
            with open("procure_plan/procurement_plan_202401.json", "r") as f:
                plan = json.load(f)
                print("JSON is_emergency:", plan.get("is_emergency"))
    except Exception as e:
        print(f"\n!!! Test Failed with error: {e}")
        import traceback
        traceback.print_exc()


def _extract_month_from_filename(path: str) -> str:
    """Return YYYYMM from a user_input filename when possible."""
    basename = os.path.basename(path)
    match = re.search(r"(20\d{4})", basename)
    return match.group(1) if match else ""


def run_all_monthly(
    input_dir: str = "input/monthly",
    output_dir: str = "procure_plan",
    enable_dynamic_ef: bool = False,
):
    """Traverse monthly inputs and save each month's procurement plan.

    When enable_dynamic_ef=True, this function will:
    - inject `use_dynamic_extra_factor=True` into each month's input JSON
    - inject rolling `p_down_history` and `accuracy_history`
    so the continuous-downtrend EF can work across months.
    """
    pattern = os.path.join(input_dir, "*.json")
    input_files = sorted(glob.glob(pattern))

    if not input_files:
        print(f"No monthly input files found under {input_dir}")
        return

    os.makedirs(output_dir, exist_ok=True)

    # Rolling histories for dynamic EF
    p_down_history: list[float] = []
    accuracy_history: list[float] = []

    for input_path in input_files:
        month_tag = _extract_month_from_filename(input_path)
        print("\n============================================")
        print(f"Processing monthly input: {input_path}")

        # Load JSON so we can optionally inject dynamic EF fields
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                user_data = json.load(f)
        except Exception as e:
            print(f"Failed to read monthly input JSON {input_path}: {e}")
            import traceback
            traceback.print_exc()
            continue

        if enable_dynamic_ef:
            user_data["use_dynamic_extra_factor"] = True
            # histories are previous months only; tools2 will append current month automatically if needed
            user_data["p_down_history"] = list(p_down_history)
            user_data["accuracy_history"] = list(accuracy_history)

        try:
            run_one(input_path, user_data=user_data)
        except Exception as e:
            print(f"Failed to run procurement generation for {input_path}: {e}")
            import traceback
            traceback.print_exc()
            continue

        src_plan = os.path.join(output_dir, "procurement_plan.json")
        if not os.path.exists(src_plan):
            print("procurement_plan.json not found; skipping copy for this month.")
            continue

        suffix = month_tag if month_tag else os.path.splitext(os.path.basename(input_path))[0]
        dest_plan = os.path.join(output_dir, f"procurement_plan_{suffix}.json")

        try:
            shutil.copyfile(src_plan, dest_plan)
            print(f"Saved monthly procurement plan to {dest_plan}")
        except Exception as copy_err:
            print(f"Failed to copy plan to {dest_plan}: {copy_err}")

        # Update rolling histories for the NEXT month.
        if enable_dynamic_ef:
            try:
                coal_infos = user_data.get("coal_infos")
                if not isinstance(coal_infos, list) or not coal_infos:
                    raise ValueError("coal_infos missing or invalid")

                # Keep aligned with tools2.run_inventory_strategy defaults
                threshold_pct = float(user_data.get("threshold_pct", 0.05))
                weeks = int(user_data.get("weeks", 4))

                s1 = compute_drop_rise_probs(coal_infos=coal_infos, threshold_pct=threshold_pct, weeks=weeks)
                p_down_history.append(float(s1.get("monthly_drop_prob", 0.0)))

                s2 = compute_accuracy_and_lambda(
                    prev_acc=float(user_data.get("prev_acc", 0.0)),
                    real_acc=float(user_data.get("real_acc", 0.0)),
                    cv_t=float(user_data.get("cv_t", 0.0)),
                    lambda_base=float(user_data.get("lambda_base", 0.5)),
                    beta1=float(user_data.get("beta1", 0.6)),
                    beta2=float(user_data.get("beta2", 0.4)),
                    decay=float(user_data.get("decay", 0.7)),
                )
                accuracy_history.append(float(s2.get("accuracy_t", 0.0)))

                print(
                    f"[dynamic-ef] history updated: months={len(p_down_history)} "
                    f"last_p_down={p_down_history[-1]:.4f} last_acc={accuracy_history[-1]:.4f}"
                )
            except Exception as hist_err:
                print(f"[dynamic-ef] failed to update history from {input_path}: {hist_err}")

if __name__ == "__main__":
    # test_emergency_strategy()
    # test_emergency_procurement_plan()
    target = sys.argv[1] if len(sys.argv) > 1 else None

    enable_dynamic_ef = "--dynamic-ef" in sys.argv

    if target in (None, "all", "--all"):
        run_all_monthly(enable_dynamic_ef=enable_dynamic_ef)
    else:
        try:
            # Single-file run: dynamic EF can be enabled but has no historical months unless the JSON contains histories.
            run_one(target)
        except Exception as e:
            print(f"Failed to run procurement generation for {target}: {e}")
            import traceback
            traceback.print_exc()
