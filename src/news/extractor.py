"""新闻关键词提取"""

from __future__ import annotations

import logging
import re
from src.models.stock import NewsItem

logger = logging.getLogger(__name__)

# A股相关关键词模式
_STOCK_CODE_RE = re.compile(r"[（(](\d{6})[）)]")
_SECTOR_KEYWORDS = [
    "利好", "涨停", "暴涨", "突破", "新高", "放量", "主力",
    "半导体", "芯片", "人工智能", "AI", "新能源", "光伏", "锂电",
    "军工", "医药", "消费", "金融", "地产", "基建", "数字经济",
    "机器人", "自动驾驶", "算力", "存储", "AIGC", "大模型",
]


def extract_keywords(news_list: list[NewsItem]) -> list[NewsItem]:
    """为每条新闻提取关键词（就地修改并返回）"""
    for item in news_list:
        kws: list[str] = []

        codes = _STOCK_CODE_RE.findall(item.content)
        kws.extend(codes)

        for kw in _SECTOR_KEYWORDS:
            if kw in item.content:
                kws.append(kw)

        item.keywords = list(dict.fromkeys(kws))  # 去重保序

    logger.info("关键词提取完成, 共 %d 条新闻", len(news_list))
    return news_list


def filter_relevant_news(news_list: list[NewsItem], min_importance: int = 0) -> list[NewsItem]:
    """只保留与A股相关或重要性达标的新闻"""
    relevant = [
        n for n in news_list
        if n.keywords or n.importance >= min_importance
    ]
    logger.info("筛选出 %d 条相关新闻 (共 %d 条)", len(relevant), len(news_list))
    return relevant
