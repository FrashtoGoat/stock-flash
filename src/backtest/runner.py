"""最小回测：从 DB/JSON 读取交易记录，用 akshare 日线模拟成交，算收益率与最大回撤"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.config import get
from src.db.repository import list_trades
from src.db.session import get_session, init_db

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_TRADES_DIR = _ROOT / "result" / "trades"  # 按日期分组：result/trades/YYYY-MM-DD/*.json


def _load_trades_from_db(since: datetime | None) -> list[dict]:
    """从数据库加载交易记录，转为 [{code, name, direction, amount, exec_price, exec_time}, ...]"""
    init_db()
    rows = list_trades(since=since)
    out = []
    for r in rows:
        out.append({
            "code": r.stock_code,
            "name": r.stock_name,
            "direction": r.direction,
            "amount": r.amount,
            "exec_price": r.exec_price,
            "exec_time": r.exec_time or r.created_at,
        })
    return out


def _load_trades_from_json(since: datetime | None) -> list[dict]:
    """从 result/trades/YYYY-MM-DD/*.json 加载交易记录（按日期分组）"""
    out = []
    if not _TRADES_DIR.exists():
        return out
    cutoff = (since or datetime.min).timestamp()
    all_jsons = list(_TRADES_DIR.glob("*/*.json"))  # 含 trade_*.json 与 trade_paper_*.json
    for path in sorted(all_jsons, key=lambda p: (p.name, str(p)), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data:
                sig = item.get("signal", {})
                stock = sig.get("stock", {})
                exec_time = item.get("exec_time")
                if exec_time:
                    ts = datetime.fromisoformat(exec_time.replace("Z", "+00:00")).timestamp()
                    if ts < cutoff:
                        continue
                out.append({
                    "code": stock.get("code", ""),
                    "name": stock.get("name", ""),
                    "direction": sig.get("direction", "buy"),
                    "amount": float(sig.get("amount", 0)),
                    "exec_price": item.get("exec_price"),
                    "exec_time": exec_time,
                })
        except Exception:
            logger.warning("读取 %s 失败", path)
    return out


def _get_daily_close(code: str, date: datetime) -> float | None:
    """取标的在 date 所在交易日的收盘价（akshare 日线）"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=(date - timedelta(days=30)).strftime("%Y%m%d"), end_date=(date + timedelta(days=1)).strftime("%Y%m%d"))
        if df is None or df.empty:
            return None
        df["日期"] = df["日期"].astype(str)
        target = date.strftime("%Y-%m-%d")
        row = df[df["日期"] <= target].tail(1)
        if row.empty:
            return None
        return float(row.iloc[0]["收盘"])
    except Exception:
        logger.debug("获取 %s 日线失败: %s", code, date)
        return None


def run_backtest(days: int = 90) -> dict:
    """
    简单回测：最近 days 天内的交易记录，按 exec_time 顺序模拟成交（用当日或最近收盘价），
    计算总收益与最大回撤。假设初始资金 0，仅统计每笔买卖的盈亏。
    返回 {"total_pnl", "total_pnl_pct", "max_drawdown_pct", "trades_count", "win_count"} 等。
    """
    since = datetime.now() - timedelta(days=days)
    trades = _load_trades_from_db(since)
    if not trades:
        trades = _load_trades_from_json(since)
    if not trades:
        logger.info("回测：无交易记录")
        return {"total_pnl": 0, "total_pnl_pct": 0, "max_drawdown_pct": 0, "trades_count": 0, "win_count": 0}

    # 按时间排序
    def _ts(t):
        if isinstance(t.get("exec_time"), str):
            try:
                return datetime.fromisoformat(t["exec_time"].replace("Z", "+00:00"))
            except Exception:
                return datetime.min
        return t.get("exec_time") or datetime.min

    trades = sorted(trades, key=_ts)

    # 持仓: code -> [(shares, cost_per_share), ...] FIFO
    positions: dict[str, list[tuple[float, float]]] = {}
    equity_curve: list[float] = [0.0]
    peak = 0.0
    max_dd = 0.0
    win_count = 0
    closed_pnl = 0.0
    total_cost = 0.0  # 总投入（买入金额累计）

    for t in trades:
        code = t["code"]
        direction = t["direction"]
        amount = float(t["amount"])  # 金额（元）
        exec_time = t.get("exec_time")
        if isinstance(exec_time, str):
            try:
                exec_time = datetime.fromisoformat(exec_time.replace("Z", "+00:00"))
            except Exception:
                exec_time = datetime.now()
        if not exec_time:
            exec_time = datetime.now()
        price = t.get("exec_price") or _get_daily_close(code, exec_time)
        if price is None or price <= 0:
            price = 0.0

        if direction == "buy":
            if price <= 0:
                continue
            shares = amount / price
            if code not in positions:
                positions[code] = []
            positions[code].append((shares, price))
            total_cost += amount
        else:
            if price <= 0:
                continue
            sell_shares = amount / price
            lots = positions.get(code, [])
            cost_basis = 0.0
            remaining = sell_shares
            while lots and remaining > 1e-6:
                s, c = lots[0]
                use = min(s, remaining)
                cost_basis += use * c
                remaining -= use
                if use >= s - 1e-6:
                    lots.pop(0)
                else:
                    lots[0] = (s - use, c)
                    break
            if not lots and code in positions:
                del positions[code]
            pnl = amount - cost_basis
            closed_pnl += pnl
            if pnl > 0:
                win_count += 1

        pos_value = sum(sum(s * c for s, c in positions.get(cd, [])) for cd in positions)
        equity_curve.append(closed_pnl + pos_value)
        if equity_curve[-1] > peak:
            peak = equity_curve[-1]
        if peak > 0:
            dd = (peak - equity_curve[-1]) / peak
            if dd > max_dd:
                max_dd = dd

    total_pnl = closed_pnl
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0
    sell_count = sum(1 for t in trades if t["direction"] == "sell")

    return {
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "trades_count": len(trades),
        "sell_count": sell_count,
        "win_count": win_count,
    }
