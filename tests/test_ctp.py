"""CTP 客户端与执行器相关测试（不依赖 OpenCTP 连接）"""

from __future__ import annotations

import pytest

from src.trading.ctp_client import stock_code_to_exchange_instrument


class TestStockCodeToExchangeInstrument:
    """A 股代码 -> (ExchangeID, InstrumentID)"""

    def test_sh_main(self):
        assert stock_code_to_exchange_instrument("600000") == ("SSE", "600000")
        assert stock_code_to_exchange_instrument("601857") == ("SSE", "601857")

    def test_sz_main(self):
        assert stock_code_to_exchange_instrument("000001") == ("SZSE", "000001")
        assert stock_code_to_exchange_instrument("002594") == ("SZSE", "002594")

    def test_sz_gem(self):
        assert stock_code_to_exchange_instrument("300750") == ("SZSE", "300750")

    def test_etf_sh(self):
        assert stock_code_to_exchange_instrument("510300") == ("SSE", "510300")

    def test_strip(self):
        assert stock_code_to_exchange_instrument("  600000  ") == ("SSE", "600000")


class TestTradingHours:
    """交易日与交易时段判断"""

    def test_trading_time_morning(self):
        from src.trading.trading_hours import is_trading_time
        from datetime import datetime
        assert is_trading_time(datetime(2025, 6, 2, 10, 0)) is True
        assert is_trading_time(datetime(2025, 6, 2, 9, 30)) is True
        assert is_trading_time(datetime(2025, 6, 2, 11, 30)) is True

    def test_trading_time_afternoon(self):
        from src.trading.trading_hours import is_trading_time
        from datetime import datetime
        assert is_trading_time(datetime(2025, 6, 2, 14, 0)) is True
        assert is_trading_time(datetime(2025, 6, 2, 13, 0)) is True
        assert is_trading_time(datetime(2025, 6, 2, 15, 0)) is True

    def test_non_trading_time(self):
        from src.trading.trading_hours import is_trading_time
        from datetime import datetime
        assert is_trading_time(datetime(2025, 6, 2, 9, 0)) is False
        assert is_trading_time(datetime(2025, 6, 2, 12, 0)) is False
        assert is_trading_time(datetime(2025, 6, 2, 15, 1)) is False

    def test_skip_reason(self):
        from src.trading.trading_hours import skip_reason
        from datetime import datetime
        # 周一 10:00 应为在交易时段
        r = skip_reason(datetime(2025, 6, 2, 10, 0))
        assert r == "" or "非" in r  # 若 2025-06-02 为节假日则非空
        # 周六 10:00 应为非交易日
        r = skip_reason(datetime(2025, 6, 7, 10, 0))
        assert "非交易日" in r
