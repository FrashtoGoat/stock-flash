"""测试新闻模块：工厂注册 + 真实拉取"""

from __future__ import annotations

import logging

import pytest

from src.models.stock import NewsItem
from src.news.base import BaseNewsFetcher
from src.news.factory import (
    _REGISTRY,
    create_fetchers,
    fetch_all_news,
    register,
)

logger = logging.getLogger(__name__)


def _ensure_all_registered():
    """确保所有内置新闻源已注册"""
    if "sina" not in _REGISTRY:
        from src.news.sina import SinaFetcher          # noqa: F401
        if "sina" not in _REGISTRY:
            register("sina")(SinaFetcher)
    if "eastmoney" not in _REGISTRY:
        from src.news.eastmoney import EastmoneyFetcher  # noqa: F401
        if "eastmoney" not in _REGISTRY:
            register("eastmoney")(EastmoneyFetcher)
    if "jin10" not in _REGISTRY:
        from src.news.jin10 import Jin10Fetcher          # noqa: F401
        if "jin10" not in _REGISTRY:
            register("jin10")(Jin10Fetcher)


# ============================================================
# 工厂注册机制测试 (使用干净注册表)
# ============================================================

class TestNewsFactory:

    def test_register_decorator(self, clean_news_registry):
        @register("test_source")
        class _FakeSource(BaseNewsFetcher):
            source_name = "test_source"
            async def fetch(self):
                return []

        assert "test_source" in clean_news_registry

    def test_create_fetchers_respects_enabled(self, clean_news_registry):
        @register("mock_a")
        class _MockA(BaseNewsFetcher):
            source_name = "mock_a"
            async def fetch(self):
                return []

        import src.config as cfg_module
        cfg_module._config_cache = {
            "news": {
                "mock_a": {"enabled": True},
                "mock_b": {"enabled": False},
            }
        }

        fetchers = create_fetchers()
        names = [f.source_name for f in fetchers]
        assert "mock_a" in names
        assert "mock_b" not in names

    def test_create_fetchers_skips_unregistered(self, clean_news_registry):
        import src.config as cfg_module
        cfg_module._config_cache = {
            "news": {"not_registered": {"enabled": True}}
        }
        fetchers = create_fetchers()
        assert len(fetchers) == 0


# ============================================================
# 新浪财经真实 API 测试
# ============================================================

class TestSinaLive:

    @pytest.mark.asyncio
    async def test_sina_fetch_returns_news(self):
        """真实调用新浪财经 API"""
        from src.news.sina import SinaFetcher
        fetcher = SinaFetcher()
        items = await fetcher.fetch()

        logger.info("新浪拉取到 %d 条新闻", len(items))
        for i, item in enumerate(items[:5]):
            logger.info("  [%d] %s | %s", i + 1, item.pub_time, item.title)

        assert isinstance(items, list)
        assert len(items) > 0, "新浪财经应该返回新闻数据"
        first = items[0]
        assert isinstance(first, NewsItem)
        assert first.source == "sina"
        assert len(first.content) > 0


# ============================================================
# 东方财富真实 API 测试
# ============================================================

class TestEastmoneyLive:

    @pytest.mark.asyncio
    async def test_eastmoney_fetch_returns_news(self):
        """真实调用东方财富快讯 API"""
        from src.news.eastmoney import EastmoneyFetcher
        fetcher = EastmoneyFetcher()
        items = await fetcher.fetch()

        logger.info("东方财富拉取到 %d 条新闻", len(items))
        for i, item in enumerate(items[:5]):
            logger.info("  [%d] %s | %s", i + 1, item.pub_time, item.title)

        assert isinstance(items, list)
        assert len(items) > 0, "东方财富应该返回新闻数据"
        first = items[0]
        assert isinstance(first, NewsItem)
        assert first.source == "eastmoney"
        assert len(first.content) > 0


# ============================================================
# 聚合拉取测试
# ============================================================

class TestAggregation:

    @pytest.mark.asyncio
    async def test_fetch_all_news_multi_source(self):
        """通过工厂聚合拉取，验证多源聚合"""
        _ensure_all_registered()

        items = await fetch_all_news()

        logger.info("聚合拉取: %d 条新闻", len(items))
        sources = set(n.source for n in items)
        logger.info("来源: %s", sources)

        assert isinstance(items, list)
        assert len(items) > 0, "聚合应返回新闻"
        assert len(sources) >= 1, "至少有一个新闻源"

        # 验证按时间倒序
        if len(items) >= 2:
            assert items[0].pub_time >= items[1].pub_time


# ============================================================
# 完整预处理流程测试（拉取 → 去重 → 预处理）
# ============================================================

class TestFullPreprocessPipeline:

    @pytest.mark.asyncio
    async def test_full_flow_with_preprocess(self):
        """模拟 main.py: 拉取 → 去重 → 预处理(分类/情绪/关键词/预筛选)"""
        _ensure_all_registered()
        from src.news.dedup import DedupStore
        from src.news.preprocessor import preprocess
        import tempfile, pathlib

        # 用临时文件做去重，不污染正式数据
        with tempfile.TemporaryDirectory() as tmp:
            dedup = DedupStore(path=pathlib.Path(tmp) / "test_seen.json")

            # 1. 拉取
            raw_news = await fetch_all_news()
            logger.info("拉取: %d 条原始新闻", len(raw_news))
            assert len(raw_news) > 0

            # 验证新字段
            first = raw_news[0]
            assert first.news_id, "应该有 news_id"
            logger.info("样本 news_id=%s, category=%s, related_stocks=%s",
                         first.news_id, first.category, first.related_stocks)

            # 2. 去重（第一次全部为新）
            new_news = dedup.filter_new(raw_news)
            assert len(new_news) == len(raw_news)

            # 再次去重（全部为旧）
            new_news2 = dedup.filter_new(raw_news)
            assert len(new_news2) == 0, "第二次去重应全部过滤"

            # 3. 预处理
            worth = preprocess(new_news)
            logger.info("预处理: %d/%d 条值得分析", len(worth), len(new_news))

            for n in worth[:10]:
                logger.info(
                    "  [%s][%s][%s] %s | KW=%s | stocks=%s",
                    n.source, n.category.value, n.sentiment.value,
                    n.title[:40], n.keywords,
                    [s.get("name") for s in n.related_stocks] or "-",
                )

            # 通过预筛选的新闻应该都有关键词或关联股票
            for n in worth:
                has_value = (n.keywords or n.related_stocks
                             or n.importance >= 2)
                assert has_value, f"不应通过预筛选: {n.title[:30]}"
