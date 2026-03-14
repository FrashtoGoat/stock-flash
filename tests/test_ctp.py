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
