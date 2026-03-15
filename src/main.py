"""主函数：串联整个流水线

完整流程：
  拉取 → 去重 → 预处理(分类/情绪/关键词/预筛选) → LLM分析 → 链式筛选 → 大盘判断 → 通知 → 交易
  新闻生命周期（storage.enabled）：pending → processed → analyzed，超时标 expired，并关联交易 id。
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path

from src.analyzer.bearish_analyzer import analyze_bearish
from src.analyzer.llm_analyzer import analyze_news
from src.config import get
from src.filters.factory import create_filter_chain
from src.models.stock import (
    BoardType,
    NewsCategory,
    NewsItem,
    NewsSentiment,
    StockTarget,
    TradeDirection,
    TradeSignal,
)
from src.news.dedup import DedupStore
from src.news.factory import fetch_all_news
from src.news.preprocessor import preprocess
from src.trading.executor import create_executor
from src.trading.market_judge import judge_market
from src.trading.notifier import notify
from src.trading.trading_hours import skip_reason

logger = logging.getLogger(__name__)

_dedup = DedupStore()


def _get_test_oil_news() -> list[NewsItem]:
    """测试用：石油主题新闻，用于 --test 跑通全流程"""
    now = datetime.now()
    return [
        NewsItem(
            news_id="test:oil_001",
            source="test",
            title="G7考虑协调释放战略石油储备，国际油价波动",
            content="七国集团(G7)考虑协调释放战略石油储备以稳定市场。国际油价近期波动加剧，石油、油服板块关注度提升。",
            url="",
            keywords=["石油", "原油", "战略储备", "G7"],
            pub_time=now,
            importance=2,
            category=NewsCategory.INDUSTRY,
            sentiment=NewsSentiment.NEUTRAL,
            related_stocks=[{"code": "160216", "name": "石油ETF"}],
        ),
        NewsItem(
            news_id="test:oil_002",
            source="test",
            title="国内油气增储上产持续推进，三桶油资本开支加码",
            content="国内油气增储上产七年行动计划持续推进，三桶油资本开支加码，利好油服、油气装备产业链。",
            url="",
            keywords=["油气", "油服", "三桶油", "资本开支"],
            pub_time=now,
            importance=2,
            category=NewsCategory.POLICY,
            sentiment=NewsSentiment.POSITIVE,
            related_stocks=[{"code": "601857", "name": "中国石油"}, {"code": "601808", "name": "中海油服"}],
        ),
        NewsItem(
            news_id="test:oil_003",
            source="test",
            title="OPEC+维持减产预期，机构看好原油供需格局",
            content="OPEC+维持减产预期，机构看好原油中长期供需格局。上游开采、中游炼化企业受益。",
            url="",
            keywords=["OPEC", "原油", "减产", "炼化"],
            pub_time=now,
            importance=1,
            category=NewsCategory.INDUSTRY,
            sentiment=NewsSentiment.POSITIVE,
            related_stocks=[{"code": "600938", "name": "中国海油"}],
        ),
    ]


async def pipeline_test() -> None:
    """测试模式：用石油主题新闻 + 临时去重跑通全流程，不依赖实时拉取与历史去重"""
    start = datetime.now()
    logger.info("===== Stock Flash Pipeline [测试模式-石油新闻] 启动 [%s] =====", start.strftime("%Y-%m-%d %H:%M:%S"))

    reason = skip_reason(start)
    if reason:
        logger.info("当前 %s，跳过后续操作（拉取/筛选/交易等）", reason)
        return

    run_news_ids: list[int] = []  # 测试模式不写新闻库，不关联
    # 临时去重存储，本次运行视为全部为新
    tmp_dedup_path = Path(tempfile.gettempdir()) / "stock_flash_test_dedup.json"
    if tmp_dedup_path.exists():
        tmp_dedup_path.unlink()
    test_dedup = DedupStore(path=tmp_dedup_path)

    # Step 1: 使用注入的石油新闻
    logger.info("[Step 1] 使用测试新闻 (石油主题)...")
    raw_news = _get_test_oil_news()
    logger.info("拉取到 %d 条测试新闻", len(raw_news))
    for n in raw_news:
        logger.info("  [%s] %s | KW=%s", n.source, n.title[:50], n.keywords)

    # Step 2: 去重（临时库，全部为新）
    logger.info("[Step 2] 去重...")
    new_news = test_dedup.filter_new(raw_news)
    if not new_news:
        logger.info("无新新闻，流水线结束")
        return
    logger.info("去重后 %d 条新新闻", len(new_news))

    # Step 3～8 与 pipeline() 一致
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

    logger.info("[Step 4] LLM 分析 (%d 条新闻)...", len(worth_news))
    bullish_task = analyze_news(worth_news)
    bearish_task = analyze_bearish(worth_news)
    targets, bearish = await asyncio.gather(bullish_task, bearish_task)

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

    logger.info("[Step 6] 大盘情况判断...")
    market = await judge_market()

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

    logger.info("[Step 7] 发送通知...")
    await notify(market, signals)

    if market.is_tradable:
        logger.info("[Step 8] 执行交易 (大盘可交易)...")
        executor = create_executor()
        records, trade_ids = await executor.execute(signals)
        logger.info("执行完成: %d 笔交易记录", len(records))
        if run_news_ids and trade_ids:
            from src.db.news_repository import link_trades
            link_trades(run_news_ids, trade_ids)
    else:
        logger.warning("[Step 8] 大盘不宜交易，跳过执行: %s", market.reason)

    from src.trading.position_manager import check_stop_profit_loss
    sell_signals = check_stop_profit_loss()
    if sell_signals:
        logger.info("[止盈止损] 产生 %d 个卖出信号", len(sell_signals))
        await notify(market, sell_signals)
        executor = create_executor()
        _, _ = await executor.execute(sell_signals)

    elapsed = (datetime.now() - start).total_seconds()
    logger.info("===== Pipeline [测试模式] 完成，耗时 %.1f秒 =====", elapsed)


async def pipeline() -> None:
    """完整的扫描-分析-筛选-交易流水线"""
    start = datetime.now()
    logger.info("===== Stock Flash Pipeline 启动 [%s] =====", start.strftime("%Y-%m-%d %H:%M:%S"))

    reason = skip_reason(start)
    if reason:
        logger.info("当前 %s，Step 8 不执行交易；拉取/筛选/入池等照常执行", reason)

    # Step 1: 聚合拉取
    logger.info("[Step 1] 拉取新闻...")
    raw_news = await fetch_all_news()
    if not raw_news:
        logger.info("无新闻，流水线结束")
        return
    logger.info("拉取到 %d 条原始新闻", len(raw_news))

    # 新闻生命周期：超时标 expired（storage.enabled 时）
    storage_cfg = get("storage") or {}
    use_news_db = storage_cfg.get("enabled", False)
    run_news_ids: list[int] = []
    if use_news_db:
        from src.db.news_repository import mark_expired, upsert_pending
        expire_hours = (storage_cfg.get("news_expire_hours") or (get("news") or {}).get("expire_hours") or 24)
        mark_expired(expire_hours)

    # Step 2: 去重（可选新闻库）
    logger.info("[Step 2] 去重...")
    new_news_id_to_db_id: dict[str, int] = {}  # 本批新新闻 news_id -> DB id（用于后续只更新进入 LLM 的）
    if use_news_db:
        new_news = []
        for n in raw_news:
            if not n.news_id:
                new_news.append(n)
                continue
            db_id, is_new = upsert_pending(n)
            if is_new:
                new_news.append(n)
                run_news_ids.append(db_id)
                new_news_id_to_db_id[n.news_id] = db_id
        skipped = len(raw_news) - len(new_news)
        if skipped:
            logger.info("去重: %d 条已存在，%d 条为新（已入新闻库）", skipped, len(new_news))
    else:
        new_news = _dedup.filter_new(raw_news)
        if new_news:
            logger.info("去重后 %d 条新新闻 (已处理库: %d 条)", len(new_news), _dedup.size)
    if not new_news:
        logger.info("无新新闻，流水线结束")
        return

    # 股票池维护（需 storage + stock_pool.enabled）：先维护再继续流水线
    use_stock_pool = use_news_db and (get("stock_pool") or {}).get("enabled", False)
    if use_stock_pool:
        from src.trading.stock_pool_maintainer import maintain
        maintain()

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
    if use_news_db and run_news_ids:
        from src.db.news_repository import update_to_processed_by_items
        update_to_processed_by_items(worth_news)
    # 仅对进入 LLM 的新闻做 analyzed / link_trades
    run_news_ids_worth = [new_news_id_to_db_id[n.news_id] for n in worth_news if n.news_id in new_news_id_to_db_id] if use_news_db else []

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
    if use_news_db and run_news_ids_worth:
        from src.db.news_repository import update_to_analyzed
        llm_result = {
            "targets": [
                {"name": t.name, "code": t.code, "score": t.score, "reason": t.reason, "tradable": t.tradable}
                for t in targets
            ],
            "bearish": {
                "market_impact": {"level": mi.level.value, "description": mi.description},
                "industry_risks": [{"industry": r.industry, "level": r.level.value, "reason": r.reason} for r in bearish.industry_risks],
            },
        }
        update_to_analyzed(run_news_ids_worth, json.dumps(llm_result, ensure_ascii=False))

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
    if use_stock_pool and run_news_ids_worth:
        from src.db.stock_pool_repository import upsert_watch
        for r in passed:
            upsert_watch(r.stock.code, r.stock.name, run_news_ids_worth, r.stock.score)
        logger.info("股票池: 本批 %d 个标的已入观察池", len(passed))

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

    # Step 7: 通知（标明来源：新闻驱动）
    logger.info("[Step 7] 发送通知...")
    await notify(market, signals, source="新闻驱动")

    # Step 8: 交易执行
    if market.is_tradable:
        logger.info("[Step 8] 执行交易 (大盘可交易)...")
        executor = create_executor()
        records, trade_ids = await executor.execute(signals, source="新闻驱动")
        logger.info("执行完成: %d 笔交易记录", len(records))
        if run_news_ids_worth and trade_ids:
            from src.db.news_repository import link_trades
            link_trades(run_news_ids_worth, trade_ids)
    else:
        logger.warning("[Step 8] 大盘不宜交易，跳过执行: %s", market.reason)

    # 止盈止损检查：若有卖出信号则通知并执行（模拟/实盘）
    from src.trading.position_manager import check_stop_profit_loss
    sell_signals = check_stop_profit_loss()
    if sell_signals:
        logger.info("[止盈止损] 产生 %d 个卖出信号", len(sell_signals))
        await notify(market, sell_signals, source="新闻驱动")
        executor = create_executor()
        _, _ = await executor.execute(sell_signals, source="新闻驱动")
        if use_stock_pool:
            from src.db.stock_pool_repository import mark_removed
            codes = [s.stock.code for s in sell_signals]
            reason = "take_profit" if any("止盈" in (s.reason or "") for s in sell_signals) else "stop_loss"
            n = mark_removed(codes, reason)
            if n:
                logger.info("股票池: %d 个标的已标为移除 (%s)", n, reason)
    else:
        logger.debug("[止盈止损] 无触发")

    elapsed = (datetime.now() - start).total_seconds()
    logger.info("===== Pipeline 完成，耗时 %.1f秒 =====", elapsed)


def load_research_pool() -> list[StockTarget]:
    """从配置加载自研池标的（与新闻驱动并列的另一条路线）。"""
    cfg = get("research_pool") or {}
    if not cfg.get("enabled", False):
        return []
    stocks = cfg.get("stocks") or []
    return [
        StockTarget(
            code=str(s.get("code", "")).strip(),
            name=str(s.get("name") or s.get("code") or "").strip() or str(s.get("code", "")),
            board=BoardType.MAIN,
            reason="自研池",
            score=50.0,
        )
        for s in stocks
        if s.get("code")
    ]


async def pipeline_research_pool() -> None:
    """自研池路线：从配置的股票列表出发，跑链式筛选 → 大盘判断 → 通知 → 交易，不入新闻池，通知/交易标明来源「自研池」。"""
    start = datetime.now()
    logger.info("===== Stock Flash Pipeline [自研池] 启动 [%s] =====", start.strftime("%Y-%m-%d %H:%M:%S"))

    targets = load_research_pool()
    if not targets:
        logger.info("自研池未配置或为空（research_pool.enabled + research_pool.stocks），流水线结束")
        return
    logger.info("自研池 %d 个标的，开始链式筛选...", len(targets))

    chain = create_filter_chain()
    results = await chain.run(targets)
    passed = [r for r in results if r.is_passed]
    if not passed:
        logger.info("自研池无标的通过筛选，流水线结束")
        return
    logger.info("%d 个标的通过筛选: %s",
                len(passed),
                ", ".join(f"{r.stock.name}({r.stock.code})" for r in passed))

    logger.info("[自研池] 大盘情况判断...")
    market = await judge_market()

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

    logger.info("[自研池] 发送通知 (来源: 自研池)...")
    await notify(market, signals, source="自研池")

    if market.is_tradable:
        logger.info("[自研池] 执行交易 (大盘可交易)...")
        executor = create_executor()
        records, trade_ids = await executor.execute(signals, source="自研池")
        logger.info("执行完成: %d 笔交易记录", len(records))
    else:
        logger.warning("[自研池] 大盘不宜交易，跳过执行: %s", market.reason)

    elapsed = (datetime.now() - start).total_seconds()
    logger.info("===== Pipeline [自研池] 完成，耗时 %.1f秒 =====", elapsed)


def run_once() -> None:
    """同步入口：执行一次完整流水线"""
    asyncio.run(pipeline())


def run_once_test() -> None:
    """测试入口：用石油新闻 + 临时去重跑通全流程"""
    asyncio.run(pipeline_test())


def run_once_research_pool() -> None:
    """同步入口：执行自研池流水线（链式筛选起，标明来源自研池）"""
    asyncio.run(pipeline_research_pool())
