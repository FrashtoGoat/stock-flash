"""筛选器工厂：注册模式，由配置驱动创建筛选器链"""

from __future__ import annotations

import logging
from typing import Type

from src.config import get
from src.filters.chain import FilterChain, StockFilter

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, Type] = {}


def register(name: str):
    """装饰器：将筛选器实现类注册到工厂"""
    def wrapper(cls: Type):
        _REGISTRY[name] = cls
        return cls
    return wrapper


def _ensure_builtins() -> None:
    """延迟导入内置筛选器，触发 @register 装饰器"""
    if _REGISTRY:
        return
    import src.filters.board_filter         # noqa: F401
    import src.filters.affordability_filter  # noqa: F401
    import src.filters.master_filter        # noqa: F401
    import src.filters.technical_filter     # noqa: F401


def create_filter_chain() -> FilterChain:
    """根据 config.filters 配置构建筛选器链"""
    _ensure_builtins()
    filters_cfg = get("filters") or {}
    chain = FilterChain()

    for filter_name, filter_cfg in filters_cfg.items():
        if not isinstance(filter_cfg, dict):
            continue
        if not filter_cfg.get("enabled", False):
            logger.debug("筛选器 %s 未启用，跳过", filter_name)
            continue

        cls = _REGISTRY.get(filter_name)
        if cls is None:
            logger.warning("筛选器 %s 未注册，跳过 (已注册: %s)", filter_name, list(_REGISTRY))
            continue

        chain.add(cls())

    return chain
