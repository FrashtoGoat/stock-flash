"""Stock Flash 启动入口

用法:
    python run.py              # 执行一次完整流水线
    python run.py --schedule   # 启动定时调度模式
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
    parser.add_argument("--once", action="store_true", default=True, help="执行一次流水线 (默认)")
    args = parser.parse_args()

    _setup_logging()
    logger = logging.getLogger(__name__)

    if args.schedule:
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
    else:
        logger.info("执行一次完整流水线...")
        from src.main import run_once
        run_once()


if __name__ == "__main__":
    main()
