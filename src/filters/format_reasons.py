"""将链式筛选的 details 格式化为可读的「通过标准/依据」，避免黑盒。"""

from __future__ import annotations


def _inner(details: dict, name: str) -> dict:
    """从 result.details[name] 取出内层 dict（可能为 {name: {...}}）。"""
    d = details.get(name)
    if not isinstance(d, dict):
        return {}
    if name in d and isinstance(d[name], dict):
        return d[name]
    return d


def format_filter_pass_reasons(passed_filters: list[str], details: dict) -> str:
    """
    根据 passed_filters 顺序与 details，生成每环通过的依据说明。
    用于通知中展示「为何通过」，而非仅列出环节名。
    """
    _display = {
        "board_filter": "板块",
        "affordability_filter": "可买",
        "anomaly_filter": "异动",
        "master_filter": "基本面",
        "institution_filter": "机构",
        "technical_filter": "技术",
    }
    parts = []
    for name in passed_filters:
        inner = _inner(details, name)
        display = _display.get(name, name)
        if name == "board_filter":
            note = inner.get("tradable_note") or inner.get("detected_board") or "—"
            parts.append(f"{display}: {note}")
        elif name == "affordability_filter":
            price = inner.get("current_price")
            mx = inner.get("max_price")
            if price is not None and mx is not None:
                parts.append(f"{display}: 股价{price:.2f}<{mx}元且主板")
            else:
                parts.append(f"{display}: 满足可买条件(价格/板块)")
        elif name == "anomaly_filter":
            c1 = inner.get("change_1d_pct")
            c5 = inner.get("change_5d_pct")
            up = inner.get("up_days_in_5")
            bits = []
            if c1 is not None:
                bits.append(f"1日{c1}%")
            if c5 is not None:
                bits.append(f"5日{c5}%")
            if up is not None:
                bits.append(f"5日收阳{up}天")
            if bits:
                parts.append(f"{display}: " + ", ".join(bits) + "，在合理区间")
            else:
                parts.append(f"{display}: 涨跌幅在合理区间、非暴涨暴跌")
        elif name == "master_filter":
            roe = inner.get("roe")
            pe = inner.get("pe")
            pb = inner.get("pb")
            debt = inner.get("debt_ratio")
            msg = []
            if roe is not None and (not isinstance(roe, float) or roe == roe):
                msg.append(f"ROE={roe:.1f}%" if isinstance(roe, (int, float)) else f"ROE={roe}")
            if pe is not None and (not isinstance(pe, float) or pe == pe):
                msg.append(f"PE={pe:.0f}" if isinstance(pe, (int, float)) else f"PE={pe}")
            if pb is not None and (not isinstance(pb, float) or pb == pb):
                msg.append(f"PB={pb:.1f}" if isinstance(pb, (int, float)) else f"PB={pb}")
            if debt is not None and (not isinstance(debt, float) or debt == debt):
                msg.append(f"负债率={debt:.0f}%" if isinstance(debt, (int, float)) else f"负债={debt}")
            if msg:
                parts.append(f"{display}: " + ", ".join(msg) + " 满足阈值")
            else:
                parts.append(f"{display}: 估值/盈利/负债/成长 满足配置阈值")
        elif name == "institution_filter":
            inst = inner.get("institutions") or {}
            cnt = inst.get("institution_count")
            lhb = inner.get("龙虎榜") or {}
            bits = []
            if cnt is not None:
                bits.append(f"十大股东机构数≥{cnt}")
            if lhb and lhb.get("recent_count"):
                bits.append(f"龙虎榜近期上榜{lhb.get('recent_count')}次")
            if bits:
                parts.append(f"{display}: " + ", ".join(bits))
            else:
                parts.append(f"{display}: 机构持仓/龙虎榜 满足")
        elif name == "technical_filter":
            vr = inner.get("volume_ratio")
            to = inner.get("turnover_rate")
            chip = inner.get("chip_profit_pct")
            last = inner.get("last_close")
            ma5 = inner.get("ma5")
            ma10 = inner.get("ma10")
            ma20 = inner.get("ma20")
            macd_val = inner.get("macd")
            macd_sig = inner.get("macd_signal")
            above_ma20 = inner.get("checks", {}).get("above_ma20")
            ma_trend_ok = inner.get("checks", {}).get("ma_trend")
            macd_ok = inner.get("checks", {}).get("macd")
            msg = []
            if vr is not None and vr != "N/A":
                msg.append(f"量比{vr}")
            elif vr == "N/A":
                msg.append("量比(行情未取到,视为通过)")
            if to is not None and to != "N/A":
                msg.append(f"换手{to}%")
            elif to == "N/A":
                msg.append("换手(行情未取到,视为通过)")
            if chip is not None and chip != "N/A":
                msg.append(f"筹码获利{chip}%")
            if last is not None:
                msg.append(f"现价{last}")
            if ma5 is not None and ma10 is not None and ma20 is not None:
                if ma_trend_ok:
                    msg.append(f"MA5({ma5})>MA10({ma10})>MA20({ma20})")
                else:
                    msg.append(f"均线MA5/10/20={ma5}/{ma10}/{ma20}")
            if last is not None and ma20 is not None and above_ma20 is True:
                msg.append("收盘站上MA20")
            elif last is not None and ma20 is not None and above_ma20 is False:
                msg.append("收盘未站上MA20")
            if macd_val is not None and macd_sig is not None:
                macd_str = f"MACD={macd_val:.3f} 信号线={macd_sig:.3f}"
                if macd_ok:
                    macd_str += "(满足配置:水上或金叉)"
                msg.append(macd_str)
            if msg:
                parts.append(f"{display}: " + ", ".join(msg))
            else:
                parts.append(f"{display}: 量比/换手/筹码/均线/MACD 满足配置阈值")
        else:
            parts.append(f"{display}: 通过")
    return " | ".join(parts)
