"""主函数：串联整个流水线

完整流程：
  拉取 → 去重 → 预处理(分类/情绪/关键词/预筛选) → LLM分析 → 链式筛选 → 大盘判断 → 通知 → 交易
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from src.analyzer.bearish_analyzer import analyze_bearish
from src.analyzer.llm_analyzer import analyze_news
from src.config import get
from src.filters.factory import create_filter_chain
from src.models.stock import TradeDirection, TradeSignal
from src.news.dedup import DedupStore
from src.news.factory import fetch_all_news
from src.news.preprocessor import preprocess
from src.trading.executor import create_executor
from src.trading.market_judge import judge_market
from src.trading.notifier import notify

logger = logging.getLogger(__name__)

_dedup = DedupStore()


async def pipeline() -> None:
    """完整的扫描-分析-筛选-交易流水线"""
    start = datetime.now()
    logger.info("===== Stock Flash Pipeline 启动 [%s] =====", start.strftime("%Y-%m-%d %H:%M:%S"))

    # Step 1: 聚合拉取
    logger.info("[Step 1] 拉取新闻...")
    raw_news = await fetch_all_news()
    if not raw_news:
        logger.info("无新闻，流水线结束")
        return
    logger.info("拉取到 %d 条原始新闻", len(raw_news))

    # Step 2: 去重
    logger.info("[Step 2] 去重...")
    new_news = _dedup.filter_new(raw_news)
    if not new_news:
        logger.info("全部为已处理新闻，流水线结束")
        return
    logger.info("去重后 %d 条新新闻 (已处理库: %d 条)", len(new_news), _dedup.size)

    # Step 3: 预处理 (分类 → 情绪 → 关键词 → 预筛选)
    logger.info("[Step 3] 预处理...")
    worth_news = preprocess(new_news)
    if not worth_news:
        logger.info("预处理后无值得分析的新闻，流水线结束")
        return

    for n in worth_news:
        logger.info("  [%s][%s][%s] %s | KW=%s | stocks=%s",
                     n.source, n.category.value, n.sentiment.value,
                     n.title[:40], n.keywords,
                     [s.get("name", "") for s in n.related_stocks] or "-")

    # Step 4: LLM 分析（利好+利空 并行）
    logger.info("[Step 4] LLM 分析 (%d 条新闻)...", len(worth_news))
    bullish_task = analyze_news(worth_news)
    bearish_task = analyze_bearish(worth_news)
    targets, bearish = await asyncio.gather(bullish_task, bearish_task)

    # 利空报告
    mi = bearish.market_impact
    logger.info("[利空] 大盘影响=%s | %s", mi.level.value, mi.description or "无")
    for risk in bearish.industry_risks:
        logger.info("  [利空] %s (%s): %s", risk.industry, risk.level.value, risk.reason)

    if not targets:
        logger.info("LLM 未分析出利好标的，流水线结束")
        return
    for t in targets:
        tag = "[可买]" if t.tradable else f"[{t.tradable_note}]"
        logger.info("  %s %s(%s) [%s] 评分=%.0f | %s",
                     tag, t.name, t.code, t.board.value, t.score, t.reason)
    logger.info("LLM 分析得 %d 个候选标的 (%d 个可直接交易)",
                len(targets), sum(1 for t in targets if t.tradable))

    # Step 5: 链式筛选
    logger.info("[Step 5] 链式筛选...")
    chain = create_filter_chain()
    results = await chain.run(targets)
    passed = [r for r in results if r.is_passed]
    if not passed:
        logger.info("所有标的未通过筛选，流水线结束")
        return
    logger.info("%d 个标的通过筛选: %s",
                len(passed),
                ", ".join(f"{r.stock.name}({r.stock.code})" for r in passed))

    # Step 6: 大盘判断
    logger.info("[Step 6] 大盘情况判断...")
    market = await judge_market()

    # 构建交易信号
    trading_cfg = get("trading") or {}
    default_amount = trading_cfg.get("default_amount", 10000)
    signals = [
        TradeSignal(
            stock=r.stock,
            direction=TradeDirection.BUY,
            amount=default_amount,
            reason=r.stock.reason,
            confidence=r.stock.score / 100,
        )
        for r in passed
    ]

    # Step 7: 通知
    logger.info("[Step 7] 发送通知...")
    await notify(market, signals)

    # Step 8: 交易执行
    if market.is_tradable:
        logger.info("[Step 8] 执行交易 (大盘可交易)...")
        executor = create_executor()
        records = await executor.execute(signals)
        logger.info("执行完成: %d 笔交易记录", len(records))
    else:
        logger.warning("[Step 8] 大盘不宜交易，跳过执行: %s", market.reason)

    elapsed = (datetime.now() - start).total_seconds()
    logger.info("===== Pipeline 完成，耗时 %.1f秒 =====", elapsed)


def run_once() -> None:
    """同步入口：执行一次完整流水线"""
    asyncio.run(pipeline())
