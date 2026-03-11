"""新闻去重模块：基于 news_id 跟踪已处理的新闻，避免重复分析"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.models.stock import NewsItem

logger = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "seen_news.json"
_EXPIRE_HOURS = 24  # 已处理记录保留时长


class DedupStore:
    """已处理新闻 ID 存储（文件持久化）

    结构: {"news_id": "2026-03-11T10:30:00", ...}
    每次 load 时自动清理过期条目。
    """

    def __init__(self, path: Path | None = None, expire_hours: int = _EXPIRE_HOURS):
        self._path = path or _STORE_PATH
        self._expire = timedelta(hours=expire_hours)
        self._seen: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._seen = {}
            return
        try:
            self._seen = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("去重存储文件损坏，重置")
            self._seen = {}
        self._cleanup()

    def _cleanup(self) -> None:
        """清理过期条目"""
        cutoff = datetime.now() - self._expire
        before = len(self._seen)
        self._seen = {
            k: v for k, v in self._seen.items()
            if datetime.fromisoformat(v) > cutoff
        }
        removed = before - len(self._seen)
        if removed:
            logger.debug("清理 %d 条过期去重记录", removed)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._seen, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def is_seen(self, news_id: str) -> bool:
        return news_id in self._seen

    def mark_seen(self, news_id: str) -> None:
        self._seen[news_id] = datetime.now().isoformat()

    def filter_new(self, news_list: list[NewsItem]) -> list[NewsItem]:
        """过滤出未处理过的新闻，同时标记为已见"""
        new_items = []
        for n in news_list:
            if not n.news_id:
                new_items.append(n)
                continue
            if not self.is_seen(n.news_id):
                new_items.append(n)
                self.mark_seen(n.news_id)

        self._save()
        skipped = len(news_list) - len(new_items)
        if skipped:
            logger.info("去重: %d 条新闻已处理过，跳过；%d 条为新", skipped, len(new_items))
        return new_items

    @property
    def size(self) -> int:
        return len(self._seen)
