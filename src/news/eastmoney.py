"""东方财富 7x24 快讯接口"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx

from src.config import get
from src.models.stock import NewsItem
from src.news.base import BaseNewsFetcher
from src.news.factory import register

logger = logging.getLogger(__name__)

_API_URL = "https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_{size}_{page}_.html"


@register("eastmoney")
class EastmoneyFetcher(BaseNewsFetcher):
    """从东方财富获取 7x24 快讯"""

    source_name = "eastmoney"

    def __init__(self) -> None:
        cfg = get("news", "eastmoney") or {}
        self.max_items = cfg.get("max_items", 20)

    async def fetch(self) -> list[NewsItem]:
        url = _API_URL.format(size=self.max_items, page=1)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                text = resp.text
        except Exception:
            logger.exception("东方财富拉取失败")
            return []

        if text.startswith("var "):
            text = text.split("=", 1)[1].strip().rstrip(";")

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("东方财富响应解析失败")
            return []

        lives = data.get("LivesList", [])
        items: list[NewsItem] = []

        for entry in lives[: self.max_items]:
            digest = entry.get("digest", "").strip()
            if not digest:
                continue

            raw_id = entry.get("newsid", entry.get("id", ""))
            showtime = entry.get("showtime", "")
            try:
                pub_time = datetime.strptime(showtime, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pub_time = datetime.now()

            url_w = entry.get("url_w", "")
            title = entry.get("title", digest[:60])

            items.append(
                NewsItem(
                    news_id=f"eastmoney:{raw_id}",
                    source=self.source_name,
                    title=title[:60],
                    content=digest,
                    url=url_w,
                    pub_time=pub_time,
                    importance=0,
                    category="other",
                )
            )

        logger.info("东方财富拉取 %d 条快讯", len(items))
        return items
