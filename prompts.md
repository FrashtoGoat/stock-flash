# Stock Flash 提示词记录

> 本文件专门记录项目中用到的所有提示词（Prompt），包括 LLM 调用、用户与 AI 交互的指令等。
> 每次新增或修改提示词时，必须同步更新此文件。

---

## 目录

1. [LLM 分析利好标的 - System Prompt](#1-llm-分析利好标的---system-prompt)
2. [LLM 分析利好标的 - User Prompt 模板](#2-llm-分析利好标的---user-prompt-模板)
3. [用户需求提示词记录](#3-用户需求提示词记录)

---

## 1. LLM 分析利好标的 - System Prompt

**文件**: `src/analyzer/llm_analyzer.py` → `SYSTEM_PROMPT`

```text
你是一位专业的A股投资分析师。你的任务是根据提供的财经新闻快讯，分析哪些A股股票可能受到利好影响。

请严格按照以下JSON格式返回结果（不要包含其他文字）：
{
  "targets": [
    {
      "code": "股票代码(6位数字)",
      "name": "股票名称",
      "board": "main/gem/star/bse",
      "reason": "利好原因简述",
      "score": 0-100的评分
    }
  ]
}

评分标准：
- 90-100: 直接重大利好，如政策直接受益、重大订单
- 70-89: 间接利好，如行业景气度提升
- 50-69: 概念相关，关联度一般
- 50以下: 关联度较弱

注意：
1. 只返回确定性较高的标的，宁缺毋滥
2. board 字段: 60开头=main, 300开头=gem, 688开头=star, 8/4开头=bse
3. 如果没有明确利好标的，返回空 targets 列表
```

**优化方向**:
- 增加 few-shot 示例提高输出质量
- 增加股票代码校验（验证代码是否真实存在）
- 考虑加入情绪分析，判断新闻正负面

---

## 2. LLM 分析利好标的 - User Prompt 模板

**文件**: `src/analyzer/llm_analyzer.py` → `_build_user_prompt()`

```text
以下是最新财经快讯，请分析利好的A股标的：

1. [09:30] xxx新闻内容 [关键词: 半导体, AI]
2. [09:35] yyy新闻内容
...
```

---

## 3. 用户需求提示词记录

每次用户提出的需求/指令，按时间倒序记录。

### 2026-03-15 需求 #14

**原始提示词**（摘要）:
> 1 将计算的结果统一放到 result 文件夹包括 data/trades/trade_20260314_231201.json，然后按照日期分组  
> 2 这是模拟交易？我要的是对接真实的模拟账户，给我推荐一个好用的模拟账号

**执行结果**:
- **结果统一 + 按日期分组**：交易记录 JSON 改为写入 **`result/trades/YYYY-MM-DD/`**（不再使用 `data/trades/`）；回测从 `result/trades/*/*.json` 读取。新增一次性迁移：首次执行时把 `data/trades/` 下已有 `trade_*.json` 按文件名日期迁移到 `result/trades/对应日期/`。README 增加「计算结果与输出」小节。
- **模拟交易 vs 真实模拟账户**：当前「模拟交易」(mode=simulated) 仅为本地落 JSON+DB，不连券商。README 增加「模拟交易 vs 真实模拟账户」小节，说明对接真实模拟账户需在 PaperExecutor 内接券商模拟盘 API，并推荐：**东方财富模拟炒股**、**券商+QMT/miniQMT 模拟**、**同花顺模拟炒股**，建议先跑通策略再选其一对接。

---

### 2026-03-15 需求 #13

**原始提示词**（摘要，脱敏）:
> 1 时间记录用东八区时间（上海）；实盘这里包括模拟盘吗，需要先对接模拟操作让整个操作闭环（真实下单先不实现）；SQLite 还没下载，Windows 帮忙下载到 D 盘 Program Files
> 2 按 README 后续规划开始做：数据库存储、止盈止损、回测、实盘预留；模拟交易接口快实现
> 3 去掉 SQLite 下载文档（Python 自带即可）；东八区是想说现在是北京时间 23:03 别搞错时间；模拟盘接口快实现
> 4 README：能跑通整个流程了吗；回测是干嘛的、要每天跑定时器吗 → 补充常见问题
> 5 prompts 文件最近怎么不更新了；想跑通整个流程，检查缺什么，没问题开始跑

**执行结果**:
- **东八区时间**：todolist 顶部「最后更新」及记录时间统一为东八区/北京时间（例：2026-03-15 23:03）。
- **实盘与模拟盘**：实盘不含模拟盘；规划为先对接**模拟盘**（券商仿真）形成闭环，实盘暂不实现。README/todolist 已区分「模拟盘交易」「实盘交易」。
- **SQLite**：去掉 README 中下载/安装说明，仅保留「Python 自带 sqlite3，无需单独安装」；脚本 `scripts/install_sqlite_tools.ps1` 保留供可选使用。
- **后续规划落地**：数据库（SQLite+SQLAlchemy、trades 表、storage.enabled）、止盈止损（position_manager+配置+流水线末尾检查）、回测（run.py --backtest）、模拟盘接口（PaperExecutor，mode=paper 落 JSON+DB）。
- **模拟盘接口**：新增 `PaperExecutor`，`trading.mode: paper` 时使用，当前与 Simulated 同样落库，后续接券商模拟盘 API。
- **README 常见问题**：补充「能跑通吗」「回测是干嘛的」「回测要每天定时吗」三条。
- **prompts 更新**：本条目为补记；规则要求每次需求均记录，后续会持续更新。
- **跑通检查与执行**：配置检查通过（LLM=bailian、email 开启）；执行 `python run.py --test`，Step 1～8 全部完成：测试新闻 3 条 → 预处理 → LLM 4 个标的 → 链式筛选 4/4 通过 → 大盘判断（实时接口断开时已用最近交易日 2026-03-13 数据）→ 邮件发送成功 → 模拟交易 4 笔落 JSON+DB，耗时约 51 秒。**结论：当前无缺项，整条流程可跑通。**

---

### 2026-03-13 需求 #12

**原始提示词**:
> 1 todolist 这里只有新闻处理流程，全程的呢
> 2 result/filter_result.txt 结果加上时间 yyyy-MM-dd HH:mm:ss；change_1d_pct/change_5d_pct 是什么意思；尽量用中文或者中英
> 3 机构筛选 龙虎榜有吗也加上
> 4 接下来是通知模块，能个微通知吗，企微会不会比较麻烦

**执行结果**:
- **完整流水线**：在 todolist 中新增「完整流水线（全程）」图，包含 Step1~8（拉取→去重→预处理→LLM利好利空→链式筛选→大盘判断→通知→交易），新闻处理流程保留为 Step3 明细。
- **filter_result 输出**：
  - 每 RUN 增加「执行时间: yyyy-MM-dd HH:mm:ss」；汇总末尾再次输出该时间。
  - 字段名改为中文/中英（RESULT_LABELS 映射），如 涨跌幅(1日)%、涨跌幅(5日)%、近5日收阳天数、当前价、量比、市盈率PE 等。
  - 异动筛选块增加说明行：「涨跌幅(1日)=当日涨跌%, 涨跌幅(5日)=近5日涨跌%, 收阳天数=近5日收盘上涨天数」。
  - 结果/结论用「通过」「未通过」「全部通过」。
- **龙虎榜**：机构筛选器增加 龙虎榜 检测（akshare `stock_lhb_stock_detail_date_em`），输出 近期是否上榜、上榜日期列表（默认近10日），details 中增加「龙虎榜」节点；配置项 `lhb_recent_days`。
- **微信通知**：
  - **企微**：群机器人 webhook（不麻烦：群设置→添加机器人→复制 webhook），`notification.wechat.enabled` + `webhook_url`，POST 文本消息。
  - **个微**：PushPlus（pushplus.plus 绑定微信获取 token），`notification.pushplus.enabled` + `token`，POST 标题+内容；.env 可选 `PUSHPLUS_TOKEN`。
  - 通知入口依次调用：邮件 → 企微 webhook → PushPlus。

---

### 2026-03-12 需求 #11

**原始提示词**:
> 1 当我说提交的时候才提交
> 2 筛选器包括但不限于当前的内容，你觉得有更好的也可以提供
> 3 分段测试筛选器，拿result里面的结果测试

**执行结果**:
- 确认提交规则：只在用户说"提交"时才执行 git commit+push
- **新增 anomaly_filter** (异动监控)：
  - 5日涨跌幅范围(-15%~25%)，排除暴涨暴跌
  - 当日涨跌幅范围(-7%~9.5%)，排除涨停/跌停接盘
  - 近5日至少2天收阳，确保资金连续性
- **新增 institution_filter** (机构/聪明资金)：
  - 十大股东中检测基金/社保/证金/汇金/QFII等机构持仓
  - 使用新浪 `stock_main_stock_holder` 接口（修复了原 stock_gdfx 参数错误）
- **修复 master_filter** 数据源：
  - PE/PB: 改用 `stock_zh_valuation_baidu`（百度估值接口，原 stock_individual_info_em 无此数据）
  - ROE/资产负债率/营收增长: 改用 `stock_financial_abstract_ths`（同花顺财报摘要）
  - 修复前：PE/PB/ROE 全部 nan → 修复后：中国石油 PE=14.13/PB=1.44/ROE=11.1%
- **修复 chip_profit 百分比**：akshare 返回 0-1 范围，筛选阈值是 0-100，增加自动转换
- **新建 test_filter_step.py** (筛选器分段测试)：
  - 从 `result/llm_result.txt` 解析最近一次 LLM 结果
  - 支持 `--run N` 指定 RUN 轮次，`--codes 601857,601808` 直接指定代码
  - 逐个筛选器独立测试（不短路），输出每个检查项 OK/X 详情
  - 结果追加到 `result/filter_result.txt`
- 筛选链: board → affordability → anomaly → master → institution → technical (6个)
- **实测结果 (RUN #2)**:
  - 石油ETF(160216): ALL PASS (ETF跳过个股筛选)
  - 中国石油(601857): 5/6通过，被 technical_filter 拦截(均线非多头+量比偏低)
  - 中海油服(601808): 5/6通过，被 technical_filter 拦截(均线非多头+量比偏低)
  - 中国海油(600938): **ALL PASS** — PE=16.58/PB=2.6/ROE=19.36%/均线多头/MACD水上

---

### 2026-03-12 需求 #10

**原始提示词**:
> 1 前面是筛选利好的，再加一个利空的（只要包括对大盘和行业的影响即可）
> 2 筛选器的实现，其中大师选股是指基本面包括财报、龙头、市占率高等等（即使被套了也有翻身机会）
> 2.2 我能买的，包括价格不要太高低于100元，沪深
> 2.3 技术选型 包括但不限于：获取实时行情（量比、换手率）通过 DataFetcherManager 自动故障切换；获取筹码分布 带熔断保护；进行趋势分析（基于交易理念）

**执行结果**:
- **利空分析**:
  - 新增 `config/prompts/bearish_system.txt` + `bearish_user.txt` — 利空 Prompt
  - 新增 `src/analyzer/bearish_analyzer.py` — 解析大盘影响 + 行业风险
  - 新增模型: `RiskLevel`, `RiskDuration`, `MarketImpact`, `IndustryRisk`, `BearishAnalysis`
  - 主流水线 Step 4 改为利好+利空并行调用 `asyncio.gather`
  - 测试脚本输出 `result/bearish_result.txt`
- **大师选股重写** (`master_filter.py`):
  - 5维筛选: 盈利(ROE)、估值(PE/PB)、成长(营收增长)、财务健康(资产负债率)、龙头(市值)
  - 核心三项(盈利+估值+财务)必过，成长/龙头为加分项
  - ETF 跳过基本面筛选
- **新增可买筛选器** (`affordability_filter.py`):
  - 股价 < 100 元
  - 板块权限: 沪深主板 或 ETF
- **技术选股重写** (`technical_filter.py`):
  - 实时行情: 量比(0.8-5)、换手率(1-15%)
  - 筹码分布: 获利比例(>30%)、集中度
  - 趋势分析: 均线多头(MA5>MA10>MA20)、价格站上MA20、MACD水上/金叉、量能趋势
- **DataFetcherManager** (`src/data/fetcher_manager.py`):
  - 多数据源自动故障切换
  - CircuitBreaker 熔断保护(3次失败→60秒冷却)
  - 统一接口: `get_kline`, `get_realtime_quote`, `get_chip_distribution`
- 筛选链顺序: board(标注) → affordability(可买) → master(基本面) → technical(技术)
- 32 个原有测试全部通过

---

### 2026-03-11 需求 #9

**原始提示词**:
> 1 新建logs文件夹，后续写测试案例，日志写进去，现在的就不用了
> 2 推荐的个股不要求是沪深两市主板（还是要A股的，因为除了主板其他我资质不够）的但是要标注，起码让我知道你是能分析出来的
> 3 这个问题结束后帮我提交代码到github，后续我只要说提交你就帮我提交

**执行结果**:
- 新建 `logs/` 目录 + `.gitkeep`，测试脚本日志同时写 terminal + `logs/test_YYYYMMDD_HHMMSS.log`
- `.gitignore` 更新：`logs/*` + `!logs/.gitkeep`
- `StockTarget` 新增 `tradable`(property) 和 `tradable_note`(property)，自动根据 board 计算可交易性
- Prompt 更新：明确指示 LLM 标注所有板块(main/gem/star/bse)，不限主板
- `board_filter` 改为标注模式（不过滤非主板标的，只记录 details 中的 tradable/tradable_note）
- 测试输出和主流水线日志均显示 `[可买]` / `[需开通创业板权限]` 等标注
- `todolist_skill.md` 新增"提交规则"
- 首次 git commit + push 到 GitHub

---

### 2026-03-11 需求 #8

**原始提示词**:
> env文件和config文件夹以及setting的关系，有必要吗分析下
> 基本ETF可以保留，我是说可以更加深入

**执行结果**:
- 分析 .env / settings.yaml / config.py 三者关系，结论：都有必要
  - `.env` → 密钥（安全隔离，不进 git）
  - `settings.yaml` → 结构化业务配置（YAML 嵌套/列表，比 KEY=VALUE 强大）
  - `config.py` → 桥接（load_dotenv → 读 YAML → 替换 `${}` → 缓存）
- 优化：`_resolve_env` 新增 `${VAR:default}` 语法，非密钥值可在 YAML 写默认值
- 清理：`ZHIPU_BASE_URL` 从 .env 移到 settings.yaml 作为默认值
- ETF 保留 + 深度个股两层分析：
  - `StockTarget` 新增 `target_type` 字段（stock/etf/index）
  - Prompt 改为两层输出：先板块ETF概览，再具体个股深挖
  - 解析器移除 ETF 过滤，改为自动识别类型
- 实测 RUN #3: 1 ETF(石油ETF) + 3 个股(中国石油/中海油服/中国海油)，1935 tokens

---

### 2026-03-11 需求 #7

**原始提示词**:
> 1 以后测试和执行能启动终端让我看到执行过程吗
> 2 这个新闻关联新闻id很不错，还有可以优化的地方，比如已经判断出来对石油利好，但还挖掘不够深，比如究竟是利好具体石油哪个过程，哪些公司等等我需要具体分析
> 3 *_result.txt后续执行不要覆盖追加，标注好第几次测试和关联提示词

**执行结果**:
- 终端可见执行：测试脚本改为后台启动，print+flush 实时输出
- LLM 深度分析 Prompt 重写：
  - 禁止返回 ETF/基金代码(15xxxx/16xxxx)，要求具体个股
  - 要求挖掘产业链位置（上游/中游/下游）
  - 要求给出完整传导逻辑（新闻→行业→公司）
  - `StockTarget` 模型新增 `industry_chain` 和 `logic` 字段
  - 解析器增加 ETF 代码过滤
- result 文件追加模式：
  - 每次运行追加到文件末尾，带 `#RUN N` 轮次标记
  - 标注关联提示词（如 `prompts.md#7`），命令行可传参
  - 自动从文件历史中计算下一轮次号
- 实测结果 (RUN #1)：
  - 中国海油(600938) 评分91 [上游原材料] — 量价齐升+资本开支1200亿
  - 中国石油(601857) 评分88 [上游原材料] — 全产业链巨头，炼油价差修复
  - 中海油服(601808) 评分85 [中游制造] — 海上油服龙头，日费率上涨12-18%
- Token: prompt=1644 + completion=874 = 2518 tokens
- `max_tokens` 从 2000 提升到 4000（深度分析需要更多输出空间）
- 39 个原有测试全部通过

---

### 2026-03-11 需求 #6

**原始提示词**:
> 分段测试 · 前面新闻接口的接口的结果简单输出的result文件夹的new_result.txt，然后开始测试大模型的接入使用效果

**执行结果**:
- 添加 `python-dotenv` 依赖，`config.py` 自动加载 `.env` 文件
- 创建 `.env` 文件（含百炼 API Key `sk-****12f9`）
- 新建 `tests/test_pipeline_step.py`: 分段测试脚本
  - Step 1: 拉取→去重→预处理 → 输出到 `result/new_result.txt`
  - Step 2: 调用百炼 qwen-plus → 输出到 `result/llm_result.txt`
- 测试结果: 40条新闻→10条通过预筛选→LLM分析出3个标的
  - 石油ETF(160216) 评分75，原因: IEA释放石油储备+输油管道风险
  - AI ETF(159363) 评分70，原因: Anthropic研究强化AI变革认知
  - 投资ETF(159352) 评分65，原因: 海湾主权基金维持长期投资
- Token 消耗: prompt=1255 + completion=354 = 总计1609 tokens
- 39个原有测试全部通过

---

### 2026-03-11 需求 #5

**原始提示词**:
> 这些新闻的结构是怎样的？能够分类有情绪吗？我多次拉取如何识别是已经处理过的？
> 拉取之后如何筛选判断是否要采纳和调用大模型，以及对应的提示词如何组织

**执行结果**:
- 增强 `NewsItem` 模型: 新增 `news_id`(去重ID)、`category`(7种分类)、`sentiment`(正/负/中)、`url`、`raw_tags`、`related_stocks`
- 新建 `src/news/dedup.py`: 基于 news_id 的文件持久化去重（24h 自动过期）
- 改造 sina/eastmoney fetcher: 提取原始 `id`→news_id、`tag`→category、`ext.stocks`→related_stocks
- 新建 `src/news/preprocessor.py`: 分类(规则)→情绪(正负词计数)→关键词→预筛选(`should_analyze`)
- 预筛选逻辑: 有关联股票 / 有关键词且情绪非中性 / 重要性>=2 / 特定分类+关键词 → 通过
- Prompt 模板化: 移到 `config/prompts/` 目录，LLM 接收带分类/情绪/关联股票的结构化新闻
- pipeline 8 步: 拉取→去重→预处理→LLM→筛选→大盘→通知→交易
- 39 个测试全部通过

---

### 2026-03-11 需求 #4

**原始提示词**:
> 新建一个测试文件夹，开始测试从项目启动到调用新闻平台获取的结果

**执行结果**:
- 新建 `tests/` 目录，含 `conftest.py` / `test_config.py` / `test_news.py` / `test_extractor.py`
- 发现金十数据免费 API 已于 2025.12 停服（返回 502）
- 新增两个可用新闻源替代：`src/news/sina.py`（新浪财经）、`src/news/eastmoney.py`（东方财富）
- 配置文件中金十改为 `enabled: false`，新浪+东方财富启用
- 28 个测试全部通过，Step 1 完整流程验证：聚合拉取 40 条新闻 → 提取 6 条含关键词 → 筛选通过
- 已知问题记录：金十停服、终端中文乱码（编码问题不影响逻辑）

---

### 2026-03-11 需求 #3

**原始提示词**:
> 大模型帮我完成阿里百炼和智谱的对接（含 AutoDL 自部署支持）。
> 大模型应该放到单独的 llm_provider 文件夹。
> 提示词记得写上日期和注意隐私信息的记录。
>
> *(用户提供了百炼 API Key: sk-****12f9，AutoDL 账号: 132****0459/\*\*\*\* — 已脱敏，实际值存于 .env)*

**执行结果**:
- 新建 `src/llm_provider/` 目录，含 `base.py` / `factory.py` / `bailian.py` / `zhipu.py`
- 阿里百炼: DashScope OpenAI 兼容接口，`@register("bailian")`
- 智谱 AI: 支持官方 API + AutoDL 自部署端点，`@register("zhipu")`
- 重构 `src/analyzer/llm_analyzer.py`，不再直接使用 OpenAI 客户端，改用 provider 工厂
- 配置文件 `settings.yaml` 重构为 `llm.active_provider` + `llm.providers.*` 结构
- 密钥/密码全部走环境变量（`.env`），prompts.md 中脱敏记录
- `todolist_skill.md` 新增隐私信息记录规则

---

### 2026-03-11 需求 #2

**原始提示词**:
> main.py 里不要直接出现金十，通过接口调用，通过配置文件确定使用金十，其他调用也是，做到封装。
> 新建一个文件专门记录我每次的提示词，todolist_skill.md 记录这个规则，后面自觉记录，不需要我再提。

**执行结果**:
- 新建 `src/news/factory.py` 新闻源工厂（注册模式 + 配置驱动）
- 新建 `src/filters/factory.py` 筛选器工厂（注册模式 + 配置驱动）
- 重构 `src/main.py`，移除所有具体类直接引用
- 各实现类加 `@register` 装饰器自注册
- 新建本文件 `prompts.md` 专门记录提示词

### 2026-03-11 需求 #1

**原始提示词**:
> 这个项目要做的事情: 通过定时器或者启动启动命令调用主函数。主函数做的事情包括：
> 1 读取金十等新闻接口，提取新闻关键词；
> 2 调用大模型接口 分析利好标的，得到A股标的列表
> 3 筛选器 链式 3.1 筛选满足交易条件的，比如只要主板 3.2筛选满足大师选股的 3.3 满足技术选型的
> 4 有个todolist_skill.md便于检查开发进度和记录提示词
> 5 交易判断，是否满足交易 5.1 大盘情况判断 5.2 发送邮件或者其他方式通知我
> 6 如果得到肯定，调用交易接口（先是模拟交易）

**执行结果**:
- 完整项目从零搭建，包含 6 步流水线
- 新闻模块、LLM分析、链式筛选、大盘判断、通知、模拟交易
- 定时调度 + CLI 入口
