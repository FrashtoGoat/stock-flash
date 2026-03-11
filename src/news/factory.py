"""新闻源工厂：注册模式，由配置驱动创建 fetcher 实例"""

from __future__ import annotations

import logging
from typing import Type

from src.config import get
from src.models.stock import NewsItem
from src.news.base import BaseNewsFetcher

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, Type[BaseNewsFetcher]] = {}


def register(name: str):
    """装饰器：将新闻源实现类注册到工厂"""
    def wrapper(cls: Type[BaseNewsFetcher]):
        _REGISTRY[name] = cls
        return cls
    return wrapper


def _ensure_builtins() -> None:
    """延迟导入内置实现，触发 @register 装饰器"""
    if _REGISTRY:
        return
    import src.news.jin10      # noqa: F401
    import src.news.sina       # noqa: F401
    import src.news.eastmoney  # noqa: F401


def create_fetchers() -> list[BaseNewsFetcher]:
    """根据 config.news 配置创建所有启用的新闻源"""
    _ensure_builtins()
    news_cfg = get("news") or {}
    fetchers: list[BaseNewsFetcher] = []

    for source_name, source_cfg in news_cfg.items():
        if not isinstance(source_cfg, dict):
            continue
        if not source_cfg.get("enabled", False):
            logger.debug("新闻源 %s 未启用，跳过", source_name)
            continue

        cls = _REGISTRY.get(source_name)
        if cls is None:
            logger.warning("新闻源 %s 未注册，跳过 (已注册: %s)", source_name, list(_REGISTRY))
            continue

        fetchers.append(cls())
        logger.info("新闻源已创建: %s", source_name)

    return fetchers


async def fetch_all_news() -> list[NewsItem]:
    """调用所有启用的新闻源，聚合返回"""
    fetchers = create_fetchers()
    if not fetchers:
        logger.warning("无可用新闻源")
        return []

    all_news: list[NewsItem] = []
    for f in fetchers:
        try:
            items = await f.fetch()
            all_news.extend(items)
        except Exception:
            logger.exception("新闻源 %s 拉取失败", f.source_name)

    all_news.sort(key=lambda n: n.pub_time, reverse=True)
    logger.info("聚合新闻: %d 条 (来自 %d 个源)", len(all_news), len(fetchers))
    return all_news
