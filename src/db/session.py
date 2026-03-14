"""数据库连接与会话"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get
from src.db.models import Base

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is not None:
        return _engine
    cfg = get("storage") or {}
    if not cfg.get("enabled", False):
        return None
    url = (cfg.get("database", {}) or {}).get("url", "")
    if not url:
        base_dir = Path(__file__).resolve().parent.parent.parent / "data"
        base_dir.mkdir(parents=True, exist_ok=True)
        db_path = (base_dir / "stock_flash.db").as_posix()
        url = f"sqlite:///{db_path}"
    _engine = create_engine(url, echo=False)
    return _engine


def init_db() -> bool:
    """创建表；若未启用存储则跳过"""
    engine = get_engine()
    if engine is None:
        return False
    Base.metadata.create_all(engine)
    return True


def get_session() -> Session | None:
    """获取当前会话；未启用存储时返回 None"""
    global _SessionLocal
    engine = get_engine()
    if engine is None:
        return None
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(engine, expire_on_commit=False)
    return _SessionLocal()
