"""新闻表持久化与生命周期：pending → processed → analyzed，过期标 expired，关联交易"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from src.db.models import News
from src.db.session import get_session, init_db
from src.models.stock import NewsItem

logger = logging.getLogger(__name__)


def upsert_pending(item: NewsItem) -> tuple[int, bool]:
    """若 news_id 已存在则返回 (已有 id, False)；否则插入 pending 并返回 (新 id, True)。"""
    init_db()
    session = get_session()
    if session is None:
        return 0, False
    try:
        row = session.query(News).filter(News.news_id == item.news_id).first()
        if row:
            return row.id, False
        row = News(
            news_id=item.news_id,
            title=item.title or "",
            content=item.content or "",
            source=item.source or "",
            publish_time=item.pub_time,
            fetch_time=datetime.now(),
            status="pending",
        )
        session.add(row)
        session.flush()
        session.commit()
        return row.id, True
    except Exception:
        logger.exception("新闻 upsert_pending 失败 news_id=%s", item.news_id)
        session.rollback()
        return 0, False
    finally:
        session.close()


def update_to_processed_by_items(items: list[NewsItem]) -> bool:
    """将这批新闻更新为 processed，从 NewsItem 取 category/sentiment/keywords。"""
    if not items:
        return True
    init_db()
    session = get_session()
    if session is None:
        return False
    try:
        for n in items:
            session.query(News).filter(News.news_id == n.news_id).update(
                {
                    News.status: "processed",
                    News.category: getattr(n.category, "value", str(n.category)) if n.category else None,
                    News.sentiment: getattr(n.sentiment, "value", str(n.sentiment)) if n.sentiment else None,
                    News.keywords: json.dumps(n.keywords, ensure_ascii=False) if n.keywords else None,
                },
                synchronize_session=False,
            )
        session.commit()
        return True
    except Exception:
        logger.exception("新闻 update_to_processed 失败")
        session.rollback()
        return False
    finally:
        session.close()


def update_to_analyzed(news_db_ids: list[int], llm_result_json: str) -> bool:
    """将指定新闻（按 DB id）更新为 analyzed，写入 LLM 结果。"""
    if not news_db_ids:
        return True
    init_db()
    session = get_session()
    if session is None:
        return False
    try:
        session.query(News).filter(News.id.in_(news_db_ids)).update(
            {
                News.status: "analyzed",
                News.llm_result: llm_result_json,
                News.llm_time: datetime.now(),
            },
            synchronize_session=False,
        )
        session.commit()
        return True
    except Exception:
        logger.exception("新闻 update_to_analyzed 失败")
        session.rollback()
        return False
    finally:
        session.close()


def link_trades(news_db_ids: list[int], trade_ids: list[int]) -> bool:
    """将本批新闻关联到产生的交易，并标记 triggered_trade。"""
    if not news_db_ids:
        return True
    trade_ids_str = ",".join(str(t) for t in trade_ids) if trade_ids else ""
    init_db()
    session = get_session()
    if session is None:
        return False
    try:
        session.query(News).filter(News.id.in_(news_db_ids)).update(
            {
                News.triggered_trade: True,
                News.trade_ids: trade_ids_str or None,
            },
            synchronize_session=False,
        )
        session.commit()
        return True
    except Exception:
        logger.exception("新闻 link_trades 失败")
        session.rollback()
        return False
    finally:
        session.close()


def mark_expired(expire_hours: int = 24) -> int:
    """将 fetch_time 超过 expire_hours 的新闻标为 expired，返回更新条数。"""
    init_db()
    session = get_session()
    if session is None:
        return 0
    try:
        cutoff = datetime.now() - timedelta(hours=expire_hours)
        result = session.query(News).filter(
            News.fetch_time < cutoff,
            News.status.in_(["pending", "processed", "analyzed"]),
        ).update({News.status: "expired"}, synchronize_session=False)
        session.commit()
        if result:
            logger.info("新闻生命周期: %d 条标为 expired (超过 %d 小时)", result, expire_hours)
        return result
    except Exception:
        logger.exception("新闻 mark_expired 失败")
        session.rollback()
        return 0
    finally:
        session.close()


def is_news_seen(news_id: str) -> bool:
    """是否已在新闻表中存在（用于去重）。"""
    init_db()
    session = get_session()
    if session is None:
        return False
    try:
        return session.query(News.id).filter(News.news_id == news_id).first() is not None
    finally:
        session.close()


def list_news_with_trades(
    since: Optional[datetime] = None,
    source: Optional[str] = None,
    limit: int = 500,
) -> list[News]:
    """查询已关联交易的新闻，用于复盘。"""
    init_db()
    session = get_session()
    if session is None:
        return []
    try:
        q = session.query(News).filter(News.triggered_trade == True)
        if since:
            q = q.filter(News.fetch_time >= since)
        if source:
            q = q.filter(News.source == source)
        return q.order_by(News.fetch_time.desc()).limit(limit).all()
    finally:
        session.close()
