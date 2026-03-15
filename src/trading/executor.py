"""交易执行器：模拟交易、模拟盘、CTP 仿真、实盘接口"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from src.config import get
from src.models.stock import TradeDirection, TradeRecord, TradeSignal

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_RESULT_TRADES_BASE = _ROOT / "result" / "trades"
_LEGACY_TRADES_DIR = _ROOT / "data" / "trades"
_migrated = False


def _migrate_legacy_trades() -> None:
    """一次性：将 data/trades/*.json 按日期迁移到 result/trades/YYYY-MM-DD/"""
    global _migrated
    if _migrated or not _LEGACY_TRADES_DIR.exists():
        return
    import shutil
    for path in _LEGACY_TRADES_DIR.glob("trade*.json"):
        # trade_20260314_231201.json -> 2026-03-14
        name = path.stem
        if "_" in name and len(name) >= 15:
            try:
                ymd = name.split("_")[1]
                if len(ymd) == 8:
                    date_dir = _RESULT_TRADES_BASE / f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
                    date_dir.mkdir(parents=True, exist_ok=True)
                    dest = date_dir / path.name
                    if not dest.exists() or dest.stat().st_mtime < path.stat().st_mtime:
                        shutil.copy2(path, dest)
                        logger.info("已迁移交易记录: %s -> %s", path, dest)
            except Exception:
                pass
    _migrated = True


def _get_trade_log_dir() -> Path:
    """按日期分组：result/trades/YYYY-MM-DD/"""
    _migrate_legacy_trades()
    d = _RESULT_TRADES_BASE / datetime.now().strftime("%Y-%m-%d")
    d.mkdir(parents=True, exist_ok=True)
    return d


class SimulatedExecutor:
    """模拟交易执行器：记录交易信号但不实际下单"""

    def __init__(self) -> None:
        _get_trade_log_dir()
        cfg = get("trading") or {}
        self.max_position_pct = cfg.get("max_position_pct", 10)
        self.max_total_positions = cfg.get("max_total_positions", 5)
        self.default_amount = cfg.get("default_amount", 10000)

    async def execute(
        self,
        signals: list[TradeSignal],
        source: str | None = None,
    ) -> tuple[list[TradeRecord], list[int]]:
        """模拟执行交易信号。source 标明路线来源（新闻驱动/自研池）。"""
        records: list[TradeRecord] = []

        for signal in signals[: self.max_total_positions]:
            verb = "卖出" if signal.direction == TradeDirection.SELL else "买入"
            record = TradeRecord(
                signal=signal,
                executed=True,
                exec_price=signal.price,
                exec_time=datetime.now(),
                status="simulated",
                message=f"模拟{verb} {signal.stock.name}({signal.stock.code}) "
                        f"金额 {signal.amount:.0f}元",
                source=source,
            )
            records.append(record)
            logger.info("模拟交易: %s", record.message)

        self._save_records(records)
        trade_ids = self._save_to_db(records)
        return records, trade_ids

    def _save_records(self, records: list[TradeRecord]) -> None:
        """持久化交易记录到 JSON 文件（result/trades/YYYY-MM-DD/）"""
        if not records:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _get_trade_log_dir() / f"trade_{ts}.json"
        data = [r.model_dump(mode="json") for r in records]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("交易记录已保存: %s", path)

    def _save_to_db(self, records: list[TradeRecord]) -> list[int]:
        """若启用存储则写入数据库，返回写入的 trade id 列表"""
        try:
            from src.db.repository import save_trade_records
            return save_trade_records(records)
        except Exception:
            logger.debug("未启用数据库存储或写入失败，已忽略")
            return []


class PaperExecutor:
    """模拟盘交易执行器：对接券商模拟盘（仿真）形成闭环，不涉及真实资金。
    当前实现：与 SimulatedExecutor 同样落 JSON+DB，仅 status/message 标为「模拟盘委托」；
    后续在 _submit_paper_order() 内接入 QMT/miniQMT 等模拟盘 API 即可。"""

    def __init__(self) -> None:
        _get_trade_log_dir()
        cfg = get("trading") or {}
        self.broker = cfg.get("broker", "eastmoney")
        self.max_total_positions = cfg.get("max_total_positions", 5)
        logger.info("模拟盘执行器已初始化 (broker=%s)", self.broker)

    async def execute(
        self,
        signals: list[TradeSignal],
        source: str | None = None,
    ) -> tuple[list[TradeRecord], list[int]]:
        records: list[TradeRecord] = []
        for signal in signals[: self.max_total_positions]:
            verb = "卖出" if signal.direction == TradeDirection.SELL else "买入"
            record = TradeRecord(
                signal=signal,
                executed=True,
                exec_price=signal.price,
                exec_time=datetime.now(),
                status="paper",
                message=f"模拟盘委托{verb} {signal.stock.name}({signal.stock.code}) 金额 {signal.amount:.0f}元",
                source=source,
            )
            records.append(record)
            logger.info("模拟盘: %s", record.message)
        self._save_records(records)
        trade_ids = self._save_to_db(records)
        return records, trade_ids

    def _save_records(self, records: list[TradeRecord]) -> None:
        if not records:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _get_trade_log_dir() / f"trade_paper_{ts}.json"
        data = [r.model_dump(mode="json") for r in records]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("模拟盘记录已保存: %s", path)

    def _save_to_db(self, records: list[TradeRecord]) -> list[int]:
        try:
            from src.db.repository import save_trade_records
            return save_trade_records(records)
        except Exception:
            logger.debug("未启用数据库存储或写入失败，已忽略")
            return []


class CTPExecutor:
    """OpenCTP 仿真/7x24 交易执行器：连接 CTP 前置，将买卖信号转为 CTP 报单并落库。"""

    def __init__(self) -> None:
        _get_trade_log_dir()
        cfg = get("trading") or {}
        ctp_cfg = cfg.get("ctp") or {}
        self.max_total_positions = cfg.get("max_total_positions", 5)
        user_id = (ctp_cfg.get("user_id") or "").strip()
        password = (ctp_cfg.get("password") or "").strip()
        if not user_id or not password:
            logger.warning("CTP 未配置 user_id/password，请在 config/settings.yaml 的 trading.ctp 或环境变量 OPENCTP_USER/OPENCTP_PASSWORD 中配置")
        self._client = None
        self._client_kw = {
            "td_url": ctp_cfg.get("td_url", "tcp://trading.openctp.cn:30002"),
            "user_id": user_id,
            "password": password,
            "broker_id": ctp_cfg.get("broker_id", "9999"),
            "app_id": (ctp_cfg.get("app_id") or "").strip(),
            "auth_code": (ctp_cfg.get("auth_code") or "").strip(),
        }
        logger.info("CTP 执行器已初始化 (td_url=%s)", self._client_kw["td_url"])

    def _get_client(self):
        from src.trading.ctp_client import OpenCTPClient
        if self._client is None:
            self._client = OpenCTPClient(**self._client_kw)
        return self._client

    async def execute(
        self,
        signals: list[TradeSignal],
        source: str | None = None,
    ) -> tuple[list[TradeRecord], list[int]]:
        records: list[TradeRecord] = []
        client = self._get_client()
        for signal in signals[: self.max_total_positions]:
            verb = "卖出" if signal.direction == TradeDirection.SELL else "买入"
            price = signal.price if signal.price and signal.price > 0 else None
            if price is None:
                record = TradeRecord(
                    signal=signal,
                    executed=False,
                    exec_price=None,
                    exec_time=datetime.now(),
                    status="ctp_skip",
                    message=f"CTP 跳过{verb} {signal.stock.name}({signal.stock.code})：无有效价格",
                    source=source,
                )
                records.append(record)
                logger.warning("CTP 跳过: %s", record.message)
                continue
            direction = "sell" if signal.direction == TradeDirection.SELL else "buy"
            result = await asyncio.to_thread(
                client.submit_order,
                direction,
                signal.stock.code,
                price,
                signal.amount,
            )
            executed = result.success
            msg = f"CTP {verb} {signal.stock.name}({signal.stock.code}) 金额 {signal.amount:.0f}元 -> {result.message}"
            if result.order_ref:
                msg += f" OrderRef={result.order_ref}"
            record = TradeRecord(
                signal=signal,
                executed=executed,
                exec_price=price,
                exec_time=datetime.now(),
                status="ctp",
                message=msg,
                source=source,
            )
            records.append(record)
            logger.info("CTP: %s", msg)
        self._save_records(records)
        trade_ids = self._save_to_db(records)
        return records, trade_ids

    def _save_records(self, records: list[TradeRecord]) -> None:
        if not records:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _get_trade_log_dir() / f"trade_ctp_{ts}.json"
        data = [r.model_dump(mode="json") for r in records]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("CTP 交易记录已保存: %s", path)

    def _save_to_db(self, records: list[TradeRecord]) -> list[int]:
        try:
            from src.db.repository import save_trade_records
            return save_trade_records(records)
        except Exception:
            logger.debug("未启用数据库存储或写入失败，已忽略")
            return []


class LiveExecutor:
    """实盘交易执行器（预留接口）。
    对接方式：在 execute() 内调用券商 API（QMT/miniQMT/东方财富等）下单，
    将委托结果转为 TradeRecord 并同样写入 JSON + DB，详见 todolist_skill.md 后续模块说明。"""

    def __init__(self) -> None:
        cfg = get("trading") or {}
        self.broker = cfg.get("broker", "eastmoney")
        logger.warning("实盘交易执行器已初始化 (broker=%s)，请谨慎使用", self.broker)

    async def execute(
        self,
        signals: list[TradeSignal],
        source: str | None = None,
    ) -> tuple[list[TradeRecord], list[int]]:
        raise NotImplementedError("实盘交易接口尚未实现，请使用 trading.mode: simulated 或 paper")


def create_executor() -> SimulatedExecutor | PaperExecutor | CTPExecutor | LiveExecutor:
    """根据配置创建交易执行器：simulated | paper | ctp | live"""
    mode = get("trading", "mode") or "simulated"
    if mode == "live":
        return LiveExecutor()
    if mode == "paper":
        return PaperExecutor()
    if mode == "ctp":
        return CTPExecutor()
    return SimulatedExecutor()
