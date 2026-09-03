"""
设备相关工具函数 - 统一封装 CUDA/XPU/MPS/CPU 的设备创建、显存清理和 AMP 功能
支持昆仑芯 P800 (XPyTorch/XPU) 适配
"""
import os
import torch
import contextlib
from typing import Optional, Union


def get_device(use_gpu: bool, gpu_type: str, gpu: int = 0, devices: Optional[str] = None, use_multi_gpu: bool = False) -> torch.device:
    """
    根据参数获取合适的设备
    
    Args:
        use_gpu: 是否使用 GPU
        gpu_type: 设备类型 ('cuda', 'xpu', 'mps')
        gpu: GPU 设备 ID
        devices: 多卡时的设备列表字符串 (如 "0,1,2,3")
        use_multi_gpu: 是否使用多卡
    
    Returns:
        torch.device 对象
    """
    if use_gpu and gpu_type == 'xpu':
        # 昆仑芯 XPU 设备
        if hasattr(torch, 'xpu') and torch.xpu.is_available():
            if use_multi_gpu and devices:
                # 多卡时设置 XPU_VISIBLE_DEVICES（如果 XPyTorch 支持）
                os.environ["XPU_VISIBLE_DEVICES"] = devices.replace(' ', '')
            device = torch.device('xpu:{}'.format(gpu))
            print('Use XPU: xpu:{}'.format(gpu))
            return device
        else:
            print('Warning: XPU requested but torch.xpu.is_available() is False, falling back to CPU')
            return torch.device('cpu')
    
    elif use_gpu and gpu_type == 'cuda':
        # NVIDIA CUDA 设备
        if torch.cuda.is_available():
            if use_multi_gpu and devices:
                os.environ["CUDA_VISIBLE_DEVICES"] = devices.replace(' ', '')
            else:
                os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
            device = torch.device('cuda:{}'.format(gpu))
            print('Use GPU: cuda:{}'.format(gpu))
            return device
        else:
            print('Warning: CUDA requested but torch.cuda.is_available() is False, falling back to CPU')
            return torch.device('cpu')
    
    elif use_gpu and gpu_type == 'mps':
        # Apple MPS 设备
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = torch.device('mps')
            print('Use GPU: mps')
            return device
        else:
            print('Warning: MPS requested but not available, falling back to CPU')
            return torch.device('cpu')
    
    else:
        # CPU
        device = torch.device('cpu')
        print('Use CPU')
        return device


def empty_cache(device_type: str) -> None:
    """
    根据设备类型清理显存
    
    Args:
        device_type: 设备类型字符串 ('cuda', 'xpu', 'mps')
    """
    if device_type == 'cuda':
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    elif device_type == 'xpu':
        if hasattr(torch, 'xpu') and torch.xpu.is_available():
            torch.xpu.empty_cache()
    elif device_type == 'mps':
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.backends.mps.empty_cache()


def get_autocast_context(device: torch.device):
    """
    获取设备无关的 autocast context manager
    
    Args:
        device: torch.device 对象
    
    Returns:
        context manager for autocast
    """
    device_type = device.type
    
    if device_type == 'cuda':
        return torch.cuda.amp.autocast()
    elif device_type == 'xpu':
        # 如果 XPyTorch 提供了 torch.xpu.amp.autocast，使用它；否则返回 no-op context
        if hasattr(torch, 'xpu') and hasattr(torch.xpu, 'amp') and hasattr(torch.xpu.amp, 'autocast'):
            return torch.xpu.amp.autocast()
        else:
            # XPU 不支持 AMP 时返回 no-op context
            return contextlib.nullcontext()
    else:
        # CPU/MPS 等不支持 AMP，返回 no-op context
        return contextlib.nullcontext()


def get_grad_scaler(device: torch.device) -> Optional[object]:
    """
    获取设备无关的 GradScaler
    
    Args:
        device: torch.device 对象
    
    Returns:
        GradScaler 对象，如果设备不支持则返回 None
    """
    device_type = device.type
    
    if device_type == 'cuda':
        return torch.cuda.amp.GradScaler()
    elif device_type == 'xpu':
        # 如果 XPyTorch 提供了 torch.xpu.amp.GradScaler，使用它；否则返回 None
        if hasattr(torch, 'xpu') and hasattr(torch.xpu, 'amp') and hasattr(torch.xpu.amp, 'GradScaler'):
            return torch.xpu.amp.GradScaler()
        else:
            # XPU 不支持 AMP 时返回 None
            return None
    else:
        # CPU/MPS 等不支持 AMP，返回 None
        return None
