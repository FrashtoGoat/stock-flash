"""LLM 利空分析：从新闻中识别大盘和行业层面的风险"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.config import get
from src.llm_provider.base import ChatMessage
from src.llm_provider.factory import create_provider
from src.models.stock import (
    BearishAnalysis,
    IndustryRisk,
    MarketImpact,
    NewsItem,
    RiskDuration,
    RiskLevel,
)

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _parse_bearish_response(text: str) -> BearishAnalysis:
    json_match = re.search(r"\{[\s\S]*\}", text)
    if not json_match:
        logger.warning("利空分析: 未找到 JSON: %s", text[:200])
        return BearishAnalysis()

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        logger.warning("利空分析: JSON 解析失败: %s", text[:200])
        return BearishAnalysis()

    mi_raw = data.get("market_impact", {})
    try:
        market_impact = MarketImpact(
            level=RiskLevel(mi_raw.get("level", "none")),
            description=mi_raw.get("description", ""),
            duration=RiskDuration(mi_raw.get("duration", "short")),
            sentiment_shift=mi_raw.get("sentiment_shift", ""),
        )
    except ValueError:
        market_impact = MarketImpact()

    industry_risks: list[IndustryRisk] = []
    for item in data.get("industry_risks", []):
        try:
            level = RiskLevel(item.get("level", "mild"))
        except ValueError:
            level = RiskLevel.MILD
        industry_risks.append(
            IndustryRisk(
                industry=item.get("industry", ""),
                level=level,
                reason=item.get("reason", ""),
                logic=item.get("logic", ""),
                affected_etfs=item.get("affected_etfs", []),
                related_news=item.get("news_ids", []),
            )
        )

    return BearishAnalysis(market_impact=market_impact, industry_risks=industry_risks)


async def analyze_bearish(news_list: list[NewsItem]) -> BearishAnalysis:
    """调用 LLM 分析利空风险，返回大盘+行业层面的风险评估"""
    if not news_list:
        return BearishAnalysis()

    from src.analyzer.llm_analyzer import _build_news_block

    llm_cfg = get("llm") or {}
    provider = create_provider()

    system_prompt = _load_prompt("bearish_system.txt")
    user_template = _load_prompt("bearish_user.txt")
    news_block = _build_news_block(news_list)
    user_prompt = user_template.format(count=len(news_list), news_block=news_block)

    messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content=user_prompt),
    ]

    try:
        resp = await provider.chat(
            messages=messages,
            temperature=llm_cfg.get("temperature", 0.3),
            max_tokens=llm_cfg.get("max_tokens", 4000),
        )
        content = resp.content
    except Exception:
        logger.exception("利空分析 LLM 调用失败 (provider=%s)", provider.provider_name)
        return BearishAnalysis()

    result = _parse_bearish_response(content)
    risk_count = len(result.industry_risks)
    logger.info(
        "利空分析 [%s]: 大盘=%s, 行业风险=%d 个",
        provider.provider_name, result.market_impact.level.value, risk_count,
    )
    return result
