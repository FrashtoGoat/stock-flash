"""Stock Flash 启动入口

用法:
    python run.py              # 执行一次完整流水线
    python run.py --test       # 测试模式：用石油新闻跑通全流程（不拉取、临时去重）
    python run.py --test-email # 仅发送一封测试邮件（检查邮箱配置）
    python run.py --backtest   # 简单回测
    python run.py --review        # 收盘后复盘：新闻-交易关联与准确率
    python run.py --research-pool # 自研池路线：配置 research_pool.stocks，跑链式筛选→通知→交易（来源标明自研池）
    python run.py --test-ctp     # 测试 OpenCTP 连接与登录
    python run.py --schedule     # 启动定时调度模式
    python run.py --help       # 帮助信息
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import load_config


def _run_test_ctp(test_order: bool = False) -> None:
    """测试 OpenCTP：登录；若 test_order 为真则发一笔低价限价单（仅验证报单，不会成交）。"""
    from src.config import get
    from src.trading.ctp_client import OpenCTPClient
    cfg = get("trading") or {}
    ctp_cfg = cfg.get("ctp") or {}
    user_id = (ctp_cfg.get("user_id") or "").strip()
    password = (ctp_cfg.get("password") or "").strip()
    if not user_id or not password:
        logging.getLogger(__name__).error("请配置 trading.ctp.user_id / password 或环境变量 OPENCTP_USER、OPENCTP_PASSWORD 后重试")
        return
    client = OpenCTPClient(
        td_url=ctp_cfg.get("td_url", "tcp://trading.openctp.cn:30002"),
        user_id=user_id,
        password=password,
        broker_id=ctp_cfg.get("broker_id", "9999"),
        app_id=(ctp_cfg.get("app_id") or "").strip(),
        auth_code=(ctp_cfg.get("auth_code") or "").strip(),
    )
    if client.start():
        logging.getLogger(__name__).info("CTP 登录成功")
        if test_order:
            # 浦发银行 600000，限价 0.01 元/股、100 股，远低于市价不会成交，仅验证报单
            result = client.submit_order("buy", "600000", 0.01, 100.0)
            logging.getLogger(__name__).info(
                "测试报单: success=%s order_ref=%s message=%s",
                result.success, result.order_ref, result.message,
            )
            if result.success:
                logging.getLogger(__name__).info("模拟报单已发出，可在 OpenCTP 监控或 TickTrader 查看挂单（0.01 元不会成交）")
        client.stop()
    else:
        logging.getLogger(__name__).error("CTP 登录失败")


def _setup_logging() -> None:
    cfg = load_config()
    log_cfg = cfg.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)

    log_file = log_cfg.get("file", "logs/stock-flash.log")
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Flash - A股智能交易助手")
    parser.add_argument("--schedule", action="store_true", help="启动定时调度模式")
    parser.add_argument("--test", action="store_true", help="测试模式：石油新闻跑通全流程")
    parser.add_argument("--test-email", action="store_true", help="仅发送一封测试邮件")
    parser.add_argument("--backtest", action="store_true", help="简单回测：根据近期交易记录算收益与回撤")
    parser.add_argument("--review", action="store_true", help="收盘后复盘：关联新闻与交易，统计准确率与建议")
    parser.add_argument("--review-days", type=int, default=1, metavar="N", help="复盘统计最近 N 天 (默认 1)")
    parser.add_argument("--test-ctp", action="store_true", help="测试 OpenCTP 连接与登录")
    parser.add_argument("--test-ctp-order", action="store_true", help="CTP 登录后发一笔测试限价单（低价不成交，仅验证报单）")
    parser.add_argument("--research-pool", action="store_true", help="自研池路线：从配置的股票列表跑链式筛选→通知→交易，来源标明「自研池」")
    parser.add_argument("--once", action="store_true", default=True, help="执行一次流水线 (默认)")
    args = parser.parse_args()

    _setup_logging()
    logger = logging.getLogger(__name__)

    if args.backtest:
        logger.info("运行简单回测（近期交易记录 + 日线）...")
        from src.backtest import run_backtest
        result = run_backtest(days=90)
        logger.info("回测结果: 总盈亏=%.2f 元 (%.2f%%) | 最大回撤=%.2f%% | 交易次数=%d | 盈利卖出=%d",
                    result["total_pnl"], result["total_pnl_pct"], result["max_drawdown_pct"],
                    result["trades_count"], result["win_count"])
    elif args.review:
        logger.info("运行复盘（新闻-交易关联，近 %d 天）...", args.review_days)
        from src.review import run_review
        run_review(since_days=args.review_days)
    elif args.test_ctp:
        logger.info("测试 CTP 连接与登录%s...", "并发一笔测试单" if args.test_ctp_order else "")
        _run_test_ctp(test_order=args.test_ctp_order)
    elif args.test_email:
        logger.info("发送测试邮件...")
        from src.models.stock import MarketCondition
        from src.trading.notifier import send_email_notification
        market = MarketCondition(
            index_code="sh000001",
            index_name="上证指数",
            current_price=4100.0,
            change_pct=-0.5,
            is_tradable=True,
            reason="这是一封测试邮件，说明邮箱配置正常。",
        )
        ok = asyncio.run(send_email_notification(market, []))
        logger.info("测试邮件 %s", "发送成功" if ok else "发送失败")
    elif args.test:
        logger.info("测试模式：使用石油新闻跑通全流程...")
        from src.main import run_once_test
        run_once_test()
    elif args.schedule:
        logger.info("启动定时调度模式...")
        from src.scheduler import create_scheduler
        scheduler = create_scheduler()
        scheduler.start()
        logger.info("定时调度器已启动，按 Ctrl+C 停止")
        try:
            asyncio.get_event_loop().run_forever()
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
            logger.info("调度器已停止")
    elif args.research_pool:
        logger.info("执行自研池流水线（链式筛选起，来源: 自研池）...")
        from src.main import run_once_research_pool
        run_once_research_pool()
    else:
        logger.info("执行一次完整流水线（新闻驱动）...")
        from src.main import run_once
        run_once()


if __name__ == "__main__":
    main()
