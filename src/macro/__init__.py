"""宏观信息模块：中美主要经济指标拉取，供大盘与策略参考。"""

from src.macro.fetcher import fetch_macro_snapshot

__all__ = ["fetch_macro_snapshot"]
