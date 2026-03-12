"""大师选股筛选器：基本面深度筛选

核心理念：选出基本面扎实的标的，即使短期被套也有翻身机会。
筛选维度：
  1. 盈利能力: ROE > 阈值，表明公司赚钱效率高
  2. 估值合理: PE < 阈值 且 PB < 阈值，避免泡沫
  3. 成长性:   营收同比增长 > 阈值，具备增长动力
  4. 财务健康: 资产负债率 < 阈值，负债可控
  5. 龙头指标: 总市值排名靠前（>= 阈值），行业地位稳固

策略: 满足 (盈利 + 估值 + 财务健康) 的必过，成长/龙头为加分项。
"""

from __future__ import annotations

import logging

import akshare as ak

from src.config import get
from src.filters.factory import register
from src.models.stock import FilterResult, StockTarget, TargetType

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLDS = {
    "pe_max": 40,
    "pb_max": 6,
    "roe_min": 8,
    "debt_ratio_max": 70,
    "revenue_growth_min": 5,
    "market_cap_min_yi": 50,
}


def _get_fundamentals(code: str) -> dict:
    """获取个股基本面数据（akshare stock_individual_info_em）"""
    try:
        df = ak.stock_individual_info_em(symbol=code)
        info: dict = {}
        for _, row in df.iterrows():
            info[row["item"]] = row["value"]
        return info
    except Exception:
        logger.warning("获取 %s 基本面数据失败", code)
        return {}


def _safe_float(value, default: float = float("nan")) -> float:
    try:
        v = float(value)
        return v
    except (ValueError, TypeError):
        return default


@register("master_filter")
class MasterFilter:
    """大师选股筛选器 — 基本面(财报/龙头/市占率/财务健康)

    即使被套也有翻身机会的标的特征：
    - 盈利能力强 (ROE)
    - 估值不贵 (PE/PB)
    - 财务稳健 (资产负债率)
    - 有成长空间 (营收增长)
    - 行业龙头 (市值够大)
    """

    name = "master_filter"

    def __init__(self) -> None:
        cfg = get("filters", "master_filter") or {}
        self.th = {**_DEFAULT_THRESHOLDS, **cfg.get("thresholds", {})}

    async def apply(self, stock: StockTarget) -> FilterResult:
        if stock.target_type == TargetType.ETF:
            return FilterResult(
                stock=stock,
                passed_filters=[self.name],
                details={self.name: {"skip": "ETF不做基本面筛选"}},
            )

        info = _get_fundamentals(stock.code)
        if not info:
            return FilterResult(
                stock=stock,
                failed_filters=[self.name],
                details={self.name: {"error": "无法获取基本面数据"}},
            )

        pe = _safe_float(info.get("市盈率(动态)"))
        pb = _safe_float(info.get("市净率"))
        roe = _safe_float(info.get("净资产收益率"))
        debt = _safe_float(info.get("资产负债率"))
        rev_growth = _safe_float(info.get("营业收入同比增长率"))
        cap_raw = info.get("总市值", "0")
        market_cap_yi = _safe_float(cap_raw) / 1e8

        checks: dict[str, bool] = {}
        details: dict = {
            "pe": pe, "pb": pb, "roe": roe,
            "debt_ratio": debt, "revenue_growth": rev_growth,
            "market_cap_yi": round(market_cap_yi, 1),
        }

        import math
        has_pe = not math.isnan(pe)
        has_pb = not math.isnan(pb)
        has_roe = not math.isnan(roe)
        has_debt = not math.isnan(debt)

        checks["valuation"] = (
            (has_pe and pe > 0 and pe < self.th["pe_max"])
            and (has_pb and pb > 0 and pb < self.th["pb_max"])
        )
        checks["profitability"] = has_roe and roe > self.th["roe_min"]
        checks["financial_health"] = has_debt and debt < self.th["debt_ratio_max"]
        checks["growth"] = not math.isnan(rev_growth) and rev_growth > self.th["revenue_growth_min"]
        checks["leader"] = market_cap_yi >= self.th["market_cap_min_yi"]

        core_pass = checks["profitability"] and checks["valuation"] and checks["financial_health"]
        bonus = checks["growth"] or checks["leader"]
        passed = core_pass or (checks["valuation"] and bonus)

        details["checks"] = checks
        details["core_pass"] = core_pass
        details["verdict"] = "通过" if passed else "未通过"

        return FilterResult(
            stock=stock,
            passed_filters=[self.name] if passed else [],
            failed_filters=[] if passed else [self.name],
            details={self.name: details},
        )
