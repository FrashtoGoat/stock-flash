"""通知模块：邮件等方式通知用户"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Template

from src.config import get
from src.models.stock import FilterResult, MarketCondition, TradeSignal

logger = logging.getLogger(__name__)

_EMAIL_TEMPLATE = """\
<html><body>
<h2>📊 Stock Flash 交易信号通知</h2>

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
) -> bool:
    """发送邮件通知"""
    cfg = get("notification", "email") or {}
    if not cfg.get("enabled", False):
        logger.info("邮件通知未启用")
        return False

    smtp_server = cfg.get("smtp_server", "")
    smtp_port = cfg.get("smtp_port", 465)
    sender = cfg.get("sender", "")
    password = cfg.get("password", "")
    receivers = cfg.get("receivers", [])

    if not all([smtp_server, sender, password, receivers]):
        logger.warning("邮件配置不完整，跳过发送")
        return False

    tpl = Template(_EMAIL_TEMPLATE)
    html = tpl.render(market=market, signals=signals)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Stock Flash: {market.index_name} {market.change_pct:+.2f}% | {len(signals)} 个信号"
    msg["From"] = sender
    msg["To"] = ", ".join(receivers)
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender, password)
            server.sendmail(sender, receivers, msg.as_string())
        logger.info("邮件通知发送成功 -> %s", receivers)
        return True
    except Exception:
        logger.exception("邮件发送失败")
        return False


async def notify(
    market: MarketCondition,
    signals: list[TradeSignal],
) -> None:
    """统一通知入口，可扩展多种通知方式"""
    await send_email_notification(market, signals)
    # TODO: 微信通知等其他方式
