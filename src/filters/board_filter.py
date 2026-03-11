"""板块筛选器：标注板块信息，不直接过滤非主板标的"""

from __future__ import annotations

import logging

from src.config import get
from src.filters.factory import register
from src.models.stock import BoardType, FilterResult, StockTarget

logger = logging.getLogger(__name__)

_CODE_BOARD_MAP = {
    "60": BoardType.MAIN,
    "00": BoardType.MAIN,
    "30": BoardType.GEM,
    "68": BoardType.STAR,
    "8": BoardType.BSE,
    "4": BoardType.BSE,
}


def _detect_board(code: str) -> BoardType:
    for prefix, board in _CODE_BOARD_MAP.items():
        if code.startswith(prefix):
            return board
    return BoardType.MAIN


@register("board_filter")
class BoardFilter:
    """板块筛选器 —— 标注可交易性，非主板标的不拦截但在 details 中警告"""

    name = "board_filter"

    def __init__(self) -> None:
        cfg = get("filters", "board_filter") or {}
        allowed = cfg.get("allowed_boards", ["main"])
        self.allowed: set[BoardType] = {BoardType(b) for b in allowed}

    async def apply(self, stock: StockTarget) -> FilterResult:
        board = _detect_board(stock.code)
        in_allowed = board in self.allowed
        if not in_allowed:
            logger.info(
                "%s(%s) 板块=%s — %s（标注，不过滤）",
                stock.name, stock.code, board.value, stock.tradable_note,
            )
        return FilterResult(
            stock=stock,
            passed_filters=[self.name],
            failed_filters=[],
            details={
                self.name: {
                    "detected_board": board.value,
                    "allowed_boards": [b.value for b in self.allowed],
                    "tradable": stock.tradable,
                    "tradable_note": stock.tradable_note,
                }
            },
        )
