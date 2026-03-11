"""新浪财经快讯接口"""

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

_API_URL = "https://zhibo.sina.com.cn/api/zhibo/feed"

# 新浪 tag.name → NewsCategory 映射
_TAG_CATEGORY_MAP = {
    "公司": "company",
    "行业": "industry",
    "基金": "market",
    "市场": "market",
    "科技": "tech",
    "国际": "global",
    "宏观": "macro",
    "政策": "policy",
}


@register("sina")
class SinaFetcher(BaseNewsFetcher):
    """从新浪财经直播获取快讯"""

    source_name = "sina"

    def __init__(self) -> None:
        cfg = get("news", "sina") or {}
        self.max_items = cfg.get("max_items", 20)
        self.zhibo_id = cfg.get("zhibo_id", 152)

    async def fetch(self) -> list[NewsItem]:
        params = {
            "page": 1,
            "page_size": self.max_items,
            "zhibo_id": self.zhibo_id,
            "tag_id": 0,
            "type": 0,
        }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(_API_URL, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            logger.exception("新浪财经拉取失败")
            return []

        feed = (
            data.get("result", {})
            .get("data", {})
            .get("feed", {})
            .get("list", [])
        )

        items: list[NewsItem] = []
        for entry in feed[: self.max_items]:
            text = entry.get("rich_text", "").strip()
            if not text:
                continue

            raw_id = entry.get("id", "")
            ctime = entry.get("create_time", "")
            try:
                pub_time = datetime.strptime(ctime, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                pub_time = datetime.now()

            # 标签 → 分类
            tags = entry.get("tag", [])
            tag_names = [t.get("name", "") for t in tags] if isinstance(tags, list) else []
            category = "other"
            for tn in tag_names:
                if tn in _TAG_CATEGORY_MAP:
                    category = _TAG_CATEGORY_MAP[tn]
                    break

            # 从 ext 字段提取关联股票
            related_stocks: list[dict] = []
            ext_str = entry.get("ext", "")
            if ext_str:
                try:
                    ext = json.loads(ext_str) if isinstance(ext_str, str) else ext_str
                    for s in ext.get("stocks", []):
                        symbol = s.get("symbol", "")
                        code = symbol.replace("sh", "").replace("sz", "")
                        name = s.get("key", "")
                        if code and len(code) == 6 and code.isdigit():
                            related_stocks.append({"code": code, "name": name, "market": s.get("market", "")})
                except (json.JSONDecodeError, TypeError):
                    pass

            importance = 3 if "重要" in tag_names else (1 if entry.get("is_focus") else 0)
            url = entry.get("docurl", "")

            items.append(
                NewsItem(
                    news_id=f"sina:{raw_id}",
                    source=self.source_name,
                    title=text[:60],
                    content=text,
                    url=url,
                    pub_time=pub_time,
                    importance=importance,
                    category=category,
                    raw_tags=tag_names,
                    related_stocks=related_stocks,
                )
            )

        logger.info("新浪财经拉取 %d 条快讯", len(items))
        return items
