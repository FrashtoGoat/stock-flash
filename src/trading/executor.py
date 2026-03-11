"""交易执行器：模拟交易 & 实盘交易接口"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from src.config import get
from src.models.stock import TradeDirection, TradeRecord, TradeSignal

logger = logging.getLogger(__name__)

_TRADE_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "trades"


class SimulatedExecutor:
    """模拟交易执行器：记录交易信号但不实际下单"""

    def __init__(self) -> None:
        _TRADE_LOG_DIR.mkdir(parents=True, exist_ok=True)
        cfg = get("trading") or {}
        self.max_position_pct = cfg.get("max_position_pct", 10)
        self.max_total_positions = cfg.get("max_total_positions", 5)
        self.default_amount = cfg.get("default_amount", 10000)

    async def execute(self, signals: list[TradeSignal]) -> list[TradeRecord]:
        """模拟执行交易信号"""
        records: list[TradeRecord] = []

        for signal in signals[: self.max_total_positions]:
            record = TradeRecord(
                signal=signal,
                executed=True,
                exec_price=signal.price,
                exec_time=datetime.now(),
                status="simulated",
                message=f"模拟买入 {signal.stock.name}({signal.stock.code}) "
                        f"金额 {signal.amount:.0f}元",
            )
            records.append(record)
            logger.info("模拟交易: %s", record.message)

        self._save_records(records)
        return records

    def _save_records(self, records: list[TradeRecord]) -> None:
        """持久化交易记录到 JSON 文件"""
        if not records:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _TRADE_LOG_DIR / f"trade_{ts}.json"
        data = [r.model_dump(mode="json") for r in records]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("交易记录已保存: %s", path)


class LiveExecutor:
    """实盘交易执行器（预留接口，后续对接券商API）"""

    def __init__(self) -> None:
        cfg = get("trading") or {}
        self.broker = cfg.get("broker", "eastmoney")
        logger.warning("实盘交易执行器已初始化 (broker=%s)，请谨慎使用", self.broker)

    async def execute(self, signals: list[TradeSignal]) -> list[TradeRecord]:
        # TODO: 对接具体券商 API (如 QMT / miniQMT / 东方财富)
        raise NotImplementedError("实盘交易接口尚未实现，请使用模拟交易模式")


def create_executor() -> SimulatedExecutor | LiveExecutor:
    """根据配置创建交易执行器"""
    mode = get("trading", "mode", "simulated")
    if mode == "live":
        return LiveExecutor()
    return SimulatedExecutor()
