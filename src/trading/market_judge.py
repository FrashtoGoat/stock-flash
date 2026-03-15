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
    """获取指数实时数据。失败时返回空 dict，由调用方尝试最近交易日回退。"""
    try:
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
            "data_date": None,
        }
    except Exception as e:
        logger.debug("获取指数 %s 实时数据失败（将回退最近交易日）: %s", index_code, e)
        return {}


def _fetch_index_latest_trading_day(index_code: str) -> dict:
    """非交易日或接口异常时：取最近一个交易日的日线收盘数据，并在返回中注明 data_date。"""
    try:
        # akshare 日线 symbol 格式：sh000001 / sz399001 / sz399006
        df = ak.stock_zh_index_daily(symbol=index_code)
        if df is None or df.empty or len(df) < 2:
            return {}
        df = df.sort_values("date").tail(2)
        prev_close = float(df.iloc[0]["close"])
        last = df.iloc[1]
        close = float(last["close"])
        data_date = str(last["date"])[:10]
        change_pct = (close - prev_close) / prev_close * 100.0 if prev_close else 0.0
        logger.info("指数 %s 使用最近交易日数据: %s 收盘 %.2f 涨跌幅 %.2f%%", index_code, data_date, close, change_pct)
        return {
            "current": close,
            "change_pct": change_pct,
            "volume_ratio": 1.0,
            "data_date": data_date,
        }
    except Exception as e:
        logger.warning("获取指数 %s 最近交易日数据失败: %s", index_code, e)
        return {}


def _get_index_data(index_code: str) -> tuple[dict, str]:
    """获取指数数据：先实时，失败则用最近交易日日线。返回 (data_dict, data_note)。"""
    data = _fetch_index_realtime(index_code)
    if data:
        data.setdefault("data_date", None)
        return data, ""
    data = _fetch_index_latest_trading_day(index_code)
    if data:
        data_date = data.get("data_date") or ""
        note = f"（数据取自最近交易日 {data_date}）" if data_date else ""
        return data, note
    return {}, ""


async def judge_market() -> MarketCondition:
    """判断大盘环境是否适合交易"""
    cfg = get("market") or {}
    index_code = cfg.get("index_code", "sh000001")
    max_decline = cfg.get("max_decline_pct", -2.0)

    data, data_note = _get_index_data(index_code)
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

    # 检查参考指数（同样支持最近交易日回退）
    ref_indices = cfg.get("reference_indices", [])
    decline_count = 0
    for ref_code in ref_indices:
        if ref_code == index_code:
            continue
        ref_data, _ = _get_index_data(ref_code)
        if ref_data and ref_data["change_pct"] < max_decline:
            decline_count += 1

    if decline_count >= 2:
        is_tradable = False
        reasons.append(f"多个参考指数大幅下跌({decline_count}个)")

    base_reason = "; ".join(reasons) if reasons else "大盘正常"
    reason = (base_reason + data_note) if data_note else base_reason

    condition = MarketCondition(
        index_code=index_code,
        index_name=_INDEX_NAME_MAP.get(index_code, index_code),
        current_price=data.get("current", 0),
        change_pct=change_pct,
        volume_ratio=data.get("volume_ratio", 1.0),
        is_tradable=is_tradable,
        reason=reason,
    )

    logger.info(
        "大盘判断: %s %.2f%% -> %s (%s)",
        condition.index_name, condition.change_pct,
        "可交易" if condition.is_tradable else "不宜交易",
        condition.reason,
    )
    return condition
