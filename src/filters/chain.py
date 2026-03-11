"""筛选器链管理"""

from __future__ import annotations

import logging
from typing import Protocol

from src.models.stock import FilterResult, StockTarget

logger = logging.getLogger(__name__)


class StockFilter(Protocol):
    """筛选器协议：所有筛选器需实现此接口"""

    name: str

    async def apply(self, stock: StockTarget) -> FilterResult:
        """对单只股票执行筛选，返回筛选结果"""
        ...


class FilterChain:
    """链式筛选器，依次执行所有启用的筛选器"""

    def __init__(self) -> None:
        self._filters: list[StockFilter] = []

    def add(self, f: StockFilter) -> "FilterChain":
        self._filters.append(f)
        logger.info("添加筛选器: %s", f.name)
        return self

    async def run(self, targets: list[StockTarget]) -> list[FilterResult]:
        """对所有标的依次执行筛选器链"""
        results: list[FilterResult] = []

        for stock in targets:
            result = FilterResult(stock=stock)

            for f in self._filters:
                try:
                    fr = await f.apply(stock)
                except Exception:
                    logger.exception("筛选器 %s 执行异常, stock=%s", f.name, stock.code)
                    result.failed_filters.append(f"{f.name}(error)")
                    break

                if fr.is_passed:
                    result.passed_filters.append(f.name)
                    result.details[f.name] = fr.details
                else:
                    result.failed_filters.append(f.name)
                    result.details[f.name] = fr.details
                    break  # 短路: 一个不过就不继续

            results.append(result)

        passed = [r for r in results if r.is_passed]
        logger.info(
            "筛选器链完成: %d/%d 通过 (%s)",
            len(passed), len(targets),
            ", ".join(f.name for f in self._filters),
        )
        return results
