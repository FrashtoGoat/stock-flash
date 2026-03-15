"""DataFetcherManager: 数据获取管理器

功能：
  1. 多数据源自动故障切换（akshare → 备用源）
  2. 熔断保护：连续失败 N 次后短暂熔断该数据源
  3. 统一接口：K线、实时行情、筹码分布
"""

from __future__ import annotations

import logging
import time
from typing import Callable

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """简单熔断器：连续失败 threshold 次后，冷却 cooldown 秒"""

    def __init__(self, threshold: int = 3, cooldown: float = 60.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def is_open(self, source: str) -> bool:
        until = self._open_until.get(source, 0)
        if time.time() < until:
            return True
        if until > 0:
            self._failures[source] = 0
            self._open_until[source] = 0
        return False

    def record_success(self, source: str) -> None:
        self._failures[source] = 0

    def record_failure(self, source: str) -> None:
        self._failures[source] = self._failures.get(source, 0) + 1
        if self._failures[source] >= self.threshold:
            self._open_until[source] = time.time() + self.cooldown
            logger.warning("数据源 %s 熔断 %.0f 秒 (连续失败 %d 次)",
                           source, self.cooldown, self._failures[source])


_breaker = CircuitBreaker(threshold=3, cooldown=60)


def _try_sources(source_funcs: list[tuple[str, Callable]], **kwargs) -> pd.DataFrame | None:
    """依次尝试多个数据源，返回第一个成功的结果"""
    for name, func in source_funcs:
        if _breaker.is_open(name):
            logger.debug("数据源 %s 处于熔断状态，跳过", name)
            continue
        try:
            result = func(**kwargs)
            if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                _breaker.record_success(name)
                return result
        except Exception as e:
            logger.debug("数据源 %s 失败: %s", name, e)
            _breaker.record_failure(name)
    return None


def get_kline(code: str, period: str = "daily", count: int = 120) -> pd.DataFrame:
    """获取K线数据，自动故障切换"""

    def _akshare_hist(code=code, period=period, count=count, **_kw):
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        return df.tail(count) if len(df) > count else df

    result = _try_sources([
        ("akshare_hist", lambda **kw: _akshare_hist(**kw)),
    ])
    df = result if isinstance(result, pd.DataFrame) else pd.DataFrame()
    if not df.empty and "日期" in df.columns and "收盘" in df.columns:
        last_date = str(df["日期"].iloc[-1])
        last_close = float(df["收盘"].iloc[-1])
        logger.info("行情[日线] %s 条数=%d 最新日期=%s 最新收盘=%.2f 获取成功",
                    code, len(df), last_date, last_close)
    elif not df.empty:
        logger.info("行情[日线] %s 条数=%d 获取成功（无日期/收盘列）", code, len(df))
    else:
        logger.warning("行情[日线] %s 获取失败或无数据", code)
    return df


def get_realtime_quote(code: str) -> dict:
    """获取实时行情：量比、换手率、最新价等"""

    def _akshare_quote(code=code, **_kw):
        df = ak.stock_bid_ask_em(symbol=code)
        info = {}
        for _, row in df.iterrows():
            info[row["item"]] = row["value"]
        return info

    def _akshare_indicator(code=code, **_kw):
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "最新": r.get("最新价"),
            "量比": r.get("量比"),
            "换手率": r.get("换手率"),
            "涨跌幅": r.get("涨跌幅"),
            "成交量": r.get("成交量"),
            "成交额": r.get("成交额"),
            "流通市值": r.get("流通市值"),
            "总市值": r.get("总市值"),
        }

    result = _try_sources([
        ("akshare_bid_ask", lambda **kw: _akshare_quote(**kw)),
        ("akshare_spot", lambda **kw: _akshare_indicator(**kw)),
    ])
    out = result if isinstance(result, dict) else {}
    price = out.get("最新") if isinstance(out.get("最新"), (int, float)) else None
    if price is not None:
        logger.info("行情[实时] %s 最新价=%.2f 获取成功", code, price)
    else:
        logger.warning("行情[实时] %s 最新价获取失败", code)
    return out


def get_chip_distribution(code: str) -> dict:
    """获取筹码分布相关数据（成本集中度）

    返回:
        avg_cost: 平均成本
        profit_ratio: 获利比例 (0-100)
        concentration_70: 70%筹码集中度
        concentration_90: 90%筹码集中度
    """

    def _akshare_chip(code=code, **_kw):
        try:
            df = ak.stock_cyq_em(symbol=code, adjust="qfq")
            if df.empty:
                return None
            latest = df.iloc[-1]
            return {
                "avg_cost": float(latest.get("平均成本", 0)),
                "profit_ratio": float(latest.get("获利比例", 0)),
                "concentration_70": float(latest.get("70集中度", 0)),
                "concentration_90": float(latest.get("90集中度", 0)),
            }
        except Exception:
            return None

    result = _try_sources([
        ("akshare_cyq", lambda **kw: _akshare_chip(**kw)),
    ])
    return result if isinstance(result, dict) else {}
