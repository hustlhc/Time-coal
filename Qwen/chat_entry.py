# chat_entry.py
# -*- coding: utf-8 -*-
"""
本地大模型 + 工具链 统一入口
用法：
    python chat_entry.py
"""
import json
import ast
import re
import os
import time
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch


# ========= 1. 导入你的工具 =========
from tools2 import tools, execute_tool  # 同目录 tools.py

# ========= 2. 模型配置 =========
MODEL_PATH = os.environ.get("/home/coal/Qwen3.5-9B", os.path.dirname(__file__))  # 默认使用仓库目录或通过环境变量覆盖
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# DEVICE = "cpu"  # 强制 CPU 测试

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True
).eval()

# ========= 3. 工具提示模板 =========
def build_system_prompt() -> str:
    """
    读取本地 prompt1.txt，把 <<TOOLS>> 替换成 tools 的 JSON。
    如果文件不存在就使用默认模板。
    """
    tools_json = json.dumps(tools, ensure_ascii=False, indent=2)
    try:
        with open("prompt1.txt", "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        template = (
            "你是一个具备工具调用能力的大模型。\n"
            "如果需要使用工具，请只输出如下 JSON（不要多余内容）：\n"
            '{ "tool": "工具名称", "args": { ... } }\n'
            "如果不需要工具，就直接回答。\n\n"
            "可用工具列表（JSON）：\n<<TOOLS>>"
        )
    return template.replace("<<TOOLS>>", tools_json)


# ========= 3.1 综合模型准确率（accuracy_t）状态持久化 =========
# 目的：把上一轮计算得到的 accuracy_t 存下来，下一轮作为 prev_acc 参与更新。
ACCURACY_STATE_FILE = os.environ.get(
    "ACCURACY_STATE_FILE",
    os.path.join(os.path.dirname(__file__), "state", "accuracy_state.json")
)


def _load_accuracy_state() -> Dict[str, Any]:
    try:
        if not os.path.exists(ACCURACY_STATE_FILE):
            return {}
        with open(ACCURACY_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"WARNING: 读取 accuracy 状态失败，将忽略并使用输入 prev_acc。原因: {e}")
        return {}


def _save_accuracy_state(prev_acc: float, meta: Optional[Dict[str, Any]] = None) -> None:
    try:
        os.makedirs(os.path.dirname(ACCURACY_STATE_FILE), exist_ok=True)
        payload: Dict[str, Any] = {
            "prev_acc": float(prev_acc),
            "updated_at": int(time.time()),
        }
        if isinstance(meta, dict):
            payload.update(meta)
        with open(ACCURACY_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"WARNING: 写入 accuracy 状态失败（不影响本次结果）。原因: {e}")


# ========= 推理封装 =========
@torch.inference_mode()
def ask_llm(messages: List[Dict[str, str]],
            max_new_tokens: int = 2048,
            temperature: float = 0.5) -> str:
    prompt_lines = []
    for m in messages:
        prompt_lines.append(f"<|im_start|>{m['role']}\n{m['content']}\n<|im_end|>")
    prompt_lines.append("<|im_start|>assistant\n")
    prompt = "\n".join(prompt_lines)

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        do_sample=True,
        repetition_penalty=1.1,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id
    )
    gen_tokens = outputs[0][inputs.input_ids.shape[-1]:]
    return tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()

# ========= JSON 提取器 =========
def _extract_json_object(text: str) -> Dict[str, Any]:
    """从模型回复里提取 JSON（容错）"""
    # 0. 预处理：替换中文标点
    text = text.replace("，", ",").replace("：", ":").replace("“", '"').replace("”", '"')
    # 去掉常见 markdown 代码块包裹
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()
    # 去掉 JSON5 风格行注释，避免 json.loads 失败
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    
    try:
        return json.loads(text)
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        snippet = text[start:end+1]
        try:
            return json.loads(snippet)
        except Exception:
            try:
                return ast.literal_eval(snippet)
            except Exception:
                pass
    # 单引号暴力替换
    fixed = re.sub(r"'([^']*?)'", lambda m: f'"{m.group(1)}"', text)
    try:
        return json.loads(fixed)
    except Exception:
        raise ValueError(f"解析 JSON 失败: {text}")


def _parse_decision_date(decision_date_raw):
    """Parse flexible decision_date values like 2024/1/1, 2024-01-01, or 含中文分隔."""
    if not decision_date_raw:
        return None

    s = str(decision_date_raw).strip()
    if not s:
        return None

    normalized = (
        s.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
        .replace(".", "-")
    )

    parts = [p for p in re.split(r"[^0-9]+", normalized) if p]
    if len(parts) >= 3:
        y, m, d = parts[:3]
        try:
            return datetime(int(y), int(m), int(d))
        except Exception:
            pass

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m"):
        try:
            return datetime.strptime(normalized, fmt)
        except Exception:
            continue

    try:
        return datetime.fromisoformat(normalized)
    except Exception:
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _resolve_legacy_procure_plan_path(
    input_file: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
) -> str:
    """Keep chat_entry.py's original procurement-plan output convention."""
    default_path = "../autoinfer/html1/procure_plan/kemen_procurement_plan.json"
    tokens: List[str] = []
    if input_file:
        tokens.append(str(input_file))
    if isinstance(args, dict):
        for key in (
            "plant_name",
            "power_plant",
            "plant",
            "station",
            "factory",
            "power_station",
            "input_file",
            "input_path",
            "inputFile",
        ):
            if args.get(key):
                tokens.append(str(args.get(key)))

    text = " ".join(tokens)
    text_lower = text.lower()
    mapping = (
        ("邵武", "shaowu"),
        ("可门", "kemen"),
        ("永安", "yongan"),
        ("漳平", "zhangping"),
        ("shaowu", "shaowu"),
        ("kemen", "kemen"),
        ("yongan", "yongan"),
        ("zhangping", "zhangping"),
    )
    for token, slug in mapping:
        if token in text or token in text_lower:
            return f"../autoinfer/html1/procure_plan/{slug}_procurement_plan.json"
    return default_path


def _build_analysis_prompt(strategy_indicators: str) -> str:
    try:
        with open("prompt_analysis.txt", "r", encoding="utf-8") as f:
            template = f.read()
    except Exception:
        return ""
    return template.replace("{strategy_indicators}", strategy_indicators)


def _slice_series(values: List[float], start: int, length: int) -> List[float]:
    if length <= 0:
        return []
    if not values:
        return [0.0] * length
    sliced = list(values[start:start + length])
    if not sliced:
        sliced = [values[-1]]
    if len(sliced) < length:
        sliced.extend([sliced[-1]] * (length - len(sliced)))
    return sliced


def _slice_coal_infos(coal_infos: List[Dict[str, Any]], start: int, length: int) -> List[Dict[str, Any]]:
    sliced_infos: List[Dict[str, Any]] = []
    for info in coal_infos:
        if not isinstance(info, dict):
            continue
        prices = info.get("forecast_prices", [])
        freights = info.get("forecast_freight", [])
        sliced_prices = _slice_series(prices, start, length) if isinstance(prices, list) else []
        sliced_freights = _slice_series(freights, start, length) if isinstance(freights, list) else []
        new_info = dict(info)
        new_info["forecast_prices"] = sliced_prices
        if sliced_freights:
            new_info["forecast_freight"] = sliced_freights
        if sliced_prices:
            new_info["current_price"] = _safe_float(new_info.get("current_price"), sliced_prices[0])
        sliced_infos.append(new_info)
    return sliced_infos


def _add_trading_days(base_date: Optional[datetime], offset: int) -> Optional[datetime]:
    if base_date is None:
        return None
    if offset <= 0:
        return base_date
    current = base_date
    added = 0
    while added < offset:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current


def _build_month_plan_output(
    args: Dict[str, Any],
    tool_result: Dict[str, Any],
    decision_date: Optional[datetime],
    month_index: int,
    day_offset: int,
    month_days: int,
) -> Dict[str, Any]:
    s3 = tool_result.get("step3", {}) if isinstance(tool_result, dict) else {}
    s4 = tool_result.get("step4", {}) if isinstance(tool_result, dict) else {}
    s5 = tool_result.get("step5", {}) if isinstance(tool_result, dict) else {}

    monthly_total = _safe_float(s3.get("monthly_qty", 0.0))
    week_qtys = s4.get("week_qty", []) if isinstance(s4.get("week_qty", []), list) else []
    purchase_days = s5.get("purchase_days_by_week", []) if isinstance(s5.get("purchase_days_by_week", []), list) else []
    blend_plans = s5.get("blend_plan", []) if isinstance(s5.get("blend_plan", []), list) else []
    latest_delivery_days = s5.get("latest_delivery_days", []) if isinstance(s5.get("latest_delivery_days", []), list) else []
    while len(latest_delivery_days) < len(week_qtys):
        latest_delivery_days.append([])

    decision_date_str = decision_date.strftime("%Y-%m-%d") if decision_date else "未指定"
    is_emergency = s3.get("components", {}).get("note", "") == "Emergency Strategy Triggered"

    coal_names: List[str] = []
    if isinstance(args.get("coal_infos"), list):
        for info in args["coal_infos"]:
            coal_names.append(info.get("name", "未知煤种") if isinstance(info, dict) else "未知煤种")

    name_mapping = {
        "CCI4500": "北方港4500",
        "CCI5000": "北方港5000",
        "CCI5500": "北方港5500",
        "CCI进口3800": "进口3800",
        "CCI进口4700": "进口4700",
        "CCI进口5500": "进口5500",
    }

    output_lines = [
        f"=== 月度计划 M{month_index} ===",
        f"决策日：{decision_date_str}",
        "【警告】触发紧急库存策略，优先满足近期需求。" if is_emergency else "【正常】库存策略执行中。",
        f"{month_days}天总采购量：{monthly_total:.2f} 吨",
        f"未来{month_days}天采购计划：",
    ]

    global_date_groups: Dict[str, List[str]] = {}
    global_json_items_by_date: Dict[str, List[Dict[str, Any]]] = {}

    for w_idx, (qty, days, blend, ldd_list) in enumerate(zip(week_qtys, purchase_days, blend_plans, latest_delivery_days)):
        if _safe_float(qty) <= 1e-6 or not isinstance(blend, list):
            continue
        for c_idx, b_val_raw in enumerate(blend):
            b_val = _safe_float(b_val_raw)
            if b_val <= 1e-6:
                continue
            c_name = coal_names[c_idx] if c_idx < len(coal_names) else f"煤种{c_idx + 1}"
            c_name = name_mapping.get(c_name, c_name)
            d_idx = days[c_idx] if isinstance(days, list) and c_idx < len(days) else None

            if isinstance(d_idx, (int, float)):
                d_int = int(d_idx)
                day_abs = day_offset + d_int
                coal_date = _add_trading_days(decision_date, d_int)
                coal_date_display = coal_date.strftime("%Y/%m/%d") if coal_date else f"第{day_abs}天"
            else:
                d_int = None
                day_abs = None
                coal_date_display = "未知"

            price_val = 0.0
            freight_val = 0.0
            if d_int is not None and isinstance(args.get("coal_infos"), list) and c_idx < len(args["coal_infos"]):
                c_info = args["coal_infos"][c_idx]
                prices = c_info.get("forecast_prices", []) if isinstance(c_info, dict) else []
                freights = c_info.get("forecast_freight", []) if isinstance(c_info, dict) else []
                if isinstance(prices, list) and 0 <= d_int < len(prices):
                    price_val = _safe_float(prices[d_int])
                if isinstance(freights, list) and 0 <= d_int < len(freights):
                    freight_val = _safe_float(freights[d_int])
            delivered_cost = price_val + freight_val

            ldd_display = "0"
            if isinstance(ldd_list, list) and c_idx < len(ldd_list):
                ldd_val = _safe_float(ldd_list[c_idx])
                if abs(ldd_val) > 1e-6:
                    ldd_date = _add_trading_days(decision_date, int(ldd_val))
                    ldd_display = ldd_date.strftime("%Y/%m/%d") if ldd_date else f"{ldd_val:.1f}"

            if coal_date_display not in global_date_groups:
                global_date_groups[coal_date_display] = []
                global_json_items_by_date[coal_date_display] = []

            global_date_groups[coal_date_display].append(
                f"{c_name} {b_val:.2f}吨 到厂单价{delivered_cost:.2f}(煤价{price_val:.2f}+运费{freight_val:.2f}) LDD:{ldd_display}"
            )
            global_json_items_by_date[coal_date_display].append(
                {
                    "month_index": month_index,
                    "cycle": w_idx + 1,
                    "global_day_index": day_abs,
                    "coal_name": c_name,
                    "quantity": round(b_val, 2),
                    "price": round(delivered_cost, 2),
                    "coal_price": round(price_val, 2),
                    "freight": round(freight_val, 2),
                    "delivered_unit_cost": round(delivered_cost, 2),
                    "latest_delivery_date": ldd_display,
                }
            )

    json_plan_list: List[Dict[str, Any]] = []
    for date_key in sorted(global_date_groups.keys()):
        day_total = sum(item["quantity"] for item in global_json_items_by_date[date_key])
        output_lines.append(f"- 采购日 {date_key} (共计 {day_total:.2f}吨)：{'；'.join(global_date_groups[date_key])}")
        json_plan_list.append(
            {
                "date": date_key,
                "total_quantity": round(day_total, 2),
                "items": global_json_items_by_date[date_key],
            }
        )

    return {
        "output_text": "\n".join(output_lines),
        "json_plan_list": json_plan_list,
        "monthly_total": monthly_total,
        "is_emergency": is_emergency,
        "decision_date_str": decision_date_str,
    }


def _build_detailed_analysis_from_tool(
    tool_result: Dict[str, Any],
    args: Dict[str, Any],
    decision_date_str: str,
    time_window: str,
) -> str:
    """Build a deterministic analysis when the LLM answer is empty or too thin."""
    if not isinstance(tool_result, dict):
        return ""

    s1 = tool_result.get("step1", {}) if isinstance(tool_result.get("step1"), dict) else {}
    s3 = tool_result.get("step3", {}) if isinstance(tool_result.get("step3"), dict) else {}
    s5 = tool_result.get("step5", {}) if isinstance(tool_result.get("step5"), dict) else {}
    comp = s3.get("components", {}) if isinstance(s3.get("components"), dict) else {}

    monthly_qty = _safe_float(s3.get("monthly_qty", 0.0))
    monthly_drop = _safe_float(s1.get("monthly_drop_prob", 0.0))
    monthly_rise = _safe_float(s1.get("monthly_rise_prob", 0.0))
    prev_stock = _safe_float(args.get("prev_stock", 0.0))
    base_demand = _safe_float(args.get("base_demand", 0.0))
    daily_use = base_demand / 30.0 if base_demand > 0 else 0.0
    cover_days = prev_stock / daily_use if daily_use > 0 else 0.0
    min_stock_level = _safe_float(comp.get("min_stock_level", 0.0))
    is_emergency = comp.get("note") == "Emergency Strategy Triggered"

    coal_infos = args.get("coal_infos", []) if isinstance(args.get("coal_infos"), list) else []
    blend_plan = s5.get("blend_plan", []) if isinstance(s5.get("blend_plan"), list) else []
    purchase_days = s5.get("purchase_days_by_week", []) if isinstance(s5.get("purchase_days_by_week"), list) else []
    total_by_coal = [0.0] * len(coal_infos)
    cost_samples: List[List[float]] = [[] for _ in coal_infos]

    for w_idx, week_blend in enumerate(blend_plan):
        if not isinstance(week_blend, list):
            continue
        days_row = purchase_days[w_idx] if w_idx < len(purchase_days) and isinstance(purchase_days[w_idx], list) else []
        for i in range(min(len(coal_infos), len(week_blend))):
            qty = _safe_float(week_blend[i])
            total_by_coal[i] += qty
            day_idx = days_row[i] if i < len(days_row) and isinstance(days_row[i], (int, float)) else None
            if day_idx is None:
                continue
            info = coal_infos[i] if isinstance(coal_infos[i], dict) else {}
            prices = info.get("forecast_prices", []) if isinstance(info.get("forecast_prices"), list) else []
            freights = info.get("forecast_freight", []) if isinstance(info.get("forecast_freight"), list) else []
            idx = int(day_idx)
            price = _safe_float(prices[idx]) if 0 <= idx < len(prices) else 0.0
            freight = _safe_float(freights[idx]) if 0 <= idx < len(freights) else 0.0
            if qty > 1e-6:
                cost_samples[i].append(price + freight)

    lines = [
        "一、总体采购策略总结",
        f"时间区间：{time_window}；决策日：{decision_date_str if decision_date_str else '未指定'}。",
        f"本期建议总采购量为 {monthly_qty:.2f} 吨。价格信号方面，月度下跌概率为 {monthly_drop:.4f}，月度上涨概率为 {monthly_rise:.4f}，策略需要在库存安全和价格窗口之间做平衡。",
        f"库存侧当前库存为 {prev_stock:.2f} 吨，预计月需求为 {base_demand:.2f} 吨，折算覆盖天数约 {cover_days:.2f} 天；策略安全库存参考值为 {min_stock_level:.2f} 吨。",
    ]
    if is_emergency:
        lines.append("当前触发紧急库存策略，因此采购优先级应先保证安全库存和到货连续性，再考虑价格择时。")
    else:
        lines.append("当前未触发紧急库存策略，采购节奏可以更偏向分批执行，在价格低点附近补库。")

    lines.append("二、按煤种的采购原因说明")
    for i, info in enumerate(coal_infos):
        if not isinstance(info, dict):
            continue
        name = str(info.get("name", f"煤种{i + 1}"))
        qty = total_by_coal[i] if i < len(total_by_coal) else 0.0
        share = qty / monthly_qty if monthly_qty > 1e-6 else 0.0
        avg_cost = sum(cost_samples[i]) / len(cost_samples[i]) if i < len(cost_samples) and cost_samples[i] else None
        sulfur = info.get("sulfur_pct", "未提供")
        heat = info.get("heat_value", "未提供")
        if qty > 1e-6:
            cost_text = f"预计到厂均价约 {avg_cost:.2f}" if avg_cost is not None else "到厂成本样本不足"
            lines.append(
                f"{i + 1}. {name}：本期配置 {qty:.2f} 吨，占总采购量 {share:.2%}。{cost_text}；"
                f"热值={heat}，硫分={sulfur}。该配置主要用于满足库存补充、煤质约束和单位热值成本优化。"
            )
        else:
            lines.append(
                f"{i + 1}. {name}：本期未安排采购。主要原因通常是库存、价格窗口、到厂成本或混煤约束下暂未形成优势，后续可随价格和库存变化重新评估。"
            )

    lines.append("三、核心驱动因素排序")
    if is_emergency:
        lines.append("库存安全约束 > 到货连续性 > 混煤煤质约束 > 单位热值成本 > 价格趋势信号。")
    elif monthly_drop >= monthly_rise:
        lines.append("价格下行窗口 > 单位热值成本 > 采购节奏控制 > 库存安全约束 > 混煤煤质约束。")
    else:
        lines.append("库存安全约束 > 价格上行风险 > 到货连续性 > 单位热值成本 > 混煤煤质约束。")
    return "\n".join(lines)


def _run_multi_month_plan(
    parsed_user_json: Dict[str, Any],
    month_count: int,
    input_file: Optional[str] = None,
) -> str:
    if not isinstance(parsed_user_json, dict) or month_count <= 0:
        return ""

    base_args = dict(parsed_user_json)
    coal_infos = base_args.get("coal_infos")
    if not isinstance(coal_infos, list) or not coal_infos:
        raise ValueError("multi-month 模式要求 coal_infos 为非空列表。")

    month_count = max(1, min(int(month_count), 3))
    base_date = _parse_decision_date(base_args.get("decision_date"))
    month_length_trading = 20
    month_length_calendar = 30
    rolling_stock = _safe_float(base_args.get("prev_stock", 0.0)) + _safe_float(base_args.get("historical_purchase", 0.0))
    base_demand_series = base_args.get("base_demand_series")
    use_demand_series = isinstance(base_demand_series, list) and len(base_demand_series) >= month_count

    merged_date_map: Dict[str, Dict[str, Any]] = {}
    month_outputs: List[str] = []
    month_entries: List[Dict[str, Any]] = []
    planned_arrivals: List[Dict[str, Any]] = []
    total_purchase = 0.0
    any_emergency = False

    for month_idx in range(month_count):
        day_offset = month_idx * month_length_trading
        month_date = _add_trading_days(base_date, day_offset)
        month_args = dict(base_args)
        month_args["prev_stock"] = rolling_stock
        month_args["duration_days"] = month_length_calendar
        month_args["coal_infos"] = _slice_coal_infos(coal_infos, day_offset, month_length_trading)
        if use_demand_series:
            month_args["base_demand"] = _safe_float(base_demand_series[month_idx])
        if month_date:
            month_args["decision_date"] = month_date.strftime("%Y-%m-%d")

        tool_result = execute_tool("run_inventory_strategy", month_args)
        month_output = _build_month_plan_output(
            args=month_args,
            tool_result=tool_result,
            decision_date=month_date,
            month_index=month_idx + 1,
            day_offset=day_offset,
            month_days=month_length_calendar,
        )

        month_outputs.append(month_output["output_text"])
        total_purchase += _safe_float(month_output["monthly_total"])
        any_emergency = any_emergency or bool(month_output["is_emergency"])

        step5 = tool_result.get("step5", {}) if isinstance(tool_result, dict) else {}
        blend_plan = step5.get("blend_plan", []) if isinstance(step5.get("blend_plan"), list) else []
        latest_delivery_days = step5.get("latest_delivery_days", []) if isinstance(step5.get("latest_delivery_days"), list) else []
        for w_idx, week_blend in enumerate(blend_plan):
            if not isinstance(week_blend, list):
                continue
            ldd_row = latest_delivery_days[w_idx] if w_idx < len(latest_delivery_days) and isinstance(latest_delivery_days[w_idx], list) else []
            for c_idx, qty_raw in enumerate(week_blend):
                qty = _safe_float(qty_raw)
                if qty <= 1e-6:
                    continue
                if c_idx >= len(ldd_row):
                    continue
                ldd_val = _safe_float(ldd_row[c_idx], -1.0)
                if ldd_val < 0:
                    continue
                ldd_abs = day_offset + int(ldd_val)
                planned_arrivals.append(
                    {
                        "ldd_abs": float(ldd_abs),
                        "qty": qty,
                        "delivery_date": _add_trading_days(base_date, ldd_abs),
                    }
                )

        if base_date and month_date:
            window_start = month_date
            window_end = month_date + timedelta(days=month_length_calendar - 1)
            arrivals = sum(
                item["qty"]
                for item in planned_arrivals
                if isinstance(item.get("delivery_date"), datetime)
                and window_start <= item["delivery_date"] <= window_end
            )
        else:
            window_start_idx = day_offset
            window_end_idx = day_offset + month_length_trading - 1
            arrivals = sum(
                item["qty"]
                for item in planned_arrivals
                if window_start_idx <= item.get("ldd_abs", -1) <= window_end_idx
            )

        consumption = _safe_float(month_args.get("base_demand", 0.0))
        end_stock = rolling_stock + arrivals - consumption

        time_window = f"{month_output['decision_date_str']}起未来{month_length_calendar}天"
        analysis_text = ""
        analysis_prompt = _build_analysis_prompt(month_output["output_text"])
        if analysis_prompt:
            analysis_text = ask_llm([{"role": "system", "content": analysis_prompt}])
            analysis_text = re.sub(r"^```(?:json)?\s*", "", analysis_text.strip(), flags=re.IGNORECASE)
            analysis_text = re.sub(r"\s*```$", "", analysis_text).strip()
        if (not analysis_text) or len(analysis_text) < 220 or "无数据可提供" in analysis_text:
            fallback = _build_detailed_analysis_from_tool(
                tool_result=tool_result,
                args=month_args,
                decision_date_str=month_output["decision_date_str"],
                time_window=time_window,
            )
            if fallback:
                analysis_text = fallback

        month_entries.append(
            {
                "decision_date": month_output["decision_date_str"],
                "is_emergency": bool(month_output["is_emergency"]),
                "duration_days": month_length_calendar,
                "total_purchase_quantity": round(_safe_float(month_output["monthly_total"]), 2),
                "decision_analysis": analysis_text,
                "procurement_plan": month_output["json_plan_list"],
                "roll_forward": {
                    "month_index": month_idx + 1,
                    "start_stock": round(rolling_stock, 2),
                    "arrivals": round(arrivals, 2),
                    "consumption": round(consumption, 2),
                    "end_stock": round(end_stock, 2),
                },
            }
        )
        rolling_stock = end_stock

        for entry in month_output["json_plan_list"]:
            date_key = str(entry.get("date", "未知"))
            if date_key not in merged_date_map:
                merged_date_map[date_key] = {"date": date_key, "total_quantity": 0.0, "items": []}
            merged_date_map[date_key]["items"].extend(entry.get("items", []))
            merged_date_map[date_key]["total_quantity"] += _safe_float(entry.get("total_quantity", 0.0))

    merged_plan_list = list(merged_date_map.values())
    for entry in merged_plan_list:
        entry["total_quantity"] = round(_safe_float(entry.get("total_quantity", 0.0)), 2)
    merged_plan_list.sort(key=lambda item: str(item.get("date", "")))

    top_analysis = "\n\n".join(
        f"M{idx + 1}：\n{entry.get('decision_analysis', '')}" for idx, entry in enumerate(month_entries)
    )
    output_json_obj = {
        "decision_date": base_date.strftime("%Y-%m-%d") if base_date else "未指定",
        "is_emergency": bool(any_emergency),
        "duration_days": month_count * month_length_calendar,
        "total_purchase_quantity": round(total_purchase, 2),
        "decision_analysis": top_analysis,
        "months": month_entries,
        "procurement_plan": merged_plan_list,
    }
    output_file = _resolve_legacy_procure_plan_path(input_file=input_file, args=base_args)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_json_obj, f, ensure_ascii=False, indent=2)

    header = f"未来{month_count * month_length_calendar}天采购计划已生成，采购计划 JSON 已保存至 {output_file}。"
    analysis_block = "\n\n".join(
        f"=== 决策分析 M{idx + 1} ===\n{entry.get('decision_analysis', '').strip()}"
        for idx, entry in enumerate(month_entries)
    )
    return header + "\n\n" + "\n\n".join(month_outputs) + "\n\n" + analysis_block


def chat_with_tools(user_query: str,
                    history: Optional[List[Dict[str, str]]] = None,
                    input_file: Optional[str] = None) -> str:             
    if history is None:
        history = []

    # ⭐ 保存用户原始 JSON，后面用它来“纠正”模型给的 args
    parsed_user_json = None

    # 1. 不再“直接调工具”，而是最多做一个“JSON 识别 + 包装”，让大模型来决定
    user_prompt = user_query
    try:
        user_json = _extract_json_object(user_query.strip())
        print("DEBUG: 尝试从用户输入中解析 JSON:", user_json)
        if isinstance(user_json, dict):
            parsed_user_json = user_json.copy()  # ⭐ 复制一份，用于存全量数据

            # --- 新增：支持从 price_file 加载价格数据 ---
            if "price_file" in parsed_user_json:
                try:
                    p_file = parsed_user_json["price_file"]
                    # 简单处理路径引号
                    p_file = p_file.strip('"').strip("'")
                    p_base_dir = os.path.dirname(os.path.abspath(p_file)) if p_file else os.getcwd()

                    def _resolve_path(path_like: Any) -> str:
                        path_str = str(path_like).strip('"').strip("'")
                        if os.path.isabs(path_str):
                            return path_str
                        if os.path.exists(path_str):
                            return path_str
                        return os.path.join(p_base_dir, path_str)

                    def _load_freight_series(file_path: str) -> List[float]:
                        # 支持 CSV（推荐）和 JSON；CSV 优先读取“预测值”列。
                        series: List[float] = []
                        if not file_path or not os.path.exists(file_path):
                            return series

                        if file_path.lower().endswith(".json"):
                            try:
                                with open(file_path, "r", encoding="utf-8") as jf:
                                    obj = json.load(jf)
                                if isinstance(obj, list):
                                    for x in obj:
                                        try:
                                            series.append(float(x))
                                        except Exception:
                                            pass
                            except Exception:
                                return []
                            return series

                        try:
                            with open(file_path, "r", encoding="utf-8") as cf:
                                reader = csv.DictReader(cf)
                                pred_key = None
                                if reader.fieldnames:
                                    # 清理表头中的 BOM/空格，并优先使用“预测值”列
                                    norm_map = {
                                        str(k).strip().lstrip("\ufeff"): k
                                        for k in reader.fieldnames
                                        if k is not None
                                    }
                                    for k in ["预测值", "pred", "prediction", "forecast", "yhat"]:
                                        if k in norm_map:
                                            pred_key = norm_map[k]
                                            break
                                    if pred_key is None:
                                        pred_key = reader.fieldnames[-1]

                                for row in reader:
                                    try:
                                        raw = row.get(pred_key, "") if pred_key else ""
                                        if raw is None or str(raw).strip() == "":
                                            continue
                                        series.append(float(raw))
                                    except Exception:
                                        continue
                        except Exception:
                            return []
                        return series

                    def _align_series(vals: List[float], n: int, offset: int = 0) -> List[float]:
                        if n <= 0:
                            return []
                        if not vals:
                            return [0.0] * n
                            
                        # 向前补齐，对于决策日之前的天数，使用第0天的预测运费（或者直接保持一致）
                        aligned = [vals[0]] * offset + vals
                        
                        if len(aligned) >= n:
                            return aligned[:n]
                        return aligned + [aligned[-1]] * (n - len(aligned))

                    # 可选：运费输入（国内/国外/按煤种）
                    # 支持两种写法：domestic_freight_file / inside_freight_file
                    domestic_freight_file = parsed_user_json.get("domestic_freight_file") or parsed_user_json.get("inside_freight_file")
                    outside_freight_file = parsed_user_json.get("outside_freight_file")
                    freight_file_map = parsed_user_json.get("freight_file_map", {})

                    domestic_series = []
                    outside_series = []
                    if domestic_freight_file:
                        domestic_series = _load_freight_series(_resolve_path(domestic_freight_file))
                    if outside_freight_file:
                        outside_series = _load_freight_series(_resolve_path(outside_freight_file))
                        # outside 运费默认按美元换算成人民币：* 6.9125
                        # 可通过 outside_fx_rate 覆盖汇率（例如传 7.0）。
                        outside_fx_rate = float(parsed_user_json.get("outside_fx_rate", 6.9125))
                        outside_series = [v * outside_fx_rate for v in outside_series]
                        print(f"DEBUG: outside 运费已按汇率 {outside_fx_rate} 换算为人民币")

                    default_domestic_coals = ["CCI4500", "CCI5000", "CCI5500"]
                    default_outside_coals = ["CCI进口3800", "CCI进口4700", "CCI进口5500"]
                    # 固定进口煤种集合，确保国外运费只作用于指定进口煤种
                    fixed_imported = set(default_outside_coals)
                    domestic_coals = set(parsed_user_json.get("domestic_coals", default_domestic_coals))
                    outside_coals = set(parsed_user_json.get("outside_coals", default_outside_coals)) | fixed_imported

                    if os.path.exists(p_file):
                        print(f"DEBUG: 正在加载外部价格文件: {p_file}")
                        with open(p_file, "r", encoding="utf-8") as f:
                            price_data = json.load(f)

                        coal_config = parsed_user_json.get("coal_config", {})

                        decision_month = None
                        decision_date_raw = parsed_user_json.get("decision_date")
                        if decision_date_raw:
                            decision_dt = _parse_decision_date(decision_date_raw)
                            if decision_dt:
                                decision_month = decision_dt.strftime("%Y%m")
                            else:
                                print("WARNING: 决策日解析失败，无法匹配月份，使用默认月份。")

                        def normalize_prices(prices_raw):
                            prices = []
                            if isinstance(prices_raw, list):
                                for item in prices_raw:
                                    try:
                                        val = item.get("value") if isinstance(item, dict) else item
                                        prices.append(float(val))
                                    except Exception:
                                        continue
                            return prices

                        def build_coal_info(coal_name, prices):
                            cfg = coal_config.get(coal_name, {})
                            freight_series = []
                            cfg_ff = cfg.get("forecast_freight")
                            if isinstance(cfg_ff, list):
                                for x in cfg_ff:
                                    try:
                                        freight_series.append(float(x))
                                    except Exception:
                                        pass
                            elif isinstance(freight_file_map, dict) and coal_name in freight_file_map:
                                freight_series = _load_freight_series(_resolve_path(freight_file_map[coal_name]))
                            elif coal_name in outside_coals:
                                freight_series = outside_series
                            elif coal_name in domestic_coals:
                                freight_series = domestic_series
                            else:
                                # 未显式配置时，默认按国内煤种使用国内运费。
                                freight_series = domestic_series
                            offset = decision_dt.day - 1 if (decision_dt is not None) else 0
                            freight_series = _align_series(freight_series, len(prices), offset=offset)
                            
                            return {
                                "name": coal_name,
                                "forecast_prices": prices,
                                "current_price": cfg.get("current_price", prices[0] if prices else 0),
                                "sulfur_pct": cfg.get("sulfur_pct", 1.0),
                                "heat_value": cfg.get("heat_value", 5000),
                                "forecast_freight": freight_series,
                            }

                        new_coal_infos = []

                        is_monthly_format = (
                            isinstance(price_data, dict)
                            and price_data
                            and all(isinstance(v, dict) for v in price_data.values())
                        )

                        if is_monthly_format:
                            month_key = None
                            if decision_month and decision_month in price_data:
                                month_key = decision_month
                            else:
                                month_key = sorted(price_data.keys())[0]
                                if decision_month:
                                    print(f"WARNING: 找不到决策月 {decision_month} 的价格，回退到 {month_key}")
                                else:
                                    print(f"WARNING: 未提供决策日，默认使用 {month_key} 的价格数据")

                            month_prices = price_data.get(month_key, {})
                            for coal_name, prices_raw in month_prices.items():
                                prices = normalize_prices(prices_raw)
                                new_coal_infos.append(build_coal_info(coal_name, prices))
                        else:
                            for coal_name, prices_raw in price_data.items():
                                prices = normalize_prices(prices_raw)
                                new_coal_infos.append(build_coal_info(coal_name, prices))

                        parsed_user_json["coal_infos"] = new_coal_infos

                        summary_infos = []
                        for info in new_coal_infos:
                            summary_infos.append({
                                "name": info["name"],
                                "forecast_prices": f"<list of {len(info['forecast_prices'])} prices loaded from file>",
                                "forecast_freight": f"<list of {len(info.get('forecast_freight', []))} freight values>",
                                "current_price": info["current_price"],
                                "sulfur_pct": info["sulfur_pct"],
                                "heat_value": info["heat_value"]
                            })
                        user_json["coal_infos"] = summary_infos

                        print(f"DEBUG: 已从文件加载 {len(new_coal_infos)} 个煤种数据")
                    else:
                        print(f"WARNING: 找不到价格文件: {p_file}")
                except Exception as e:
                    print(f"ERROR: 加载价格文件失败: {e}")
            # ------------------------------------------

        if isinstance(parsed_user_json, dict):
            duration_days = parsed_user_json.get("duration_days")
            multi_months = parsed_user_json.get("multi_months")
            has_explicit_window = duration_days is not None or multi_months is not None
            has_coal_infos = isinstance(parsed_user_json.get("coal_infos"), list) and bool(parsed_user_json.get("coal_infos"))
            try:
                duration_days_int = int(duration_days) if duration_days is not None else 0
            except Exception:
                duration_days_int = 0
            try:
                multi_months_int = int(multi_months) if multi_months is not None else 0
            except Exception:
                multi_months_int = 0

            if has_coal_infos and not has_explicit_window:
                parsed_user_json["duration_days"] = 90
                duration_days_int = 90

            if duration_days_int in (40, 60, 90):
                month_count = int(duration_days_int // 20) if duration_days_int != 90 else 3
                return _run_multi_month_plan(parsed_user_json, month_count, input_file=input_file)
            if multi_months_int in (2, 3):
                return _run_multi_month_plan(parsed_user_json, multi_months_int, input_file=input_file)

        if isinstance(user_json, dict) and "coal_infos" in user_json:
            # ✅ 不直接 execute_tool，而是把 JSON 明确告诉大模型
            user_prompt = (
                "下面是用户提供的参数 JSON，请根据系统指令判断是否需要调用库存策略工具 "
                "`run_inventory_strategy`。如果需要，请在你的回复中返回一个 JSON，"
                "格式为：{\"tool\": \"run_inventory_strategy\", \"args\": <下方 JSON 原样> }。\n\n"
                f"用户参数 JSON：\n{json.dumps(user_json, ensure_ascii=False)}"
            )
    except Exception as e:
        print(f"DEBUG: JSON 解析失败，按普通文本处理。错误信息: {e}")
        # 出错就忽略，当普通文本处理
        pass

    # 2. 正常对话 messages：所有决策都交给大模型
    messages = [{"role": "system", "content": build_system_prompt()}] + history
    messages.append({"role": "user", "content": user_prompt})

    # 第一次推理：让大模型决定是否调用工具
    first_resp = ask_llm(messages)
    print("[LLM 第一次回复] >>>", first_resp)

    # 3. 尝试从第一次回复中解析“工具调用 JSON”
    try:
        call = _extract_json_object(first_resp)
        if not isinstance(call, dict):
            # 解析出来的不是 dict，当纯文本返回
            return first_resp

        tool_name = call.get("tool")
        args = call.get("args") or {}

        if tool_name:
            print(f"[工具调用] {tool_name} :: {args}")

            # ⭐ 关键修正：若是库存策略工具，强制使用“用户原始 JSON”的所有参数
            if (
                tool_name == "run_inventory_strategy"
                and isinstance(parsed_user_json, dict)
            ):
                # 将用户原始 JSON 的所有字段合并到 args 中 (优先使用原始数据)
                # 这样即使 LLM 漏掉了某些参数，也能从原始输入中补全
                for k, v in parsed_user_json.items():
                    args[k] = v

            # （可选）再做一个简单结构校验，提前发现问题
            if tool_name == "run_inventory_strategy":
                # 兼容命名：文档里常写 alpha，这里工具实现用 decay
                if "alpha" in args and "decay" not in args:
                    args["decay"] = args["alpha"]

                # === 关键：动态更新综合模型准确率（accuracy_t）===
                # 如果存在状态文件，则用上次 accuracy_t 作为本次 prev_acc。
                # 可通过 use_dynamic_accuracy=false 显式关闭。
                use_dyn = True
                if isinstance(parsed_user_json, dict) and "use_dynamic_accuracy" in parsed_user_json:
                    use_dyn = bool(parsed_user_json.get("use_dynamic_accuracy"))
                if "use_dynamic_accuracy" in args:
                    use_dyn = bool(args.get("use_dynamic_accuracy"))

                if use_dyn:
                    state = _load_accuracy_state()
                    if isinstance(state, dict) and "prev_acc" in state:
                        try:
                            args["prev_acc"] = float(state["prev_acc"])
                            print(f"DEBUG: 使用持久化 prev_acc={args['prev_acc']:.4f} 进行准确率滚动更新")
                        except Exception:
                            pass
                else:
                    print("DEBUG: use_dynamic_accuracy=false，本次不使用持久化 prev_acc")

                coal_infos = args.get("coal_infos")
                if (
                    not isinstance(coal_infos, list)
                    or not coal_infos
                    or not isinstance(coal_infos[0], dict)
                ):
                    raise ValueError(
                        "run_inventory_strategy 的参数结构异常：coal_infos 必须是非空的字典列表。"
                    )

                # 如果用户没有传 prev_acc（或被上游漏掉），给一个保守缺省，避免工具直接报错。
                if "prev_acc" not in args:
                    args["prev_acc"] = 0.75
                    print("WARNING: 未提供 prev_acc，已使用默认值 0.75")

            # 3.1 实际执行工具（仍然有容错逻辑）
            try:
                tool_result = execute_tool(tool_name, args)
            except TypeError as e:
                msg = str(e)
                print(f"[工具调用错误] {msg}, 尝试移除多余参数重试...")

                # 只针对 unexpected keyword argument 做参数精简重试
                if "unexpected keyword" in msg or "got an unexpected keyword argument" in msg:
                    args.pop("month", None)
                    args.pop("single_month", None)
                    try:
                        tool_result = execute_tool(tool_name, args)
                    except Exception as e2:
                        # 第二次还是失败，直接回退：不再触发工具流程，返回 first_resp
                        print("[工具调用二次失败] >>>", e2)
                        return first_resp
                else:
                    # 像 list indices must be integers or slices, not str 这种，
                    # 说明内部逻辑类型不匹配，继续 raise 交给外层处理
                    raise

            print("[工具返回] >>>", tool_result)

            # === 将本次计算出的 accuracy_t 持久化，供下次作为 prev_acc ===
            if tool_name == "run_inventory_strategy":
                try:
                    s2 = tool_result.get("step2", {}) if isinstance(tool_result, dict) else {}
                    acc_t = s2.get("accuracy_t") if isinstance(s2, dict) else None
                    if acc_t is not None:
                        _save_accuracy_state(
                            prev_acc=float(acc_t),
                            meta={
                                "real_acc": args.get("real_acc"),
                                "decay": args.get("decay"),
                            },
                        )
                        print(f"DEBUG: 已保存 accuracy_t={float(acc_t):.4f} 到 {ACCURACY_STATE_FILE}")
                except Exception as e:
                    print(f"WARNING: 保存 accuracy_t 失败（不影响本次结果）。原因: {e}")

            # =====================================================
            # 新增：在 Python 端预处理数据，直接生成 Markdown 表格
            # =====================================================
            final_table_str = ""  # 1. 定义变量暂存表格
            
            try:
                # 提取关键数据
                s3 = tool_result.get("step3", {})
                s5 = tool_result.get("step5", {})
                s4 = tool_result.get("step4", {})
                
                monthly_total = s3.get("monthly_qty", 0)
                week_qtys = s4.get("week_qty", [])
                purchase_days = s5.get("purchase_days_by_week", [])
                blend_plans = s5.get("blend_plan", [])
                latest_delivery_days = s5.get("latest_delivery_days", [])
                # Ensure length match for safety
                while len(latest_delivery_days) < len(week_qtys):
                    latest_delivery_days.append([])

                # --- 修改为用户指定的文本格式 ---
                # 尝试获取决策日
                decision_date_raw = args.get("decision_date") or parsed_user_json.get("decision_date")
                start_date = _parse_decision_date(decision_date_raw)
                decision_date_str = decision_date_raw
                if start_date:
                    decision_date_str = start_date.strftime("%Y-%m-%d")

                # Check for emergency
                is_emergency = False
                note = s3.get("components", {}).get("note", "")
                if note == "Emergency Strategy Triggered":
                    is_emergency = True

                output_str = f"决策日： {decision_date_str if decision_date_str else '未指定'}\n"
                if is_emergency:
                    output_str += "【警告】触发紧急库存策略！库存低于安全水位，优先满足近期需求。\n"
                else:
                    output_str += "【正常】库存策略执行中。\n"

                output_str += f"30天总采购量：{monthly_total:.2f} 吨\n"
                output_str += "未来30天采购计划：\n"
                # 尝试获取煤种名称
                coal_names = []
                if "coal_infos" in args and isinstance(args["coal_infos"], list):
                    for info in args["coal_infos"]:
                        coal_names.append(info.get("name", "未知煤种"))

                # 全局按日期分组
                global_date_groups = {}
                global_json_items_by_date = {}

                for i, (qty, days, blend, ldd_list) in enumerate(zip(week_qtys, purchase_days, blend_plans, latest_delivery_days)):
                    if qty <= 1e-6:
                        continue
                        
                    for k, b_val in enumerate(blend):
                        if b_val <= 1e-6:
                            continue
                        c_name = coal_names[k] if k < len(coal_names) else f"煤种{k+1}"
                        name_mapping = {
                            "CCI4500": "北方港4500",
                            "CCI5000": "北方港5000",
                            "CCI5500": "北方港5500",
                            "CCI进口3800": "进口3800",
                            "CCI进口4700": "进口4700",
                            "CCI进口5500": "进口5500"
                        }
                        c_name = name_mapping.get(c_name, c_name)
                        
                        # 获取该独立煤种的采购日期
                        d_idx = days[k] if (isinstance(days, list) and k < len(days)) else "未知"
                        coal_date_display = f"第{d_idx}天"
                        if start_date is not None and isinstance(d_idx, (int, float)):
                            c_date = start_date + timedelta(days=int(d_idx))
                            coal_date_display = c_date.strftime("%Y/%m/%d")
                            
                        # 获取当天预测煤价/运费/到厂成本
                        price_str = ""
                        price_val = 0.0
                        freight_val = 0.0
                        delivered_cost = 0.0
                        try:
                            if "coal_infos" in args:
                                c_info = args["coal_infos"][k]
                                prices = c_info.get("forecast_prices", [])
                                freights = c_info.get("forecast_freight", [])
                                if isinstance(prices, list) and len(prices) > int(d_idx):
                                    price_val = float(prices[int(d_idx)])
                                if isinstance(freights, list) and len(freights) > int(d_idx):
                                    freight_val = float(freights[int(d_idx)])

                                delivered_cost = price_val + freight_val
                                price_str = f"到厂单价{delivered_cost:.2f}(煤价{price_val:.2f}+运费{freight_val:.2f})"
                        except:
                            pass
                        
                        # 获取 LDD
                        ldd_val = 0.0
                        ldd_display = "0"
                        try:
                            if k < len(ldd_list):
                                ldd_val = ldd_list[k]
                                if abs(ldd_val) > 1e-6:
                                    if start_date:
                                        ldd_date = start_date + timedelta(days=int(ldd_val))
                                        ldd_display = ldd_date.strftime("%Y/%m/%d")
                                    else:
                                        ldd_display = f"{ldd_val:.1f}"
                                else:
                                    ldd_display = "0"
                        except Exception as e:
                            print(f"LDD error: {e}")

                        ldd_text = f"LDD:{ldd_display}"
                        
                        # 按全局日期分组
                        if coal_date_display not in global_date_groups:
                            global_date_groups[coal_date_display] = []
                            global_json_items_by_date[coal_date_display] = []
                            
                        global_date_groups[coal_date_display].append(
                            f"{c_name} {b_val:.2f}吨({price_str} {ldd_text})"
                        )
                        
                        global_json_items_by_date[coal_date_display].append({
                            "cycle": i + 1,
                            "coal_name": c_name,
                            "quantity": round(b_val, 2),
                            "price": round(delivered_cost, 2),
                            "coal_price": round(price_val, 2),
                            "freight": round(freight_val, 2),
                            "delivered_unit_cost": round(delivered_cost, 2),
                            "latest_delivery_date": ldd_display
                        })

                # 构建全局输出字符串，突出展示日期
                json_plan_list = []
                for date_key in sorted(global_date_groups.keys()):
                    date_items = "，".join(global_date_groups[date_key])
                    # 计算该日的总和
                    day_total = sum(item["quantity"] for item in global_json_items_by_date[date_key])
                    output_str += f"- 采购日 {date_key} (共计 {day_total:.2f}吨)：{date_items}\n"
                    
                    json_plan_list.append({
                        "date": date_key,
                        "total_quantity": round(day_total, 2),
                        "items": global_json_items_by_date[date_key]
                    })


                # -------- 计算并附加未来30天最低预测价格 --------
                try:
                    output_str += "\n【补充数据：未来30天各煤种最低价格预估】\n"
                    name_mapping = {
                        "CCI4500": "北方港4500",
                        "CCI5000": "北方港5000",
                        "CCI5500": "北方港5500",
                        "CCI进口3800": "进口3800",
                        "CCI进口4700": "进口4700",
                        "CCI进口5500": "进口5500"
                    }
                    c_infos = args.get("coal_infos", [])
                    st_date = start_date if start_date else datetime.now()
                    
                    for info in c_infos:
                        c_raw = info.get("name", "未知")
                        c_disp = name_mapping.get(c_raw, c_raw)
                        p_list = info.get("forecast_prices", [])
                        
                        p_30 = p_list[:30]
                        if not p_30:
                            continue
                            
                        min_p = min(p_30)
                        min_idx = p_30.index(min_p)
                        min_d = st_date + timedelta(days=min_idx)
                        min_d_str = min_d.strftime("%Y/%m/%d")
                        output_str += f"{c_disp}：{min_d_str} 的 {min_p:.2f}元/吨；"
                    output_str += "\n\n"
                except Exception as e:
                    print("计算最低价格附件失败:", e)

                # 保存 JSON 文件
                try:
                    output_json_obj = {
                        "decision_date": decision_date_str if decision_date_str else '未指定',
                        "is_emergency": is_emergency,
                        "duration_days": 30,
                        "total_purchase_quantity": round(monthly_total, 2),
                        "procurement_plan": json_plan_list
                    }
                    output_file = _resolve_legacy_procure_plan_path(input_file=input_file, args=args)
                    os.makedirs(os.path.dirname(output_file), exist_ok=True)
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(output_json_obj, f, ensure_ascii=False, indent=2)
                    print(f"DEBUG: 采购计划已保存至 {output_file}")
                except Exception as e:
                    print(f"保存 JSON 文件失败: {e}")

                final_table_str = output_str
                
                # 传给 LLM 的内容包含格式化后的文本，供其理解
                tool_content_for_llm = (
                    f"计算完成。\n"
                    f"月度总采购量: {monthly_total:.2f} 吨\n\n"
                    f"{output_str}"
                )

            except Exception as e:
                print(f"数据预处理出错: {e}")
                tool_content_for_llm = json.dumps(tool_result, ensure_ascii=False)

            # =====================================================

            # 插入工具结果
            messages.append({"role": "assistant", "content": first_resp})
            messages.append({"role": "tool", "name": tool_name, "content": tool_content_for_llm})
            
            # 3. 修改 Prompt：从 prompt_analysis.txt 读取用户的要求
            try:
                with open("prompt_analysis.txt", "r", encoding="utf-8") as _f:
                    _template = _f.read()
                # 注入计算结果
                summary_prompt = _template.replace("{strategy_indicators}", tool_content_for_llm)
            except Exception:
                summary_prompt = (
                    "计算已完成。请根据工具返回的数据，输出以下决策分析文字版：\n"
                    "1. 煤价月度综合下跌概率；\n"
                    "2. 按采购日分析决策的原因。\n"
                    "**注意：你只需要输出文字分析，不要输出表格。**\n"
                    f"数据如下：\n{tool_content_for_llm}"
                )
            
            messages.append({"role": "user", "content": summary_prompt})

            # 第二轮推理
            final_resp = ask_llm(messages)

            def strip_code_fence(s: str) -> str:
                s = re.sub(r"^```(?:json)?\s*", "", s.strip())
                s = re.sub(r"\s*```$", "", s).strip()
                return s

            final_resp = strip_code_fence(final_resp)

            if (
                (not final_resp.strip())
                or (len(final_resp.strip()) < 220)
                or ("无数据可提供" in final_resp)
            ):
                fallback_analysis = _build_detailed_analysis_from_tool(
                    tool_result=tool_result,
                    args=args,
                    decision_date_str=decision_date_str,
                    time_window=f"{decision_date_str}起未来30天" if decision_date_str else "当前决策周期",
                )
                if fallback_analysis:
                    final_resp = fallback_analysis
            
            # --- 新增：将最终分析文本追加到 procurement_plan.json ---
            try: 
                output_file = _resolve_legacy_procure_plan_path(input_file=input_file, args=args)
                #plan_file = "../autoinfer/html1/procure_plan/kemen_procurement_plan.json"
                if os.path.exists(output_file):
                    with open(output_file, "r", encoding="utf-8") as f:
                        plan_data = json.load(f)
                    # 重新构造字典顺序，让 decision_analysis 放在 procurement_plan 前面
                    new_plan_data = {}
                    for k, v in plan_data.items():
                        if k == "procurement_plan":
                            new_plan_data["decision_analysis"] = final_resp
                            new_plan_data[k] = v
                        else:
                            new_plan_data[k] = v
                    if "decision_analysis" not in new_plan_data:
                        new_plan_data["decision_analysis"] = final_resp

                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(new_plan_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"追加分析文本到 JSON 失败: {e}")
            
            print("[LLM 最终回复] >>>", final_resp)
            return final_resp

        else:
            # 模型没给出 tool 字段：当普通聊天结果返回
            return first_resp

    except Exception as e:
        # 包括 list indices must be integers or slices, not str 之类
        print("[未触发工具或解析失败]", str(e))
        # 兜底：直接返回第一次回复，不再继续报错
        return first_resp




# ========= 控制台交互 =========
# if __name__ == "__main__":
#     print("=== 本地模型 + 工具链 Demo ===")
#     print("输入 exit/quit 退出\n")
#     session_history: List[Dict[str, str]] = []

#     while True:
#         try:
#             user = input("你 >>> ").strip()
#             if user in {"exit", "quit"}:
#                 break
#             if not user:
#                 continue
#             bot = chat_with_tools(user, session_history)
#             session_history.append({"role": "user", "content": user})
#             session_history.append({"role": "assistant", "content": bot})
#         except KeyboardInterrupt:
#             print("\nBye~")
#             break
