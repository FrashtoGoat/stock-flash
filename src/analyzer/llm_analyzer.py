"""LLM 大模型分析：从预处理后的新闻中提取利好A股标的"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.config import get
from src.llm_provider.base import ChatMessage
from src.llm_provider.factory import create_provider
from src.models.stock import BoardType, NewsItem, NewsSentiment, StockTarget, TargetType

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "prompts"


def _load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def _build_news_block(news_list: list[NewsItem]) -> str:
    """将新闻列表格式化为结构化文本，包含分类/情绪/关键词/关联股票"""
    lines: list[str] = []
    for i, n in enumerate(news_list, 1):
        parts = [f"{i}. [{n.pub_time:%H:%M}]"]
        parts.append(f"[{n.category.value}]")
        parts.append(f"[{n.sentiment.value}]")
        parts.append(n.content)

        if n.keywords:
            parts.append(f"  关键词: {', '.join(n.keywords)}")
        if n.related_stocks:
            stocks_str = ", ".join(
                f"{s.get('name', '')}({s.get('code', '')})"
                for s in n.related_stocks
            )
            parts.append(f"  关联股票: {stocks_str}")
        parts.append(f"  ID: {n.news_id}")

        lines.append(" ".join(parts[:4]))
        for extra in parts[4:]:
            lines.append(extra)

    return "\n".join(lines)


def _parse_response(text: str) -> list[StockTarget]:
    """从 LLM 返回文本中解析出标的列表"""
    json_match = re.search(r"\{[\s\S]*\}", text)
    if not json_match:
        logger.warning("LLM 返回中未找到 JSON: %s", text[:200])
        return []

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        logger.warning("LLM 返回 JSON 解析失败: %s", text[:200])
        return []

    targets: list[StockTarget] = []
    for item in data.get("targets", []):
        try:
            score = float(item.get("score", 0))
            if score < 50:
                continue
            code = str(item["code"]).zfill(6)

            raw_type = item.get("type", "stock")
            if raw_type == "etf" or code.startswith(("15", "16", "51")):
                target_type = TargetType.ETF
            else:
                target_type = TargetType.STOCK

            board_str = item.get("board", "main")
            try:
                board = BoardType(board_str)
            except ValueError:
                board = BoardType.MAIN if target_type == TargetType.STOCK else BoardType.GEM

            targets.append(
                StockTarget(
                    code=code,
                    name=item["name"],
                    board=board,
                    target_type=target_type,
                    reason=item.get("reason", ""),
                    industry_chain=item.get("industry_chain", ""),
                    logic=item.get("logic", ""),
                    score=score,
                    related_news=item.get("news_ids", []),
                )
            )
        except (KeyError, ValueError) as e:
            logger.warning("跳过无效标的 %s: %s", item, e)
            continue

    return targets


async def analyze_news(news_list: list[NewsItem]) -> list[StockTarget]:
    """调用 LLM 分析新闻，返回利好标的列表

    新闻已经过 preprocessor 预处理（含分类/情绪/关键词），
    Prompt 从 config/prompts/ 模板文件加载。
    """
    if not news_list:
        return []

    llm_cfg = get("llm") or {}
    provider = create_provider()

    system_prompt = _load_prompt("analyze_system.txt")
    user_template = _load_prompt("analyze_user.txt")

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
            max_tokens=llm_cfg.get("max_tokens", 2000),
        )
        content = resp.content
    except Exception:
        logger.exception("LLM 调用失败 (provider=%s)", provider.provider_name)
        return []

    targets = _parse_response(content)
    logger.info("LLM [%s] 分析得出 %d 个利好标的", provider.provider_name, len(targets))
    return targets
