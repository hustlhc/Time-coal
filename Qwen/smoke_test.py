import sys
import importlib

print('Python executable:', sys.executable)

try:
    import torch
    print('torch version:', torch.__version__)
    print('cuda available:', torch.cuda.is_available())
except Exception as e:
    print('torch import failed:', e)

try:
    import transformers
    print('transformers version:', transformers.__version__)
except Exception as e:
    print('transformers import failed:', e)

try:
    import safetensors
    print('safetensors available')
except Exception as e:
    print('safetensors import failed or not installed:', e)
