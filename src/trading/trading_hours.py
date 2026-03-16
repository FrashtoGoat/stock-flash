"""A 股交易日与交易时段判断：非交易日或非交易时段可直接跳过流水线后续操作。"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

# 北京时区：A 股 9:30-11:30、13:00-15:00
_MORNING_START = time(9, 30)
_MORNING_END = time(11, 30)
_AFTERNOON_START = time(13, 0)
_AFTERNOON_END = time(15, 0)

_trading_dates_cache: Optional[set[str]] = None
_trading_dates_cache_date: Optional[date] = None


def _load_trading_dates() -> set[str]:
    """加载 A 股交易日历（akshare），带简单缓存。"""
    global _trading_dates_cache, _trading_dates_cache_date
    today = date.today()
    if _trading_dates_cache is not None and _trading_dates_cache_date == today:
        return _trading_dates_cache
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        if df is not None and not df.empty and "trade_date" in df.columns:
            _trading_dates_cache = set(df["trade_date"].astype(str).tolist())
            _trading_dates_cache_date = today
            return _trading_dates_cache
    except Exception as e:
        logger.debug("加载交易日历失败，回退到周一至五: %s", e)
    _trading_dates_cache = None
    _trading_dates_cache_date = today
    return set()


def is_trading_day(d: Optional[date] = None) -> bool:
    """判断是否为 A 股交易日。d 默认今天；若日历加载失败则按周一～五回退。"""
    if d is None:
        d = date.today()
    dates = _load_trading_dates()
    if dates:
        return d.strftime("%Y-%m-%d") in dates
    # 回退：仅排除周末
    return d.weekday() < 5


def is_trading_time(dt: Optional[datetime] = None) -> bool:
    """判断当前（或给定时间）是否在 A 股交易时段内（9:30-11:30、13:00-15:00）。
    统一按北京时间(Asia/Shanghai)判断，避免本机时区不同导致误判。"""
    if dt is None:
        if ZoneInfo is not None:
            dt = datetime.now(ZoneInfo("Asia/Shanghai"))
        else:
            dt = datetime.now()
    # 若传入为带 tz 的时间，转为北京时间；若为 naive，则按其本身 time() 视为本地（尽量不抛错）
    if getattr(dt, "tzinfo", None) is not None and ZoneInfo is not None:
        dt = dt.astimezone(ZoneInfo("Asia/Shanghai"))
    t = dt.time()
    if _MORNING_START <= t <= _MORNING_END:
        return True
    if _AFTERNOON_START <= t <= _AFTERNOON_END:
        return True
    return False


def is_in_trading_session(dt: Optional[datetime] = None) -> bool:
    """是否处于「交易日 + 交易时段」内。"""
    if dt is None:
        if ZoneInfo is not None:
            dt = datetime.now(ZoneInfo("Asia/Shanghai"))
        else:
            dt = datetime.now()
    return is_trading_day(dt.date()) and is_trading_time(dt)


def skip_reason(dt: Optional[datetime] = None) -> str:
    """若当前应跳过流水线，返回原因字符串；否则返回空字符串。"""
    if dt is None:
        if ZoneInfo is not None:
            dt = datetime.now(ZoneInfo("Asia/Shanghai"))
        else:
            dt = datetime.now()
    if not is_trading_day(dt.date()):
        return "非交易日"
    if not is_trading_time(dt):
        return "非交易时段（A股 9:30-11:30、13:00-15:00）"
    return ""
