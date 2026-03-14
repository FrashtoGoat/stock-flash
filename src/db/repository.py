"""交易记录持久化与查询"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from src.db.models import Trade
from src.db.session import get_session, init_db
from src.models.stock import TradeRecord

logger = logging.getLogger(__name__)


def save_trade_records(records: list[TradeRecord]) -> bool:
    """将 TradeRecord 列表写入数据库；未启用存储时返回 False"""
    if not records:
        return True
    init_db()
    session = get_session()
    if session is None:
        return False
    try:
        for r in records:
            sig = r.signal
            row = Trade(
                stock_code=sig.stock.code,
                stock_name=sig.stock.name,
                direction=sig.direction.value,
                amount=sig.amount,
                exec_price=r.exec_price,
                exec_time=r.exec_time,
                status=r.status,
                message=r.message,
                signal_snapshot=json.dumps(r.model_dump(mode="json"), ensure_ascii=False),
            )
            session.add(row)
        session.commit()
        logger.info("交易记录已写入数据库: %d 条", len(records))
        return True
    except Exception:
        logger.exception("写入交易记录失败")
        session.rollback()
        return False
    finally:
        session.close()


def list_trades(
    direction: str | None = None,
    stock_code: str | None = None,
    since: datetime | None = None,
    limit: int = 500,
) -> list[Trade]:
    """查询交易记录"""
    init_db()
    session = get_session()
    if session is None:
        return []
    try:
        q = session.query(Trade).order_by(Trade.id.desc())
        if direction:
            q = q.filter(Trade.direction == direction)
        if stock_code:
            q = q.filter(Trade.stock_code == stock_code)
        if since:
            q = q.filter(Trade.exec_time >= since)
        return q.limit(limit).all()
    finally:
        session.close()


def get_open_positions_from_trades() -> list[dict]:
    """根据交易记录汇总未平仓持仓（仅买入未对应卖出的数量，按 code 汇总）"""
    init_db()
    session = get_session()
    if session is None:
        return []
    try:
        buys = session.query(Trade).filter(Trade.direction == "buy").order_by(Trade.exec_time).all()
        sells = session.query(Trade).filter(Trade.direction == "sell").order_by(Trade.exec_time).all()
    finally:
        session.close()

    # 简单按 code 汇总：买入量 - 卖出量，按买入时间 FIFO 取成本价
    from collections import defaultdict
    buy_qty: dict[str, list[tuple[float, float, datetime]]] = defaultdict(list)  # code -> [(amount, price, time), ...]
    sell_qty: dict[str, float] = defaultdict(float)

    for b in buys:
        buy_qty[b.stock_code].append((b.amount, b.exec_price or 0, b.exec_time or b.created_at))
    for s in sells:
        sell_qty[s.stock_code] += s.amount

    positions = []
    for code, lots in buy_qty.items():
        total_bought = sum(a for a, _, _ in lots)
        sold = sell_qty.get(code, 0)
        if sold >= total_bought:
            continue
        remaining = total_bought - sold
        # 成本价：按金额加权（简化取第一笔的 exec_price 与 exec_time 作为代表）
        cost = 0.0
        acc = 0.0
        first_time = None
        for amount, price, t in lots:
            if acc >= remaining:
                break
            use = min(amount, remaining - acc)
            cost += use * (price or 0)
            acc += use
            if first_time is None:
                first_time = t
        if acc <= 0:
            continue
        avg_price = cost / acc
        positions.append({
            "stock_code": code,
            "stock_name": "",
            "amount": acc,
            "cost_price": avg_price,
            "first_buy_time": first_time,
        })
    for p in positions:
        for b in buys:
            if b.stock_code == p["stock_code"]:
                p["stock_name"] = b.stock_name
                break
    return positions
