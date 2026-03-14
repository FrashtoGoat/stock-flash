"""机构/聪明资金筛选器：十大股东机构 + 龙虎榜

筛选维度：
  1. 机构持仓：十大股东中是否有基金/社保/QFII/保险/证金等机构持仓
  2. 龙虎榜：近期是否上过龙虎榜（异动/大额成交，主力关注）

理念：跟随聪明资金（机构 + 龙虎榜资金），它们的研究/博弈能力远强于散户。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import akshare as ak

from src.config import get
from src.filters.factory import register
from src.models.stock import FilterResult, StockTarget, TargetType

logger = logging.getLogger(__name__)

_INSTITUTION_KEYWORDS = [
    "基金", "社保", "保险", "QFII", "信托", "证金", "汇金",
    "养老", "年金", "资管", "理财", "证券金融",
]


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def _check_institutions(code: str) -> dict:
    """检查十大股东中的机构持仓（新浪财经接口）"""
    try:
        df = ak.stock_main_stock_holder(stock=code)
        if df is None or df.empty:
            return {"has_data": False}

        latest_date = df["截至日期"].max()
        latest = df[df["截至日期"] == latest_date]

        institution_holders = []
        for _, row in latest.iterrows():
            holder_name = str(row.get("股东名称", ""))
            for kw in _INSTITUTION_KEYWORDS:
                if kw in holder_name:
                    institution_holders.append({
                        "name": holder_name[:25],
                        "ratio": _safe_float(row.get("持股比例")),
                    })
                    break

        return {
            "has_data": True,
            "period": str(latest_date),
            "total_holders": len(latest),
            "institution_count": len(institution_holders),
            "institutions": institution_holders[:5],
        }
    except Exception as e:
        logger.debug("获取 %s 十大股东失败: %s", code, e)
        return {"has_data": False, "error": str(e)}


def _check_lhb(code: str, recent_days: int = 10) -> dict:
    """检查近期是否上过龙虎榜（东方财富个股龙虎榜上榜日期）"""
    try:
        df = ak.stock_lhb_stock_detail_date_em(symbol=code)
        if df is None or df.empty:
            return {"has_data": False, "lhb_recent": False, "lhb_dates": []}
        date_col = None
        for c in ["上榜日期", "交易日期"]:
            if c in df.columns:
                date_col = c
                break
        if date_col is None and len(df.columns) >= 3:
            date_col = df.columns[2]
        if date_col is None:
            return {"has_data": True, "lhb_recent": False, "lhb_dates": []}
        dates = []
        for _, row in df.iterrows():
            d = row.get(date_col)
            if d is None:
                continue
            ds = str(d).strip()
            if len(ds) >= 8:
                try:
                    dt = datetime.strptime(ds[:10], "%Y-%m-%d")
                    dates.append(dt)
                except ValueError:
                    pass
        if not dates:
            return {"has_data": True, "lhb_recent": False, "lhb_dates": []}
        cutoff = datetime.now() - timedelta(days=recent_days)
        recent = [d for d in dates if d >= cutoff]
        recent_str = sorted(set(d.strftime("%Y-%m-%d") for d in recent), reverse=True)[:5]
        return {
            "has_data": True,
            "lhb_recent": len(recent) > 0,
            "lhb_dates": recent_str,
            "lhb_count_recent": len(recent),
        }
    except Exception as e:
        logger.debug("获取 %s 龙虎榜日期失败: %s", code, e)
        return {"has_data": False, "lhb_recent": False, "lhb_dates": [], "error": str(e)}


@register("institution_filter")
class InstitutionFilter:
    """机构/聪明资金筛选器 — 跟随机构"""

    name = "institution_filter"

    def __init__(self) -> None:
        cfg = get("filters", "institution_filter") or {}
        self.min_institutions: int = cfg.get("min_institutions", 1)
        self.lhb_recent_days: int = cfg.get("lhb_recent_days", 10)

    async def apply(self, stock: StockTarget) -> FilterResult:
        if stock.target_type == TargetType.ETF:
            return FilterResult(
                stock=stock,
                passed_filters=[self.name],
                details={self.name: {"skip": "ETF不做机构筛选"}},
            )

        checks: dict[str, bool] = {}
        details: dict = {}

        inst = _check_institutions(stock.code)
        details["institutions"] = inst
        if inst.get("has_data"):
            checks["has_institution"] = inst["institution_count"] >= self.min_institutions
        else:
            checks["has_institution"] = True

        lhb = _check_lhb(stock.code, recent_days=self.lhb_recent_days)
        details["龙虎榜"] = lhb

        details["checks"] = checks
        passed = checks.get("has_institution", True)

        if not passed:
            logger.info(
                "%s(%s) 机构筛选未通过: 机构持仓 %d < %d",
                stock.name, stock.code,
                inst.get("institution_count", 0), self.min_institutions,
            )

        return FilterResult(
            stock=stock,
            passed_filters=[self.name] if passed else [],
            failed_filters=[] if passed else [self.name],
            details={self.name: details},
        )
