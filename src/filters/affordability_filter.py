"""可买性筛选器：价格门槛 + 板块交易权限

筛选逻辑：
  1. 股价 < max_price（默认100元），买得起
  2. 必须是沪深主板 或 ETF（用户有交易权限）
"""

from __future__ import annotations

import logging

import akshare as ak

from src.config import get
from src.filters.factory import register
from src.models.stock import BoardType, FilterResult, StockTarget, TargetType

logger = logging.getLogger(__name__)


def _get_current_price(code: str) -> float | None:
    """获取最新股价"""
    try:
        df = ak.stock_bid_ask_em(symbol=code)
        for _, row in df.iterrows():
            if row["item"] == "最新":
                return float(row["value"])
        return None
    except Exception:
        logger.warning("获取 %s 实时价格失败", code)
        return None


@register("affordability_filter")
class AffordabilityFilter:
    """可买性筛选器 — 价格 + 板块权限"""

    name = "affordability_filter"

    def __init__(self) -> None:
        cfg = get("filters", "affordability_filter") or {}
        self.max_price: float = cfg.get("max_price", 100.0)
        allowed = cfg.get("allowed_boards", ["main"])
        self.allowed_boards: set[BoardType] = {BoardType(b) for b in allowed}

    async def apply(self, stock: StockTarget) -> FilterResult:
        checks: dict[str, bool] = {}
        details: dict = {}

        if stock.target_type == TargetType.ETF:
            checks["board"] = True
            details["board_note"] = "ETF无门槛"
        else:
            checks["board"] = stock.board in self.allowed_boards
            details["board"] = stock.board.value
            details["board_note"] = stock.tradable_note

        price = _get_current_price(stock.code)
        if price is not None:
            checks["price"] = price <= self.max_price
            details["current_price"] = price
            details["max_price"] = self.max_price
        else:
            checks["price"] = True
            details["price_note"] = "未获取到价格，放行"

        passed = all(checks.values())
        details["checks"] = checks

        if not passed:
            reasons = []
            if not checks.get("board", True):
                reasons.append(f"板块={stock.board.value}({stock.tradable_note})")
            if not checks.get("price", True):
                reasons.append(f"价格={price:.2f}>{self.max_price}")
            logger.info("%s(%s) 不可买: %s", stock.name, stock.code, ", ".join(reasons))

        return FilterResult(
            stock=stock,
            passed_filters=[self.name] if passed else [],
            failed_filters=[] if passed else [self.name],
            details={self.name: details},
        )
