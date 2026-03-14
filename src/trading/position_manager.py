"""持仓管理与止盈止损：汇总持仓、计算盈亏、生成卖出信号"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.config import get
from src.db.repository import get_open_positions_from_trades
from src.models.stock import BoardType, TradeDirection, TradeSignal, StockTarget, TargetType

logger = logging.getLogger(__name__)


def _get_current_price(code: str) -> float | None:
    try:
        import akshare as ak
        df = ak.stock_bid_ask_em(symbol=code)
        for _, row in df.iterrows():
            if row.get("item") == "最新":
                return float(row["value"])
        return None
    except Exception:
        logger.warning("获取 %s 实时价格失败", code)
        return None


def check_stop_profit_loss() -> list[TradeSignal]:
    """
    根据当前持仓与配置的止盈止损比例，生成卖出信号。
    持仓来源：数据库 trades 表汇总（仅当 storage.enabled 且已有买入记录时有效）。
    """
    cfg = get("trading") or {}
    stop_profit = cfg.get("stop_profit_pct", 0.10)
    stop_loss = cfg.get("stop_loss_pct", -0.05)
    hold_days_min = cfg.get("hold_days_min", 1)

    positions = get_open_positions_from_trades()
    if not positions:
        logger.debug("无持仓，跳过止盈止损检查")
        return []

    signals: list[TradeSignal] = []
    today = datetime.now().date()

    for pos in positions:
        code = pos["stock_code"]
        name = pos["stock_name"]
        amount = pos["amount"]
        cost = pos["cost_price"]
        first_time = pos.get("first_buy_time")
        if not first_time:
            continue
        if hasattr(first_time, "date"):
            first_date = first_time.date() if hasattr(first_time, "date") else first_time
        else:
            first_date = first_time
        hold_days = (today - first_date).days if hasattr(today, "__sub__") else 0
        if hold_days < hold_days_min:
            continue

        current = _get_current_price(code)
        if current is None or cost <= 0:
            continue
        pnl_pct = (current - cost) / cost

        reason = ""
        if pnl_pct >= stop_profit:
            reason = f"止盈(盈亏{pnl_pct:.1%}≥{stop_profit:.0%})"
        elif pnl_pct <= stop_loss:
            reason = f"止损(盈亏{pnl_pct:.1%}≤{stop_loss:.0%})"
        if not reason:
            continue

        stock = StockTarget(
            code=code,
            name=name or code,
            board=BoardType.MAIN,
            target_type=TargetType.STOCK,
            reason=reason,
        )
        signals.append(
            TradeSignal(
                stock=stock,
                direction=TradeDirection.SELL,
                amount=amount,
                price=current,
                reason=reason,
                confidence=0.9,
            )
        )
        logger.info("止盈止损: %s(%s) %s 成本%.2f 现价%.2f 盈亏%.2f%%", name, code, reason, cost, current, pnl_pct * 100)

    return signals
