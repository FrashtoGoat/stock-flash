"""通知模块：邮件、企业微信、PushPlus(个微) 通知用户"""

from __future__ import annotations

import base64
import logging
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import httpx
from jinja2 import Template

from src.config import get
from src.models.stock import MarketCondition, TradeSignal

logger = logging.getLogger(__name__)


def _confidence_and_conditions(signal: TradeSignal, source: str) -> str:
    """返回信心说明与满足条件：为何是该百分比、原因里通过了哪些环节。"""
    pct = round(signal.confidence * 100)
    reason = signal.reason or ""
    if source == "自研池" and "通过链式筛选:" in reason:
        # 自研池：信心 = 基础 50% + 每过一环 +7%，上限 95%
        part = reason.split("通过链式筛选:")[-1].strip()
        conditions = [x.strip() for x in part.split(",") if x.strip()]
        n = len(conditions)
        expl = f"{pct}%：共{n}环全部通过（{', '.join(conditions)}），基础50%+每环7%。满足条件：{', '.join(conditions)}。"
        return expl
    # 新闻驱动或其它：信心来自 LLM 综合评分
    return f"{pct}%：来自 LLM 对新闻与标的的综合评分。原因：{reason[:80]}{'…' if len(reason) > 80 else ''}"


def _build_short_text(
    market: MarketCondition,
    signals: list[TradeSignal],
    source: str = "新闻驱动",
) -> str:
    """构建纯文本摘要，用于企微/PushPlus"""
    lines = [
        f"【来源】{source}",
        f"【大盘】{market.index_name} {market.current_price:.2f} ({market.change_pct:+.2f}%)",
        "可交易" if market.is_tradable else f"不宜交易: {market.reason}",
        "",
    ]
    if signals:
        sells = [s for s in signals if s.direction.value == "sell"]
        buys = [s for s in signals if s.direction.value == "buy"]
        if sells:
            lines.append(f"【卖出信号】{len(sells)} 个（止盈/止损触发，请关注）")
            for s in sells[:5]:
                lines.append(f"  {s.stock.name}({s.stock.code}) 卖出 | {s.reason or ''}")
            if buys:
                lines.append("")
        if buys:
            lines.append(f"【买入信号】{len(buys)} 个")
            for s in buys[:10]:
                expl = _confidence_and_conditions(s, source)
                lines.append(f"  {s.stock.name}({s.stock.code}) 买入 {s.amount:.0f} 元 | {expl}")
    else:
        lines.append("【信号】本次无交易信号")
    return "\n".join(lines)

_EMAIL_TEMPLATE = """\
<html><body>
<h2>📊 Stock Flash 交易信号通知</h2>
<p><b>来源</b>: {{ source }}</p>

<h3>大盘环境</h3>
<p>{{ market.index_name }}: {{ "%.2f"|format(market.current_price) }}
  ({{ "%.2f"|format(market.change_pct) }}%)
  — <b>{{ "可交易" if market.is_tradable else "不宜交易" }}</b>
</p>
{% if market.reason %}<p>备注: {{ market.reason }}</p>{% endif %}

{% if sell_signals %}
<h3>⚠️ 卖出信号 ({{ sell_signals|length }}个) — 止盈/止损触发，请关注</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>代码</th><th>名称</th><th>方向</th><th>金额</th><th>原因</th></tr>
{% for s in sell_signals %}
<tr>
  <td>{{ s.stock.code }}</td>
  <td>{{ s.stock.name }}</td>
  <td>卖出</td>
  <td>{{ "%.0f"|format(s.amount) }}</td>
  <td>{{ s.reason }}</td>
</tr>
{% endfor %}
</table>
{% endif %}

{% if buy_signals %}
<h3>买入信号 ({{ buy_signals|length }}个)</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>代码</th><th>名称</th><th>方向</th><th>金额</th><th>信心</th><th>原因</th><th>信心说明与满足条件</th></tr>
{% for s in buy_signals %}
<tr>
  <td>{{ s.stock.code }}</td>
  <td>{{ s.stock.name }}</td>
  <td>买入</td>
  <td>{{ "%.0f"|format(s.amount) }}</td>
  <td>{{ "%.0f"|format(s.confidence * 100) }}%</td>
  <td>{{ s.reason }}</td>
  <td>{{ confidence_explanations[loop.index0] }}</td>
</tr>
{% endfor %}
</table>
{% endif %}

{% if not sell_signals and not buy_signals %}
<p>本次扫描无交易信号。</p>
{% endif %}

<hr><small>Stock Flash 自动生成 · 仅供参考 · 满足卖出条件时同样会通知</small>
</body></html>
"""


async def send_email_notification(
    market: MarketCondition,
    signals: list[TradeSignal],
    source: str = "新闻驱动",
) -> bool:
    """发送邮件通知。含买入与卖出信号；买入信号附带信心说明与满足条件。"""
    cfg = get("notification", "email") or {}
    if not cfg.get("enabled", False):
        logger.info("邮件通知未启用")
        return False

    smtp_server = cfg.get("smtp_server", "")
    smtp_port = cfg.get("smtp_port", 465)
    sender = (cfg.get("sender") or "").strip()
    sender_name = (cfg.get("sender_name") or "").strip()
    password = cfg.get("password", "")
    receivers = [r.strip() for r in cfg.get("receivers", []) if (r or "").strip()]

    if not all([smtp_server, sender, password, receivers]):
        logger.warning("邮件配置不完整，跳过发送")
        return False

    sell_signals = [s for s in signals if s.direction.value == "sell"]
    buy_signals = [s for s in signals if s.direction.value == "buy"]
    confidence_explanations = [_confidence_and_conditions(s, source) for s in buy_signals]

    tpl = Template(_EMAIL_TEMPLATE)
    html = tpl.render(
        market=market,
        source=source,
        sell_signals=sell_signals,
        buy_signals=buy_signals,
        confidence_explanations=confidence_explanations,
    )

    subject_parts = [f"Stock Flash [{source}]", market.index_name, f"{market.change_pct:+.2f}%"]
    if sell_signals:
        subject_parts.append(f"| {len(sell_signals)} 个卖出信号(止盈/止损)")
    if buy_signals:
        subject_parts.append(f"| {len(buy_signals)} 个买入信号")
    if not signals:
        subject_parts.append("| 无信号")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(" ".join(subject_parts), "utf-8")
    if sender_name:
        msg["From"] = formataddr((str(Header(sender_name, "utf-8")), sender))
    else:
        msg["From"] = sender
    msg["To"] = ", ".join(receivers)
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            # 使用 UTF-8 做 AUTH PLAIN，支持授权码中含中文等非 ASCII 字符
            auth_str = f"\0{sender}\0{password}"
            b64 = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
            server.docmd("AUTH PLAIN", b64)
            server.sendmail(sender, receivers, msg.as_string())
        logger.info("邮件通知发送成功 -> %s", receivers)
        return True
    except Exception:
        logger.exception("邮件发送失败")
        return False


async def send_wecom_webhook(
    market: MarketCondition,
    signals: list[TradeSignal],
    source: str = "新闻驱动",
) -> bool:
    """企业微信群机器人 webhook 通知（不麻烦：群设置 -> 添加机器人 -> 复制 webhook 即可）"""
    cfg = get("notification", "wechat") or {}
    if not cfg.get("enabled", False):
        return False
    webhook_url = (cfg.get("webhook_url") or "").strip()
    if not webhook_url:
        logger.debug("企微 webhook_url 未配置，跳过")
        return False

    text = _build_short_text(market, signals, source=source)
    body = {"msgtype": "text", "text": {"content": text}}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(webhook_url, json=body)
            r.raise_for_status()
        logger.info("企微 webhook 通知发送成功")
        return True
    except Exception:
        logger.exception("企微 webhook 发送失败")
        return False


async def send_pushplus(
    market: MarketCondition,
    signals: list[TradeSignal],
    source: str = "新闻驱动",
) -> bool:
    """PushPlus 推送到个人微信（需在 pushplus.plus 绑定微信获取 token）。
    若手机未收到：请检查 (1) token 是否正确 (2) 是否已在 pushplus.plus 绑定微信并关注公众号
    (3) 登录 pushplus.plus 查看「发送记录」是否有该条。"""
    cfg = get("notification", "pushplus") or {}
    if not cfg.get("enabled", False):
        return False
    token = (cfg.get("token") or "").strip()
    if not token:
        logger.debug("PushPlus token 未配置，跳过")
        return False

    text = _build_short_text(market, signals, source=source)
    title = f"Stock Flash [{source}] | {market.index_name} {market.change_pct:+.2f}% | {len(signals)} 个信号"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                "https://www.pushplus.plus/send",
                json={"token": token, "title": title, "content": text},
            )
            r.raise_for_status()
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            code = body.get("code")
            msg = body.get("msg", "")
            if code != 200 and code is not None:
                logger.warning("PushPlus 返回异常: code=%s msg=%s（若手机未收到请检查 token、是否已关注公众号、官网发送记录）", code, msg)
                return False
        logger.info("PushPlus(个微) 通知发送成功")
        return True
    except Exception:
        logger.exception("PushPlus 发送失败")
        return False


async def notify(
    market: MarketCondition,
    signals: list[TradeSignal],
    source: str = "新闻驱动",
) -> None:
    """统一通知入口：邮件 / 企微 webhook / PushPlus(个微)。source 标明路线来源（新闻驱动/自研池）。"""
    await send_email_notification(market, signals, source=source)
    await send_wecom_webhook(market, signals, source=source)
    await send_pushplus(market, signals, source=source)
