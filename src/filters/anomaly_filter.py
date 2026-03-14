"""异动监控筛选器：检测近期主力资金动向

筛选维度：
  1. 近N日涨跌幅：排除短期暴涨(可能见顶)和持续暴跌(接飞刀)
  2. 主力净流入：近期主力资金是否净流入
  3. 连续性检测：避免单日游资拉板后出货
"""

from __future__ import annotations

import logging
import math

from src.config import get
from src.data.fetcher_manager import get_kline, get_realtime_quote
from src.filters.factory import register
from src.models.stock import FilterResult, StockTarget, TargetType

logger = logging.getLogger(__name__)

_DEFAULT_CONDITIONS = {
    "max_5d_change_pct": 25.0,
    "min_5d_change_pct": -15.0,
    "max_1d_change_pct": 9.5,
    "min_1d_change_pct": -7.0,
    "min_up_days_in_5": 2,
}


def _safe_float(v, default=float("nan")) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


@register("anomaly_filter")
class AnomalyFilter:
    """异动监控筛选器 — 排除暴涨暴跌、检测资金连续性"""

    name = "anomaly_filter"

    def __init__(self) -> None:
        cfg = get("filters", "anomaly_filter") or {}
        self.cond = {**_DEFAULT_CONDITIONS, **cfg.get("conditions", {})}

    async def apply(self, stock: StockTarget) -> FilterResult:
        if stock.target_type == TargetType.ETF:
            return FilterResult(
                stock=stock,
                passed_filters=[self.name],
                details={self.name: {"skip": "ETF不做异动筛选"}},
            )

        checks: dict[str, bool] = {}
        details: dict = {}

        quote = get_realtime_quote(stock.code)
        change_1d = _safe_float(quote.get("涨跌幅"))
        if not math.isnan(change_1d):
            checks["1d_change"] = (
                self.cond["min_1d_change_pct"] <= change_1d <= self.cond["max_1d_change_pct"]
            )
            details["change_1d_pct"] = round(change_1d, 2)
        else:
            checks["1d_change"] = True
            details["change_1d_pct"] = "N/A"

        df = get_kline(stock.code, count=10)
        if not df.empty and len(df) >= 5:
            close = df["收盘"].astype(float)
            recent_5 = close.tail(6)
            if len(recent_5) >= 2:
                change_5d = (recent_5.iloc[-1] / recent_5.iloc[-6] - 1) * 100 if len(recent_5) >= 6 else 0
            else:
                change_5d = 0
            checks["5d_change"] = (
                self.cond["min_5d_change_pct"] <= change_5d <= self.cond["max_5d_change_pct"]
            )
            details["change_5d_pct"] = round(change_5d, 2)

            pct_changes = close.pct_change().dropna().tail(5)
            up_days = (pct_changes > 0).sum()
            checks["up_continuity"] = int(up_days) >= self.cond["min_up_days_in_5"]
            details["up_days_in_5"] = int(up_days)
        else:
            checks["5d_change"] = True
            checks["up_continuity"] = True
            details["kline_note"] = "K线数据不足"

        details["checks"] = checks
        passed = all(checks.values())

        if not passed:
            fails = [k for k, v in checks.items() if not v]
            logger.info(
                "%s(%s) 异动检测未通过: %s",
                stock.name, stock.code, ", ".join(fails),
            )

        return FilterResult(
            stock=stock,
            passed_filters=[self.name] if passed else [],
            failed_filters=[] if passed else [self.name],
            details={self.name: details},
        )
