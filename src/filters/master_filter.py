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
import math

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


def _safe_float(value, default: float = float("nan")) -> float:
    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").strip()
        if value in ("", "-", "None", "False"):
            return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _get_valuation(code: str) -> dict:
    """从百度接口获取最新 PE(TTM) 和 PB"""
    result: dict = {}
    for indicator, key in [("市盈率(TTM)", "pe"), ("市净率", "pb")]:
        try:
            df = ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator, period="近一年")
            if df is not None and not df.empty:
                result[key] = float(df.iloc[-1]["value"])
        except Exception as e:
            logger.debug("获取 %s %s 失败: %s", code, indicator, e)
    return result


def _get_financials(code: str) -> dict:
    """从同花顺接口获取 ROE、资产负债率、营收增长率"""
    try:
        df = ak.stock_financial_abstract_ths(symbol=code, indicator="按年度")
        if df is None or df.empty:
            return {}
        latest = df.iloc[-1]
        return {
            "roe": _safe_float(latest.get("净资产收益率")),
            "debt_ratio": _safe_float(latest.get("资产负债率")),
            "revenue_growth": _safe_float(latest.get("营业总收入同比增长率")),
            "report_period": str(latest.get("报告期", "")),
        }
    except Exception as e:
        logger.debug("获取 %s 财报摘要失败: %s", code, e)
        return {}


def _get_market_cap(code: str) -> float:
    """从 stock_individual_info_em 获取总市值（亿）"""
    try:
        df = ak.stock_individual_info_em(symbol=code)
        for _, row in df.iterrows():
            if row["item"] == "总市值":
                return _safe_float(row["value"]) / 1e8
    except Exception:
        pass
    return float("nan")


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

        valuation = _get_valuation(stock.code)
        financials = _get_financials(stock.code)
        market_cap_yi = _get_market_cap(stock.code)

        pe = valuation.get("pe", float("nan"))
        pb = valuation.get("pb", float("nan"))
        roe = financials.get("roe", float("nan"))
        debt = financials.get("debt_ratio", float("nan"))
        rev_growth = financials.get("revenue_growth", float("nan"))

        checks: dict[str, bool] = {}
        details: dict = {
            "pe": pe, "pb": pb, "roe": roe,
            "debt_ratio": debt, "revenue_growth": rev_growth,
            "market_cap_yi": round(market_cap_yi, 1) if not math.isnan(market_cap_yi) else "N/A",
            "report_period": financials.get("report_period", "N/A"),
        }

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
        checks["leader"] = not math.isnan(market_cap_yi) and market_cap_yi >= self.th["market_cap_min_yi"]

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
