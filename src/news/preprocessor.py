"""新闻预处理器：分类、情绪判断、关键词提取、预筛选

替代原来的 extractor.py，提供完整的预处理管道：
  raw news → 去重 → 分类 → 情绪 → 关键词 → 预筛选 → 决定是否送 LLM
"""

from __future__ import annotations

import logging
import re
from src.models.stock import NewsCategory, NewsItem, NewsSentiment

logger = logging.getLogger(__name__)

# ============================================================
# 关键词提取
# ============================================================

_STOCK_CODE_RE = re.compile(r"[（(](\d{6})[）)]")

_SECTOR_KEYWORDS = [
    "利好", "涨停", "暴涨", "突破", "新高", "放量", "主力",
    "半导体", "芯片", "人工智能", "AI", "新能源", "光伏", "锂电",
    "军工", "医药", "消费", "金融", "地产", "基建", "数字经济",
    "机器人", "自动驾驶", "算力", "存储", "AIGC", "大模型",
    "量子", "低空经济", "固态电池", "脑机接口", "卫星", "华为",
]


def extract_keywords(news: NewsItem) -> list[str]:
    """提取单条新闻的关键词"""
    kws: list[str] = []
    codes = _STOCK_CODE_RE.findall(news.content)
    kws.extend(codes)
    for kw in _SECTOR_KEYWORDS:
        if kw in news.content:
            kws.append(kw)
    return list(dict.fromkeys(kws))


# ============================================================
# 分类（规则优先，源站 tag 补充）
# ============================================================

_CATEGORY_RULES: list[tuple[list[str], NewsCategory]] = [
    (["GDP", "CPI", "PMI", "失业率", "利率", "降准", "降息", "通胀", "央行"], NewsCategory.MACRO),
    (["政策", "监管", "国务院", "证监会", "发改委", "两会"], NewsCategory.POLICY),
    (["IPO", "财报", "业绩", "并购", "回购", "增持", "减持", "高管"], NewsCategory.COMPANY),
    (["行业", "板块", "赛道", "产业链", "上游", "下游"], NewsCategory.INDUSTRY),
    (["AI", "芯片", "半导体", "量子", "机器人", "自动驾驶", "大模型"], NewsCategory.TECH),
    (["美股", "纳斯达克", "标普", "欧股", "日经", "外资"], NewsCategory.GLOBAL),
    (["大盘", "指数", "涨停", "跌停", "成交量", "北向资金"], NewsCategory.MARKET),
]


def classify(news: NewsItem) -> NewsCategory:
    """判断新闻分类"""
    if news.category != NewsCategory.OTHER:
        return news.category
    text = news.content
    for keywords, cat in _CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return cat
    return NewsCategory.OTHER


# ============================================================
# 情绪判断（正面/负面/中性）
# ============================================================

_POSITIVE_WORDS = [
    "利好", "涨停", "暴涨", "突破", "新高", "大涨", "飙升", "强势",
    "增长", "超预期", "盈利", "回暖", "景气", "加速", "创新高",
    "大单", "重大突破", "订单", "中标", "获批", "放量上涨",
]

_NEGATIVE_WORDS = [
    "利空", "跌停", "暴跌", "大跌", "下挫", "崩盘", "爆雷",
    "亏损", "下滑", "萎缩", "退市", "违规", "处罚", "预警",
    "减持", "清仓", "断崖", "熔断", "制裁", "暂停上市",
]

_PRICE_ACTION_WORDS = [
    "涨停", "跌停", "大涨", "大跌", "暴涨", "暴跌", "飙升", "跳水",
    "领涨", "领跌", "冲高回落", "高开高走", "放量上涨", "放量下跌",
    "创新高", "新高", "创历史新高", "逼近涨停", "封板", "炸板",
]

_CATALYST_WORDS = [
    # 更偏“信息驱动”的触发因素（避免把纯走势当成信号）
    "中标", "订单", "签约", "合作", "落地", "获批", "批复", "立项",
    "政策", "国务院", "证监会", "发改委", "央行", "两会",
    "业绩", "预增", "预减", "年报", "季报", "利润", "营收", "指引",
    "回购", "增持", "减持", "重组", "并购", "募资", "定增",
    "停产", "复产", "涨价", "降价", "供给", "需求", "出口", "关税",
]


def _is_price_action_only(news: NewsItem) -> bool:
    """是否属于“涨了/跌了”型快讯（更多描述走势而非信息变化）。"""
    text = news.content or ""
    if not text:
        return False
    has_price_action = any(w in text for w in _PRICE_ACTION_WORDS)
    if not has_price_action:
        return False
    # 若包含明显催化词，则不算“纯走势”
    has_catalyst = any(w in text for w in _CATALYST_WORDS)
    if has_catalyst:
        return False
    # 市场类/中性/且有明确标的时，通常就是“谁涨了”的快讯
    if news.category in (NewsCategory.MARKET, NewsCategory.OTHER) and news.related_stocks:
        return True
    # 其它分类里也可能出现“纯走势”描述，但更谨慎：必须同时是正/负情绪且带标的
    if news.sentiment != NewsSentiment.NEUTRAL and news.related_stocks:
        return True
    return False


def detect_sentiment(news: NewsItem) -> NewsSentiment:
    """判断新闻情绪"""
    text = news.content
    pos = sum(1 for w in _POSITIVE_WORDS if w in text)
    neg = sum(1 for w in _NEGATIVE_WORDS if w in text)
    if pos > neg:
        return NewsSentiment.POSITIVE
    if neg > pos:
        return NewsSentiment.NEGATIVE
    return NewsSentiment.NEUTRAL


# ============================================================
# 预筛选：决定是否值得送 LLM 分析
# ============================================================

def should_analyze(news: NewsItem) -> bool:
    """判断这条新闻是否值得交给 LLM 深入分析

    通过条件（满足任一即可）：
    1. 有明确关联的 A 股代码
    2. 有 A 股相关关键词 且 情绪非中性
    3. 重要性 >= 2
    4. 分类为 公司/行业/政策/科技 且有关键词
    """
    # 先过滤“已涨成事实”的走势型快讯，避免黑盒式追涨推送
    if _is_price_action_only(news):
        return False

    if news.related_stocks:
        return True

    if news.keywords and news.sentiment != NewsSentiment.NEUTRAL:
        return True

    if news.importance >= 2:
        return True

    if news.category in (NewsCategory.COMPANY, NewsCategory.INDUSTRY,
                          NewsCategory.POLICY, NewsCategory.TECH):
        if news.keywords:
            return True

    return False


# ============================================================
# 完整预处理管道
# ============================================================

def preprocess(news_list: list[NewsItem]) -> list[NewsItem]:
    """对新闻列表执行完整预处理：关键词 → 分类 → 情绪 → 预筛选"""
    for news in news_list:
        news.keywords = extract_keywords(news)
        news.category = classify(news)
        news.sentiment = detect_sentiment(news)

    total = len(news_list)
    worth = [n for n in news_list if should_analyze(n)]

    logger.info(
        "预处理完成: %d 条新闻 → %d 条值得分析 "
        "(正面=%d 负面=%d 中性=%d)",
        total, len(worth),
        sum(1 for n in news_list if n.sentiment == NewsSentiment.POSITIVE),
        sum(1 for n in news_list if n.sentiment == NewsSentiment.NEGATIVE),
        sum(1 for n in news_list if n.sentiment == NewsSentiment.NEUTRAL),
    )
    return worth
