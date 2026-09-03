# 定义多个工具，1个入口
tools = [
    {
        "type": "function",
        "function": {
            "name": "run_inventory_strategy",
            "description": "执行库存策略：包含 Step1~Step5（涨跌概率 → λ_t → 月度量 → 周度量 → 每周采购日与配煤）。返回完整结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "coal_infos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "forecast_prices": {"type": "array", "items": {"type": "number"}},
                                "current_price": {"type": "number"},
                                "heat_value": {"type": "number"},
                                "forecast_freight": {
                                    "type": "array",
                                    "items": {"type": "number"},
                                    "description": "可选：预测运费序列(元/吨)，按天与 forecast_prices 对齐"
                                }
                            },
                            "required": ["forecast_prices", "current_price", "heat_value"]
                        }
                    },

                    "prev_acc": {"type": "number"},
                    "real_acc": {"type": "number"},
                    "lambda_base": {"type": "number"},
                    "cv_t": {"type": "number"},
                    "beta1": {"type": "number"},
                    "beta2": {"type": "number"},
                    "decay": {"type": "number"},

                    "base_demand": {"type": "number"},
                    "max_stock": {"type": "number"},
                    "prev_stock": {"type": "number"},
                    "extra_factor": {"type": "number"},
                    "safety_stock_days": {"type": "number", "description": "安全库存天数，默认 15 天。"},
                    "min_stock_buffer_days": {"type": "number", "description": "固定库存缓冲值折算成多少天平均耗煤量，建议 1 到 3 天，默认 2 天。"},
                    "min_stock_buffer": {"type": "number", "description": "在安全库存基础上追加的固定库存缓冲值，单位与库存一致。若传入则优先于 min_stock_buffer_days。"},

                    "use_dynamic_extra_factor": {"type": "boolean", "description": "是否启用连续下跌动态 Extra Factor（EF_t）。默认 false，保持 extra_factor 作为静态值。"},
                    "p_down_history": {"type": "array", "items": {"type": "number"}, "description": "历史月度 P_down 序列（可包含或不包含当月；若不包含将自动追加当月）。"},
                    "accuracy_history": {"type": "array", "items": {"type": "number"}, "description": "历史月度 Accuracy 序列（可包含或不包含当月；若不包含将自动追加当月）。"},
                    "base_factors": {"type": "array", "items": {"type": "number"}, "description": "连续下跌权重 BaseFactor 序列，如 [1.0,1.5,2.0,...]。长度不足时自动按 0.5 递增补齐。"},
                    "ef_start_pdown": {"type": "number", "description": "进入连续下跌期的 P_down 阈值（默认 0.6）。"},
                    "ef_start_acc": {"type": "number", "description": "进入连续下跌期的 Accuracy 阈值（默认 0.7）。"},
                    "ef_stop_pdown": {"type": "number", "description": "退出/暂停 EF 的 P_down 阈值（默认 0.5）。"},
                    "ef_stop_acc": {"type": "number", "description": "退出/暂停 EF 的 Accuracy 阈值（默认 0.6）。"},
                    "ef_cap": {"type": "number", "description": "EF 上限（默认 0.3）。"},
                    "ef_floor": {"type": "number", "description": "EF 下限（默认 0.0）。"},

                    "weekly_accuracy": {
                        "type": "array",
                        "items": {"type": "number"}
                    },

                    "target_heat": {"type": "number"},
                    "min_ship_qty": {"type": "number", "description": "单煤种最小船运量约束，默认 50000"}
                },
                "required": [
                    "coal_infos",
                    "prev_acc", "real_acc", "lambda_base", 
                    "beta1", "beta2", "decay",
                    "base_demand", "max_stock", "prev_stock", "extra_factor",
                    "weekly_accuracy"
                ]
            }
        }
    }
]


# 实现对应的工具函数

# ===================== 库存策略工具函数（新增） =====================
# 注意：函数名必须与 tools_schema 完全一致，返回 dict
import json
import os
import time
from typing import Optional, Dict, Any
import numpy as np
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpInteger, value, LpBinary


# ========= 综合模型准确率（accuracy_t）状态持久化 =========
# 目的：把上一轮计算得到的 accuracy_t 存下来，下一轮作为 prev_acc 参与更新。
ACCURACY_STATE_FILE = os.environ.get(
    "ACCURACY_STATE_FILE",
    os.path.join(os.path.dirname(__file__), "state", "accuracy_state.json"),
)


def _load_accuracy_state(state_file: str = ACCURACY_STATE_FILE) -> Dict[str, Any]:
    try:
        if not state_file or not os.path.exists(state_file):
            return {}
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_accuracy_state(prev_acc: float, meta: Optional[Dict[str, Any]] = None, state_file: str = ACCURACY_STATE_FILE) -> None:
    try:
        if not state_file:
            return
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        payload: dict = {
            "prev_acc": float(prev_acc),
            "updated_at": int(time.time()),
        }
        if isinstance(meta, dict):
            payload.update(meta)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        # 持久化失败不影响本次策略
        return


def _compute_min_stock_level(
    base_demand: float,
    safety_stock_days: float = 15.0,
    min_stock_buffer: Optional[float] = None,
    min_stock_buffer_days: float = 2.0,
) -> Dict[str, float]:
    daily_use = float(base_demand) / 30.0
    safety_stock_days = float(safety_stock_days)
    min_stock_buffer_days = float(min_stock_buffer_days)
    safety_stock = max(safety_stock_days, 0.0) * daily_use
    if min_stock_buffer is None:
        resolved_buffer_days = min(max(min_stock_buffer_days, 1.0), 3.0)
        min_stock_buffer_value = resolved_buffer_days * daily_use
        buffer_source = "days_of_demand"
    else:
        resolved_buffer_days = float(min_stock_buffer) / daily_use if daily_use > 1e-9 else 0.0
        min_stock_buffer_value = max(float(min_stock_buffer), 0.0)
        buffer_source = "explicit_tonnage"
    min_stock_level = safety_stock + min_stock_buffer_value
    return {
        "daily_use": float(daily_use),
        "safety_stock_days": float(max(safety_stock_days, 0.0)),
        "safety_stock": float(safety_stock),
        "min_stock_buffer_days": float(resolved_buffer_days),
        "min_stock_buffer": float(min_stock_buffer_value),
        "min_stock_buffer_source": buffer_source,
        "min_stock_level": float(min_stock_level),
    }

def run_emergency_strategy(prev_stock, base_demand, min_ship_qty=50000.0, max_stock=None, safety_stock_days=15.0, min_stock_buffer=None, min_stock_buffer_days=2.0, **kwargs):
    stock_guard = _compute_min_stock_level(
        base_demand=base_demand,
        safety_stock_days=safety_stock_days,
        min_stock_buffer=min_stock_buffer,
        min_stock_buffer_days=min_stock_buffer_days,
    )
    daily_use = stock_guard["daily_use"]
    safety_stock = stock_guard["safety_stock"]
    min_stock_level = stock_guard["min_stock_level"]
    
    if prev_stock >= min_stock_level:
        print(f"【提示】正常库存策略: 当前库存 {prev_stock:.2f} >= 库存下限 {min_stock_level:.2f}")
        return {
            "is_emergency": False,
            "message": "Normal stock level."
        }
    
    print(f"【提示】触发紧急库存策略: 当前库存 {prev_stock:.2f} < 库存下限 {min_stock_level:.2f}")
    
    # Step B: Q_need
    q_need = max(min_stock_level - prev_stock, min_ship_qty)
    
    month_qty = float(q_need)
    
    return {
        "is_emergency": True,
        "monthly_qty": month_qty,
        "week_qty": [month_qty, 0.0, 0.0, 0.0], # All in first week
        "components": {
            "note": "Emergency Strategy Triggered",
            "base_demand": base_demand,
            "safety_stock_days": stock_guard["safety_stock_days"],
            "safety_stock": safety_stock,
            "min_stock_buffer_days": stock_guard["min_stock_buffer_days"],
            "min_stock_buffer": stock_guard["min_stock_buffer"],
            "min_stock_buffer_source": stock_guard["min_stock_buffer_source"],
            "min_stock_level": min_stock_level
        }
    }

def run_inventory_strategy(
    coal_infos,
    prev_acc, real_acc, lambda_base, beta1, beta2, decay,
    base_demand, max_stock, prev_stock, extra_factor,
    weekly_accuracy,
    target_heat,
    cv_t=0.06,
    threshold_pct=0.05, weeks=4,
    month: int = 0, single_month: bool = False, 
    min_ship_qty: float = 50000.0,
    use_dynamic_accuracy: bool = True,
    accuracy_state_file: Optional[str] = None,
    **kwargs
):
    # ---------- -1. accuracy_t 动态更新（跨调用持久化） ----------
    # 按策略公式：Accuracy_t = α * Accuracy_{t-1} + (1-α) * RealAccuracy_t
    # 这里 α 对应入参 decay。
    state_file = accuracy_state_file or ACCURACY_STATE_FILE
    if use_dynamic_accuracy:
        state = _load_accuracy_state(state_file)
        if isinstance(state, dict) and "prev_acc" in state:
            try:
                prev_acc = float(state["prev_acc"])
            except Exception:
                pass

    # ---------- 0. 紧急库存检查 ----------
    emergency_res = run_emergency_strategy(
        prev_stock=prev_stock,
        base_demand=base_demand,
        min_ship_qty=min_ship_qty,
        max_stock=max_stock,
        safety_stock_days=float(kwargs.get("safety_stock_days", 15.0)),
        min_stock_buffer=kwargs.get("min_stock_buffer"),
        min_stock_buffer_days=float(kwargs.get("min_stock_buffer_days", 2.0)),
    )
    is_emergency = emergency_res["is_emergency"]

    # ---------- Step1：涨跌概率 ----------
    step1 = compute_drop_rise_probs(
        coal_infos=coal_infos,
        threshold_pct=threshold_pct,
        weeks=weeks
    )

    p_down = step1["monthly_drop_prob"]
    p_up   = step1["monthly_rise_prob"]
    weekly_drop = step1["weekly_drop_prob"]

    # 从 step1 结果中获取动态计算的 system_cv
    # 如果有效（>0），则覆盖传入的静态 cv_t
    system_cv = step1.get("system_cv", 0.0)
    if system_cv > 1e-9:
        cv_t = system_cv

    # ---------- Step2：准确率与 λ_t ----------
    step2 = compute_accuracy_and_lambda(
        prev_acc=prev_acc,
        real_acc=real_acc,
        cv_t=cv_t,
        lambda_base=lambda_base,
        beta1=beta1,
        beta2=beta2,
        decay=decay
    )
    lambda_t = step2["lambda_t"]

    # 保存本次 accuracy_t，供下次作为 prev_acc
    if use_dynamic_accuracy:
        try:
            acc_t = step2.get("accuracy_t")
            if acc_t is not None:
                _save_accuracy_state(
                    prev_acc=float(acc_t),
                    meta={"real_acc": real_acc, "decay": decay},
                    state_file=state_file,
                )
        except Exception:
            pass

    # ---------- Step2.5：动态 Extra Factor（连续下跌策略，可选） ----------
    use_dynamic_ef = bool(kwargs.get("use_dynamic_extra_factor", False))
    accuracy_t = float(step2.get("accuracy_t", 0.0))
    dynamic_ef = 0.0
    dynamic_ef_detail = {
        "enabled": use_dynamic_ef,
        "reason": "disabled",
        "k": 0,
        "ef_raw": 0.0,
        "ef": 0.0,
    }
    if use_dynamic_ef:
        dynamic_ef, dynamic_ef_detail = compute_dynamic_extra_factor(
            p_down_current=float(p_down),
            accuracy_current=float(accuracy_t),
            p_down_history=kwargs.get("p_down_history"),
            accuracy_history=kwargs.get("accuracy_history"),
            base_factors=kwargs.get("base_factors"),
            start_pdown=float(kwargs.get("ef_start_pdown", 0.6)),
            start_acc=float(kwargs.get("ef_start_acc", 0.7)),
            stop_pdown=float(kwargs.get("ef_stop_pdown", 0.5)),
            stop_acc=float(kwargs.get("ef_stop_acc", 0.6)),
            ef_cap=float(kwargs.get("ef_cap", 0.3)),
            ef_floor=float(kwargs.get("ef_floor", 0.0)),
        )

    effective_extra_factor = float(dynamic_ef if use_dynamic_ef else extra_factor)

    # ---------- Step3：月度采购量 ----------
    if is_emergency:
        # Align emergency replenishment to the same 10k rounding rule.
        int_unit = 10000.0
        emergency_units = int(round(float(emergency_res["monthly_qty"]) / int_unit))
        if emergency_units == 0:
            emergency_units = 1
        emergency_qty = float(emergency_units * int_unit)
        # 紧急补库后继续按策略计算当月剩余采购量
        step3_normal = compute_monthly_qty(
            base_demand=base_demand,
            lambda_t=lambda_t,
            p_down=p_down,
            p_up=p_up,
            max_stock=max_stock,
            prev_stock=float(prev_stock) + emergency_qty,
            extra_factor=effective_extra_factor,
            enforce_capacity=True,
            hist_purchase=float(kwargs.get("historical_purchase", 0.0)),
            min_stock_level=float(kwargs.get("min_stock_level", 0.0))
        )
        step3_normal.setdefault("components", {})
        step3_normal["components"].update(
            {
                "extra_factor_input": float(extra_factor),
                "extra_factor_effective": float(effective_extra_factor),
                "extra_factor_dynamic": dynamic_ef_detail,
            }
        )
        normal_qty = float(step3_normal.get("monthly_qty", 0.0))
        month_qty = emergency_qty + normal_qty
        step3 = {
            "raw_qty": float(step3_normal.get("raw_qty", 0.0)) + emergency_qty,
            "monthly_qty": month_qty,
            "available_space": max(float(max_stock) - float(prev_stock), 0.0),
            "components": {
                **emergency_res["components"],
                "emergency_qty": emergency_qty,
                "normal_qty": normal_qty,
                "normal_components": step3_normal.get("components", {}),
            },
        }
        print(
            "DEBUG: step3 emergency | "
            f"prev_stock={float(prev_stock):.2f} | "
            f"min_stock_level={emergency_res['components'].get('min_stock_level', 0.0):.2f} | "
            f"emergency_qty={emergency_qty:.2f} | "
            f"normal_raw_qty={float(step3_normal.get('raw_qty', 0.0)):.2f} | "
            f"normal_qty={normal_qty:.2f} | "
            f"monthly_qty={month_qty:.2f}"
        )
    else:
        # 实时计算购买上限需要的参数传给月度采购量模块
        step3 = compute_monthly_qty(
            base_demand=base_demand,
            lambda_t=lambda_t,
            p_down=p_down,
            p_up=p_up,
            max_stock=max_stock,
            prev_stock=prev_stock,
            extra_factor=effective_extra_factor,
            enforce_capacity=True,
            hist_purchase=float(kwargs.get("historical_purchase", 0.0)),
            min_stock_level=float(kwargs.get("min_stock_level", 0.0))
        )
        # 注入 EF 诊断信息，便于对齐算法文档
        step3.setdefault("components", {})
        step3["components"].update(
            {
                "extra_factor_input": float(extra_factor),
                "extra_factor_effective": float(effective_extra_factor),
                "extra_factor_dynamic": dynamic_ef_detail,
            }
        )
        month_qty = step3["monthly_qty"]
        print(
            "DEBUG: step3 normal | "
            f"prev_stock={float(prev_stock):.2f} | "
            f"raw_qty={float(step3.get('raw_qty', 0.0)):.2f} | "
            f"monthly_qty={month_qty:.2f}"
        )

    # ---------- Step4：周度量 ----------
    if is_emergency:
        # Keep emergency qty consistent with the rounded value used in Step3.
        int_unit = 10000.0
        emergency_units = int(round(float(emergency_res["monthly_qty"]) / int_unit))
        if emergency_units == 0:
            emergency_units = 1
        emergency_qty = float(emergency_units * int_unit)
        step4 = compute_weekly_distribution(
            month_qty=float(month_qty) - emergency_qty,
            weekly_drop_prob=weekly_drop,
            weekly_accuracy=weekly_accuracy
        )
        week_qty = step4["week_qty"]
        if week_qty:
            week_qty[0] = float(week_qty[0]) + emergency_qty
        else:
            week_qty = [emergency_qty, 0.0, 0.0, 0.0]
        step4["week_qty"] = week_qty
        step4["emergency_qty"] = emergency_qty
    else:
        step4 = compute_weekly_distribution(
            month_qty=month_qty,
            weekly_drop_prob=weekly_drop,
            weekly_accuracy=weekly_accuracy
        )
        week_qty = step4["week_qty"]

    # ---------- Step5：采购日 + 配煤比例 ----------
    step5 = compute_purchase_days_and_blending(
        week_qty=week_qty,
        coal_infos=coal_infos,
        target_heat=target_heat,
        month=month,  # 传递 month 以便按需聚合
        single_month=single_month,
        min_ship_qty=min_ship_qty
    )

    # ---------- 新增：计算最晚到货日期 (Latest Delivery Date) ----------
    # 每天消耗 = base_demand / 30
    # 库存下限 = 安全库存 + 固定库存缓冲值
    # LDD = 采购日 + (在该采购日时的库存 - 库存下限) / 每天消耗
    stock_guard = _compute_min_stock_level(
        base_demand=base_demand,
        safety_stock_days=float(kwargs.get("safety_stock_days", 15.0)),
        min_stock_buffer=kwargs.get("min_stock_buffer"),
        min_stock_buffer_days=float(kwargs.get("min_stock_buffer_days", 2.0)),
    )
    daily_use = stock_guard["daily_use"]
    min_stock_level = stock_guard["min_stock_level"]
    hist_purchase = float(kwargs.get("historical_purchase", 0.0))
    
    latest_delivery_days = []
    # 已确认订单（qty, ldd_day_index），用于按周滚动叠加“已到货量”
    planned_orders = []
    
    # 获取每周各煤种的采购日 (Weeks x Coals)
    purchase_days_by_week = step5.get("purchase_days_by_week", [])

    for w_idx, w_qty in enumerate(week_qty):
        # 当前周的配煤计划 (list of floats)
        current_blend = step5["blend_plan"][w_idx]
        
        # 获取当前周各煤种的采购日列表
        current_days = purchase_days_by_week[w_idx] if w_idx < len(purchase_days_by_week) else [0]*len(current_blend)

        week_ldds = []
        for c_idx, c_qty in enumerate(current_blend):
            if c_qty > 0.01:
                # 获取该煤种的采购日
                p_day = current_days[c_idx] if c_idx < len(current_days) else 0

                # 可用库存按周滚动：从决策日到采购日叠加此前已到货订单
                arrived_qty = 0.0
                for qty_i, ldd_i in planned_orders:
                    arrived_qty += float(qty_i)

                # (a) 最大库存量 = max_stock
                # (b) 最低安全库存 = min_stock_level
                # (c) 日均消耗量 = daily_use
                # (d) 历史购买量 (此处的已到货量+原本的历史) = hist_purchase + arrived_qty
                # (e) 当前库存量 = prev_stock
                # t 为从当前决策日期起到最迟到货日期之间的天数
                d_history = hist_purchase + arrived_qty
                e_current = float(prev_stock)
                b_min = float(min_stock_level)
                c_use = float(daily_use)
                
                if c_use > 1e-6:
                    t = (d_history + e_current - b_min) / c_use
                else:
                    t = 999.0
                    
                # 按照用户的逻辑：从当前决策日期起计算最迟到货日期，即 LDD = 当前(0) + t
                ldd = float(t)
                
                # 我们不能截断量，否则导致分配量加起来不够总采购量
                # 取而代之我们要计算最晚到货时间，既要保证不低于最小库存（原逻辑），
                # 若单批次很大还要防止溢舱（推迟 LDD）。这里暂且尊重其分配的原有 c_qty
                # 并推迟 t，确保 a_max 的限制得到满足。
                
                # 购买上限逻辑仅用于推导 LDD，不在此处修改配煤数量，避免总量被隐式削减。
                t_limit = max(0, t - 1)
                a_max = float(max_stock * 1.3)
                buy_limit = max(0.0, a_max + c_use * t_limit - d_history - e_current)
                
                
                # 增设下限：根据煤种判断，如果是进口煤则至少为 p_day + 14，否则北方港至少为 p_day + 7
                c_name = coal_infos[c_idx].get("name", "") if c_idx < len(coal_infos) else ""
                min_ldd_offset = 14.0 if "进口" in c_name else 7.0
                if ldd < p_day + min_ldd_offset:
                    ldd = float(p_day + min_ldd_offset)
                    
                week_ldds.append(float(ldd))
                # 当前采购批次作为“未来待到货订单”参与后续滚动
                planned_orders.append((float(c_qty), float(ldd)))
            else:
                week_ldds.append(0.0)
        
        latest_delivery_days.append(week_ldds)

    # 将计算结果注入到 step5
    step5["latest_delivery_days"] = latest_delivery_days

    # 如果请求 single_month，按语义化结构返回单月视图
    if single_month:
        # 构造明确的单月结构：按周的采购日 & 每周配煤（每周内为各煤种量）
        per_week = {
            "week_qty": step4["week_qty"],
            "purchase_days_by_week": step5.get("purchase_days_by_week", []),
            "blend_plan_by_week": step5.get("blend_plan", [])
        }
        return {
            "month": int(month),
            "step1": step1,
            "step2": step2,
            "step3": step3,
            "step4": step4,
            "step5": per_week
        }

    return {
        "step1": step1,
        "step2": step2,
        "step3": step3,
        "step4": step4,
        "step5": step5
    }
    print("库存策略工具函数已执行完毕。")


# 1. 工具函数（保持签名一致，返回 dict）
def compute_drop_rise_probs(coal_infos, threshold_pct=0.05, weeks=4):
    monthly_drops = []
    monthly_rises = []
    weekly_drops  = []
    weekly_rises  = []
    values        = []

    for info in coal_infos:
        fc   = np.array(info["forecast_prices"])
        curr = info["current_price"]
        low  = curr * (1 - threshold_pct)
        high = curr * (1 + threshold_pct)

        # 月度概率
        monthly_drops.append((fc < low).sum() / len(fc))
        monthly_rises.append((fc > high).sum() / len(fc))

        # 周度概率
        size = len(fc) // weeks
        wd, wr = [], []
        for i in range(weeks):
            seg = fc[i*size:(i+1)*size]
            wd.append((seg < low).sum() / len(seg))
            wr.append((seg > high).sum() / len(seg))
        weekly_drops.append(wd)
        weekly_rises.append(wr)

        # 煤种价值权重
        val = (info["heat_value"] / curr)
        values.append(val)


    w = np.array(values); w = w / w.sum()

    # 系统级 CV：基于每个煤种的 forecast_prices 计算 CV（std/mean），避免除以 0
    cv_each = []
    for info in coal_infos:
        arr = np.asarray(info.get("forecast_prices", []), dtype=float)
        if arr.size == 0:
            cv_each.append(0.0)
            continue
        mean = arr.mean()
        std = arr.std()
        cv_each.append(float(std / mean) if mean != 0 else 0.0)
    cv_sys = float(np.dot(w, np.asarray(cv_each)))

    monthly_drop_prob = float(np.dot(w, monthly_drops))
    monthly_rise_prob = float(np.dot(w, monthly_rises))
    weekly_drop_prob  = np.einsum('i,ij->j', w, np.array(weekly_drops))
    weekly_rise_prob  = np.einsum('i,ij->j', w, np.array(weekly_rises))
    print("计算涨跌率的函数已经调用。")
    return {
        "monthly_drop_prob": monthly_drop_prob,
        "monthly_rise_prob": monthly_rise_prob,
        "weekly_drop_prob": weekly_drop_prob.tolist(),
        "weekly_rise_prob": weekly_rise_prob.tolist(),
        "weights": w.tolist(),
        "system_cv": cv_sys
    }


def compute_accuracy_and_lambda(
    prev_acc: float,
    real_acc: float,
    cv_t: float,
    lambda_base: float = 0.5,
    beta1: float = 0.6,
    beta2: float = 0.4,
    decay: float = 0.7,
):
    """
    更新 accuracy_t（滚动值）并计算 lambda_t
    """
    # β 归一化
    beta_sum = beta1 + beta2
    beta1, beta2 = beta1 / beta_sum, beta2 / beta_sum

    # ----- 1) 滚动更新 accuracy -----
    accuracy_t = decay * prev_acc + (1 - decay) * real_acc
    accuracy_t = max(0, min(1, accuracy_t))

    # ----- 2) 计算 λ_t -----
    lambda_t = lambda_base * (beta1 * accuracy_t + beta2 * (1 - cv_t))
    lambda_t = max(0.0, lambda_t)
    print("计算 accuracy 和 lambda 的函数已经调用。")
    return {
        "accuracy_t": accuracy_t,     # ⚠️ 存档！用于下月 prev_acc
        "lambda_t": lambda_t
    }


def compute_dynamic_extra_factor(
    p_down_current: float,
    accuracy_current: float,
    p_down_history=None,
    accuracy_history=None,
    base_factors=None,
    start_pdown: float = 0.6,
    start_acc: float = 0.7,
    stop_pdown: float = 0.5,
    stop_acc: float = 0.6,
    ef_cap: float = 0.3,
    ef_floor: float = 0.0,
):
    """连续下跌 Extra Factor（EF_t）计算。

    逻辑对齐文档：
    - 有效下跌期判别：连续 k 个月满足 P_down>start_pdown 且 Accuracy>start_acc。
    - 停止条件：当月 P_down<stop_pdown 或 Accuracy<stop_acc，则 EF=0（暂停使用）。
    - 计算公式：
      EF_raw = sum_{i=0..k-1}(BaseFactor_{i+1} * Acc_{t-i} * P_down_{t-i}) / sum_{i=0..k-1}(BaseFactor_{i+1})
      EF = clip(EF_raw, [ef_floor, ef_cap])
    - BaseFactor 默认按 1.0,1.5,2.0,... 递增。
    """
    p_down_current = float(p_down_current)
    accuracy_current = float(accuracy_current)

    # 停止条件：当月不满足，则直接归零
    if (p_down_current < float(stop_pdown)) or (accuracy_current < float(stop_acc)):
        return 0.0, {
            "enabled": True,
            "reason": "stopped_by_condition",
            "p_down_current": p_down_current,
            "accuracy_current": accuracy_current,
            "k": 0,
            "ef_raw": 0.0,
            "ef": 0.0,
        }

    # 组装历史序列（允许传入不含当月的历史；此处自动追加当月）
    p_hist = []
    a_hist = []
    if isinstance(p_down_history, (list, tuple)):
        p_hist = [float(x) for x in p_down_history]
    if isinstance(accuracy_history, (list, tuple)):
        a_hist = [float(x) for x in accuracy_history]

    # 长度对齐：只取共同长度
    n = min(len(p_hist), len(a_hist))
    p_hist = p_hist[-n:]
    a_hist = a_hist[-n:]

    # 是否已包含当月：用“最后一个值是否接近当前值”做鲁棒判断
    def _close(x, y, eps=1e-9):
        return abs(float(x) - float(y)) <= eps

    if n == 0:
        p_hist = [p_down_current]
        a_hist = [accuracy_current]
    else:
        if (not _close(p_hist[-1], p_down_current)) or (not _close(a_hist[-1], accuracy_current)):
            p_hist.append(p_down_current)
            a_hist.append(accuracy_current)

    # 计算连续下跌长度 k（从当月向前数，遇到不满足 start 条件即停止）
    k = 0
    for pd, acc in zip(reversed(p_hist), reversed(a_hist)):
        if (pd > float(start_pdown)) and (acc > float(start_acc)):
            k += 1
        else:
            break

    if k <= 0:
        return 0.0, {
            "enabled": True,
            "reason": "not_in_effective_downtrend",
            "p_down_current": p_down_current,
            "accuracy_current": accuracy_current,
            "k": 0,
            "ef_raw": 0.0,
            "ef": 0.0,
        }

    # BaseFactor 序列
    bf = []
    if isinstance(base_factors, (list, tuple)) and len(base_factors) > 0:
        bf = [float(x) for x in base_factors]

    # 不足则按 0.5 递增补齐
    if len(bf) < k:
        if len(bf) == 0:
            bf = [1.0 + 0.5 * i for i in range(k)]
        else:
            last = bf[-1]
            if last <= 0:
                # 异常保护：回退到默认序列
                bf = [1.0 + 0.5 * i for i in range(k)]
            else:
                while len(bf) < k:
                    last = last + 0.5
                    bf.append(last)
    else:
        bf = bf[:k]

    # 套用公式（i=0 对应当月；BaseFactor_{i+1} 对应 bf[i]）
    num = 0.0
    den = 0.0
    for i in range(k):
        idx = -1 - i
        bfi = float(bf[i])
        num += bfi * float(a_hist[idx]) * float(p_hist[idx])
        den += bfi

    ef_raw = (num / den) if den > 0 else 0.0
    ef = min(float(ef_cap), max(float(ef_floor), float(ef_raw)))

    return float(ef), {
        "enabled": True,
        "reason": "ok",
        "p_down_current": p_down_current,
        "accuracy_current": accuracy_current,
        "k": int(k),
        "base_factors_used": [float(x) for x in bf],
        "ef_raw": float(ef_raw),
        "ef": float(ef),
    }
    


def compute_monthly_qty(
    base_demand: float,
    lambda_t: float,
    p_down: float,
    p_up: float,
    max_stock: float,
    prev_stock: float,
    extra_factor: float = 0.0,
    enforce_capacity: bool = True,
    hist_purchase: float = 0.0,
    min_stock_level: float = 0.0,
) -> dict:
    """
    按照公式 Q_t = D_t + lambda_t * (p_down - p_up) * (C_max - I_{t-1}) * (1 + EF_t)
    返回 dict 以便作为工具返回：
      {
        "raw_qty": float,    # 按公式直接算出的数量（未强制库容）
        "monthly_qty": float,# 最终下单量（非负，且可选地不超过可用库容）
        "available_space": float  # C_max - prev_stock（>=0）
      }
    """
    # 转为浮点并保护输入
    base_demand = float(base_demand)
    lambda_t = float(lambda_t)
    p_down = float(p_down)
    p_up = float(p_up)
    max_stock = float(max_stock)
    prev_stock = float(prev_stock)
    extra_factor = float(extra_factor)

    # 1) 可用库容（保护为非负）
    available_space = max(max_stock - prev_stock, 0.0)

    # 2) 计算趋势项差 (P_down - P_up)
    prob_diff = p_down - p_up

    # 3) 按公式计算 raw（未做 capacity 限制）
    raw_add = lambda_t * prob_diff * available_space * (1.0 + extra_factor)
    raw_qty = base_demand + raw_add

    # 4) 非负约束
    qty = max(raw_qty, 0.0)

    # 5) 月度总需求上限：恢复为“容纳能力限制”，防止因“每次购买限制公式”误伤导致月度挨饿
    if enforce_capacity:
        cap_stock = float(max_stock) * 1.3
        max_purchasable_this_month = max(cap_stock - float(prev_stock) + float(base_demand), 0.0)
        qty = min(qty, max_purchasable_this_month)
        
    # 约束新增：总采购量取整“万吨”
    int_unit = 10000.0
    qty_units = int(round(qty / int_unit))
    if qty > 0 and qty_units == 0:
        qty_units = 1
    qty = float(qty_units * int_unit)
    
    print("计算月度采购量的函数已经调用。")

    return {
        "raw_qty": float(raw_qty),
        "monthly_qty": float(qty),
        "available_space": float(available_space),
        "components": {
            "base_demand": base_demand,
            "lambda_t": lambda_t,
            "prob_diff": prob_diff,
            "extra_factor": extra_factor,
            "raw_add": float(raw_add)
        }
    }

def compute_weekly_distribution(month_qty, weekly_drop_prob, weekly_accuracy, gamma=1.2):
    """
    Step 4: 根据系统级 weekly_drop_prob & weekly_accuracy 分配周采购量。
    保证长度固定为 4，缺失周补 0。
    """
    # 确保长度为 4
    n_weeks = 4
    p = np.array(weekly_drop_prob, dtype=float)
    if len(p) < n_weeks:
        p = np.pad(p, (0, n_weeks - len(p)), 'constant', constant_values=0)
    else:
        p = p[:n_weeks]

    acc = np.array(weekly_accuracy, dtype=float)
    if len(acc) < n_weeks:
        acc = np.pad(acc, (0, n_weeks - len(acc)), 'constant', constant_values=0)
    else:
        acc = acc[:n_weeks]

    score = (p * acc) ** gamma
    if score.sum() > 0:
        W = score / score.sum()
    else:
        W = np.zeros(n_weeks)

    # 按整数“万吨”分配
    int_unit = 10000.0
    total_units = int(round(month_qty / int_unit))
    
    if total_units <= 0:
        week_qty = [0.0] * n_weeks
    else:
        base = (W * total_units).astype(int)
        remain = total_units - base.sum()
        remainders = (W * total_units - base)
        order = np.argsort(-remainders)
        for i in range(remain):
            base[order[i % len(base)]] += 1
        week_qty = (base * int_unit).tolist()
        
    print("计算周度分布的函数已经调用。")
    return {
        "week_weights": W.tolist(),
        "week_qty": week_qty
    }

def compute_purchase_days_and_blending(week_qty, coal_infos, target_heat,month: int = 0, single_month: bool = False, min_ship_qty: float = 50000.0):
    """
    每周统一选一天：按 compute_drop_rise_probs 返回的 weights 加权价格最低日
    week_qty: 每周总采购量，长度 = 周数
    coal_infos: 每种煤的信息列表，每个 dict 必须包含：
        "forecast_prices" : list[float] , 长度 = 总交易日
        其余字段保留（配煤计划仍返回吨数，但比例用外部 weights）
    返回:
        {
          "purchase_days"        : (煤种数, 周数)
          "purchase_days_by_week": (周数, 煤种数)
          "blend_plan"           : (周数, 煤种数) 吨数
        }

        预测成本口径（与你给的公式一致）：
            P_i = 预测煤价 + 预测运费
    """
    num_weeks = len(week_qty)
    num_coals = len(coal_infos)
    num_days_per_week = 5
    total_days = len(coal_infos[0]["forecast_prices"])
    week_size = 5

    # ---------- 1. 获取外部权重 (用于无解时的兜底) ----------
    ext_ret = compute_drop_rise_probs(coal_infos, threshold_pct=0.05, weeks=4)
    weights = np.array(ext_ret["weights"])

    # ---------- 2 & 3. 遍历每日寻找最优 (选日+配煤同时优化) ----------
    purchase_days = [[] for _ in range(num_coals)]
    blend_plan = []
    
    # 约束设定
    TARGET_HEAT = target_heat 

    def _get_predicted_freight(info: dict, day_idx: int) -> float:
        # 仅使用 forecast_freight（日度预测运费）
        ff = info.get("forecast_freight")
        if isinstance(ff, (list, tuple, np.ndarray)) and len(ff) > 0:
            idx = int(max(0, min(day_idx, len(ff) - 1)))
            try:
                return float(ff[idx])
            except Exception:
                return 0.0
        return 0.0

    def _clamp_day(idx: int) -> int:
        if total_days <= 0:
            return 0
        return max(0, min(idx, total_days - 1))

    for w in range(num_weeks):
        wq = week_qty[w]
        start_day = w * week_size
        
        # 如果当周无采购量，直接跳过
        if wq <= 0.01:
            blend_plan.append([0.0] * num_coals)
            safe_day = _clamp_day(start_day)
            for c in range(num_coals):
                purchase_days[c].append(safe_day)
            continue

        best_cost = float('inf')
        best_day_idx = start_day
        best_blend = None
        found_solution = False

        # 遍历本周的 5 个交易日
        for d in range(num_days_per_week):
            day_idx = start_day + d
            if day_idx >= total_days: break # 防止越界

            # 定义优化问题：求当天的最低成本配方
            prob = LpProblem(f"Blend_W{w}_D{d}", LpMinimize)
            x = [LpVariable(f"x_{w}_{d}_{c}", lowBound=0) for c in range(num_coals)]

            # 船型约束：如果购买某煤种，则量必须 >= min_ship_qty (除非总采购量本身就很小)
            # 引入二进制变量 y[c]：1表示购买，0表示不购买
            # 约束：x[c] >= min_ship_qty * y[c]
            #       x[c] <= wq * y[c]
            if min_ship_qty > 0 and wq >= min_ship_qty:
                y = [LpVariable(f"y_{w}_{d}_{c}", cat=LpBinary) for c in range(num_coals)]
                for c in range(num_coals):
                    prob += x[c] >= min_ship_qty * y[c]
                    prob += x[c] <= wq * y[c]

            # 目标：最小化预测到厂成本 P_i = 预测煤价 + 预测运费
            current_prices = [float(coal_infos[c]["forecast_prices"][day_idx]) for c in range(num_coals)]
            predicted_freights = [_get_predicted_freight(coal_infos[c], day_idx) for c in range(num_coals)]
            predicted_costs = [current_prices[c] + predicted_freights[c] for c in range(num_coals)]
            prob += lpSum(x[c] * predicted_costs[c] for c in range(num_coals))

            # 约束
            prob += lpSum(x) == wq
            prob += lpSum(x[c] * coal_infos[c]["heat_value"] for c in range(num_coals)) >= wq * TARGET_HEAT

            # 求解
            try:
                from pulp import PULP_CBC_CMD
                prob.solve(PULP_CBC_CMD(msg=0))
            except:
                prob.solve()

            # 如果找到可行解，检查成本是否更低
            if prob.status == 1:
                cost = value(prob.objective)
                if cost < best_cost:
                    best_cost = cost
                    best_day_idx = day_idx
                    best_blend = [value(v) for v in x]
                    found_solution = True

        # 记录本周的最佳结果
        if found_solution:
            blend_plan.append([round(v, 2) for v in best_blend])
            for c in range(num_coals):
                purchase_days[c].append(best_day_idx)
        else:
            # 如果5天都无解（指标太苛刻），回退到按权重分配，并默认选周一
            blend_plan.append((weights * wq).round(2).tolist())
            safe_day = _clamp_day(start_day)
            for c in range(num_coals):
                purchase_days[c].append(safe_day)

    # ---------- 4. 整理成按周视图 ----------
    purchase_days_by_week = []
    for w in range(num_weeks):
        purchase_days_by_week.append([purchase_days[c][w] for c in range(num_coals)])

    return {
        "purchase_days": purchase_days,
        "purchase_days_by_week": purchase_days_by_week,
        "blend_plan": blend_plan
    }

def execute_tool(function_name, function_args):
    if function_name == "run_inventory_strategy":
        return run_inventory_strategy(**function_args)
    return {"error": f"未知工具: {function_name}"}
