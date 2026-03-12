"""技术面筛选器：实时行情 + 筹码分布 + 趋势分析

通过 DataFetcherManager 获取数据，自带故障切换和熔断保护。

检查维度：
  1. 实时行情: 量比(>阈值表示资金关注)、换手率(适中范围)
  2. 筹码分布: 获利比例(>阈值表示套牢盘少)、筹码集中度(高度集中表示控盘)
  3. 趋势分析: 均线多头排列(MA5>MA10>MA20)、MACD金叉/水上、价格站上MA20
"""

from __future__ import annotations

import logging
import math

import ta

from src.config import get
from src.data.fetcher_manager import get_chip_distribution, get_kline, get_realtime_quote
from src.filters.factory import register
from src.models.stock import FilterResult, StockTarget, TargetType

logger = logging.getLogger(__name__)

_DEFAULT_CONDITIONS = {
    "volume_ratio_min": 0.8,
    "volume_ratio_max": 5.0,
    "turnover_rate_min": 1.0,
    "turnover_rate_max": 15.0,
    "profit_ratio_min": 30.0,
    "ma_trend": "bullish",
    "require_above_ma20": True,
    "macd_mode": "positive",
}


def _safe_float(v, default=float("nan")) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


@register("technical_filter")
class TechnicalFilter:
    """技术面筛选器 — 行情/筹码/趋势 三维度"""

    name = "technical_filter"

    def __init__(self) -> None:
        cfg = get("filters", "technical_filter") or {}
        self.cond = {**_DEFAULT_CONDITIONS, **cfg.get("conditions", {})}

    async def apply(self, stock: StockTarget) -> FilterResult:
        if stock.target_type == TargetType.ETF:
            return FilterResult(
                stock=stock,
                passed_filters=[self.name],
                details={self.name: {"skip": "ETF不做技术筛选"}},
            )

        checks: dict[str, bool] = {}
        details: dict = {}

        # ---- 1. 实时行情 ----
        quote = get_realtime_quote(stock.code)
        vol_ratio = _safe_float(quote.get("量比"))
        turnover = _safe_float(quote.get("换手率"))
        cur_price = _safe_float(quote.get("最新"))

        if not math.isnan(vol_ratio):
            checks["volume_ratio"] = (
                self.cond["volume_ratio_min"] <= vol_ratio <= self.cond["volume_ratio_max"]
            )
            details["volume_ratio"] = round(vol_ratio, 2)
        else:
            checks["volume_ratio"] = True
            details["volume_ratio"] = "N/A"

        if not math.isnan(turnover):
            checks["turnover"] = (
                self.cond["turnover_rate_min"] <= turnover <= self.cond["turnover_rate_max"]
            )
            details["turnover_rate"] = round(turnover, 2)
        else:
            checks["turnover"] = True
            details["turnover_rate"] = "N/A"

        # ---- 2. 筹码分布 ----
        chip = get_chip_distribution(stock.code)
        if chip:
            profit_ratio = chip.get("profit_ratio", 0)
            checks["chip_profit"] = profit_ratio >= self.cond["profit_ratio_min"]
            details["chip"] = chip
        else:
            checks["chip_profit"] = True
            details["chip"] = "N/A (数据未获取)"

        # ---- 3. 趋势分析 ----
        df = get_kline(stock.code, count=60)
        if not df.empty and len(df) >= 20:
            close = df["收盘"].astype(float)
            volume = df["成交量"].astype(float)

            ma5 = close.rolling(5).mean().iloc[-1]
            ma10 = close.rolling(10).mean().iloc[-1]
            ma20 = close.rolling(20).mean().iloc[-1]
            last_close = close.iloc[-1]

            details["ma5"] = round(ma5, 2)
            details["ma10"] = round(ma10, 2)
            details["ma20"] = round(ma20, 2)
            details["last_close"] = round(last_close, 2)

            if self.cond["ma_trend"] == "bullish":
                checks["ma_trend"] = ma5 > ma10 > ma20
            elif self.cond["ma_trend"] == "up":
                checks["ma_trend"] = ma5 > ma20
            else:
                checks["ma_trend"] = True

            if self.cond["require_above_ma20"]:
                checks["above_ma20"] = last_close > ma20
            else:
                checks["above_ma20"] = True

            # MACD
            macd_line = ta.trend.macd(close)
            macd_signal = ta.trend.macd_signal(close)
            if macd_line is not None and macd_signal is not None:
                cur_macd = macd_line.iloc[-1]
                cur_sig = macd_signal.iloc[-1]
                prev_macd = macd_line.iloc[-2]
                prev_sig = macd_signal.iloc[-2]
                is_golden = prev_macd <= prev_sig and cur_macd > cur_sig
                is_positive = cur_macd > 0

                details["macd"] = round(cur_macd, 4)
                details["macd_signal"] = round(cur_sig, 4)
                details["is_golden_cross"] = is_golden
                details["macd_positive"] = is_positive

                mode = self.cond["macd_mode"]
                if mode == "golden":
                    checks["macd"] = is_golden
                elif mode == "positive":
                    checks["macd"] = is_positive or is_golden
                else:
                    checks["macd"] = True
            else:
                checks["macd"] = True

            # 量能趋势：近5日均量 > 近20日均量（放量趋势）
            avg_vol_5 = volume.tail(5).mean()
            avg_vol_20 = volume.tail(20).mean()
            if avg_vol_20 > 0:
                vol_trend = avg_vol_5 / avg_vol_20
                checks["vol_trend"] = vol_trend > 0.8
                details["vol_trend_ratio"] = round(vol_trend, 2)
            else:
                checks["vol_trend"] = True
        else:
            checks["ma_trend"] = True
            checks["above_ma20"] = True
            checks["macd"] = True
            checks["vol_trend"] = True
            details["kline_note"] = "K线数据不足"

        details["checks"] = checks
        core_pass = checks.get("ma_trend", False) and checks.get("above_ma20", False)
        all_pass = all(checks.values())

        passed = core_pass and (
            sum(checks.values()) >= len(checks) - 1
        )

        return FilterResult(
            stock=stock,
            passed_filters=[self.name] if passed else [],
            failed_filters=[] if passed else [self.name],
            details={self.name: details},
        )
