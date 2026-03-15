"""宏观数据拉取：美联储利率、美债收益率、美元指数等（akshare），落 result/macro/，可选邮件报告。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.config import get

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_RESULT_MACRO = _ROOT / "result" / "macro"


def _parse_date(s: str) -> datetime | None:
    """解析日期字符串为 datetime，支持 YYYY-MM-DD 等。"""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    return None


def _usa_fed_rate() -> dict | None:
    """美联储利率决议：取最新一条（今值 %）。"""
    try:
        import akshare as ak
        df = ak.macro_bank_usa_interest_rate()
        if df is None or df.empty:
            return None
        row = df.dropna(subset=["今值"]).tail(1)
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "name": "美国联邦基金利率(美联储)",
            "date": str(r.get("日期", "")),
            "value": float(r["今值"]),
            "unit": "%",
        }
    except Exception as e:
        logger.warning("拉取美联储利率失败: %s", e)
        return None


def _usa_bond_yield() -> dict | None:
    """美国国债收益率：取最近一条 10Y（东方财富 bond_zh_us_rate）。列序：0=日期，8/9/10=美国2Y/5Y/10Y。"""
    try:
        import akshare as ak
        start = f"{datetime.now().year - 1}0101"
        df = ak.bond_zh_us_rate(start_date=start)
        if df is None or df.empty or len(df.columns) < 11:
            return None
        row = df.tail(1).iloc[0]
        date_val = str(row.iloc[0])
        # 美国10年期国债收益率 列索引 10
        val_10y = row.iloc[10]
        if val_10y is None or (isinstance(val_10y, float) and (val_10y != val_10y)):
            return None
        return {
            "name": "美国10年期国债收益率",
            "date": date_val,
            "value": float(val_10y),
            "unit": "%",
        }
    except Exception as e:
        logger.warning("拉取美债收益率失败: %s", e)
        return None


def _last_12_month_keys() -> list[str]:
    """最近 12 个月份键，按时间正序（如 2025-04, 2025-05, ..., 2026-03）。"""
    now = datetime.now()
    keys = []
    for i in range(12):
        m = now.month - 1 - i
        y = now.year + m // 12
        m = m % 12 + 1
        keys.append(f"{y}-{m:02d}")
    return list(reversed(keys))


def _group_by_month_and_year(
    rows: list[dict], date_key: str = "date", value_key: str = "value"
) -> tuple[list[dict], list[dict]]:
    """按月度（最近12个月）、年份（近30年）聚合，每期取该期最后一条的 value。"""
    now = datetime.now()
    year_cutoff = now.year - 30
    sorted_rows = sorted(
        [r for r in rows if _parse_date(str(r.get(date_key, "")))],
        key=lambda x: str(x.get(date_key, "")),
    )
    by_month: dict[str, float] = {}
    by_year: dict[int, float] = {}
    for r in sorted_rows:
        dt = _parse_date(str(r.get(date_key, "")))
        if not dt:
            continue
        val = r.get(value_key)
        if val is None:
            continue
        try:
            val_f = float(val)
        except (TypeError, ValueError):
            continue
        by_month[dt.strftime("%Y-%m")] = val_f
        if dt.year >= year_cutoff:
            by_year[dt.year] = val_f
    month_keys = _last_12_month_keys()
    month_list = [(k, by_month[k]) for k in month_keys if k in by_month]
    year_list = sorted(by_year.items(), key=lambda x: x[0])[:30]  # 正序：旧→新，折线图从左到右时间递增
    return (
        [{"period": m, "value": v} for m, v in month_list],
        [{"period": str(y), "value": v} for y, v in year_list],
    )


def _usa_fed_rate_by_month_and_year() -> tuple[list[dict], list[dict]]:
    """美联储利率：月度=当年每月末/最新决议值，年份=近30年每年末/最新值。"""
    try:
        import akshare as ak
        df = ak.macro_bank_usa_interest_rate()
        if df is None or df.empty or "今值" not in df.columns:
            return [], []
        rows = []
        for _, r in df.dropna(subset=["今值"]).iterrows():
            d = str(r.get("日期", ""))[:10]
            rows.append({"date": d, "value": float(r["今值"])})
        return _group_by_month_and_year(rows)
    except Exception as e:
        logger.warning("拉取美联储利率序列失败: %s", e)
        return [], []


def _usa_bond_yield_by_month_and_year() -> tuple[list[dict], list[dict]]:
    """美国10年期国债收益率：按日频聚合为月度（当年）、年份（有数据的最近30年）。"""
    try:
        import akshare as ak
        start = f"{datetime.now().year - 31}0101"
        df = ak.bond_zh_us_rate(start_date=start)
        if df is None or df.empty or len(df.columns) < 11:
            return [], []
        rows = []
        for _, row in df.iterrows():
            date_val = str(row.iloc[0])[:10]
            val_10y = row.iloc[10]
            if val_10y is not None and (not isinstance(val_10y, float) or val_10y == val_10y):
                rows.append({"date": date_val, "value": round(float(val_10y), 2)})
        return _group_by_month_and_year(rows)
    except Exception as e:
        logger.warning("拉取美债收益率序列失败: %s", e)
        return [], []


def _dollar_index() -> dict | None:
    """美元指数：若 akshare 有则拉取，否则返回 None（后续可接其他源）。"""
    try:
        import akshare as ak
        # 部分版本有 fx_spot_quote 或 currency 相关接口
        if hasattr(ak, "fx_spot_quote"):
            df = ak.fx_spot_quote()
            if df is not None and not df.empty and "美元指数" in str(df.columns):
                row = df[df.iloc[:, 0].astype(str).str.contains("美元", na=False)].head(1)
                if not row.empty:
                    return {"name": "美元指数", "date": datetime.now().strftime("%Y-%m-%d"), "value": float(row.iloc[0].iloc[-1]), "unit": ""}
        return None
    except Exception as e:
        logger.debug("拉取美元指数失败(可选): %s", e)
        return None


def fetch_macro_snapshot() -> dict:
    """
    拉取当前宏观快照：美联储利率、美债收益率、美元指数（如有）。
    写入 result/macro/YYYY-MM-DD/HH.json，返回汇总 dict。
    """
    cfg = get("macro") or {}
    if not cfg.get("enabled", True):
        logger.info("宏观模块未启用，跳过")
        return {"enabled": False}

    out: dict = {"ts": datetime.now().isoformat(), "items": []}

    fed = _usa_fed_rate()
    if fed:
        out["items"].append(fed)

    bond = _usa_bond_yield()
    if bond:
        out["items"].append(bond)

    dollar = _dollar_index()
    if dollar:
        out["items"].append(dollar)

    # 落盘
    _RESULT_MACRO.mkdir(parents=True, exist_ok=True)
    day_dir = _RESULT_MACRO / datetime.now().strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    hour = datetime.now().strftime("%H")
    path = day_dir / f"{hour}.json"
    try:
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("宏观快照已写入: %s (%d 项)", path, len(out["items"]))
    except Exception as e:
        logger.warning("写入宏观快照失败: %s", e)

    # 可选：按月度（当年）、年份（近30年）拉取并发邮件表格
    if cfg.get("notify_email", False):
        report = fetch_macro_report()
        if report:
            html = build_macro_report_html(report)
            subject = f"Stock Flash 宏观报告 | 月度·年份 | {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            try:
                from src.trading.notifier import send_custom_email
                send_custom_email(subject, html)
            except Exception as e:
                logger.warning("宏观报告邮件发送失败: %s", e)

    return out


def fetch_macro_report() -> dict:
    """拉取宏观数据，按月度（当年）、年份（近30年）聚合。返回 {指标名: {"by_month": [...], "by_year": [...]}}。"""
    report = {}
    fed_m, fed_y = _usa_fed_rate_by_month_and_year()
    if fed_m or fed_y:
        report["美国联邦基金利率(美联储)"] = {"by_month": fed_m, "by_year": fed_y}
    bond_m, bond_y = _usa_bond_yield_by_month_and_year()
    if bond_m or bond_y:
        report["美国10年期国债收益率"] = {"by_month": bond_m, "by_year": bond_y}
    return report


def _svg_line_chart(rows: list[dict], width: int = 520, height: int = 200) -> str:
    """根据 [{"period", "value"}, ...] 生成折线图 SVG（内联，邮件可用）。"""
    if not rows:
        return ""
    values = [float(r["value"]) for r in rows]
    vmin = min(values)
    vmax = max(values)
    if vmax <= vmin:
        vmax = vmin + 1
    pad_left = 44
    pad_right = 20
    pad_top = 16
    pad_bottom = 28
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    n = len(rows)
    points = []
    for i, r in enumerate(rows):
        x = pad_left + (i / (n - 1) * plot_w) if n > 1 else pad_left + plot_w // 2
        y = pad_top + plot_h - (float(r["value"]) - vmin) / (vmax - vmin) * plot_h
        points.append(f"{x:.1f},{y:.1f}")
    polyline = f'<polyline fill="none" stroke="#1a73e8" stroke-width="2" points="{" ".join(points)}"/>'
    # Y 轴刻度（左）
    y_ticks = []
    for i in range(4):
        v = vmin + (vmax - vmin) * (1 - i / 3)
        y = pad_top + plot_h * i / 3
        y_ticks.append(f'<text x="{pad_left - 6}" y="{y + 4}" font-size="10" fill="#666" text-anchor="end">{v:.1f}</text>')
    # X 轴标签（底部，间隔显示避免拥挤）
    step = max(1, n // 8)
    x_labels = []
    for i in range(0, n, step):
        x = pad_left + (i / (n - 1) * plot_w) if n > 1 else pad_left
        label = rows[i]["period"]
        if "-" in label:
            label = label.split("-")[-1]  # 月度只显示月份如 04
        x_labels.append(f'<text x="{x}" y="{height - 6}" font-size="10" fill="#666" text-anchor="middle">{label}</text>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="#fafafa"/>'
        + "".join(y_ticks)
        + "".join(x_labels)
        + polyline
        + "</svg>"
    )
    return svg


def build_macro_report_html(report: dict) -> str:
    """将 report 转为 HTML：按月度（最近12月）、年份（近30年）表+折线图。"""
    unit_suffix = " %"
    parts = []
    for name, data in report.items():
        if not data:
            continue
        unit = unit_suffix if ("利率" in name or "收益" in name) else ""
        by_month = data.get("by_month") or []
        by_year = data.get("by_year") or []
        if by_month:
            trs = "".join(
                f"<tr><td>{r['period']}</td><td>{r['value']}{unit}</td></tr>"
                for r in by_month
            )
            parts.append(
                f"<h3>{name} · 月度（最近12个月）</h3>"
                f"<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\">"
                f"<tr><th>月份</th><th>数值</th></tr>{trs}</table>"
            )
            svg = _svg_line_chart(by_month)
            if svg:
                parts.append(f"<p>{svg}</p>")
        if by_year:
            trs = "".join(
                f"<tr><td>{r['period']}年</td><td>{r['value']}{unit}</td></tr>"
                for r in by_year
            )
            parts.append(
                f"<h3>{name} · 年份（近30年）</h3>"
                f"<table border=\"1\" cellpadding=\"6\" cellspacing=\"0\">"
                f"<tr><th>年份</th><th>数值</th></tr>{trs}</table>"
            )
            svg = _svg_line_chart(by_year)
            if svg:
                parts.append(f"<p>{svg}</p>")
    if not parts:
        return "<p>暂无宏观数据。</p>"
    body = (
        "<html><body><h2>📊 Stock Flash 宏观报告</h2>"
        "<p>生成时间：{}</p>{}<hr><small>月度=最近12月，年份=近30年 · 仅供参考</small></body></html>"
    ).format(datetime.now().strftime("%Y-%m-%d %H:%M"), "".join(parts))
    return body
