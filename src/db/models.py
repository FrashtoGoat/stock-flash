"""SQLAlchemy 表定义"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class News(Base):
    """新闻主表：生命周期 pending → processed → analyzed，超时可标 expired"""

    __tablename__ = "news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[str] = mapped_column(String(256), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(64), default="")
    publish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetch_time: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    category: Mapped[str] = mapped_column(String(32), nullable=True)
    sentiment: Mapped[str] = mapped_column(String(32), nullable=True)
    keywords: Mapped[str] = mapped_column(Text, nullable=True)
    llm_result: Mapped[str] = mapped_column(Text, nullable=True)
    llm_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    triggered_trade: Mapped[bool] = mapped_column(Boolean, default=False)
    trade_ids: Mapped[str] = mapped_column(String(256), nullable=True)
    profit_loss: Mapped[float | None] = mapped_column(Float, nullable=True)


class StockPool(Base):
    """股票池：观察池 watch / 稳定池 stable / 高位池 high / 移除池 removed"""

    __tablename__ = "stock_pool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    pool_type: Mapped[str] = mapped_column(String(16), default="watch", index=True)
    entry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_news_ids: Mapped[str | None] = mapped_column(String(256), nullable=True)  # 逗号分隔 news.id
    llm_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_price_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    change_1d_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_5d_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    removed_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class Trade(Base):
    """交易记录表（与 TradeRecord 对应）"""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    stock_name: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # buy / sell
    amount: Mapped[float] = mapped_column(Float, default=0)
    exec_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exec_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    message: Mapped[str] = mapped_column(Text, default="")
    signal_snapshot: Mapped[str] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
