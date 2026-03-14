"""分段测试筛选器：从 result/llm_result.txt 读取最近一次 LLM 分析结果，
逐个筛选器独立测试，输出详细结果到 result/filter_result.txt + 终端。

用法:
    python tests/test_filter_step.py                  # 使用最新一次 LLM 结果
    python tests/test_filter_step.py --run 3          # 指定 RUN #3 的结果
    python tests/test_filter_step.py --codes 601857,601808  # 直接指定股票代码
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULT_DIR = ROOT / "result"
LLM_RESULT = RESULT_DIR / "llm_result.txt"
FILTER_RESULT = RESULT_DIR / "filter_result.txt"

# 结果文件字段名：英文 -> 中文/中英，便于阅读
RESULT_LABELS = {
    "change_1d_pct": "涨跌幅(1日)%",
    "change_5d_pct": "涨跌幅(5日)%",
    "up_days_in_5": "近5日收阳天数",
    "current_price": "当前价",
    "max_price": "价格上限",
    "volume_ratio": "量比",
    "turnover_rate": "换手率%",
    "profit_ratio": "筹码获利比例%",
    "ma5": "MA5",
    "ma10": "MA10",
    "ma20": "MA20",
    "last_close": "最新收盘",
    "pe": "市盈率PE",
    "pb": "市净率PB",
    "roe": "净资产收益率ROE%",
    "debt_ratio": "资产负债率%",
    "revenue_growth": "营收同比增长%",
    "market_cap_yi": "总市值(亿)",
    "report_period": "财报期",
    "detected_board": "检测板块",
    "allowed_boards": "允许板块",
    "tradable": "可交易",
    "tradable_note": "交易门槛说明",
    "board": "板块",
    "board_note": "板块说明",
    "checks": "检查项",
    "core_pass": "核心通过",
    "verdict": "结论",
    "skip": "跳过原因",
    "institutions": "机构持仓",
    "institution_count": "机构家数",
    "period": "报告期",
    "kline_note": "K线说明",
    "chip": "筹码分布",
    "chip_profit_pct": "筹码获利%",
    "龙虎榜": "龙虎榜(近期上榜)",
    "lhb_recent": "近期上榜",
    "lhb_dates": "上榜日期",
}


def p(msg: str = "") -> None:
    print(msg, flush=True)


def _extract_targets_from_llm_result(run_no: int | None = None) -> list:
    """从 llm_result.txt 中解析标的"""
    from src.analyzer.llm_analyzer import _parse_response

    if not LLM_RESULT.exists():
        p(f"  [ERROR] {LLM_RESULT} 不存在")
        return []

    content = LLM_RESULT.read_text(encoding="utf-8")

    if run_no:
        pattern = rf"#RUN {run_no}.*?(?=#RUN |\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            p(f"  [ERROR] 未找到 RUN #{run_no}")
            return []
        block = match.group()
    else:
        runs = list(re.finditer(r"#RUN (\d+)", content))
        if not runs:
            p("  [ERROR] llm_result.txt 中无 RUN 记录")
            return []
        last_match = runs[-1]
        run_no = int(last_match.group(1))
        block = content[last_match.start():]

    p(f"  从 RUN #{run_no} 解析标的...")
    json_match = re.search(r"--- LLM 原始返回 ---\n(.*?)(?=\n模型:|\n---|\Z)", block, re.DOTALL)
    if not json_match:
        p("  [ERROR] 未找到 LLM 原始返回")
        return []

    raw_json = json_match.group(1).strip()
    targets = _parse_response(raw_json)
    return targets


def _build_targets_from_codes(codes: list[str]) -> list:
    """根据代码直接构建 StockTarget"""
    from src.models.stock import BoardType, StockTarget, TargetType

    targets = []
    for code in codes:
        code = code.strip().zfill(6)
        if code.startswith(("15", "16", "51")):
            tt = TargetType.ETF
            board = BoardType.MAIN
        elif code.startswith(("60", "00")):
            tt = TargetType.STOCK
            board = BoardType.MAIN
        elif code.startswith("30"):
            tt = TargetType.STOCK
            board = BoardType.GEM
        elif code.startswith("68"):
            tt = TargetType.STOCK
            board = BoardType.STAR
        else:
            tt = TargetType.STOCK
            board = BoardType.BSE
        targets.append(StockTarget(
            code=code, name=f"手动({code})", board=board,
            target_type=tt, score=70,
        ))
    return targets


def _next_run_no(path: Path) -> int:
    if not path.exists():
        return 1
    content = path.read_text(encoding="utf-8")
    matches = re.findall(r"#RUN (\d+)", content)
    return max((int(m) for m in matches), default=0) + 1


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


async def run_filter_tests(targets: list, run_no: int) -> None:
    """对每个标的逐个运行所有筛选器（不短路），输出每个维度的详细结果"""
    from src.filters.factory import _ensure_builtins, _REGISTRY
    from src.config import get

    _ensure_builtins()
    filters_cfg = get("filters") or {}

    filter_names = [
        name for name, cfg in filters_cfg.items()
        if isinstance(cfg, dict) and cfg.get("enabled", False)
    ]

    filter_instances = []
    for name in filter_names:
        cls = _REGISTRY.get(name)
        if cls:
            filter_instances.append((name, cls()))
        else:
            p(f"  [WARN] 筛选器 {name} 未注册")

    p(f"\n  筛选器链({len(filter_instances)}个): {' -> '.join(n for n, _ in filter_instances)}")
    p(f"  待筛选标的: {len(targets)} 个")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append(f"\n\n{'#' * 80}")
    lines.append(f"#RUN {run_no} | 执行时间: {ts} (yyyy-MM-dd HH:mm:ss)")
    lines.append(f"# 筛选器: {' -> '.join(n for n, _ in filter_instances)}")
    lines.append(f"# 标的数: {len(targets)}")
    lines.append(f"{'#' * 80}")

    summary: list[dict] = []

    for i, stock in enumerate(targets, 1):
        trade_tag = "[可买]" if stock.tradable else f"[{stock.tradable_note}]"
        header = f"\n{'=' * 60}\n[{i}/{len(targets)}] {trade_tag} {stock.name}({stock.code}) [{stock.board.value}] 评分={stock.score}\n{'=' * 60}"
        p(header)
        lines.append(header)

        stock_summary = {"name": stock.name, "code": stock.code, "filters": {}}

        for fname, fobj in filter_instances:
            p(f"\n  --- {fname} ---")
            lines.append(f"\n  --- {fname} ---")
            try:
                result = await fobj.apply(stock)
                passed = result.is_passed
                icon = "通过" if passed else "未通过"
                p(f"  结果: [{icon}]")
                lines.append(f"  结果: [{icon}]")

                det = result.details.get(fname, result.details)
                if isinstance(det, dict):
                    if fname == "anomaly_filter" and "change_1d_pct" in det:
                        lines.append("  说明: 涨跌幅(1日)=当日涨跌%, 涨跌幅(5日)=近5日涨跌%, 收阳天数=近5日收盘上涨天数")
                    for k, v in det.items():
                        label = RESULT_LABELS.get(k, k)
                        if k == "checks":
                            p(f"  检查项:")
                            lines.append(f"  检查项:")
                            for ck, cv in v.items():
                                mark = "OK" if cv else "X"
                                ck_label = RESULT_LABELS.get(ck, ck)
                                p(f"    [{mark}] {ck_label}")
                                lines.append(f"    [{mark}] {ck_label}")
                        elif k == "fundamentals":
                            continue
                        elif isinstance(v, dict) and len(str(v)) > 100:
                            p(f"  {label}: (详见文件)")
                            lines.append(f"  {label}: {json.dumps(v, ensure_ascii=False, default=str)}")
                        else:
                            p(f"  {label}: {v}")
                            lines.append(f"  {label}: {v}")

                stock_summary["filters"][fname] = passed

            except Exception as e:
                p(f"  [ERROR] {fname}: {e}")
                lines.append(f"  [ERROR] {fname}: {e}")
                import traceback
                lines.append(traceback.format_exc())
                stock_summary["filters"][fname] = False

        all_pass = all(stock_summary["filters"].values())
        final = "[全部通过]" if all_pass else "[未通过]"
        blocked_by = [k for k, v in stock_summary["filters"].items() if not v]
        verdict_line = f"\n  >> {final}"
        if blocked_by:
            verdict_line += f" 被拦截: {', '.join(blocked_by)}"
        p(verdict_line)
        lines.append(verdict_line)
        stock_summary["final"] = all_pass
        summary.append(stock_summary)

    p(f"\n\n{'=' * 60}")
    p(f"  筛选汇总 (RUN #{run_no})")
    p(f"{'=' * 60}")
    lines.append(f"\n\n{'=' * 60}")
    lines.append(f"  筛选汇总")
    lines.append(f"{'=' * 60}")

    passed_list = [s for s in summary if s["final"]]
    failed_list = [s for s in summary if not s["final"]]

    p(f"\n  通过: {len(passed_list)}/{len(summary)}")
    lines.append(f"\n  通过: {len(passed_list)}/{len(summary)}")
    for s in passed_list:
        p(f"    [PASS] {s['name']}({s['code']})")
        lines.append(f"    [PASS] {s['name']}({s['code']})")

    if failed_list:
        p(f"\n  未通过: {len(failed_list)}/{len(summary)}")
        lines.append(f"\n  未通过: {len(failed_list)}/{len(summary)}")
        for s in failed_list:
            blocked = [k for k, v in s["filters"].items() if not v]
            p(f"    [FAIL] {s['name']}({s['code']}) <- {', '.join(blocked)}")
            lines.append(f"    [FAIL] {s['name']}({s['code']}) <- {', '.join(blocked)}")

    for fname, _ in filter_instances:
        pass_count = sum(1 for s in summary if s["filters"].get(fname, False))
        p(f"    {fname}: {pass_count}/{len(summary)} 通过")
        lines.append(f"    {fname}: {pass_count}/{len(summary)} 通过")
    lines.append("")
    lines.append(f"执行时间: {ts} (yyyy-MM-dd HH:mm:ss)")

    _append(FILTER_RESULT, "\n".join(lines))
    p(f"\n  >> 结果追加到: {FILTER_RESULT}")


async def main():
    import logging

    LOG_DIR = ROOT / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"filter_{datetime.now():%Y%m%d_%H%M%S}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    from src.config import load_config
    load_config(force_reload=True)

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    run_no = _next_run_no(FILTER_RESULT)

    p(f"\n{'=' * 60}")
    p(f"  Stock Flash 筛选器分段测试  #RUN {run_no}")
    p(f"  时间: {datetime.now():%Y-%m-%d %H:%M:%S}")
    p(f"{'=' * 60}")

    args = sys.argv[1:]
    targets = []

    if "--codes" in args:
        idx = args.index("--codes")
        codes = args[idx + 1].split(",") if idx + 1 < len(args) else []
        targets = _build_targets_from_codes(codes)
        p(f"  模式: 手动指定代码 ({len(targets)} 个)")
    else:
        specified_run = None
        if "--run" in args:
            idx = args.index("--run")
            specified_run = int(args[idx + 1]) if idx + 1 < len(args) else None
        targets = _extract_targets_from_llm_result(specified_run)
        p(f"  模式: 读取 LLM 结果 ({len(targets)} 个标的)")

    if not targets:
        p("  无标的可测试!")
        return

    for i, t in enumerate(targets, 1):
        tag = "[可买]" if t.tradable else f"[{t.tradable_note}]"
        p(f"  {i}. {tag} {t.name}({t.code}) [{t.board.value}] 评分={t.score}")

    await run_filter_tests(targets, run_no)

    p(f"\n{'=' * 60}")
    p(f"  RUN #{run_no} 完成!")
    p(f"  筛选结果: {FILTER_RESULT}")
    p(f"  日志文件: {log_file}")
    p(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
