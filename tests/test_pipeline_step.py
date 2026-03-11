"""分段测试：新闻拉取 → result/new_result.txt，LLM 分析 → result/llm_result.txt

特性：
- 追加模式：每次运行追加到文件末尾，不覆盖历史结果
- 标注轮次：自动计算第 N 次测试
- 关联提示词：记录触发本次测试的需求编号
- 终端友好：print 即时刷新，方便在终端中观看执行过程
"""

from __future__ import annotations

import asyncio
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULT_DIR = ROOT / "result"
NEWS_RESULT = RESULT_DIR / "new_result.txt"
LLM_RESULT = RESULT_DIR / "llm_result.txt"


def _next_run_no(path: Path) -> int:
    """从文件中读取历史轮次号，返回下一次的编号"""
    if not path.exists():
        return 1
    content = path.read_text(encoding="utf-8")
    matches = re.findall(r"#RUN (\d+)", content)
    return max((int(m) for m in matches), default=0) + 1


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def p(msg: str = "") -> None:
    """print + flush，确保终端能实时看到"""
    print(msg, flush=True)


async def step_news(run_no: int, prompt_ref: str) -> list:
    """Step 1-2: 拉取 → 去重 → 预处理"""
    from src.news.factory import fetch_all_news
    from src.news.dedup import DedupStore
    from src.news.preprocessor import preprocess

    p("=" * 60)
    p(f"[RUN #{run_no}] Step 1: 拉取新闻")
    p("=" * 60)

    raw_news = await fetch_all_news()
    p(f"  拉取到 {len(raw_news)} 条原始新闻")

    with tempfile.TemporaryDirectory() as tmp:
        dedup = DedupStore(path=Path(tmp) / "test_seen.json")
        new_news = dedup.filter_new(raw_news)
        p(f"  去重后 {len(new_news)} 条新新闻")

    p(f"\n[RUN #{run_no}] Step 2: 预处理 (分类/情绪/关键词/预筛选)")
    worth = preprocess(new_news)
    p(f"  预处理: {len(new_news)} → {len(worth)} 条值得分析")

    # 终端打印摘要
    for i, n in enumerate(worth[:8], 1):
        tag = f"[{n.source}][{n.category.value}][{n.sentiment.value}]"
        stocks = " | " + ",".join(s.get("name", "") for s in n.related_stocks) if n.related_stocks else ""
        kws = " | KW=" + ",".join(n.keywords) if n.keywords else ""
        p(f"    {i}. {tag} {n.title[:45]}{kws}{stocks}")
    if len(worth) > 8:
        p(f"    ... 还有 {len(worth) - 8} 条")

    # 追加写入文件
    lines = []
    lines.append(f"\n\n{'#' * 80}")
    lines.append(f"#RUN {run_no} | 时间: {datetime.now():%Y-%m-%d %H:%M:%S} | 关联提示词: {prompt_ref}")
    lines.append(f"# 原始: {len(raw_news)} 条 | 去重后: {len(new_news)} 条 | 预筛选通过: {len(worth)} 条")
    lines.append(f"{'#' * 80}")

    lines.append(f"\n--- 全部原始新闻 ({len(new_news)} 条) ---\n")
    for i, n in enumerate(new_news, 1):
        lines.append(f"[{i}] {n.pub_time:%H:%M:%S} [{n.source}] ID={n.news_id}")
        lines.append(f"    {n.content[:200]}")
        lines.append(f"    分类={n.category.value} 情绪={n.sentiment.value} 重要性={n.importance}")
        if n.raw_tags:
            lines.append(f"    标签={n.raw_tags}")
        if n.keywords:
            lines.append(f"    关键词={n.keywords}")
        if n.related_stocks:
            lines.append(f"    关联={n.related_stocks}")
        lines.append("")

    lines.append(f"\n--- 预筛选通过 ({len(worth)} 条) → 送 LLM ---\n")
    for i, n in enumerate(worth, 1):
        lines.append(f"[{i}] {n.pub_time:%H:%M:%S} [{n.source}][{n.category.value}][{n.sentiment.value}]")
        lines.append(f"    {n.content[:200]}")
        if n.keywords:
            lines.append(f"    关键词={n.keywords}")
        if n.related_stocks:
            stock_tags = ["{0}({1})".format(s.get("name", ""), s.get("code", "")) for s in n.related_stocks]
            lines.append(f"    关联={stock_tags}")
        lines.append("")

    _append(NEWS_RESULT, "\n".join(lines))
    p(f"\n  >> 追加到: {NEWS_RESULT}")
    return worth


async def step_llm(worth_news: list, run_no: int, prompt_ref: str) -> None:
    """Step 3: 调用 LLM 深度分析"""
    from src.analyzer.llm_analyzer import analyze_news, _build_news_block, _load_prompt
    from src.llm_provider.factory import create_provider
    from src.llm_provider.base import ChatMessage
    from src.config import get

    p(f"\n{'=' * 60}")
    p(f"[RUN #{run_no}] Step 3: LLM 深度分析")
    p("=" * 60)

    if not worth_news:
        p("  没有值得分析的新闻，跳过 LLM")
        return

    llm_cfg = get("llm") or {}
    provider_name = llm_cfg.get("active_provider", "bailian")
    model = llm_cfg.get("providers", {}).get(provider_name, {}).get("model", "?")
    p(f"  Provider: {provider_name} | 模型: {model} | 输入: {len(worth_news)} 条新闻")

    system_prompt = _load_prompt("analyze_system.txt")
    user_template = _load_prompt("analyze_user.txt")
    news_block = _build_news_block(worth_news)
    user_prompt = user_template.format(count=len(worth_news), news_block=news_block)

    lines = []
    lines.append(f"\n\n{'#' * 80}")
    lines.append(f"#RUN {run_no} | 时间: {datetime.now():%Y-%m-%d %H:%M:%S} | 关联提示词: {prompt_ref}")
    lines.append(f"# Provider: {provider_name} | Model: {model}")
    lines.append(f"{'#' * 80}")

    lines.append(f"\n--- System Prompt ---\n{system_prompt}")
    lines.append(f"\n--- User Prompt ---\n{user_prompt}")

    p(f"\n  正在调用 LLM ...")
    try:
        from src.analyzer.llm_analyzer import _parse_response
        provider = create_provider()
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ]
        resp = await provider.chat(
            messages=messages,
            temperature=llm_cfg.get("temperature", 0.3),
            max_tokens=llm_cfg.get("max_tokens", 4000),
        )

        p(f"  LLM 调用成功! 模型={resp.model}")
        if resp.usage:
            p(f"  Token: prompt={resp.usage.get('prompt_tokens')} + completion={resp.usage.get('completion_tokens')} = {resp.usage.get('total_tokens')}")

        lines.append(f"\n--- LLM 原始返回 ---\n{resp.content}")
        lines.append(f"\n模型: {resp.model}")
        if resp.usage:
            lines.append(f"Token: {resp.usage}")

        targets = _parse_response(resp.content)

        etfs = [t for t in targets if t.target_type.value == "etf"]
        stocks = [t for t in targets if t.target_type.value == "stock"]

        lines.append(f"\n--- 解析结果: {len(etfs)} 个ETF + {len(stocks)} 个个股 ---\n")
        p(f"\n  解析得出 {len(etfs)} 个板块ETF + {len(stocks)} 个深度个股:")

        if etfs:
            p(f"\n  [板块/ETF 概览]")
            lines.append("  [板块/ETF 概览]")
            for t in etfs:
                p(f"    {t.name}({t.code}) 评分={t.score} | {t.reason}")
                lines.append(f"    {t.name}({t.code}) 评分={t.score}")
                lines.append(f"      原因: {t.reason}")
                if t.logic:
                    lines.append(f"      逻辑: {t.logic}")
                if t.related_news:
                    lines.append(f"      关联新闻: {t.related_news}")
                lines.append("")

        if stocks:
            p(f"\n  [具体个股 深度分析]")
            lines.append("  [具体个股 深度分析]")
            for t in stocks:
                chain_tag = f" [{t.industry_chain}]" if t.industry_chain else ""
                trade_tag = "[可买]" if t.tradable else "[" + t.tradable_note + "]"
                p(f"    {trade_tag} {t.name}({t.code}) [{t.board.value}]{chain_tag} 评分={t.score}")
                p(f"      原因: {t.reason}")
                if t.logic:
                    p(f"      逻辑: {t.logic[:120]}...")
                lines.append(f"    {trade_tag} {t.name}({t.code}) [{t.board.value}]{chain_tag} 评分={t.score}")
                lines.append(f"      原因: {t.reason}")
                if t.industry_chain:
                    lines.append(f"      产业链: {t.industry_chain}")
                if t.logic:
                    lines.append(f"      逻辑: {t.logic}")
                if t.related_news:
                    lines.append(f"      关联新闻: {t.related_news}")
                lines.append("")

    except Exception as e:
        p(f"\n  LLM 调用失败: {e}")
        lines.append(f"\n--- LLM 调用失败 ---\n{e}")
        import traceback
        lines.append(traceback.format_exc())

    _append(LLM_RESULT, "\n".join(lines))
    p(f"\n  >> 追加到: {LLM_RESULT}")


async def main():
    import logging

    LOG_DIR = ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"test_{datetime.now():%Y%m%d_%H%M%S}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    logging.info("日志文件: %s", log_file)

    from src.config import load_config
    load_config(force_reload=True)

    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    run_no = max(_next_run_no(NEWS_RESULT), _next_run_no(LLM_RESULT))
    prompt_ref = sys.argv[1] if len(sys.argv) > 1 else "prompts.md#7"

    p(f"\n{'=' * 60}")
    p(f"  Stock Flash 分段测试  #RUN {run_no}")
    p(f"  关联提示词: {prompt_ref}")
    p(f"  时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    p(f"{'=' * 60}")

    worth = await step_news(run_no, prompt_ref)
    await step_llm(worth, run_no, prompt_ref)

    p(f"\n{'=' * 60}")
    p(f"  RUN #{run_no} 完成!")
    p(f"  新闻结果: {NEWS_RESULT}")
    p(f"  LLM结果:  {LLM_RESULT}")
    p(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
