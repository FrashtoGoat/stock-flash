"""新闻源基类"""

from __future__ import annotations

import abc
from src.models.stock import NewsItem


class BaseNewsFetcher(abc.ABC):
    """所有新闻源的抽象基类"""

    source_name: str = "unknown"

    @abc.abstractmethod
    async def fetch(self) -> list[NewsItem]:
        """拉取最新新闻列表"""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} source={self.source_name}>"
