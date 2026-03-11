"""技术面筛选器：基于技术指标的筛选"""

from __future__ import annotations

import logging

import akshare as ak
import pandas as pd
import ta

from src.config import get
from src.filters.factory import register
from src.models.stock import FilterResult, StockTarget

logger = logging.getLogger(__name__)


def _get_kline(code: str, period: str = "daily", count: int = 120) -> pd.DataFrame:
    """获取K线数据"""
    try:
        df = ak.stock_zh_a_hist(symbol=code, period=period, adjust="qfq")
        return df.tail(count) if len(df) > count else df
    except Exception:
        logger.warning("获取 %s K线数据失败", code)
        return pd.DataFrame()


@register("technical_filter")
class TechnicalFilter:
    """技术面筛选器

    检查:
    - 均线趋势 (MA5 > MA20 视为上升趋势)
    - 量比 (当日成交量 / 过去5日均量)
    - MACD 金叉/死叉
    """

    name = "technical_filter"

    def __init__(self) -> None:
        cfg = get("filters", "technical_filter") or {}
        cond = cfg.get("conditions", {})
        self.ma_trend = cond.get("ma_trend", "up")
        self.volume_ratio_min = cond.get("volume_ratio_min", 1.0)
        self.macd_signal = cond.get("macd_signal", "any")

    async def apply(self, stock: StockTarget) -> FilterResult:
        df = _get_kline(stock.code)
        if df.empty or len(df) < 20:
            return FilterResult(
                stock=stock,
                failed_filters=[self.name],
                details={self.name: {"error": "K线数据不足"}},
            )

        close = df["收盘"].astype(float)
        volume = df["成交量"].astype(float)

        checks: dict[str, bool] = {}
        details: dict = {}

        # 均线趋势
        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        if self.ma_trend == "up":
            checks["ma_trend"] = ma5 > ma20
        elif self.ma_trend == "down":
            checks["ma_trend"] = ma5 < ma20
        else:
            checks["ma_trend"] = True
        details["ma5"] = round(ma5, 2)
        details["ma20"] = round(ma20, 2)

        # 量比
        avg_vol_5 = volume.tail(6).head(5).mean()
        cur_vol = volume.iloc[-1]
        vol_ratio = cur_vol / avg_vol_5 if avg_vol_5 > 0 else 0
        checks["volume_ratio"] = vol_ratio >= self.volume_ratio_min
        details["volume_ratio"] = round(vol_ratio, 2)

        # MACD
        macd_line = ta.trend.macd(close)
        macd_signal_line = ta.trend.macd_signal(close)
        if macd_line is not None and macd_signal_line is not None:
            cur_macd = macd_line.iloc[-1]
            cur_signal = macd_signal_line.iloc[-1]
            prev_macd = macd_line.iloc[-2]
            prev_signal = macd_signal_line.iloc[-2]
            is_golden = prev_macd <= prev_signal and cur_macd > cur_signal

            if self.macd_signal == "golden":
                checks["macd"] = is_golden
            else:
                checks["macd"] = True
            details["macd"] = round(cur_macd, 4)
            details["macd_signal"] = round(cur_signal, 4)
            details["is_golden_cross"] = is_golden
        else:
            checks["macd"] = self.macd_signal == "any"

        passed = all(checks.values())
        return FilterResult(
            stock=stock,
            passed_filters=[self.name] if passed else [],
            failed_filters=[] if passed else [self.name],
            details={self.name: {**details, "checks": checks}},
        )
