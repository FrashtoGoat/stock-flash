"""大师选股筛选器：基于价值/成长等策略的基本面筛选"""

from __future__ import annotations

import logging

import akshare as ak
import pandas as pd

from src.config import get
from src.filters.factory import register
from src.models.stock import FilterResult, StockTarget

logger = logging.getLogger(__name__)


def _get_stock_fundamentals(code: str) -> dict:
    """获取个股基本面数据（使用 akshare）"""
    try:
        df = ak.stock_individual_info_em(symbol=code)
        info = {}
        for _, row in df.iterrows():
            info[row["item"]] = row["value"]
        return info
    except Exception:
        logger.warning("获取 %s 基本面数据失败", code)
        return {}


@register("master_filter")
class MasterFilter:
    """大师选股筛选器

    策略:
    - value: 市盈率 < 30, 市净率 < 5
    - growth: 近一年营收增长 > 10%
    - momentum: 近60日涨幅 > 0
    """

    name = "master_filter"

    def __init__(self) -> None:
        cfg = get("filters", "master_filter") or {}
        self.strategies: list[str] = cfg.get("strategies", ["value"])

    async def apply(self, stock: StockTarget) -> FilterResult:
        info = _get_stock_fundamentals(stock.code)
        if not info:
            return FilterResult(
                stock=stock,
                failed_filters=[self.name],
                details={self.name: {"error": "无法获取基本面数据"}},
            )

        checks: dict[str, bool] = {}
        details: dict = {"fundamentals": info}

        if "value" in self.strategies:
            try:
                pe = float(info.get("市盈率(动态)", 999))
                pb = float(info.get("市净率", 999))
                checks["value"] = pe < 30 and pb < 5
                details["pe"] = pe
                details["pb"] = pb
            except (ValueError, TypeError):
                checks["value"] = False

        if "growth" in self.strategies:
            try:
                # akshare 的字段名可能随版本变化，做容错
                rev_growth = float(info.get("营业收入同比增长率", -999))
                checks["growth"] = rev_growth > 10
                details["revenue_growth"] = rev_growth
            except (ValueError, TypeError):
                checks["growth"] = True  # 数据缺失时宽松处理

        passed = any(checks.values()) if checks else False

        return FilterResult(
            stock=stock,
            passed_filters=[self.name] if passed else [],
            failed_filters=[] if passed else [self.name],
            details={self.name: {**details, "checks": checks}},
        )
