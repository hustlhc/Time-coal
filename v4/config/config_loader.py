#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置加载器 - 支持 YAML 配置文件和环境变量
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置加载器

        Args:
            config_path: 配置文件路径，默认为 config/config.yaml
        """
        if config_path is None:
            # 默认配置路径
            app_root = Path(__file__).parent.parent
            config_path = app_root / "config" / "config.yaml"

        self.config_path = Path(config_path)
        self.app_root = Path(__file__).parent.parent
        self._config = None

    def load(self) -> Dict[str, Any]:
        """
        加载配置

        Returns:
            配置字典
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {self.config_path}\n"
                f"请从 config.example.yaml 复制并修改"
            )

        # 读取 YAML
        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

        # 环境变量替换
        self._config = self._replace_env_vars(self._config)

        # 变量替换（如 ${data.output_dir}）
        self._config = self._replace_config_vars(self._config)

        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值（支持点号分隔的嵌套键）

        Args:
            key: 配置键，如 'data.output_dir'
            default: 默认值

        Returns:
            配置值
        """
        if self._config is None:
            self.load()

        keys = key.split(".")
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def _replace_env_vars(self, config: Any) -> Any:
        """
        替换环境变量（递归）

        ${ENV_VAR} 格式的字符串会被替换为环境变量
        ${ENV_VAR:-default} 格式支持默认值
        """
        if isinstance(config, dict):
            return {k: self._replace_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._replace_env_vars(item) for item in config]
        elif isinstance(config, str):
            # 检查是否包含环境变量
            pattern = r"\$\{([A-Z_][A-Z0-9_]*)(:-([^}]+))?\}"

            def replacer(match):
                var_name = match.group(1)
                default_value = match.group(3)

                # 特殊处理 APP_ROOT
                if var_name == "APP_ROOT":
                    return str(self.app_root)

                return os.getenv(var_name, default_value or "")

            return re.sub(pattern, replacer, config)
        else:
            return config

    def _replace_config_vars(self, config: Any, root: Optional[Dict] = None) -> Any:
        """
        替换配置内部变量（递归）

        ${data.output_dir} 格式的字符串会被替换为配置值
        """
        if root is None:
            root = config

        if isinstance(config, dict):
            return {k: self._replace_config_vars(v, root) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._replace_config_vars(item, root) for item in config]
        elif isinstance(config, str):
            # 检查是否包含配置变量
            pattern = r"\$\{([a-z_.]+)\}"

            def replacer(match):
                var_path = match.group(1)
                keys = var_path.split(".")
                value = root

                for k in keys:
                    if isinstance(value, dict) and k in value:
                        value = value[k]
                    else:
                        return match.group(0)  # 保持原样

                return str(value) if value is not None else ""

            result = re.sub(pattern, replacer, config)

            # 如果还有未替换的变量，递归替换
            if "${" in result and result != config:
                return self._replace_config_vars(result, root)

            return result
        else:
            return config

    def validate(self) -> bool:
        """
        验证配置

        Returns:
            配置是否有效
        """
        if self._config is None:
            self.load()

        required_keys = [
            "data.raw_data_root",
            "data.output_dir",
            "data.baseline.coal",
            "data.baseline.freight",
        ]

        for key in required_keys:
            if self.get(key) is None:
                print(f"错误: 缺少必需配置项: {key}")
                return False

        # 检查路径是否存在（警告，不强制）
        raw_data_root = Path(self.get("data.raw_data_root"))
        if not raw_data_root.exists():
            print(f"警告: 原始数据目录不存在: {raw_data_root}")

        return True

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典

        Returns:
            配置字典
        """
        if self._config is None:
            self.load()
        return self._config.copy()


# 全局配置实例
_config_instance = None


def get_config(config_path: Optional[str] = None) -> ConfigLoader:
    """
    获取全局配置实例（单例模式）

    Args:
        config_path: 配置文件路径

    Returns:
        ConfigLoader 实例
    """
    global _config_instance

    if _config_instance is None or config_path is not None:
        _config_instance = ConfigLoader(config_path)
        _config_instance.load()

    return _config_instance


if __name__ == "__main__":
    # 测试配置加载
    try:
        config = get_config()
        print("配置加载成功！")
        print(f"输出目录: {config.get('data.output_dir')}")
        print(f"煤价基准: {config.get('data.baseline.coal')}")
        print(f"运费基准: {config.get('data.baseline.freight')}")

        if config.validate():
            print("✓ 配置验证通过")
        else:
            print("✗ 配置验证失败")
    except FileNotFoundError as e:
        print(f"错误: {e}")
        print("请先创建配置文件: cp config/config.example.yaml config/config.yaml")
