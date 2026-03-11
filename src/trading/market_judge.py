"""大盘情况判断：决定当前是否适合交易"""

from __future__ import annotations

import logging

import akshare as ak

from src.config import get
from src.models.stock import MarketCondition

logger = logging.getLogger(__name__)

_INDEX_NAME_MAP = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
}


def _fetch_index_realtime(index_code: str) -> dict:
    """获取指数实时数据"""
    try:
        # akshare 需要纯数字代码
        pure_code = index_code.replace("sh", "").replace("sz", "")
        df = ak.stock_zh_index_spot_em()
        row = df[df["代码"] == pure_code]
        if row.empty:
            return {}
        r = row.iloc[0]
        return {
            "current": float(r.get("最新价", 0)),
            "change_pct": float(r.get("涨跌幅", 0)),
            "volume_ratio": float(r.get("量比", 1)) if "量比" in r.index else 1.0,
        }
    except Exception:
        logger.exception("获取指数 %s 实时数据失败", index_code)
        return {}


async def judge_market() -> MarketCondition:
    """判断大盘环境是否适合交易"""
    cfg = get("market") or {}
    index_code = cfg.get("index_code", "sh000001")
    max_decline = cfg.get("max_decline_pct", -2.0)

    data = _fetch_index_realtime(index_code)
    if not data:
        return MarketCondition(
            index_code=index_code,
            index_name=_INDEX_NAME_MAP.get(index_code, index_code),
            current_price=0,
            change_pct=0,
            is_tradable=False,
            reason="无法获取大盘数据",
        )

    change_pct = data["change_pct"]
    is_tradable = change_pct >= max_decline

    reasons = []
    if not is_tradable:
        reasons.append(f"大盘跌幅 {change_pct:.2f}% 超过阈值 {max_decline}%")

    # 检查参考指数
    ref_indices = cfg.get("reference_indices", [])
    decline_count = 0
    for ref_code in ref_indices:
        if ref_code == index_code:
            continue
        ref_data = _fetch_index_realtime(ref_code)
        if ref_data and ref_data["change_pct"] < max_decline:
            decline_count += 1

    if decline_count >= 2:
        is_tradable = False
        reasons.append(f"多个参考指数大幅下跌({decline_count}个)")

    condition = MarketCondition(
        index_code=index_code,
        index_name=_INDEX_NAME_MAP.get(index_code, index_code),
        current_price=data.get("current", 0),
        change_pct=change_pct,
        volume_ratio=data.get("volume_ratio", 1.0),
        is_tradable=is_tradable,
        reason="; ".join(reasons) if reasons else "大盘正常",
    )

    logger.info(
        "大盘判断: %s %.2f%% -> %s (%s)",
        condition.index_name, condition.change_pct,
        "可交易" if condition.is_tradable else "不宜交易",
        condition.reason,
    )
    return condition
