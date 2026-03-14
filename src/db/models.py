"""SQLAlchemy 表定义"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
