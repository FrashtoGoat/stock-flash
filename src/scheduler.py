"""定时器模块：基于 APScheduler 的任务调度"""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import get
from src.main import pipeline, pipeline_research_pool

logger = logging.getLogger(__name__)


async def _run_both_routes() -> None:
    """先跑新闻驱动，再跑自研池，互不干扰（便于持续观察两条路线）。"""
    await pipeline()
    await pipeline_research_pool()


async def _run_macro() -> None:
    """拉取宏观快照（美联储利率、美债收益率等），落 result/macro/。"""
    from src.macro import fetch_macro_snapshot
    await asyncio.to_thread(fetch_macro_snapshot)


def _parse_cron(expr: str) -> dict:
    """解析 cron 表达式为 APScheduler 参数
    格式: minute hour day month day_of_week
    支持 */N 语法
    """
    parts = expr.split()
    if len(parts) == 5:
        return {
            "minute": parts[0],
            "hour": parts[1],
            "day": parts[2],
            "month": parts[3],
            "day_of_week": parts[4],
        }
    # 带秒的6段格式
    if len(parts) == 6:
        return {
            "second": parts[0],
            "minute": parts[1],
            "hour": parts[2],
            "day": parts[3],
            "month": parts[4],
            "day_of_week": parts[5],
        }
    raise ValueError(f"无效的 cron 表达式: {expr}")


def create_scheduler() -> AsyncIOScheduler:
    """创建并配置定时调度器"""
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    cfg = get("scheduler") or {}
    jobs = cfg.get("jobs", [])

    for job in jobs:
        name = job.get("name", "unnamed")
        cron_expr = job.get("cron", "")
        if not cron_expr:
            continue
        run_both = job.get("run_both", False)
        run_macro = job.get("macro", False)
        if run_macro:
            fn = _run_macro
        elif run_both:
            fn = _run_both_routes
        else:
            fn = pipeline

        try:
            cron_params = _parse_cron(cron_expr)
            scheduler.add_job(
                fn,
                trigger=CronTrigger(**cron_params, timezone="Asia/Shanghai"),
                id=name,
                name=name,
                replace_existing=True,
            )
            kind = "宏观" if run_macro else ("双路线" if run_both else "新闻驱动")
            logger.info("定时任务已添加: %s -> %s (%s)", name, cron_expr, kind)
        except Exception:
            logger.exception("添加定时任务失败: %s", name)

    return scheduler
