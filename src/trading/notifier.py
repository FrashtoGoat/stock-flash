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
        lines.append(f"【信号】{len(signals)} 个")
        for s in signals[:10]:
            lines.append(f"  {s.stock.name}({s.stock.code}) 买入 {s.amount:.0f} 元 | {s.reason[:40]}")
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

{% if signals %}
<h3>交易信号 ({{ signals|length }}个)</h3>
<table border="1" cellpadding="6" cellspacing="0">
<tr><th>代码</th><th>名称</th><th>方向</th><th>金额</th><th>信心</th><th>原因</th></tr>
{% for s in signals %}
<tr>
  <td>{{ s.stock.code }}</td>
  <td>{{ s.stock.name }}</td>
  <td>{{ s.direction.value }}</td>
  <td>{{ "%.0f"|format(s.amount) }}</td>
  <td>{{ "%.0f"|format(s.confidence * 100) }}%</td>
  <td>{{ s.reason }}</td>
</tr>
{% endfor %}
</table>
{% else %}
<p>本次扫描无交易信号。</p>
{% endif %}

<hr><small>Stock Flash 自动生成 · 仅供参考</small>
</body></html>
"""


async def send_email_notification(
    market: MarketCondition,
    signals: list[TradeSignal],
    source: str = "新闻驱动",
) -> bool:
    """发送邮件通知"""
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

    tpl = Template(_EMAIL_TEMPLATE)
    html = tpl.render(market=market, signals=signals, source=source)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(f"Stock Flash [{source}]: {market.index_name} {market.change_pct:+.2f}% | {len(signals)} 个信号", "utf-8")
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
