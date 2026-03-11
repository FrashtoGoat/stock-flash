"""配置加载与管理"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "config" / "settings.yaml"

load_dotenv(_ROOT / ".env", override=False)

_config_cache: dict | None = None


def _resolve_env(value: Any) -> Any:
    """递归替换 ${ENV_VAR} 或 ${ENV_VAR:default} 占位符为环境变量值"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        inner = value[2:-1]
        if ":" in inner:
            env_key, default = inner.split(":", 1)
            return os.environ.get(env_key, default)
        return os.environ.get(inner, value)
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


def load_config(force_reload: bool = False) -> dict:
    """加载并缓存配置"""
    global _config_cache
    if _config_cache is not None and not force_reload:
        return _config_cache

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    _config_cache = _resolve_env(raw)
    return _config_cache


def get(section: str, key: str | None = None, default: Any = None) -> Any:
    """便捷获取配置项, 如 get('llm', 'model')"""
    cfg = load_config()
    sec = cfg.get(section, {})
    if key is None:
        return sec
    return sec.get(key, default)
