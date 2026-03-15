"""收盘后复盘：关联新闻表与交易表，统计各源准确率与建议"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from src.config import get
from src.db.news_repository import list_news_with_trades
from src.db.repository import get_trades_by_ids

logger = logging.getLogger(__name__)


def _parse_trade_ids(trade_ids_str: str | None) -> list[int]:
    if not trade_ids_str or not trade_ids_str.strip():
        return []
    return [int(x.strip()) for x in trade_ids_str.split(",") if x.strip().isdigit()]


def _realized_pnl_for_trades(trades: list) -> float:
    """根据买卖记录估算已实现盈亏（按股票 FIFO 匹配买卖）。"""
    buys = [t for t in trades if t.direction == "buy"]
    sells = [t for t in trades if t.direction == "sell"]
    if not buys or not sells:
        return 0.0
    # 按股票分组
    buy_by_code: dict[str, list[tuple[float, float]]] = defaultdict(list)
    sell_by_code: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for b in sorted(buys, key=lambda x: x.exec_time or x.created_at):
        buy_by_code[b.stock_code].append((b.amount, b.exec_price or 0.0))
    for s in sorted(sells, key=lambda x: x.exec_time or x.created_at):
        sell_by_code[s.stock_code].append((s.amount, s.exec_price or 0.0))

    pnl = 0.0
    for code, sell_lots in sell_by_code.items():
        buy_lots = list(buy_by_code.get(code, []))
        if not buy_lots:
            continue
        for sell_amt, sell_price in sell_lots:
            cost = 0.0
            to_consume = sell_amt
            new_buy_lots = []
            for a, p in buy_lots:
                if to_consume <= 0:
                    new_buy_lots.append((a, p))
                    continue
                use = min(a, to_consume)
                cost += use * p
                to_consume -= use
                if a > use:
                    new_buy_lots.append((a - use, p))
            buy_lots = new_buy_lots
            pnl += sell_amt * sell_price - cost
    return pnl


def run_review(since_days: int = 1, source: str | None = None) -> None:
    """
    复盘：统计各新闻源触发的交易数量与盈亏，输出报告与调整建议。
    建议收盘后运行，since_days 默认 1 表示最近一天。
    """
    storage_cfg = get("storage") or {}
    if not storage_cfg.get("enabled", False):
        logger.warning("未启用 storage，无法进行新闻-交易复盘")
        return

    since = datetime.now() - timedelta(days=since_days)
    news_list = list_news_with_trades(since=since, source=source, limit=1000)
    if not news_list:
        logger.info("复盘: 统计区间内无触发交易的新闻")
        return

    all_trade_ids: list[int] = []
    for n in news_list:
        all_trade_ids.extend(_parse_trade_ids(n.trade_ids))
    all_trade_ids = list(dict.fromkeys(all_trade_ids))
    trades = get_trades_by_ids(all_trade_ids)
    trade_map = {t.id: t for t in trades}

    # 按来源统计
    by_source: dict[str, dict] = defaultdict(lambda: {"news_count": 0, "trade_count": 0, "trade_ids": set()})
    for n in news_list:
        s = n.source or "unknown"
        by_source[s]["news_count"] += 1
        for tid in _parse_trade_ids(n.trade_ids):
            by_source[s]["trade_ids"].add(tid)
    for s, d in by_source.items():
        d["trade_count"] = len(d["trade_ids"])

    # 各源涉及交易的可计算已实现盈亏（用全部 trades 子集）
    for s, d in by_source.items():
        subset = [trade_map[tid] for tid in d["trade_ids"] if tid in trade_map]
        d["realized_pnl"] = _realized_pnl_for_trades(subset)

    # 输出报告
    total_news = len(news_list)
    total_trades = len(all_trade_ids)
    total_pnl = sum(d["realized_pnl"] for d in by_source.values())
    logger.info("===== 新闻-交易复盘 (近 %d 天) =====", since_days)
    logger.info("触发交易的新闻: %d 条 | 关联交易: %d 笔 | 估算已实现盈亏: %.2f 元", total_news, total_trades, total_pnl)
    logger.info("按来源:")
    for s, d in sorted(by_source.items(), key=lambda x: -x[1]["news_count"]):
        logger.info("  [%s] 新闻 %d 条, 交易 %d 笔, 已实现盈亏 %.2f 元", s, d["news_count"], d["trade_count"], d["realized_pnl"])

    # 简单建议
    if by_source:
        worst = min(by_source.items(), key=lambda x: x[1]["realized_pnl"])
        if worst[1]["trade_count"] >= 1 and worst[1]["realized_pnl"] < 0:
            logger.info("建议: 来源 [%s] 近期导致亏损，可考虑降低权重或优化该源筛选/LLM 提示词", worst[0])
        logger.info("可根据上述准确率调整: 新闻源权重、LLM 提示词、链式筛选通过条件。")
