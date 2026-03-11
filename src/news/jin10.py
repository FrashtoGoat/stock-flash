"""金十数据快讯接口"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

from src.config import get
from src.models.stock import NewsItem
from src.news.base import BaseNewsFetcher
from src.news.factory import register

logger = logging.getLogger(__name__)


@register("jin10")
class Jin10Fetcher(BaseNewsFetcher):
    """从金十数据获取财经快讯"""

    source_name = "jin10"

    def __init__(self) -> None:
        cfg = get("news", "jin10") or {}
        self.api_url = cfg.get("api_url", "https://flash-api.jin10.com/get")
        self.max_items = cfg.get("max_items", 20)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.jin10.com/",
            "x-app-id": "SO1EJGmSbQ",
            "x-version": "1.0.0",
        }

    async def fetch(self) -> list[NewsItem]:
        params = {"max_time": "", "channel": "-8200", "vip": 1}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    self.api_url, params=params, headers=self.headers
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("金十数据拉取失败")
            return []

        items: list[NewsItem] = []
        for entry in (data.get("data") or [])[:self.max_items]:
            content = entry.get("data", {})
            # 金十的 content 字段可能是 dict 或 str
            text = content.get("content", "") if isinstance(content, dict) else str(content)
            if not text:
                continue

            pub_str = entry.get("time", "")
            try:
                pub_time = datetime.fromisoformat(pub_str)
            except (ValueError, TypeError):
                pub_time = datetime.now()

            importance = entry.get("important", 0)
            items.append(
                NewsItem(
                    source=self.source_name,
                    title=text[:60],
                    content=text,
                    pub_time=pub_time,
                    importance=importance if isinstance(importance, int) else 0,
                )
            )

        logger.info("金十数据拉取 %d 条快讯", len(items))
        return items
