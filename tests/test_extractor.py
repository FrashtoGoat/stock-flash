"""测试新闻预处理器（分类、情绪、关键词、预筛选）"""

from __future__ import annotations

from datetime import datetime

from src.models.stock import NewsCategory, NewsItem, NewsSentiment
from src.news.preprocessor import (
    classify,
    detect_sentiment,
    extract_keywords,
    preprocess,
    should_analyze,
)


def _make_news(content: str, importance: int = 0, **kwargs) -> NewsItem:
    return NewsItem(
        news_id=kwargs.get("news_id", "test:1"),
        source="test",
        title=content[:60],
        content=content,
        pub_time=datetime.now(),
        importance=importance,
        **{k: v for k, v in kwargs.items() if k != "news_id"},
    )


class TestExtractKeywords:

    def test_extracts_stock_code(self):
        news = _make_news("某公司（600519）发布利好公告")
        kws = extract_keywords(news)
        assert "600519" in kws

    def test_extracts_sector_keywords(self):
        news = _make_news("人工智能行业迎来重大利好，半导体板块全线涨停")
        kws = extract_keywords(news)
        assert "人工智能" in kws
        assert "半导体" in kws
        assert "利好" in kws
        assert "涨停" in kws

    def test_no_keywords_for_irrelevant(self):
        news = _make_news("今天天气不错，适合出门")
        kws = extract_keywords(news)
        assert kws == []

    def test_deduplicates(self):
        news = _make_news("AI推动AI半导体行业AI发展")
        kws = extract_keywords(news)
        assert kws.count("AI") == 1

    def test_multiple_stock_codes(self):
        news = _make_news("贵州茅台（600519）和五粮液（000858）联手")
        kws = extract_keywords(news)
        assert "600519" in kws
        assert "000858" in kws


class TestClassify:

    def test_policy(self):
        news = _make_news("国务院发布新政策支持半导体行业发展")
        assert classify(news) == NewsCategory.POLICY

    def test_company(self):
        news = _make_news("某公司发布财报，业绩大幅增长")
        assert classify(news) == NewsCategory.COMPANY

    def test_tech(self):
        news = _make_news("AI大模型技术取得重大突破")
        assert classify(news) == NewsCategory.TECH

    def test_macro(self):
        news = _make_news("央行宣布降息25个基点")
        assert classify(news) == NewsCategory.MACRO

    def test_keeps_source_category(self):
        news = _make_news("普通新闻", category=NewsCategory.INDUSTRY)
        assert classify(news) == NewsCategory.INDUSTRY

    def test_other_for_unmatched(self):
        news = _make_news("今天天气不错")
        assert classify(news) == NewsCategory.OTHER


class TestDetectSentiment:

    def test_positive(self):
        news = _make_news("半导体板块利好，涨停潮来袭，暴涨超预期")
        assert detect_sentiment(news) == NewsSentiment.POSITIVE

    def test_negative(self):
        news = _make_news("某公司爆雷，股价跌停暴跌")
        assert detect_sentiment(news) == NewsSentiment.NEGATIVE

    def test_neutral(self):
        news = _make_news("今天大盘横盘震荡")
        assert detect_sentiment(news) == NewsSentiment.NEUTRAL


class TestShouldAnalyze:

    def test_with_related_stocks(self):
        news = _make_news("某新闻", related_stocks=[{"code": "600519", "name": "贵州茅台"}])
        news.keywords = []
        assert should_analyze(news) is True

    def test_keywords_with_positive_sentiment(self):
        news = _make_news("AI行业利好")
        news.keywords = ["AI", "利好"]
        news.sentiment = NewsSentiment.POSITIVE
        assert should_analyze(news) is True

    def test_keywords_neutral_no_category(self):
        news = _make_news("AI行业正常发展")
        news.keywords = ["AI"]
        news.sentiment = NewsSentiment.NEUTRAL
        news.category = NewsCategory.OTHER
        assert should_analyze(news) is False

    def test_keywords_neutral_with_good_category(self):
        news = _make_news("AI行业正常发展")
        news.keywords = ["AI"]
        news.sentiment = NewsSentiment.NEUTRAL
        news.category = NewsCategory.TECH
        assert should_analyze(news) is True

    def test_high_importance(self):
        news = _make_news("重要通知", importance=2)
        news.keywords = []
        assert should_analyze(news) is True

    def test_irrelevant_news(self):
        news = _make_news("今天天气不错")
        news.keywords = []
        news.sentiment = NewsSentiment.NEUTRAL
        news.category = NewsCategory.OTHER
        news.importance = 0
        assert should_analyze(news) is False


class TestPreprocess:

    def test_full_pipeline(self):
        news_list = [
            _make_news("半导体板块大涨利好", news_id="t:1"),
            _make_news("今天天气不错适合出门", news_id="t:2"),
            _make_news("国务院发布AI产业政策支持", news_id="t:3"),
        ]
        result = preprocess(news_list)
        # 天气新闻应该被过滤掉
        assert len(result) >= 1
        contents = [n.content for n in result]
        assert "今天天气不错适合出门" not in contents

    def test_empty_input(self):
        assert preprocess([]) == []
