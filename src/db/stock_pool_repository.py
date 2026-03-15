"""股票池持久化：入池、按类型查询、更新池类型与价格、判断关联新闻是否全部过期"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from src.db.models import News, StockPool
from src.db.session import get_session, init_db

logger = logging.getLogger(__name__)


def _parse_news_ids(source_news_ids: str | None) -> list[int]:
    if not source_news_ids or not source_news_ids.strip():
        return []
    return [int(x.strip()) for x in source_news_ids.split(",") if x.strip().isdigit()]


def is_source_news_all_expired(source_news_ids: str | None) -> bool:
    """判断 source_news_ids 中的新闻在 news 表里是否全部为 expired。"""
    ids = _parse_news_ids(source_news_ids)
    if not ids:
        return False
    init_db()
    session = get_session()
    if session is None:
        return False
    try:
        count = session.query(News).filter(News.id.in_(ids)).count()
        expired_count = session.query(News).filter(News.id.in_(ids), News.status == "expired").count()
        return count > 0 and count == expired_count
    finally:
        session.close()


def list_by_type(pool_type: str, limit: int = 200) -> list[StockPool]:
    """按池类型查询（非 removed 用于维护；stable 用于生成买入候选）。"""
    init_db()
    session = get_session()
    if session is None:
        return []
    try:
        return session.query(StockPool).filter(StockPool.pool_type == pool_type).order_by(StockPool.entry_time.desc()).limit(limit).all()
    finally:
        session.close()


def list_active(limit: int = 500) -> list[StockPool]:
    """查询所有非 removed 的池记录，用于维护时更新价格与状态。"""
    init_db()
    session = get_session()
    if session is None:
        return []
    try:
        return session.query(StockPool).filter(StockPool.pool_type != "removed").order_by(StockPool.entry_time.desc()).limit(limit).all()
    finally:
        session.close()


def get_by_code(stock_code: str) -> StockPool | None:
    """按股票代码取当前记录（任意类型）。"""
    init_db()
    session = get_session()
    if session is None:
        return None
    try:
        return session.query(StockPool).filter(StockPool.stock_code == stock_code).first()
    finally:
        session.close()


def upsert_watch(
    stock_code: str,
    stock_name: str,
    source_news_ids: list[int],
    llm_score: float | None = None,
) -> bool:
    """
    入池为观察池：若池中无该 code 或当前为 removed，则插入/更新为 watch。
    若已在 watch/stable/high，仅刷新 updated_at，不覆盖 source_news_ids。
    """
    if not stock_code:
        return False
    init_db()
    session = get_session()
    if session is None:
        return False
    now = datetime.now()
    ids_str = ",".join(str(i) for i in source_news_ids) if source_news_ids else None
    try:
        row = session.query(StockPool).filter(StockPool.stock_code == stock_code).first()
        if row is None:
            session.add(StockPool(
                stock_code=stock_code,
                stock_name=stock_name or "",
                pool_type="watch",
                entry_time=now,
                source_news_ids=ids_str,
                llm_score=llm_score,
                updated_at=now,
            ))
        elif row.pool_type == "removed":
            row.pool_type = "watch"
            row.entry_time = now
            row.source_news_ids = ids_str
            row.llm_score = llm_score
            row.removed_reason = None
            row.updated_at = now
            row.stock_name = stock_name or row.stock_name
        else:
            row.updated_at = now
            if stock_name:
                row.stock_name = stock_name
        session.commit()
        return True
    except Exception:
        logger.exception("股票池 upsert_watch 失败 code=%s", stock_code)
        session.rollback()
        return False
    finally:
        session.close()


def update_pool_type(stock_code: str, pool_type: str, removed_reason: Optional[str] = None) -> bool:
    """将指定标的的池类型更新为 stable / high / removed，entry_time 设为当前时间。"""
    init_db()
    session = get_session()
    if session is None:
        return False
    now = datetime.now()
    try:
        row = session.query(StockPool).filter(StockPool.stock_code == stock_code).first()
        if row is None:
            session.close()
            return False
        row.pool_type = pool_type
        row.entry_time = now
        row.updated_at = now
        if pool_type == "removed" and removed_reason:
            row.removed_reason = removed_reason
        session.commit()
        return True
    except Exception:
        logger.exception("股票池 update_pool_type 失败 code=%s type=%s", stock_code, pool_type)
        session.rollback()
        return False
    finally:
        session.close()


def update_pool_type_batch(codes: list[str], pool_type: str, removed_reason: Optional[str] = None) -> int:
    """批量更新池类型，返回更新条数。"""
    if not codes:
        return 0
    init_db()
    session = get_session()
    if session is None:
        return 0
    now = datetime.now()
    try:
        result = session.query(StockPool).filter(StockPool.stock_code.in_(codes)).update(
            {
                StockPool.pool_type: pool_type,
                StockPool.entry_time: now,
                StockPool.updated_at: now,
                **({StockPool.removed_reason: removed_reason} if pool_type == "removed" and removed_reason else {}),
            },
            synchronize_session=False,
        )
        session.commit()
        return result
    except Exception:
        logger.exception("股票池 update_pool_type_batch 失败")
        session.rollback()
        return 0
    finally:
        session.close()


def update_price(stock_code: str, latest_price: float | None, change_1d_pct: float | None, change_5d_pct: float | None) -> bool:
    """更新单条记录的价格与涨跌幅。"""
    init_db()
    session = get_session()
    if session is None:
        return False
    now = datetime.now()
    try:
        row = session.query(StockPool).filter(StockPool.stock_code == stock_code).first()
        if row is None:
            return False
        row.latest_price = latest_price
        row.latest_price_time = now
        row.change_1d_pct = change_1d_pct
        row.change_5d_pct = change_5d_pct
        row.updated_at = now
        session.commit()
        return True
    except Exception:
        logger.exception("股票池 update_price 失败 code=%s", stock_code)
        session.rollback()
        return False
    finally:
        session.close()


def update_prices_batch(updates: dict[str, tuple[float | None, float | None, float | None]]) -> None:
    """批量更新价格：code -> (latest_price, change_1d_pct, change_5d_pct)。"""
    if not updates:
        return
    init_db()
    session = get_session()
    if session is None:
        return
    now = datetime.now()
    try:
        for code, (price, c1, c5) in updates.items():
            row = session.query(StockPool).filter(StockPool.stock_code == code).first()
            if row:
                row.latest_price = price
                row.latest_price_time = now
                row.change_1d_pct = c1
                row.change_5d_pct = c5
                row.updated_at = now
        session.commit()
    except Exception:
        logger.exception("股票池 update_prices_batch 失败")
        session.rollback()
    finally:
        session.close()


def mark_removed(stock_codes: list[str], reason: str = "take_profit") -> int:
    """将一批标的标为移除池，reason: take_profit / stop_loss / news_expired 等。"""
    return update_pool_type_batch(stock_codes, "removed", removed_reason=reason)
