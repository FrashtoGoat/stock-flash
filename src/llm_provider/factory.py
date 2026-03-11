"""LLM Provider 工厂：注册模式，由配置驱动创建 provider 实例"""

from __future__ import annotations

import logging
from typing import Type

from src.config import get
from src.llm_provider.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, Type[BaseLLMProvider]] = {}


def register(name: str):
    """装饰器：将 LLM Provider 实现类注册到工厂"""
    def wrapper(cls: Type[BaseLLMProvider]):
        _REGISTRY[name] = cls
        return cls
    return wrapper


def _ensure_builtins() -> None:
    """延迟导入内置实现，触发 @register 装饰器"""
    if _REGISTRY:
        return
    import src.llm_provider.bailian  # noqa: F401
    import src.llm_provider.zhipu    # noqa: F401


def create_provider(provider_name: str | None = None) -> BaseLLMProvider:
    """根据配置创建 LLM Provider

    Args:
        provider_name: 指定 provider 名称；为 None 时从 config.llm.active_provider 读取
    """
    _ensure_builtins()
    llm_cfg = get("llm") or {}

    if provider_name is None:
        provider_name = llm_cfg.get("active_provider", "bailian")

    cls = _REGISTRY.get(provider_name)
    if cls is None:
        available = list(_REGISTRY.keys())
        raise ValueError(
            f"LLM Provider '{provider_name}' 未注册 (可用: {available})"
        )

    provider = cls()
    logger.info("LLM Provider 已创建: %s", provider_name)
    return provider
