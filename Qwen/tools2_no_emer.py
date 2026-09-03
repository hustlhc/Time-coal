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
                                "heat_value": {"type": "number"}
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

                    "weekly_accuracy": {
                        "type": "array",
                        "items": {"type": "number"}
                    },

                    "target_heat": {"type": "number"},
                    "min_ship_qty": {"type": "number", "description": "单煤种最小船运量约束，默认 50000"}
                },
                "required": [
                    "coal_infos",
                    "prev_acc", "real_acc", "lambda_base", "cv_t",
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
import numpy as np
from inventory_strategy.monthly import coal_probs, coal_cv, monthly_qty
from inventory_strategy.weekly import weekly_weights
from inventory_strategy.daily import blend_coal
from inventory_strategy.emergency import emergency_qty
from inventory_strategy.correction import extra_factor
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpInteger, value, LpBinary

def run_inventory_strategy(
    coal_infos,
    prev_acc, real_acc, lambda_base, cv_t, beta1, beta2, decay,
    base_demand, max_stock, prev_stock, extra_factor,
    weekly_accuracy,
    target_heat,
    threshold_pct=0.05, weeks=4,
    month: int = 0, single_month: bool = False, 
    min_ship_qty: float = 50000.0,
    **kwargs
):
    # ---------- Step1：涨跌概率 ----------
    step1 = compute_drop_rise_probs(
        coal_infos=coal_infos,
        threshold_pct=threshold_pct,
        weeks=weeks
    )

    p_down = step1["monthly_drop_prob"]
    p_up   = step1["monthly_rise_prob"]
    weekly_drop = step1["weekly_drop_prob"]

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

    # ---------- Step3：月度采购量 ----------
    step3 = compute_monthly_qty(
        base_demand=base_demand,
        lambda_t=lambda_t,
        p_down=p_down,
        p_up=p_up,
        max_stock=max_stock,
        prev_stock=prev_stock,
        extra_factor=extra_factor,
        enforce_capacity=True
    )

    month_qty = step3["monthly_qty"]

    # ---------- Step4：周度量 ----------
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

    # ---------- 新增：计算最短到货日期 (Latest Delivery Date) ----------
    # 每天消耗 = base_demand / 30
    # 安全库存 = 15 * 每天消耗
    # LDD = 采购日 + (在该采购日时的库存 - 安全库存) / 每天消耗
    daily_use = base_demand / 30.0
    safety_stock = 8.0 * daily_use
    
    latest_delivery_days = []
    cumulative_purchase = 0.0
    
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
                
                # 计算在该采购日的库存 (假设线性消耗)
                # Stock_at_P = Prev_Stock + Cumulative_Purchase - (P_day * Daily_Use)
                stock_at_p = prev_stock + cumulative_purchase - (p_day * daily_use)
                
                # 计算还能撑多久 (Days Lasting)
                if daily_use > 1e-6:
                    days_lasting = (stock_at_p - safety_stock) / daily_use
                else:
                    days_lasting = 999.0
                
                # LDD = Purchase Day + Days Lasting
                ldd = p_day + days_lasting
                
                # 如果计算出的 LDD 早于采购日（说明库存早已不足），则修正为采购日（即需立即到货）
                if ldd < p_day:
                    ldd = p_day
                    
                week_ldds.append(float(ldd))
            else:
                week_ldds.append(0.0)
        
        latest_delivery_days.append(week_ldds)
        cumulative_purchase += w_qty

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
    


def compute_monthly_qty(
    base_demand: float,
    lambda_t: float,
    p_down: float,
    p_up: float,
    max_stock: float,
    prev_stock: float,
    extra_factor: float = 0.0,
    enforce_capacity: bool = True,
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

    # 5) 可选：不超过可用库容（如果业务要求采购不能超过空位）
    if enforce_capacity:
        qty = min(qty, available_space)
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

    week_qty = (W * month_qty).tolist()
    print("计算周度分布的函数已经调用。")
    return {
        "week_weights": W.tolist(),
        "week_qty": week_qty
    }



# def compute_purchase_days_and_blending(week_qty, coal_infos,month: int = 0, single_month: bool = False):
#     """
#     Step 5: 每周选择最低价日进行采购，并按煤种优化配煤
#     week_qty: 每周总采购量列表
#     coal_infos: 每种煤信息列表
#     """
#     purchase_days = []
#     num_weeks = len(week_qty)
#     num_days_per_week = 5  # 一周 5 个交易日

#     # 每周选择最低价日（purchase_days: 按煤种 -> 每周的日索引）
#     for info in coal_infos:
#         fc = np.array(info["forecast_prices"])
#         week_size = len(fc) // num_weeks
#         days = []
#         for i in range(num_weeks):
#             start = i * week_size
#             seg = fc[start:start+num_days_per_week]  # 只看周前5天
#             day_offset = int(np.argmin(seg))
#             days.append(start + day_offset)  # 全月索引
#         purchase_days.append(days)

#     # 配煤优化：最小化成本，满足热值和硫分约束
#     blend = []
#     for wq in week_qty:
#         prob = LpProblem("CoalBlending", LpMinimize)
#         # 决策变量：每种煤采购量
#         x = [LpVariable(f"x{i}", lowBound=0, cat=LpInteger) for i in range(len(coal_infos))]

#         # 目标：最小化采购成本
#         prob += lpSum(x[i] * coal_infos[i]["current_price"] for i in range(len(coal_infos)))

#         # 约束：总量等于周采购量
#         prob += lpSum(x) == wq

#         # 约束：热值下限
#         total_cal = lpSum(x[i] * coal_infos[i]["heat_value"] for i in range(len(coal_infos)))
#         Cal_min = wq * min(info["heat_value"] for info in coal_infos)  # 可按实际需求调整
#         prob += total_cal >= Cal_min

#         # 约束：硫分上限
#         total_s = lpSum(x[i] * coal_infos[i]["sulfur_pct"] for i in range(len(coal_infos)))
#         S_max = 1.0  # 可根据实际需求调整
#         prob += total_s <= S_max * wq

#         # 求解
#         prob.solve()
#         blend.append([value(var) for var in x])

#     # 转换为按周的视图：purchase_days_by_week[week][coal_index]
#     num_coals = len(coal_infos)
#     purchase_days_by_week = []
#     for w in range(num_weeks):
#         row = [purchase_days[c][w] for c in range(num_coals)]
#         purchase_days_by_week.append(row)

#     result = {
#         "purchase_days": purchase_days,
#         "purchase_days_by_week": purchase_days_by_week,
#         "blend_plan": blend  # 已是按周的列表，元素为每周各煤种量
#     }
#     # 若请求单月视图，可由上层决定；这里统一返回两种视图
#     print("计算采购日和配煤的函数已经调用。")
#     return result

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
    """
    num_weeks = len(week_qty)
    num_coals = len(coal_infos)
    num_days_per_week = 5
    total_days = len(coal_infos[0]["forecast_prices"])
    week_size = total_days // num_weeks

    # ---------- 1. 获取外部权重 (用于无解时的兜底) ----------
    ext_ret = compute_drop_rise_probs(coal_infos, threshold_pct=0.05, weeks=4)
    weights = np.array(ext_ret["weights"])

    # ---------- 2 & 3. 遍历每日寻找最优 (选日+配煤同时优化) ----------
    purchase_days = [[] for _ in range(num_coals)]
    blend_plan = []
    
    # 约束设定
    TARGET_HEAT = target_heat 

    for w in range(num_weeks):
        wq = week_qty[w]
        start_day = w * week_size
        
        # 如果当周无采购量，直接跳过
        if wq <= 0.01:
            blend_plan.append([0.0] * num_coals)
            for c in range(num_coals):
                purchase_days[c].append(start_day)
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

            # 目标：最小化成本 (使用当天的预测价)
            current_prices = [coal_infos[c]["forecast_prices"][day_idx] for c in range(num_coals)]
            prob += lpSum(x[c] * current_prices[c] for c in range(num_coals))

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
            for c in range(num_coals):
                purchase_days[c].append(start_day)

    # ---------- 4. 整理成按周视图 ----------
    purchase_days_by_week = []
    for w in range(num_weeks):
        purchase_days_by_week.append([purchase_days[c][w] for c in range(num_coals)])

    return {
        "purchase_days": purchase_days,
        "purchase_days_by_week": purchase_days_by_week,
        "blend_plan": blend_plan
    }

# # 工具调度器
# def execute_tool(function_name, function_args):
#     """根据工具名称调用相应的函数（原有逻辑不动）"""
#     tool_functions = {
#         # ====== 库存策略（追加） ======
#         "compute_drop_rise_probs": compute_drop_rise_probs,
#         "compute_accuracy_and_lambda": compute_accuracy_and_lambda,
#         "compute_monthly_qty": compute_monthly_qty,
#         "compute_weekly_distribution": compute_weekly_distribution,
#         "compute_purchase_days_and_blending": compute_purchase_days_and_blending,
#     }
#     if function_name in tool_functions:
#         return tool_functions[function_name](**function_args)
#     else:
#         return {"error": f"未知工具: {function_name}"}

def execute_tool(function_name, function_args):
    if function_name == "run_inventory_strategy":
        return run_inventory_strategy(**function_args)
    return {"error": f"未知工具: {function_name}"}


# if __name__ == "__main__":
#     coal_infos = [
#         {
#             "forecast_prices": [742, 688, 755, 734, 701, 769, 758, 720, 760, 745, 776, 772, 690, 865, 873, 899, 820, 812, 835, 848],
#             "current_price": 740,
#             "sulfur_pct": 0.8,
#             "heat_value": 5500
#         }
#     ]
    
#     args = {
#         "coal_infos": coal_infos,
#         "prev_acc": 0.8,
#         "real_acc": 0.85,
#         "lambda_base": 0.5,
#         "cv_t": 0.06,
#         "beta1": 0.6,
#         "beta2": 0.4,
#         "decay": 0.7,
#         "base_demand": 60,
#         "max_stock": 120,
#         "prev_stock": 80,
#         "extra_factor": 0.05,
#         "weekly_accuracy": [0.75, 0.8, 0.78, 0.77]
#     }

#     print(execute_tool("run_inventory_strategy", args))

