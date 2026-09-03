from data_provider.data_factory import data_provider
from exp.exp_basic import Exp_Basic
from utils.tools import EarlyStopping, adjust_learning_rate, visual
from utils.metrics import metric
from utils.device_helper import get_autocast_context, get_grad_scaler
import torch
import torch.nn as nn
from torch import optim
import os
import time
import warnings
import numpy as np
import pandas as pds
from utils.dtw_metric import dtw, accelerated_dtw
from utils.augmentation import run_augmentation, run_augmentation_single

import torch.nn.functional as F


warnings.filterwarnings('ignore')

def acc_cal(file_path, length):

    # 读取CSV文件
  
    df = pds.read_csv(file_path, header=0)
    max_row = df.shape[0] - 1

    # 记录准确率 & 变化曲线
    acc1_list = []
    acc2_list = []
    acc3_list = []
    for n in range(length):
        current_row = 20 + n  # 当前处理行号（1-based）
        current_row_idx = current_row - 1  # 0-based索引

        # 过去一个月真实均值
        past_start = max(0, current_row_idx - 19)
        past_values = df.iloc[past_start:current_row_idx+1, 0]
        mean_past = past_values.mean()

        # 预测值均值
        pred1 = df.iloc[current_row_idx, 1:21].mean()
        pred2 = df.iloc[current_row_idx, 21:41].mean()
        pred3 = df.iloc[current_row_idx, 41:61].mean()

        current_row_idx += 1

        # 真实值均值（带边界检查）
        def get_true_mean(start_offset, end_offset):
            start = current_row_idx + start_offset
            end = min(current_row_idx + end_offset, max_row)
            if start > max_row: return float('nan')
            return df.iloc[start:end+1, 0].mean()

        true1 = get_true_mean(0, 19)
        true2 = get_true_mean(20, 39)
        true3 = get_true_mean(40, 59)

        # 趋势判断函数
        def get_trend(value, base):
            if pds.isna(value): return 'N/A'
            return '涨' if value > base else '跌'

        # 各月预测趋势准确性判断
        true_trend1 = get_trend(true1, mean_past)
        pred_trend1 = get_trend(pred1, mean_past)
        acc1 = 1 if (true_trend1 == pred_trend1) else 0
        acc1_list.append(acc1)  
        
        true_trend2 = get_trend(true2, true1)
        pred_trend2 = get_trend(pred2, pred1)
        acc2 = 1 if (true_trend2 == pred_trend2) else 0
        acc2_list.append(acc2)  
        
        true_trend3 = get_trend(true3, true2)
        pred_trend3 = get_trend(pred3, pred2)
        acc3 = 1 if (true_trend3 == pred_trend3) else 0
        acc3_list.append(acc3)  
        
    ACC_1 = sum(acc1_list) / length
    ACC_2 = sum(acc2_list) / length
    ACC_3 = sum(acc3_list) / length
    return ACC_1, ACC_2, ACC_3

def acc_week_cal(file_path, length):
    """
    计算未来12周（每周5个交易日）的煤价涨跌预测准确率
    按照相对前一周的均值涨跌进行比较
    
    参数:
    file_path: CSV文件路径
    length: 要计算的样本数量（n=1到n=60）
    
    返回:
    ACC_list: 长度为12的列表，包含每周的预测准确率
    """
    
    # 读取CSV文件
    df = pds.read_csv(file_path, header=0)
    max_row = df.shape[0] - 1
    
    # 初始化12周的准确率得分列表
    weekly_acc_scores = [[] for _ in range(12)]
    
    # 处理每个指数日 n=1 到 n=length
    # print(length)
    for n in range(length):
        current_row_idx = 6 + n  # 0-based索引，对应第n+1个指数日
        
        # 过去1周（5个交易日）的真实均值作为基准
        past_start = max(0, current_row_idx - 6)  # 过去5天
        past_values = df.iloc[past_start:current_row_idx-1, 0]
        '''
        if n < 2 or n > 303: 
            print("当前天数：", current_row_idx)
            print(past_start)
            print("过去5天的真实值：")
            print(past_values)
        '''
        mean_past = past_values.mean()
        
        # 获取未来12周的真实值（每周5个交易日，共60个）
        true_future_values = []
        for day in range(60):  # 未来60个交易日
            future_idx = current_row_idx + day  # 从下一天开始
            if future_idx <= max_row:
                true_future_values.append(df.iloc[future_idx, 0])
            else:
                true_future_values.append(np.nan)
        
        # 计算未来每周的真实均值
        weekly_true_means = []
        for week in range(12):
            start_idx = week * 5
            end_idx = start_idx + 5
            week_values = true_future_values[start_idx:end_idx]
            '''
            if n < 2 or n > 303: 
                if week < 1 or week > 10:
                    print("未来第",week+1,"周的真实值：")
                    print(week_values)
            '''
            if any(pds.isna(x) for x in week_values):
                weekly_true_means.append(np.nan)
            else:
                weekly_true_means.append(np.mean(week_values))
        
        # 获取未来12周的预测值（每周5个预测值，共60个）
        # 假设预测值存储在列1-60中
        all_predictions = df.iloc[current_row_idx-1, 1:61].values
        
        # 计算未来每周的预测均值
        weekly_pred_means = []
        for week in range(12):
            start_idx = week * 5
            end_idx = start_idx + 5
            week_predictions = all_predictions[start_idx:end_idx]
            '''
            if n < 2 or n > 303: 
                if week < 1 or week > 10:
                    print("第",n+1,"天")
                    print("未来第",week+1,"周的预测值：")
                    print(week_predictions)
            '''
            weekly_pred_means.append(np.mean(week_predictions))
        
        # 计算真实趋势 True_m(n)
        true_trends = []
        for m in range(12):
            if m == 0:  # 第1周：与过去1周比较
                if pds.isna(weekly_true_means[0]):
                    true_trends.append(np.nan)
                else:
                    true_trends.append(1 if weekly_true_means[0] > mean_past else 0)
            else:  # 第2-12周：与前一周比较
                if pds.isna(weekly_true_means[m]) or pds.isna(weekly_true_means[m-1]):
                    true_trends.append(np.nan)
                else:
                    true_trends.append(1 if weekly_true_means[m] > weekly_true_means[m-1] else 0)
        
        # 计算预测趋势 Pred_m(n)
        pred_trends = []
        for m in range(12):
            if m == 0:  # 第1周：与过去1周比较
                pred_trends.append(1 if weekly_pred_means[0] > mean_past else 0)
            else:  # 第2-12周：与前一周预测比较
                pred_trends.append(1 if weekly_pred_means[m] > weekly_pred_means[m-1] else 0)
        
        # 计算每周的准确率得分 acc_m(n)
        for m in range(12):
            if not pds.isna(true_trends[m]):  # 只有当真实趋势有效时才计算
                acc_score = 1 if pred_trends[m] == true_trends[m] else 0
                weekly_acc_scores[m].append(acc_score)
    # 计算每周的最终准确率 ACC_m
    ACC_list = []
    # 遍历每个周
    for m in range(12):
        # 初始化一个列表用于存储当前周的滑动窗口均值
        weekly_window_means = []
        # 遍历当前周的每个滑动窗口
        for i in range(len(weekly_acc_scores[m]) - 60 + 1):
            # 计算当前滑动窗口的均值
            window_mean = sum(weekly_acc_scores[m][i:i+60]) / 60
            # 将当前滑动窗口的均值添加到列表中
            weekly_window_means.append(window_mean)
        
        #print(weekly_window_means)
        # 如果当前周有数据，则计算所有滑动窗口均值的均值
        if len(weekly_window_means) > 0:
            ACC_m = sum(weekly_window_means) / len(weekly_window_means)
        else:
            ACC_m = 0
        
        # 将当前周的 ACC 均值添加到 ACC_list 中
        ACC_list.append(ACC_m)
    
    return ACC_list

def calc_mape_score(mape_7, mape_14):
    """计算MAPE得分"""
    score = 0
    if mape_7 < 3:
        score += 3
    if mape_14 < 6:
        score += 2
    return score

def calc_mape_score_freight(mape_7, mape_14): # 运费mape得分（模型四、五）
    """计算MAPE得分"""
    score = 0
    if mape_7 < 10:
        score += 3
    if mape_14 < 20:
        score += 2
    return score

def calc_month_score(acc_1, acc_2, acc_3):
    """
    计算月颗粒度得分
    - ACC为百分比小数，如0.85表示85%
    - ACC_1 >= 0.8, ACC_2 >= 0.7, ACC_3 >= 0.7 为及格线，基础得分60%（3分）
    - 在及格基础上每增加1%，得分增加1%满分（5分），每降低1%减1%
    - 最低0分，最高5分
    """
    base_thresholds = [0.8, 0.7, 0.7]  # 及格线
    base_score = 3.0                    # 基础得分
    max_score = 5.0
    min_score = 0.0

    score = base_score
    for acc, thresh in zip([acc_1, acc_2, acc_3], base_thresholds):
        diff = acc - thresh
        score += diff * max_score  # 每1%满分5分
    score = max(min_score, min(max_score, score))
    return score

def calc_week_score(acc_week_list):
    """
    计算周颗粒度得分
    - acc_week_list: 长度12，每个值为0~1小数
    - 满足及格线：ACC1,ACC2>=0.85; ACC3,ACC4>=0.75; ACC5~12>=0.70
    - 基础分3分（60%）
    - 每提高1%，得分增加0.25%满分（5分）
    - 每降低1%，得分减少
    - 最小0分，最大5分
    """
    if len(acc_week_list) != 12:
        raise ValueError("acc_week_list 长度必须是12")
    
    thresholds = [0.85, 0.85, 0.75, 0.75] + [0.7]*8
    base_score = 3.0
    max_score = 5.0
    min_score = 0.0
    increment_per_1pct = 0.0025 * max_score  # 0.25% × 满分5分 = 0.0125

    score = base_score
    for acc, t in zip(acc_week_list, thresholds):
        diff = acc - t
        score += diff * 100 * increment_per_1pct  # 百分比换算
    score = max(min_score, min(max_score, score))
    return score

def calc_score(mape_7, mape_14, acc_1, acc_2, acc_3, acc_week_list):
    """计算总得分"""
    mape_score = calc_mape_score(mape_7, mape_14)
    month_score = calc_month_score(acc_1, acc_2, acc_3)
    week_score = calc_week_score(acc_week_list)
    total = mape_score + month_score + week_score
    return {
        "MAPE_score": mape_score,
        "Month_score": month_score,
        "Week_score": week_score,
        "Total_score": total
    }

def calc_score_freight(mape_7, mape_14, acc_1, acc_2, acc_3, acc_week_list):
    """计算总得分"""
    mape_score = calc_mape_score_freight(mape_7, mape_14)
    month_score = calc_month_score(acc_1, acc_2, acc_3)
    week_score = calc_week_score(acc_week_list)
    total = mape_score + month_score + week_score
    return {
        "MAPE_score": mape_score,
        "Month_score": month_score,
        "Week_score": week_score,
        "Total_score": total
    }

def make_weights(T, mode="linear", alpha=0.2, beta=3.0, split=0.6):
    """
    生成权重序列（前期低，后期高）

    参数：
        T (int): 样本总长度
        mode (str): 权重模式，可选 ["linear", "exp", "piecewise"]
        alpha (float): 线性模式下的起始权重 (0<alpha<=1)，或分段模式下前期权重
        beta (float): 指数模式的强度系数，越大后期越重要
        split (float): 分段模式的分界点 (0<split<1)，表示前 split 比例的样本用 alpha，后面用 1.0

    返回：
        weights (torch.Tensor): 长度为 T 的权重张量
    """
    t_idx = torch.arange(T).float()
    t_norm = t_idx / (T - 1)  # 归一化到 [0,1]

    if mode == "linear":
        # 前 alpha，后 1.0，线性递增
        weights = alpha + (1 - alpha) * t_norm

    elif mode == "exp":
        # 指数增长，再归一化
        weights = torch.exp(beta * t_norm)
        weights = weights / weights.mean()

    elif mode == "piecewise":
        # 前期 alpha，后期 1.0
        weights = torch.ones_like(t_norm)
        cutoff = int(split * T)
        weights[:cutoff] = alpha

    else:
        raise ValueError(f"未知 mode: {mode}")

    return weights

def make_batch_weights(num_batches, mode="linear", alpha=0.2, beta=3.0, split=0.6):
    """
    按 batch 生成权重序列，同一 batch 内权重相同。

    参数：
        num_batches (int): batch 总数量
        mode (str): 权重模式，可选 ["linear", "exp", "piecewise"]
        alpha (float): 线性模式下的起始权重 (0<alpha<=1)，或分段模式下前期权重
        beta (float): 指数模式的强度系数
        split (float): 分段模式的分界点 (0<split<1)，表示前 split 比例的 batch 用 alpha，后面用 1.0

    返回：
        batch_weights (torch.Tensor): 长度为 num_batches 的权重张量
    """
    b_idx = torch.arange(num_batches).float()
    b_norm = b_idx / (num_batches - 1)  # 归一化到 [0,1]

    if mode == "linear":
        # 线性递增
        weights = alpha + (1 - alpha) * b_norm

    elif mode == "exp":
        # 指数增长
        weights = torch.exp(beta * b_norm)
        weights = weights / weights.mean()  # 可选归一化

    elif mode == "piecewise":
        # 前期 alpha，后期 1.0
        weights = torch.ones_like(b_norm)
        cutoff = int(split * num_batches)
        weights[:cutoff] = alpha

    else:
        raise ValueError(f"未知 mode: {mode}")

    return weights

def monthly_acc_all(outputs, batch_y, month_len=20):
    """
    计算三个月度趋势ACC（逐日计算再平均）
    
    Args:
        outputs: Tensor, [N, pred_len] 预测值
        batch_y: Tensor, [N] 真实值
        month_len: int, 每月天数 (默认20)
        
    Returns:
        (ACC_1, ACC_2, ACC_3)
    """
    N = batch_y.shape[0]
    pred_len = outputs.shape[1]   # 假设预测 horizon >= 60
    
    acc1_list, acc2_list, acc3_list = [], [], []

    # 从第21天开始，到倒数60天结束
    for cur in range(month_len, N - 3*month_len):
        # ---- 过去一个月真实均值 ----
        mean_past = batch_y[cur-month_len:cur+1].mean().item()

        # ---- 各个月预测均值 ----
        pred1 = outputs[cur, 0:month_len].mean().item()
        pred2 = outputs[cur, month_len:2*month_len].mean().item()
        pred3 = outputs[cur, 2*month_len:3*month_len].mean().item()

        # ---- 各个月真实均值 ----
        true1 = batch_y[cur:cur+month_len].mean().item()
        true2 = batch_y[cur+month_len:cur+2*month_len].mean().item()
        true3 = batch_y[cur+2*month_len:cur+3*month_len].mean().item()

        # ---- 趋势函数 ----
        def trend(v, base):
            return 1 if v > base else 0  # 1=涨, 0=跌

        # ---- ACC1 ----
        acc1_list.append(1 if trend(true1, mean_past) == trend(pred1, mean_past) else 0)
        # ---- ACC2 ----
        acc2_list.append(1 if trend(true2, true1) == trend(pred2, pred1) else 0)
        # ---- ACC3 ----
        acc3_list.append(1 if trend(true3, true2) == trend(pred3, pred2) else 0)

    ACC_1 = sum(acc1_list) / len(acc1_list)
    ACC_2 = sum(acc2_list) / len(acc2_list)
    ACC_3 = sum(acc3_list) / len(acc3_list)

    return ACC_1, ACC_2, ACC_3

def trend_loss(outputs, batch_y, month_len=20):
    """
    趋势损失 (可导)，近似ACC
    Args:
        outputs: [B, T, C] 模型预测
        batch_y: [B, T, C] 真值
    """
    
    # 历史均值
    mean_past = batch_y[:, :month_len].mean(dim=1)  # [B, C]

    # 月预测均值
    pred1 = outputs[:, :month_len].mean(dim=1)  # [B, C]
    pred2 = outputs[:, month_len:2*month_len].mean(dim=1)
    pred3 = outputs[:, 2*month_len:3*month_len].mean(dim=1)

    # 月真实均值
    true1 = batch_y[:, month_len:2*month_len].mean(dim=1)
    true2 = batch_y[:, 2*month_len:3*month_len].mean(dim=1)
    true3 = batch_y[:, 3*month_len:4*month_len].mean(dim=1)

    # 趋势标签: >0 → 1 (涨), ≤0 → 0 (跌)
    label1 = (true1 - mean_past > 0).float()
    label2 = (true2 - true1 > 0).float()
    label3 = (true3 - true2 > 0).float()

    # 预测趋势分数 (差值作为logit)
    logit1 = pred1 - mean_past
    logit2 = pred2 - pred1
    logit3 = pred3 - pred2

    # BCE Loss
    loss1 = F.binary_cross_entropy_with_logits(logit1, label1)
    loss2 = F.binary_cross_entropy_with_logits(logit2, label2)
    loss3 = F.binary_cross_entropy_with_logits(logit3, label3)

    return (loss1 + loss2 + loss3) / 3

def short_trend_loss(
    outputs,
    batch_y,
    history_y,
    month_len=20,
    month_weights=None,
    max_segments=3,
):
    """
    Short-horizon trend loss.

    The first segment compares the next month prediction with the recent
    history mean, so recent momentum directly affects the direction label.
    """
    if outputs.dim() == 2:
        outputs = outputs.unsqueeze(-1)
    if batch_y.dim() == 2:
        batch_y = batch_y.unsqueeze(-1)
    if history_y.dim() == 2:
        history_y = history_y.unsqueeze(-1)

    if outputs.shape[1] < month_len or history_y.shape[1] == 0:
        return outputs.new_tensor(0.0)

    available_segments = min(outputs.shape[1] // month_len, batch_y.shape[1] // month_len)
    max_segments = min(max(1, int(max_segments)), available_segments)
    if max_segments <= 0:
        return outputs.new_tensor(0.0)

    if month_weights is None:
        month_weights = [1.0] * max_segments
    month_weights = list(month_weights)[:max_segments]
    if len(month_weights) < max_segments:
        month_weights += [month_weights[-1] if month_weights else 1.0] * (max_segments - len(month_weights))

    history_len = min(month_len, history_y.shape[1])
    prev_pred = history_y[:, -history_len:, :].mean(dim=1)
    prev_true = prev_pred
    losses = []
    weights = []
    for segment_idx in range(max_segments):
        start = segment_idx * month_len
        end = start + month_len
        pred_mean = outputs[:, start:end, :].mean(dim=1)
        true_mean = batch_y[:, start:end, :].mean(dim=1)

        label = (true_mean - prev_true > 0).float()
        logit = pred_mean - prev_pred
        losses.append(F.binary_cross_entropy_with_logits(logit, label))
        weights.append(float(month_weights[segment_idx]))

        prev_pred = pred_mean
        prev_true = true_mean

    weight_tensor = torch.tensor(weights, dtype=outputs.dtype, device=outputs.device)
    weight_tensor = weight_tensor / weight_tensor.sum().clamp_min(1e-6)
    stacked = torch.stack(losses)
    return (stacked * weight_tensor).sum()

class Exp_Long_Term_Forecast(Exp_Basic):
    def __init__(self, args):
        super(Exp_Long_Term_Forecast, self).__init__(args)

    def _build_model(self):
        model = self.model_dict[self.args.model].Model(self.args).float()

        if self.args.use_multi_gpu and self.args.use_gpu:
            model = nn.DataParallel(model, device_ids=self.args.device_ids)
        return model

    def _get_data(self, flag):
        data_set, data_loader = data_provider(self.args, flag)
        return data_set, data_loader

    def _select_optimizer(self):
        model_optim = optim.Adam(self.model.parameters(), lr=self.args.learning_rate)
        return model_optim
    
    def _select_criterion(self):
        criterion = nn.MSELoss()
        return criterion
        
    def _select_criterion1(self):
        return nn.MSELoss(reduction='none')

    def _parse_seasonal_loss_months(self):
        if hasattr(self, '_seasonal_loss_months'):
            return self._seasonal_loss_months

        months = []
        for raw_month in str(getattr(self.args, 'seasonal_loss_months', '')).split(','):
            raw_month = raw_month.strip()
            if not raw_month:
                continue
            month = int(raw_month)
            if month < 1 or month > 12:
                raise ValueError(f"seasonal_loss_months contains invalid month: {month}")
            months.append(month)

        self._seasonal_loss_months = sorted(set(months))
        return self._seasonal_loss_months

    def _parse_short_trend_month_weights(self):
        if hasattr(self, '_short_trend_month_weights'):
            return self._short_trend_month_weights

        weights = []
        for raw_weight in str(getattr(self.args, 'short_trend_month_weights', '0.6,0.25,0.15')).split(','):
            raw_weight = raw_weight.strip()
            if raw_weight:
                weights.append(float(raw_weight))
        if not weights:
            weights = [1.0]

        self._short_trend_month_weights = weights
        return self._short_trend_month_weights

    def _target_history_from_batch_x(self, batch_x):
        if self.args.features == 'MS':
            f_dim = -self.args.targetnum
            return batch_x[:, :, f_dim]
        f_dim = -self.args.target_features
        return batch_x[:, :, f_dim:]

    def _get_prediction_months(self, data_set, indices, pred_len):
        month_stamp = getattr(data_set, 'month_stamp', None)
        if month_stamp is None:
            return None

        month_tensor = torch.as_tensor(month_stamp, dtype=torch.long, device=self.device)
        offsets = torch.arange(pred_len, dtype=torch.long, device=self.device)
        positions = indices.long().view(-1, 1) + self.args.seq_len + offsets.view(1, -1)
        positions = positions.clamp(min=0, max=month_tensor.numel() - 1)
        return month_tensor[positions]

    def _sync_indices(self, width):
        all_indices = list(range(width))
        domestic_indices = list(range(min(3, width)))
        imported_indices = list(range(3, min(6, width)))

        anchor_mode = getattr(self.args, 'sync_anchor_mode', 'all_mean')
        align_targets = getattr(self.args, 'sync_align_targets', 'all')

        if anchor_mode == 'domestic_mean':
            anchor_indices = domestic_indices
        elif anchor_mode == 'imported_mean':
            anchor_indices = imported_indices
        else:
            anchor_indices = all_indices

        if align_targets == 'domestic':
            target_indices = domestic_indices
        elif align_targets == 'imported':
            target_indices = imported_indices
        else:
            target_indices = all_indices

        if not anchor_indices:
            anchor_indices = all_indices
        if not target_indices:
            target_indices = all_indices
        return anchor_indices, target_indices

    def _sync_trend_loss(self, outputs):
        if outputs.dim() < 3 or outputs.shape[-1] < 2:
            return outputs.new_tensor(0.0)

        anchor_indices, target_indices = self._sync_indices(outputs.shape[-1])
        trend = outputs - outputs[:, :1, :]
        shared_trend = trend[:, :, anchor_indices].mean(dim=-1, keepdim=True)
        target_trend = trend[:, :, target_indices]
        return F.mse_loss(target_trend, shared_trend.expand_as(target_trend))

    def _apply_short_horizon_weight(self, loss_map):
        if not getattr(self.args, 'use_short_horizon_weight_loss', 0):
            return loss_map

        short_days = int(getattr(self.args, 'short_horizon_weight_days', 30))
        if short_days <= 0 or loss_map.shape[1] <= 0:
            return loss_map

        weight_value = float(getattr(self.args, 'short_horizon_weight', 2.0))
        if weight_value <= 0:
            return loss_map

        horizon_weights = torch.ones(loss_map.shape[1], dtype=loss_map.dtype, device=loss_map.device)
        horizon_weights[:min(short_days, loss_map.shape[1])] = weight_value
        if getattr(self.args, 'short_horizon_weight_normalize', 1):
            horizon_weights = horizon_weights / horizon_weights.mean().clamp_min(1e-6)

        view_shape = [1] * loss_map.dim()
        view_shape[1] = loss_map.shape[1]
        horizon_weights = horizon_weights.view(*view_shape)
        return loss_map * horizon_weights

    def _sync_target_forecast_np(self, preds):
        if not getattr(self.args, 'sync_infer_targets', 0):
            return preds
        if preds is None or preds.ndim < 2 or preds.shape[-1] < 2:
            return preds

        strength = float(getattr(self.args, 'sync_infer_strength', 0.6))
        strength = min(1.0, max(0.0, strength))
        if strength <= 0:
            return preds

        arr = np.asarray(preds, dtype=np.float64)
        squeeze = False
        if arr.ndim == 2:
            arr = arr[None, ...]
            squeeze = True

        anchor_indices, target_indices = self._sync_indices(arr.shape[-1])
        base = arr[:, :1, :]
        if np.any(base <= 0) or np.any(arr <= 0):
            trend = arr - base
            shared = np.nanmean(trend[:, :, anchor_indices], axis=-1, keepdims=True)
            synced = arr.copy()
            synced[:, :, target_indices] = (
                base[:, :, target_indices]
                + (1 - strength) * trend[:, :, target_indices]
                + strength * shared
            )
        else:
            log_rel = np.log(np.clip(arr / base, 1e-9, None))
            shared = np.nanmean(log_rel[:, :, anchor_indices], axis=-1, keepdims=True)
            synced = arr.copy()
            synced_log_rel = (
                (1 - strength) * log_rel[:, :, target_indices]
                + strength * shared
            )
            synced[:, :, target_indices] = np.exp(synced_log_rel) * base[:, :, target_indices]

        synced[:, 0, :] = arr[:, 0, :]
        if squeeze:
            synced = synced[0]
        return synced.astype(preds.dtype, copy=False)

    def _forecast_loss(self, outputs, batch_y, data_set=None, indices=None, batch_weight=None):
        loss_name = str(getattr(self.args, 'forecast_loss', 'mse')).lower()
        if loss_name == 'huber':
            loss_map = F.smooth_l1_loss(
                outputs,
                batch_y,
                reduction='none',
                beta=float(getattr(self.args, 'huber_delta', 1.0)),
            )
        elif loss_name == 'mae':
            loss_map = F.l1_loss(outputs, batch_y, reduction='none')
        else:
            loss_map = F.mse_loss(outputs, batch_y, reduction='none')

        if getattr(self.args, 'use_seasonal_loss', 0) and data_set is not None and indices is not None:
            pred_months = self._get_prediction_months(data_set, indices, outputs.shape[1])
            months = self._parse_seasonal_loss_months()
            if pred_months is not None and months:
                month_mask = torch.zeros_like(pred_months, dtype=torch.bool)
                for month in months:
                    month_mask |= pred_months == month

                weights = torch.ones_like(pred_months, dtype=loss_map.dtype, device=loss_map.device)
                weights = torch.where(
                    month_mask,
                    torch.full_like(weights, float(self.args.seasonal_loss_weight)),
                    weights,
                )
                if getattr(self.args, 'seasonal_loss_normalize', 1):
                    weights = weights / weights.mean().clamp_min(1e-6)

                while weights.dim() < loss_map.dim():
                    weights = weights.unsqueeze(-1)
                loss_map = loss_map * weights

        loss_map = self._apply_short_horizon_weight(loss_map)
        loss = loss_map.mean()
        if getattr(self.args, 'use_sync_loss', 0):
            loss = loss + float(getattr(self.args, 'sync_loss_weight', 0.05)) * self._sync_trend_loss(outputs)
        if batch_weight is not None:
            loss = loss * batch_weight
        return loss

    def _make_mark_tensor(self, data_set, start, end):
        data_stamp = getattr(data_set, 'data_stamp', None)
        if data_stamp is None:
            return None
        mark_data = data_stamp[start:end]
        return torch.tensor(mark_data, dtype=torch.float32).unsqueeze(0).to(self.device)

 

    def vali(self, vali_data, vali_loader, criterion):
        total_loss = []
        self.model.eval()
        with torch.no_grad():
            for i, (batch_x, batch_y, batch_x_mark, batch_y_mark, indices) in enumerate(vali_loader):
                batch_x = batch_x.float().to(self.device)
                batch_y = batch_y.float()

                batch_x_mark = batch_x_mark.float().to(self.device)
                batch_y_mark = batch_y_mark.float().to(self.device)

                # decoder input
                dec_inp = torch.zeros(
                    (batch_y.shape[0], self.args.pred_len, batch_y.shape[-1]),
                    dtype=batch_y.dtype,
                    device=self.device,
                )
                dec_inp = torch.cat([batch_y[:, :self.args.label_len, :], dec_inp], dim=1).float().to(self.device)
                # encoder - decoder
                if self.args.use_amp:
                    with get_autocast_context(self.device):
                        outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                else:
                    outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                #f_dim = -1 if self.args.features == 'MS' else 0
                if self.args.features == 'MS' :
                    eval_pred_len = min(
                        getattr(self.args, 'eval_pred_len', 0) or self.args.pred_len,
                        outputs.shape[1],
                        max(0, batch_y.shape[1] - self.args.label_len),
                    )
                    f_dim=-self.args.targetnum
                    outputs = outputs[:, :eval_pred_len, f_dim]
                    batch_y = batch_y[:, -eval_pred_len:, f_dim].to(self.device)
                else:
                    eval_pred_len = min(
                        getattr(self.args, 'eval_pred_len', 0) or self.args.pred_len,
                        outputs.shape[1],
                        max(0, batch_y.shape[1] - self.args.label_len),
                    )
                    f_dim=-self.args.target_features
                    outputs = outputs[:, :eval_pred_len, f_dim:]
                    batch_y = batch_y[:, -eval_pred_len:, f_dim:].to(self.device)
                '''   
                f_dim = -1 if self.args.features == 'MS' else -self.args.target_features
                outputs = outputs[:, -self.args.pred_len:, f_dim:]
                batch_y = batch_y[:, -self.args.pred_len:, f_dim:].to(self.device)
                '''

                pred = outputs.detach()
                true = batch_y.detach()
                loss = self._forecast_loss(pred, true)
                
                '''
                if self.args.use_weighted_loss:
                    B, T, C = pred.shape
                    weights = make_weights(T, mode=self.args.loss_weight_mode, alpha=self.args.loss_weight_alpha, split=self.args.loss_weight_split).to(pred.device)
                    # print(weights)
                    loss = torch.mean(weights * criterion(pred, true))
                else:
                    loss = criterion(pred, true)
                '''
            
                total_loss.append(loss.item())
        total_loss = np.average(total_loss)
        self.model.train()
        return total_loss

    def train(self, setting):
        train_data, train_loader = self._get_data(flag='train')
        vali_data, vali_loader = self._get_data(flag='val')
        if self.args.is_testing:
            test_data, test_loader = self._get_data(flag='test')
        #test_data, test_loader = self._get_data(flag='train')
        '''
        N = len(train_data)  # 训练集总样本数
        all_weights = make_weights(N, mode=self.args.loss_weight_mode,
                                alpha=self.args.loss_weight_alpha,
                                split=self.args.loss_weight_split).to(self.device)
        
        print(all_weights)
        all_weights = all_weights / all_weights.sum()
        print(all_weights.shape)
        print(all_weights)
        '''

        path = os.path.join(self.args.checkpoints, setting)
        if not os.path.exists(path):
            os.makedirs(path)

        time_now = time.time()

        train_steps = len(train_loader)
        batch_weights = make_batch_weights(train_steps, mode=self.args.loss_weight_mode,
                                alpha=self.args.loss_weight_alpha,
                                split=self.args.loss_weight_split).to(self.device) # train_steps=batch_num
        #print(batch_weights)
        early_stopping = EarlyStopping(patience=self.args.patience, verbose=True)

        model_optim = self._select_optimizer()
        criterion = self._select_criterion()

        if self.args.use_amp:
            scaler = get_grad_scaler(self.device)
        else:
            scaler = None

        for epoch in range(self.args.train_epochs):
            iter_count = 0
            train_loss = []

            self.model.train()
            epoch_time = time.time()
            for i, (batch_x, batch_y, batch_x_mark, batch_y_mark, indices) in enumerate(train_loader):
                iter_count += 1
                model_optim.zero_grad()
                batch_x = batch_x.float().to(self.device)
                batch_y = batch_y.float().to(self.device)
                batch_x_mark = batch_x_mark.float().to(self.device)
                batch_y_mark = batch_y_mark.float().to(self.device)

                indices = indices.to(self.device)  # 当前 batch 在整个训练集的索引

                '''
                if i == 1 :
                    print("x shape:",batch_x.shape)
                    print("y shape:",batch_y.shape)
                    print("x mark shape:",batch_x_mark.shape)
                    print("y mark shape:",batch_y_mark.shape)
                '''

                # decoder input
                dec_inp = torch.zeros_like(batch_y[:, -self.args.pred_len:, :]).float()
                dec_inp = torch.cat([batch_y[:, :self.args.label_len, :], dec_inp], dim=1).float().to(self.device)
                
                # encoder - decoder
                if self.args.use_amp:
                    with get_autocast_context(self.device):
                        outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)

                        if self.args.features == 'MS':
                            f_dim = -self.args.targetnum
                            outputs = outputs[:, -self.args.pred_len:, f_dim]
                            batch_y = batch_y[:, -self.args.pred_len:, f_dim].to(self.device)
                        else:
                            f_dim = -self.args.target_features
                            outputs = outputs[:, -self.args.pred_len:, f_dim:]
                            batch_y = batch_y[:, -self.args.pred_len:, f_dim:].to(self.device)

                        batch_weight = batch_weights[i] if self.args.use_weighted_loss else None
                        loss = self._forecast_loss(outputs, batch_y, train_data, indices, batch_weight)
                        if self.args.use_acc_loss:
                            loss = loss + self.args.acc_loss_weight * trend_loss(outputs, batch_y)
                        if getattr(self.args, 'use_short_trend_loss', 0):
                            history_y = self._target_history_from_batch_x(batch_x)
                            loss = loss + self.args.short_trend_loss_weight * short_trend_loss(
                                outputs,
                                batch_y,
                                history_y,
                                getattr(self.args, 'short_trend_month_len', 20),
                                self._parse_short_trend_month_weights(),
                                getattr(self.args, 'short_trend_max_segments', 3),
                            )
                        train_loss.append(loss.item())
                else:
                    #outputs,trend_logits = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                    outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                    #f_dim = -1 if self.args.features == 'MS' else 0
                    
                    if self.args.features == 'MS' :
                        f_dim=-self.args.targetnum
                        outputs = outputs[:, -self.args.pred_len:, f_dim]
                        batch_y = batch_y[:, -self.args.pred_len:, f_dim].to(self.device)
                    else:
                        f_dim=-self.args.target_features
                        outputs = outputs[:, -self.args.pred_len:, f_dim:]
                        batch_y = batch_y[:, -self.args.pred_len:, f_dim:].to(self.device)
                        
                    '''
                    f_dim = -1 if self.args.features == 'MS' else -self.args.target_features
                    outputs = outputs[:, -self.args.pred_len:, f_dim:]
                    batch_y = batch_y[:, -self.args.pred_len:, f_dim:].to(self.device)
                    '''
                    '''
                    if self.args.use_weighted_loss:
                        #print("数据集添加权重成功")
                        B, T, C = outputs.shape
                        weights = make_weights(T, mode=self.args.loss_weight_mode, alpha=self.args.loss_weight_alpha, split=self.args.loss_weight_split).to(outputs.device)
                        loss = torch.mean(weights * criterion(outputs, batch_y))
                    else:
                        loss = criterion(outputs, batch_y)
                    '''
                    # 全局权重
                    batch_weight = batch_weights[i] if self.args.use_weighted_loss else None
                    loss = self._forecast_loss(outputs, batch_y, train_data, indices, batch_weight)

                    if self.args.use_acc_loss:
                        #print("use_acc_loss = true")
                        #print("acc_loss_weight = ", self.args.acc_loss_weight)
                        loss = loss + self.args.acc_loss_weight * trend_loss(outputs, batch_y)
                    if getattr(self.args, 'use_short_trend_loss', 0):
                        history_y = self._target_history_from_batch_x(batch_x)
                        loss = loss + self.args.short_trend_loss_weight * short_trend_loss(
                            outputs,
                            batch_y,
                            history_y,
                            getattr(self.args, 'short_trend_month_len', 20),
                            self._parse_short_trend_month_weights(),
                            getattr(self.args, 'short_trend_max_segments', 3),
                        )
                    
                    train_loss.append(loss.item())

                if (i + 1) % 100 == 0:
                    print("\titers: {0}, epoch: {1} | loss: {2:.7f}".format(i + 1, epoch + 1, loss.item()))
                    speed = (time.time() - time_now) / iter_count
                    left_time = speed * ((self.args.train_epochs - epoch) * train_steps - i)
                    print('\tspeed: {:.4f}s/iter; left time: {:.4f}s'.format(speed, left_time))
                    iter_count = 0
                    time_now = time.time()

                if self.args.use_amp:
                    scaler.scale(loss).backward()
                    scaler.step(model_optim)
                    scaler.update()
                else:
                    loss.backward()
                    model_optim.step()

            print("Epoch: {} cost time: {}".format(epoch + 1, time.time() - epoch_time))
            train_loss = np.average(train_loss)
            if len(vali_loader) > 0:
                vali_loss = self.vali(vali_data, vali_loader, criterion)
            else:
                vali_loss = train_loss
                print("[WARN] Vali loader is empty; using train loss for checkpoint selection.")
            if self.args.is_testing:
                if len(test_loader) > 0:
                    test_loss = self.vali(test_data, test_loader, criterion)
                else:
                    test_loss = float('nan')
                    print("[WARN] Test loader is empty; skip test loss.")
                print("Epoch: {0}, Steps: {1} | Train Loss: {2:.7f} Vali Loss: {3:.7f} Test Loss: {4:.7f}".format(
                    epoch + 1, train_steps, train_loss, vali_loss, test_loss))
            else:
                print("Epoch: {0}, Steps: {1} | Train Loss: {2:.7f} Vali Loss: {3:.7f}".format(
                    epoch + 1, train_steps, train_loss, vali_loss))
            early_stopping(vali_loss, self.model, path)
            if early_stopping.early_stop:
                print("Early stopping")
                break

            adjust_learning_rate(model_optim, epoch + 1, self.args)

        best_model_path = path + '/' + 'checkpoint.pth'
        self.model.load_state_dict(torch.load(best_model_path))

        return self.model
    
    def predict2(self, setting):
        #获取数据
        print("predict begin")
        test_data, test_loader = self._get_data(flag='test')
        data_x = getattr(test_data, 'data_x', None)
        data_y = getattr(test_data, 'data_y', None)

        print(f"[Predict] Input data shape: {data_x.shape, data_y.shape}")  # (40, 101) 例如

        if data_x.shape[0] < self.args.seq_len:
            raise ValueError(f"数据行数不足 seq_len={self.args.seq_len}")
        
        # 2. 取最后 seq_len 行作为输入
        if self.args.last_ten:
            input_data = data_x[-(self.args.seq_len+30):-30]
        else:
            input_data = data_x[-self.args.seq_len:]
        input_tensor = torch.tensor(input_data, dtype=torch.float32).unsqueeze(0).to(self.device)  # [1, seq_len, enc_in]
        
        # 3. 加载模型 checkpoint
        checkpoint_path = os.path.join('./checkpoints/', setting, 'checkpoint.pth')
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device))
        self.model.eval()

        # 4. 推理
        with torch.no_grad():
            '''
            dec_inp = torch.zeros((1, self.args.pred_len, input_tensor.shape[-1]), dtype=torch.float32).to(self.device)
            # 如果模型需要 label_len 的开头，可以用 zeros 或者 input_data[-label_len:]
            '''
            # 如果有label_len，需要构造相同的decoder输入
            dec_inp_start = torch.zeros((1, self.args.label_len, input_tensor.shape[-1])).to(self.device)
            dec_inp_zeros = torch.zeros((1, self.args.pred_len, input_tensor.shape[-1])).to(self.device)
            dec_inp = torch.cat([dec_inp_start, dec_inp_zeros], dim=1)
            #dec_inp_start = input_tensor[:, -self.args.label_len:, :].clone()
            #dec_inp_zeros = torch.zeros((1, self.args.pred_len, input_tensor.shape[-1])).to(self.device)
            #dec_inp = torch.cat([dec_inp_start, dec_inp_zeros], dim=1)


            outputs = self.model(input_tensor, None, dec_inp, None)  # 注意这里根据你的模型接口调整
        #preds = outputs.squeeze(0).cpu().numpy()  # [pred_len, c_out]
        outputs = outputs.cpu().numpy().squeeze(0)  # [pred_len]
        outputs = test_data.inverse_transform(outputs)
        ot_index = self.args.target_features
        preds = outputs[:, -ot_index:]  # [pred_len]
        
        
        
        print(preds.shape)

        # 5. 保存结果
        os.makedirs('./predict_result', exist_ok=True)
        save_path =self.args.csv_path
        pds.DataFrame(preds).to_csv(save_path, index=False,header=False)
        print(f"[Predict] 保存预测结果到 {save_path}")
    
    
    def predict(self, setting):
        import pandas as pds
        import torch
        import os
        
        print("predict begin")
        # 获取数据
        test_data, test_loader = self._get_data(flag='test')
        data_x = getattr(test_data, 'data_x', None)
        data_y = getattr(test_data, 'data_y', None)

        print(f"[Predict] Input data shape: {data_x.shape, data_y.shape}")

        if data_x.shape[0] < self.args.seq_len:
            raise ValueError(f"数据行数不足 seq_len={self.args.seq_len}")

        # ---------- 阶段 1：预测最新一天 + 未来59天 ----------
        use_seasonal_predict = getattr(self.args, 'use_month_onehot', 0)
        if use_seasonal_predict and self.args.last_ten:
            input_start = data_x.shape[0] - self.args.seq_len - 30
            input_end = data_x.shape[0] - 30
        else:
            input_start = data_x.shape[0] - self.args.seq_len
            input_end = data_x.shape[0]
        if input_start < 0:
            raise ValueError(f"not enough rows for seq_len={self.args.seq_len}, last_ten={self.args.last_ten}")
        input_data = data_x[input_start:input_end]
        input_mark = self._make_mark_tensor(test_data, input_start, input_end) if use_seasonal_predict else None
        input_tensor = torch.tensor(input_data, dtype=torch.float32).unsqueeze(0).to(self.device)

        checkpoint_path = os.path.join('./checkpoints/', setting, 'checkpoint.pth')
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device))
        self.model.eval()

        with torch.no_grad():
            dec_inp_start = torch.zeros((1, self.args.label_len, input_tensor.shape[-1])).to(self.device)
            dec_inp_zeros = torch.zeros((1, self.args.pred_len, input_tensor.shape[-1])).to(self.device)
            dec_inp = torch.cat([dec_inp_start, dec_inp_zeros], dim=1)

            outputs = self.model(input_tensor, input_mark, dec_inp, None)

        outputs = outputs.cpu().numpy().squeeze(0)  # [pred_len, c_out]
        outputs_inv = test_data.inverse_transform(outputs)  # 反归一化
        preds_stage1 = outputs_inv[:, -self.args.target_features:]  # 目标特征

        # 找到真实的“最新一天”的真实值（反归一化）
        delta=0
        if self.args.delt==1:
            true_last = test_data.inverse_transform(data_y[-1:])[:, -self.args.target_features:]  # shape (1, c)
            pred_last = preds_stage1[0:1, :]  # shape (1, c)
            delta = true_last - pred_last  # 预测与真实差值
            
            print(true_last,pred_last)
            print(f"[Predict] 差值 delta = {delta.flatten()}")

        # ---------- 阶段 2：预测未来60天 ----------
        with torch.no_grad():
            outputs2 = self.model(input_tensor, input_mark, dec_inp, None)
        outputs2 = outputs2.cpu().numpy().squeeze(0)
        outputs2_inv = test_data.inverse_transform(outputs2)
        preds_stage2 = outputs2_inv[:, -self.args.target_features:]

        # 叠加偏差修正
        preds_corrected = preds_stage2 + delta
        preds_corrected = self._sync_target_forecast_np(preds_corrected)

        print(f"[Predict] 修正后预测 shape = {preds_corrected.shape}")

        # ---------- 保存结果 ----------
        os.makedirs('./predict_result', exist_ok=True)
        save_path = self.args.csv_path
        pds.DataFrame(preds_corrected).to_csv(save_path, index=False, header=False)
        print(f"[Predict] 保存预测结果到 {save_path}")


    def predict_batch(self, setting):
        #获取数据
        test_data, test_loader = self._get_data(flag='test')
        data_x = getattr(test_data, 'data_x', None)
        data_y = getattr(test_data, 'data_y', None)

        print(f"[Predict] Input data shape: {data_x.shape, data_y.shape}")  # (40, 101) 例如

        if data_x.shape[0] < self.args.seq_len:
            raise ValueError(f"数据行数不足 seq_len={self.args.seq_len}")
        
        # 2. 取最后 seq_len 行作为输入
        input_data = data_x[-self.args.seq_len-self.args.batch_size+1:]
        total_timesteps = input_data.shape[0]
        num_samples = total_timesteps - self.args.seq_len + 1
    
        result = np.array([input_data[i:i + self.args.seq_len] for i in range(num_samples)])
        input_tensor = torch.tensor(result, dtype=torch.float32).to(self.device)  # [batch_size, seq_len, enc_in]
        
        # 3. 加载模型 checkpoint
        checkpoint_path = os.path.join('./checkpoints/', setting, 'checkpoint.pth')
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device))
        self.model.eval()

        # 4. 推理
        with torch.no_grad():
            '''
            dec_inp = torch.zeros((1, self.args.pred_len, input_tensor.shape[-1]), dtype=torch.float32).to(self.device)
            # 如果模型需要 label_len 的开头，可以用 zeros 或者 input_data[-label_len:]
            '''
            # 如果有label_len，需要构造相同的decoder输入
            dec_inp_start = torch.zeros((self.args.batch_size, self.args.label_len, input_tensor.shape[-1])).to(self.device)
            dec_inp_zeros = torch.zeros((self.args.batch_size, self.args.pred_len, input_tensor.shape[-1])).to(self.device)
            dec_inp = torch.cat([dec_inp_start, dec_inp_zeros], dim=1)

            outputs = self.model(input_tensor, None, dec_inp, None)  # 注意这里根据你的模型接口调整
        #preds = outputs.squeeze(0).cpu().numpy()  # [pred_len, c_out]
        outputs = outputs.cpu().numpy()  # [batch_size,pred_len,cout]
        if test_data.scale and self.args.inverse:
            shape = outputs.shape
            outputs = test_data.inverse_transform(outputs.reshape(shape[0] * shape[1], -1)).reshape(shape)
        ot_index = self.args.target_features
        preds = outputs[-1, :, -ot_index:]  # [pred_len]
        

        # 5. 保存结果
        
        os.makedirs('./predict_result', exist_ok=True)
        save_path =self.args.csv_path
        pds.DataFrame(preds).to_csv(save_path, index=False,header=False)
        print(f"[Predict] 保存预测结果到 {save_path}")
        

    '''
    
    def predict(self, setting):
        # 获取数据
        test_data, test_loader = self._get_data(flag='test')
        data_x = getattr(test_data, 'data_x', None)
        data_y = getattr(test_data, 'data_y', None)

        print(f"[Predict] Input data shape: {data_x.shape, data_y.shape}")

        if data_x.shape[0] < self.args.seq_len:
            raise ValueError(f"数据行数不足 seq_len={self.args.seq_len}")
        
        # 加载模型 checkpoint
        checkpoint_path = os.path.join('./checkpoints/', setting, 'checkpoint.pth')
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device))
        self.model.eval()

        # 确定batch_size，如果没有设置则使用默认值
        batch_size = getattr(self.args, 'batch_size', 32)
        
        # 创建数据批次
        total_samples = data_x.shape[0] - self.args.seq_len + 1
        all_preds = []
        
        print(f"[Predict] 总样本数: {total_samples}, batch_size: {batch_size}")
        
        # 分batch进行推理
        with torch.no_grad():
            for i in range(0, total_samples, batch_size):
                batch_end = min(i + batch_size, total_samples)
                batch_inputs = []
                
                # 准备当前batch的数据
                for j in range(i, batch_end):
                    seq_begin = j
                    seq_end = j + self.args.seq_len
                    input_seq = data_x[seq_begin:seq_end]
                    batch_inputs.append(input_seq)
                
                if not batch_inputs:
                    continue
                    
                # 将batch数据转换为tensor [batch_size, seq_len, enc_in]
                input_tensor = torch.tensor(np.array(batch_inputs), dtype=torch.float32).to(self.device)
                
                # 准备decoder输入
                dec_inp = torch.zeros((input_tensor.shape[0], self.args.pred_len, input_tensor.shape[-1]), 
                                    dtype=torch.float32).to(self.device)
                
                # 模型推理
                outputs = self.model(input_tensor, None, dec_inp, None)
                
                # 处理输出
                batch_preds = outputs.cpu().numpy()  # [batch_size, pred_len, c_out]
                
                # 逆变换
                for k in range(batch_preds.shape[0]):
                    single_pred = batch_preds[k]  # [pred_len, c_out]
                    single_pred = test_data.inverse_transform(single_pred)
                    ot_index = self.args.target_features
                    single_pred = single_pred[:, -ot_index:]  # [pred_len]
                    all_preds.append(single_pred)
                
                print(f"[Predict] 处理批次 {i//batch_size + 1}/{(total_samples-1)//batch_size + 1}")
        
        # 合并所有预测结果
        if all_preds:
            # 如果只需要最后seq_len的预测，取最后pred_len个时间步
            if getattr(self.args, 'only_last_sequence', True):
                final_preds = all_preds[-1]  # 只取最后一个序列的预测
            else:
                final_preds = np.concatenate(all_preds, axis=0)
        else:
            final_preds = np.array([])
        
        print(f"[Predict] 最终预测结果形状: {final_preds.shape}")

        # 保存结果
        os.makedirs('./predict_result', exist_ok=True)
        save_path = self.args.csv_path
        pds.DataFrame(final_preds).to_csv(save_path, index=False, header=False)
        print(f"[Predict] 保存预测结果到 {save_path}")
    '''
    
    def predict_old(self, setting):

        # 🔹 1. 读取输入 CSV（去掉表头）
        
        df = pds.read_csv(self.args.root_path+self.args.data_path, header=0)  # header=0 读表头，但不使用
        df_values = df.iloc[:, 1:].apply(pds.to_numeric, errors='coerce').fillna(0).values.astype(np.float32)
        print(f"[Predict] Input data shape: {df_values.shape}")  # (40, 101) 例如

        if df_values.shape[0] < self.args.seq_len:
            raise ValueError(f"数据行数不足 seq_len={self.args.seq_len}")

        # 2. 取最后 seq_len 行作为输入
        input_data = df_values[-self.args.seq_len:]
        input_tensor = torch.tensor(input_data, dtype=torch.float32).unsqueeze(0).to(self.device)  # [1, seq_len, enc_in]
        
        # 3. 加载模型 checkpoint
        checkpoint_path = os.path.join('./checkpoints/', setting, 'checkpoint.pth')
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device))
        self.model.eval()

        # 4. 推理
        with torch.no_grad():
            dec_inp = torch.zeros((1, self.args.pred_len, input_tensor.shape[-1]), dtype=torch.float32).to(self.device)
            # 如果模型需要 label_len 的开头，可以用 zeros 或者 input_data[-label_len:]
            outputs = self.model(input_tensor, None, dec_inp, None)  # 注意这里根据你的模型接口调整
        preds = outputs.squeeze(0).cpu().numpy()  # [pred_len, c_out]
        print(outputs.shape)
        ot_index = self.args.target_features
        preds = outputs[:, :, -3].cpu().numpy().squeeze(0)  # [pred_len]
        print(preds.shape)

        # 5. 保存结果
        os.makedirs('./predict_result', exist_ok=True)
        save_path =self.args.csv_path
        pds.DataFrame(preds).to_csv(save_path, index=False,header=False)
        print(f"[Predict] 保存预测结果到 {save_path}")


    def test(self, setting, test=0):
        test_data, test_loader = self._get_data(flag='test')
        #test_data, test_loader = self._get_data(flag='train')
        if test:
            print('loading model')
            self.model.load_state_dict(torch.load(os.path.join('./checkpoints/' + setting, 'checkpoint.pth')))

        preds = []
        trues = []
        folder_path = './test_results/' + setting + '/'
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        self.model.eval()
        with torch.no_grad():
            for i, (batch_x, batch_y, batch_x_mark, batch_y_mark, indices) in enumerate(test_loader):
                
                batch_x = batch_x.float().to(self.device)
                batch_y = batch_y.float().to(self.device)

                batch_x_mark = batch_x_mark.float().to(self.device)
                batch_y_mark = batch_y_mark.float().to(self.device)

                # decoder input
                dec_inp = torch.zeros_like(batch_y[:, -self.args.pred_len:, :]).float()
                dec_inp = torch.cat([batch_y[:, :self.args.label_len, :], dec_inp], dim=1).float().to(self.device)
                # encoder - decoder
                if self.args.use_amp:
                    with get_autocast_context(self.device):
                        outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                else:
                    #outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                    outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)

                #f_dim = -1 if self.args.features == 'MS' else 0
                
                    
                f_dim = -self.args.targetnum if self.args.features == 'MS' else -self.args.target_features
                outputs = outputs[:, -self.args.pred_len:, :]
                batch_y = batch_y[:, -self.args.pred_len:, :].to(self.device)
                
                outputs = outputs.detach().cpu().numpy()
                batch_y = batch_y.detach().cpu().numpy()
                if test_data.scale and self.args.inverse:
                    shape = batch_y.shape
                    if outputs.shape[-1] != batch_y.shape[-1]:
                        outputs = np.tile(outputs, [1, 1, int(batch_y.shape[-1] / outputs.shape[-1])])
                    outputs = test_data.inverse_transform(outputs.reshape(shape[0] * shape[1], -1)).reshape(shape)
                    batch_y = test_data.inverse_transform(batch_y.reshape(shape[0] * shape[1], -1)).reshape(shape)
                    

                
                outputs = outputs[:, :, f_dim:]
                batch_y = batch_y[:, :, f_dim:]
                outputs = self._sync_target_forecast_np(outputs)

                pred = outputs
                true = batch_y
                
                #print('test shape:', pred.shape, true.shape)

                preds.append(pred)
                trues.append(true)
                if i % 20 == 0:
                    input = batch_x.detach().cpu().numpy()
                    if test_data.scale and self.args.inverse:
                        shape = input.shape
                        input = test_data.inverse_transform(input.reshape(shape[0] * shape[1], -1)).reshape(shape)
                    gt = np.concatenate((input[0, :, -1], true[0, :, -1]), axis=0)
                    pd = np.concatenate((input[0, :, -1], pred[0, :, -1]), axis=0)
                    visual(gt, pd, os.path.join(folder_path, str(i) + '.pdf'))

        preds = np.concatenate(preds, axis=0)
        trues = np.concatenate(trues, axis=0)
        print('test shape:', preds.shape, trues.shape)
        preds = preds.reshape(-1, preds.shape[-2], preds.shape[-1])
        trues = trues.reshape(-1, trues.shape[-2], trues.shape[-1])
        print('test shape:', preds.shape, trues.shape)

        # result save
        folder_path = './results/' + setting + '/'
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        # dtw calculation
        if self.args.use_dtw:
            dtw_list = []
            manhattan_distance = lambda x, y: np.abs(x - y)
            for i in range(preds.shape[0]):
                x = preds[i].reshape(-1, 1)
                y = trues[i].reshape(-1, 1)
                if i % 100 == 0:
                    print("calculating dtw iter:", i)
                d, _, _, _ = accelerated_dtw(x, y, dist=manhattan_distance)
                dtw_list.append(d)
            dtw = np.array(dtw_list).mean()
        else:
            dtw = 'Not calculated'

        #mae, mse, rmse, mape_5, mape_10, mspe = metric(preds, trues)
        
        #print(trues.shape)
        score_import=[]
        score_local=[]
        for target in range(0,self.args.target_features):
            
            preds_np = preds[:, :, target]  # shape: [N, 10]
            trues_np = trues[:, 0, target]  # shape: [N]，只取第一个时间点的真实值
            #print("shape:",preds[...,[target]].shape)
            #print("trueshape:",trues_np[...,[target]])
            mae, mse, rmse, mape_5, mape_10, mspe = metric(preds[...,[target]], trues[...,[target]])

            # 构造列名
            columns = ['true'] + [f'pred_day{i+1}' for i in range(preds_np.shape[1])]

            # 构造数据：第一列是真值，后十列是预测
            data = np.concatenate([trues_np.reshape(-1, 1), preds_np], axis=1)
        
            # 构造 DataFrame 并保存
            df_export = pds.DataFrame(data, columns=columns)
            os.makedirs('pre_result', exist_ok=True)

            # 替换原来的保存代码：
            csv_path = self.args.csv_path +str(target)
            df_export.to_csv(csv_path, index=False)
            print(f"[INFO] 预测窗口结果已保存到: {csv_path}")
            
            print('mse:{}, mae:{}, mape_5:{}, mape_10:{}, dtw:{}'.format(mse, mae, mape_5, mape_10, dtw))
            
            print("第",target+1,"个指数：")
            acc_1, acc_2, acc_3=acc_cal(csv_path,trues_np.shape[0]-self.args.pred_len)
            df = pds.read_csv(csv_path, header=0)
            length = df.shape[0] - 60 - 5 # 表格行数（去除表头）-60
            acc_week_list = acc_week_cal(csv_path,length)
            print("周ACC：")
            # print(acc_week_list[0])
            for i in range(0, len(acc_week_list), 6):  
                line = []
                for j, acc in enumerate(acc_week_list[i:i+6], start=i+1):
                    line.append(f"ACC_{j}={acc*100:.4g}%")
                print("  ".join(line))
            print("月ACC：")
            # print(acc_1)
            print(f"acc_1: {acc_1:.2%}, acc_2:{acc_2:.2%}, acc_3:{acc_3:.2%}")
            if self.args.trans:
                score=calc_score_freight(mape_5, mape_10, acc_1, acc_2, acc_3, acc_week_list)
            else:
                score = calc_score(mape_5, mape_10, acc_1, acc_2, acc_3, acc_week_list)
            if target < 3 :
                score_local.append(score)
            if target > 3 and target < 6:
                score_import.append(score)
        
        
        avg_import = np.mean([s["Total_score"] for s in score_import])
        avg_local = np.mean([s["Total_score"] for s in score_local])
        print(f"根据模型验收标准，小模型一（进口煤价格预测）得分为：{avg_import:.2f}")
        print(f"根据模型验收标准，小模型二（国内北港煤价预测）得分为：{avg_local:.2f}")
        

        f = open("result_long_term_forecast.txt", 'a')
        f.write(setting + "  \n")
        f.write('mse:{}, mae:{}, mape_5:{}, mape_10:{}, dtw:{}'.format(mse, mae, mape_5, mape_10, dtw))
        f.write('\n')
        f.write('\n')
        f.close()

        np.save(folder_path + 'metrics.npy', np.array([mae, mse, rmse, mape_5, mape_10, mspe]))
        np.save(folder_path + 'pred.npy', preds)
        np.save(folder_path + 'true.npy', trues)

        return

    def test_for_predict(self, setting, test=0):
        test_data, test_loader = self._get_data(flag='test')
        #test_data, test_loader = self._get_data(flag='train')
        if test:
            print('loading model')
            self.model.load_state_dict(torch.load(os.path.join('./checkpoints/' + setting, 'checkpoint.pth')))

        preds = []
        folder_path = './test_results/' + setting + '/'
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        self.model.eval()
        with torch.no_grad():
            for i, (batch_x, batch_y, batch_x_mark, batch_y_mark, indices) in enumerate(test_loader):
                print(i)
                batch_x = batch_x.float().to(self.device)
                batch_y = batch_y.float().to(self.device)

                batch_x_mark = batch_x_mark.float().to(self.device)
                batch_y_mark = batch_y_mark.float().to(self.device)
                
                # decoder input
                dec_inp = torch.zeros_like(batch_y[:, -self.args.pred_len:, :]).float()
                dec_inp = torch.cat([batch_y[:, :self.args.label_len, :], dec_inp], dim=1).float().to(self.device)
                # encoder - decoder
                if self.args.use_amp:
                    with get_autocast_context(self.device):
                        outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                else:
                    #outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                    outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)

                #f_dim = -1 if self.args.features == 'MS' else 0
                
                    
                f_dim = -self.args.targetnum if self.args.features == 'MS' else -self.args.target_features
                outputs = outputs[:, -self.args.pred_len:, :]
                batch_y = batch_y[:, -self.args.pred_len:, :].to(self.device)
                
                outputs = outputs.detach().cpu().numpy()
                batch_y = batch_y.detach().cpu().numpy()
                if test_data.scale and self.args.inverse:
                    shape = batch_y.shape
                    #if outputs.shape[-1] != batch_y.shape[-1]:
                        #outputs = np.tile(outputs, [1, 1, int(batch_y.shape[-1] / outputs.shape[-1])])
                    outputs = test_data.inverse_transform(outputs.reshape(shape[0] * shape[1], -1)).reshape(shape)
                    #batch_y = test_data.inverse_transform(batch_y.reshape(shape[0] * shape[1], -1)).reshape(shape)
                    

                
                outputs = outputs[:, :, f_dim:]
                outputs = self._sync_target_forecast_np(outputs)
                #batch_y = batch_y[:, :, f_dim:]

                pred = outputs
                #true = batch_y
                
                #print('test shape:', pred.shape, true.shape)

                preds.append(pred)
                #trues.append(true)
                '''
                if i % 20 == 0:
                    input = batch_x.detach().cpu().numpy()
                    if test_data.scale and self.args.inverse:
                        shape = input.shape
                        input = test_data.inverse_transform(input.reshape(shape[0] * shape[1], -1)).reshape(shape)
                    gt = np.concatenate((input[0, :, -1], true[0, :, -1]), axis=0)
                    pd = np.concatenate((input[0, :, -1], pred[0, :, -1]), axis=0)
                    visual(gt, pd, os.path.join(folder_path, str(i) + '.pdf'))
                '''
        preds = np.concatenate(preds, axis=0)
        #trues = np.concatenate(trues, axis=0)
        print('test shape:', preds.shape)
        preds = preds.reshape(-1, preds.shape[-2], preds.shape[-1])
        #trues = trues.reshape(-1, trues.shape[-2], trues.shape[-1])
        print('test shape:', preds.shape)

        # result save
        folder_path = './results/' + setting + '/'
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        # dtw calculation
        '''
        if self.args.use_dtw:
            dtw_list = []
            manhattan_distance = lambda x, y: np.abs(x - y)
            for i in range(preds.shape[0]):
                x = preds[i].reshape(-1, 1)
                y = trues[i].reshape(-1, 1)
                if i % 100 == 0:
                    print("calculating dtw iter:", i)
                d, _, _, _ = accelerated_dtw(x, y, dist=manhattan_distance)
                dtw_list.append(d)
            dtw = np.array(dtw_list).mean()
        else:
            dtw = 'Not calculated'

        #mae, mse, rmse, mape_5, mape_10, mspe = metric(preds, trues)
        '''
        #print(trues.shape)
        score_import=[]
        score_local=[]
        for target in range(0,self.args.target_features):
            
            preds_np = preds[:, :, target]  # shape: [N, 10]
            #trues_np = trues[:, 0, target]  # shape: [N]，只取第一个时间点的真实值
            #print("shape:",preds[...,[target]].shape)
            #print("trueshape:",trues_np[...,[target]])
            #mae, mse, rmse, mape_5, mape_10, mspe = metric(preds[...,[target]], trues[...,[target]])

            # 构造列名
            columns = [f'pred_day{i+1}' for i in range(preds_np.shape[1])]

            # 构造数据：都是预测
            data = preds_np
        
            # 构造 DataFrame 并保存
            df_export = pds.DataFrame(data, columns=columns)
            os.makedirs('pre_result', exist_ok=True)

            # 替换原来的保存代码：
            csv_path = self.args.csv_path +str(target)
            df_export.to_csv(csv_path, index=False)
            print(f"[INFO] 预测窗口结果已保存到: {csv_path}")


        return

    def finetune_old(self, setting):
        """
        增量微调：加载已有模型参数，用新数据继续训练（不做验证和测试）
        """
        # 1. 加载新数据集（只需要train）
        train_data, train_loader = self._get_data(flag='val')

        # 2. 加载已有模型
        path = os.path.join(self.args.checkpoints, setting)
        checkpoint_path = os.path.join(path, 'checkpoint.pth')

        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"没有找到已有模型 {checkpoint_path}")

        print(f"加载已有模型: {checkpoint_path}")
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device))
        time_now = time.time()
        train_steps = len(train_loader)

        # 3. 是否冻结部分参数（可选）
        if getattr(self.args, "freeze_backbone", False):
            for name, param in self.model.named_parameters():
                if "predict_linear" not in name:   # 只训练预测层
                    param.requires_grad = False

        # 4. 设置优化器（重新设置学习率）
        model_optim = self._select_optimizer()
       
        criterion = self._select_criterion()

        for epoch in range(self.args.train_epochs):
            iter_count = 0
            train_loss = []

            self.model.train()
            epoch_time = time.time()

            for i, (batch_x, batch_y, batch_x_mark, batch_y_mark, indices) in enumerate(train_loader):
                iter_count += 1
                model_optim.zero_grad()

                batch_x = batch_x.float().to(self.device)
                batch_y = batch_y.float().to(self.device)
                batch_x_mark = batch_x_mark.float().to(self.device)
                batch_y_mark = batch_y_mark.float().to(self.device)

                # decoder input
                dec_inp = torch.zeros_like(batch_y[:, -self.args.pred_len:, :]).float()
                dec_inp = torch.cat([batch_y[:, :self.args.label_len, :], dec_inp], dim=1).float().to(self.device)

                # forward
                if self.args.use_amp:
                    with get_autocast_context(self.device):
                        outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                        f_dim = -1 if self.args.features == 'MS' else -self.args.target_features
                        outputs = outputs[:, -self.args.pred_len:, f_dim:]
                        batch_y = batch_y[:, -self.args.pred_len:, f_dim:].to(self.device)
                        loss = criterion(outputs, batch_y)
                        train_loss.append(loss.item())
                else:
                    outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                    f_dim = -1 if self.args.features == 'MS' else -self.args.target_features
                    outputs = outputs[:, -self.args.pred_len:, f_dim:]
                    batch_y = batch_y[:, -self.args.pred_len:, f_dim:].to(self.device)
                    loss = criterion(outputs, batch_y)
                    train_loss.append(loss.item())

                if (i + 1) % 100 == 0:
                    print("\titers: {0}, epoch: {1} | loss: {2:.7f}".format(
                        i + 1, epoch + 1, loss.item()))
                    speed = (time.time() - time_now) / iter_count
                    left_time = speed * ((self.args.train_epochs - epoch) * train_steps - i)
                    print('\tspeed: {:.4f}s/iter; left time: {:.4f}s'.format(speed, left_time))
                    iter_count = 0
                    time_now = time.time()

                # backward
                if self.args.use_amp and scaler is not None:
                    scaler.scale(loss).backward()
                    scaler.step(model_optim)
                    scaler.update()
                else:
                    loss.backward()
                    model_optim.step()

            print("Epoch: {} cost time: {}".format(epoch + 1, time.time() - epoch_time))
            print("Epoch: {0}, Steps: {1} | Train Loss: {2:.7f}".format(
                epoch + 1, train_steps, np.average(train_loss)))

            adjust_learning_rate(model_optim, epoch + 1, self.args)

        # 保存微调后的模型
        best_model_path = path + '/' + 'checkpoint.pth'
        torch.save(self.model.state_dict(), best_model_path)
        print(f"✅ Finetune done, model saved at {best_model_path}")

        return self.model

    def finetune(self, setting, k=25):
        """
        增量微调：加载已有模型参数，用全量数据集的最后k条数据进行训练
        """
        # 1. 获取全量数据(最后的部分在测试集里面），但只使用最后k个batch
        train_data, full_loader = self._get_data(flag='test')
        
        # 获取全量数据的batch数量
        all_batches = []
        for batch in full_loader:
            all_batches.append(batch)
        # 取最后k个batch（如果k大于总batch数，则取全部）
        recent_batches = all_batches[-min(k, len(all_batches)):]
        train_steps = len(recent_batches)
        
        print(f"使用最后 {train_steps} 个batch进行增量微调")

        # 2. 加载已有模型
        path = os.path.join(self.args.checkpoints, setting)
        checkpoint_path = os.path.join(path, 'checkpoint.pth')

        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"没有找到已有模型 {checkpoint_path}")

        print(f"加载已有模型: {checkpoint_path}")
        self.model.load_state_dict(torch.load(checkpoint_path, map_location=self.device))
        time_now = time.time()

        # 3. 是否冻结部分参数（可选）
        if getattr(self.args, "freeze_backbone", False):
            for name, param in self.model.named_parameters():
                if "predict_linear" not in name:   # 只训练预测层
                    param.requires_grad = False

        # 4. 设置优化器（重新设置学习率）
        model_optim = self._select_optimizer()
        criterion = self._select_criterion()

        for epoch in range(self.args.train_epochs):
            iter_count = 0
            train_loss = []

            self.model.train()
            epoch_time = time.time()

            # 直接使用最后k个batch进行训练
            for i, (batch_x, batch_y, batch_x_mark, batch_y_mark, indices) in enumerate(recent_batches):
                iter_count += 1
                model_optim.zero_grad()

                batch_x = batch_x.float().to(self.device)
                batch_y = batch_y.float().to(self.device)
                batch_x_mark = batch_x_mark.float().to(self.device)
                batch_y_mark = batch_y_mark.float().to(self.device)

                # decoder input
                dec_inp = torch.zeros_like(batch_y[:, -self.args.pred_len:, :]).float()
                dec_inp = torch.cat([batch_y[:, :self.args.label_len, :], dec_inp], dim=1).float().to(self.device)

                # forward
                if self.args.use_amp:
                    with get_autocast_context(self.device):
                        outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                        f_dim = -1 if self.args.features == 'MS' else -self.args.target_features
                        outputs = outputs[:, -self.args.pred_len:, f_dim:]
                        batch_y = batch_y[:, -self.args.pred_len:, f_dim:].to(self.device)
                        loss = criterion(outputs, batch_y)
                        train_loss.append(loss.item())
                else:
                    outputs = self.model(batch_x, batch_x_mark, dec_inp, batch_y_mark)
                    f_dim = -1 if self.args.features == 'MS' else -self.args.target_features
                    outputs = outputs[:, -self.args.pred_len:, f_dim:]
                    batch_y = batch_y[:, -self.args.pred_len:, f_dim:].to(self.device)
                    loss = criterion(outputs, batch_y)
                    train_loss.append(loss.item())

                if (i + 1) % 100 == 0:
                    print("\titers: {0}, epoch: {1} | loss: {2:.7f}".format(
                        i + 1, epoch + 1, loss.item()))
                    speed = (time.time() - time_now) / iter_count
                    left_time = speed * ((self.args.train_epochs - epoch) * train_steps - i)
                    print('\tspeed: {:.4f}s/iter; left time: {:.4f}s'.format(speed, left_time))
                    iter_count = 0
                    time_now = time.time()

                # backward
                if self.args.use_amp and scaler is not None:
                    scaler.scale(loss).backward()
                    scaler.step(model_optim)
                    scaler.update()
                else:
                    loss.backward()
                    model_optim.step()

            print("Epoch: {} cost time: {}".format(epoch + 1, time.time() - epoch_time))
            train_loss_avg = np.average(train_loss) if train_loss else 0.0
            print("Epoch: {0}, Steps: {1} | Train Loss: {2:.7f}".format(
                epoch + 1, train_steps, train_loss_avg))

            adjust_learning_rate(model_optim, epoch + 1, self.args)

        # 保存微调后的模型
        best_model_path = path + '/' + 'checkpoint.pth'
        torch.save(self.model.state_dict(), best_model_path)
        print(f"✅ Finetune done, model saved at {best_model_path}")

        return self.model
    
