"""股票池维护：拉取行情、按配置规则更新 watch/stable/high/removed"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from src.config import get
from src.data.fetcher_manager import get_kline, get_realtime_quote
from src.db.models import StockPool
from src.db.stock_pool_repository import (
    is_source_news_all_expired,
    list_active,
    update_pool_type,
    update_prices_batch,
)

logger = logging.getLogger(__name__)


def _safe_float(v, default: float | None = None) -> float | None:
    try:
        if v is None:
            return default
        f = float(v)
        return f if not math.isnan(f) else default
    except (ValueError, TypeError):
        return default


def _get_quote_for_pool(code: str) -> tuple[float | None, float | None, float | None]:
    """返回 (latest_price, change_1d_pct, change_5d_pct)。"""
    price, c1, c5 = None, None, None
    quote = get_realtime_quote(code)
    if quote:
        price = _safe_float(quote.get("最新"))
        c1 = _safe_float(quote.get("涨跌幅"))
    df = get_kline(code, count=10)
    if not df.empty and len(df) >= 6:
        close = df["收盘"].astype(float)
        last = close.iloc[-1]
        first_5 = close.iloc[-6]
        if first_5 and first_5 != 0:
            c5 = (last / first_5 - 1) * 100
        if price is None and len(close) > 0:
            price = float(close.iloc[-1])
    return price, c1, c5


def maintain() -> None:
    """
    池维护：对 list_active() 的每条记录拉取最新价与涨跌幅，按配置做状态流转。
    在流水线 Step 2 后（mark_expired 之后）调用。
    """
    cfg = get("stock_pool") or {}
    if not cfg.get("enabled", False):
        return
    active = list_active()
    if not active:
        logger.debug("股票池维护: 无活跃记录")
        return

    now = datetime.now()
    stable_watch_hours = cfg.get("stable_watch_hours", 24)
    watch_max_hours = cfg.get("watch_max_hours", 72)
    stable_min_1d = cfg.get("stable_min_1d_pct", -3.0)
    stable_max_1d = cfg.get("stable_max_1d_pct", 5.0)
    stable_min_5d = cfg.get("stable_min_5d_pct", -10.0)
    stable_max_5d = cfg.get("stable_max_5d_pct", 20.0)
    high_threshold_5d = cfg.get("high_threshold_5d_pct", 15.0)
    remove_stable_when_expired = cfg.get("remove_stable_when_news_expired", True)
    allow_high_to_stable = cfg.get("allow_high_to_stable", False)

    updates: dict[str, tuple[float | None, float | None, float | None]] = {}
    for row in active:
        price, c1, c5 = _get_quote_for_pool(row.stock_code)
        updates[row.stock_code] = (price, c1, c5)

    update_prices_batch(updates)

    for row in active:
        code = row.stock_code
        pt = row.pool_type
        entry = row.entry_time
        hours_in = (now - entry).total_seconds() / 3600
        price, c1, c5 = updates.get(code, (None, None, None))
        c1 = _safe_float(c1)
        c5 = _safe_float(c5)
        all_expired = is_source_news_all_expired(row.source_news_ids)

        if pt == "watch":
            if all_expired:
                update_pool_type(code, "removed", "news_expired")
                logger.info("股票池 %s(%s) 关联新闻已过期 -> 移除", row.stock_name or code, code)
                continue
            if hours_in >= watch_max_hours:
                update_pool_type(code, "removed", "watch_timeout")
                logger.info("股票池 %s(%s) 观察超时 -> 移除", row.stock_name or code, code)
                continue
            if hours_in >= stable_watch_hours and c1 is not None and c5 is not None:
                if stable_min_1d <= c1 <= stable_max_1d and stable_min_5d <= c5 <= stable_max_5d:
                    update_pool_type(code, "stable")
                    logger.info("股票池 %s(%s) 观察满%.0fh且价格稳定 -> 稳定池", row.stock_name or code, code, stable_watch_hours)

        elif pt == "stable":
            if all_expired and remove_stable_when_expired:
                update_pool_type(code, "removed", "news_expired")
                logger.info("股票池 %s(%s) 稳定池关联新闻已过期 -> 移除", row.stock_name or code, code)
                continue
            if c5 is not None and c5 >= high_threshold_5d:
                update_pool_type(code, "high")
                logger.info("股票池 %s(%s) 5日涨幅%.1f%% -> 高位池", row.stock_name or code, code, c5)

        elif pt == "high":
            if all_expired:
                update_pool_type(code, "removed", "news_expired")
                logger.info("股票池 %s(%s) 高位池关联新闻已过期 -> 移除", row.stock_name or code, code)
            elif allow_high_to_stable and c5 is not None and stable_min_5d <= c5 <= stable_max_5d and c1 is not None and stable_min_1d <= c1 <= stable_max_1d:
                update_pool_type(code, "stable")

    logger.info("股票池维护完成: 处理 %d 条活跃记录", len(active))
