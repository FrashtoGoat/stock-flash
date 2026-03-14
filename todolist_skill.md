# Stock Flash 开发清单与进度

> **文档分工**：总览与快速上手见 [README.md](README.md)；本文档为开发清单与进度，含待完善项、后续模块说明与选型。**重要：清单与选型相关更新须记录时间。**  
> **时间约定**：所有时间记录均为**东八区（上海）时间**。  
> **最后更新**：2026-03-15 23:03（东八区/北京时间）

---

## 项目概述

通过定时器或命令触发，自动完成：新闻抓取 → 去重 → 预处理(分类/情绪/筛选) → LLM分析 → 链式筛选 → 大盘判断 → 通知 → 模拟交易

---

## 开发规则

> **提示词记录规则**: 每次用户提出的需求/指令，必须记录到 `prompts.md` 文件中，包含原始提示词和执行结果。此规则自动执行，无需用户提醒。

> **封装规则**: `main.py` 不直接引用任何具体实现类，所有组件通过工厂模式 + 配置文件驱动创建。新增实现只需：1) 写实现类 2) 加 `@register` 装饰器 3) 在 `settings.yaml` 中启用。

> **隐私规则**: `prompts.md` 记录用户提示词时，必须对 API Key、密码、手机号等敏感信息做脱敏处理（如 `sk-****12f9`、`132****0459`）。实际密钥只存放在 `.env` 文件中，绝不出现在代码或文档里。每条记录必须标注日期。

> **提交规则**: 用户说"提交"即表示 `git add . && git commit && git push`。提交信息使用中文，简述本次变更。遵循 conventional commits 风格（feat/fix/chore 等前缀）。

> **时间记录规则**: 每次更新「开发进度」「待完善」「后续模块说明与选型」或已知问题后，须同步更新本文档顶部的 **最后更新** 日期（格式：YYYY-MM-DD，东八区上海时间）。

---

## 开发进度

（清单更新时间：2026-03-15，东八区）

### ✅ 已完成

| 模块 | 文件 | 状态 | 说明 |
|------|------|------|------|
| 项目架构 | `config/settings.yaml` | ✅ | 全局配置，支持环境变量替换 |
| 数据模型 | `src/models/stock.py` | ✅ | NewsItem(含news_id/category/sentiment/related_stocks), StockTarget, FilterResult 等 |
| 配置管理 | `src/config.py` | ✅ | YAML加载 + 环境变量解析 + 缓存 |
| 新闻源工厂 | `src/news/factory.py` | ✅ | 注册模式，配置驱动创建 fetcher |
| 新闻拉取 | `src/news/jin10.py` | ✅ | 金十数据快讯接口 (@register 自注册) |
| 新浪财经 | `src/news/sina.py` | ✅ | 提取 id/tag/ext.stocks 完整字段 |
| 东方财富 | `src/news/eastmoney.py` | ✅ | 提取 newsid/title/digest 完整字段 |
| 新闻去重 | `src/news/dedup.py` | ✅ | 基于 news_id 文件持久化去重，24h 自动过期 |
| 新闻预处理 | `src/news/preprocessor.py` | ✅ | 分类(7种) → 情绪(正/负/中) → 关键词 → 预筛选 |
| Prompt 模板 | `config/prompts/*.txt` | ✅ | LLM 提示词外部模板化，支持结构化新闻输入 |
| LLM Provider工厂 | `src/llm_provider/factory.py` | ✅ | 注册模式，配置驱动创建 LLM Provider |
| 阿里百炼 | `src/llm_provider/bailian.py` | ✅ | DashScope OpenAI 兼容 (@register 自注册) |
| 智谱AI | `src/llm_provider/zhipu.py` | ✅ | 官方API + AutoDL 自部署 (@register 自注册) |
| LLM分析 | `src/analyzer/llm_analyzer.py` | ✅ | 模板化 Prompt + 结构化新闻输入 + 评分≥50过滤 |
| 筛选器工厂 | `src/filters/factory.py` | ✅ | 注册模式，配置驱动创建筛选器链 |
| 板块筛选 | `src/filters/board_filter.py` | ✅ | 标注可交易性，不过滤非主板 |
| 可买筛选 | `src/filters/affordability_filter.py` | ✅ | 股价<100元 + 沪深主板/ETF |
| 异动监控 | `src/filters/anomaly_filter.py` | ✅ | 排除暴涨暴跌+资金连续性 |
| 大师选股 | `src/filters/master_filter.py` | ✅ | 5维基本面: PE/PB/ROE/负债率/市值 |
| 机构筛选 | `src/filters/institution_filter.py` | ✅ | 十大股东机构检测 |
| 技术选股 | `src/filters/technical_filter.py` | ✅ | 量比+换手率+筹码+均线+MACD+量能 |
| 筛选器链 | `src/filters/chain.py` | ✅ | 链式执行，短路机制 |
| 大盘判断 | `src/trading/market_judge.py` | ✅ | 上证指数+参考指数综合判断 |
| 邮件通知 | `src/trading/notifier.py` | ✅ | SMTP邮件，HTML模板 |
| 企微通知 | `src/trading/notifier.py` | ✅ | 群机器人 webhook，配置即用 |
| PushPlus个微 | `src/trading/notifier.py` | ✅ | 推送到个人微信(pushplus.plus) |
| 模拟交易 | `src/trading/executor.py` | ✅ | 模拟执行，JSON 落 result/trades/YYYY-MM-DD/ + DB |
| 主流水线 | `src/main.py` | ✅ | 8步流水线: 拉取→去重→预处理→LLM→筛选→大盘→通知→交易 |
| 定时调度 | `src/scheduler.py` | ✅ | APScheduler cron定时 |
| 启动入口 | `run.py` | ✅ | CLI: --once / --schedule |
| 提示词记录 | `prompts.md` | ✅ | 独立文件记录所有提示词和用户需求 |
| 测试框架 | `tests/conftest.py` | ✅ | pytest + pytest-asyncio，registry 隔离 |
| 配置测试 | `tests/test_config.py` | ✅ | 10 个用例，覆盖加载/环境变量/get |
| 新闻测试 | `tests/test_news.py` | ✅ | 7 个用例，工厂机制 + 真实API + 去重 + 预处理流程 |
| 预处理测试 | `tests/test_extractor.py` | ✅ | 22 个用例，关键词/分类/情绪/预筛选/完整管道 |
| 分段测试 | `tests/test_pipeline_step.py` | ✅ | 新闻→result/new_result.txt + LLM→result/llm_result.txt |
| 百炼LLM | 阿里百炼 qwen-plus | ✅ | 实测通过：1609 tokens，3个标的，JSON解析正常 |
| dotenv | `src/config.py` + `.env` | ✅ | python-dotenv 自动加载 .env 环境变量 |
| LLM深度分析 | `config/prompts/analyze_system.txt` | ✅ | 禁止ETF，要求个股+产业链+传导逻辑 |
| StockTarget增强 | `src/models/stock.py` | ✅ | 新增 industry_chain / logic 字段 |
| result追加模式 | `tests/test_pipeline_step.py` | ✅ | #RUN轮次标记+关联提示词+不覆盖追加 |
| 两层分析 | Prompt + `StockTarget` | ✅ | ETF概览 + 具体个股深挖，target_type 区分 |
| ${VAR:default} | `src/config.py` | ✅ | 环境变量支持默认值语法 |
| 日志目录 | `logs/` | ✅ | 测试日志同时输出 terminal + logs/test_*.log |
| 可交易性标注 | `StockTarget.tradable` | ✅ | 自动根据 board 标注可买/需开通权限 |
| 板块筛选改标注 | `board_filter.py` | ✅ | 不再过滤非主板标的，改为 details 标注 |
| Git提交规则 | `todolist_skill.md` | ✅ | 用户说"提交"即 commit+push |
| 利空分析 | `src/analyzer/bearish_analyzer.py` | ✅ | 大盘影响+行业风险，与利好并行调用 |
| 利空模型 | `src/models/stock.py` | ✅ | RiskLevel/MarketImpact/IndustryRisk/BearishAnalysis |
| 利空Prompt | `config/prompts/bearish_*.txt` | ✅ | 系统+用户模板，只分析大盘/行业层面 |
| DataFetcherManager | `src/data/fetcher_manager.py` | ✅ | 多源故障切换+CircuitBreaker熔断保护 |
| 大师选股v2 | `src/filters/master_filter.py` | ✅ | 5维: ROE/PE+PB/资产负债率/营收增长/市值 |
| 可买筛选器 | `src/filters/affordability_filter.py` | ✅ | 股价<100元 + 沪深主板/ETF |
| 技术选股v2 | `src/filters/technical_filter.py` | ✅ | 量比+换手率+筹码+均线+MACD+量能 |
| 异动监控 | `src/filters/anomaly_filter.py` | ✅ | 5日/1日涨跌幅范围+收阳连续性 |
| 机构筛选 | `src/filters/institution_filter.py` | ✅ | 十大股东机构+龙虎榜(近期上榜)检测 |
| master数据修复 | `master_filter.py` | ✅ | PE/PB用百度估值，ROE用同花顺财报 |
| 筛码比例修复 | `technical_filter.py` | ✅ | chip_profit 0-1→百分比自动转换 |
| 筛选器分段测试 | `tests/test_filter_step.py` | ✅ | 读取LLM结果→逐筛选器独立测试→filter_result.txt |
| 数据库存储 | `src/db/` | ✅ | SQLite+SQLAlchemy，trades 表，storage.enabled，执行器落库 |
| 止盈止损 | `src/trading/position_manager.py` | ✅ | 持仓汇总、止盈/止损比例与最短持仓天数，流水线末尾检查 |
| 回测 | `src/backtest/` + `run.py --backtest` | ✅ | 近期交易记录+akshare日线，总盈亏与最大回撤 |
| 模拟盘接口 | `src/trading/executor.py` PaperExecutor | ✅ | mode=paper 落 JSON+DB，后续接券商模拟盘 API |

### 🔨 待完善

| 模块 | 优先级 | 说明 |
|------|--------|------|
| ~~微信通知~~ | ✅ | 企微 webhook + PushPlus 个微 已实现 |
| 模拟盘交易接口 | ✅ | PaperExecutor 已实现，mode=paper 落 JSON+DB；后续在 executor 内接入券商模拟盘 API |
| 实盘交易 | 暂不做 | 真实资金下单，模拟盘闭环后再考虑 |
| ~~止盈止损~~ | ✅ | 已实现 position_manager + 配置 |
| ~~回测模块~~ | ✅ | 已实现 run.py --backtest |
| ~~数据库存储~~ | ✅ | 已实现 SQLite + trades 表 |
| Web Dashboard | P3 | 可视化看板 |

---

## 后续模块说明与选型

（记录时间：2026-03-14 东八区；实现落地：2026-03-15 23:03 东八区/北京时间）

### 1. 交易执行（当前状态）

| 类型 | 状态 | 说明 |
|------|------|------|
| **模拟交易** | ✅ 已实现 | `SimulatedExecutor`：仅落库/JSON，不向券商发单。 |
| **模拟盘交易** | ✅ 接口已实现 | `PaperExecutor`：当前与 Simulated 同样落 JSON+DB（status=paper），后续在类内接入 QMT/miniQMT 等模拟盘 API 即形成闭环。 |
| **实盘交易** | 暂不实现 | 真实资金下单，待模拟盘闭环后再做。 |

- 切换方式：`config/settings.yaml` 中 `trading.mode: "simulated"`（默认）/ `"paper"`（模拟盘）/ `"live"`（实盘）。
- 使用模拟盘：将 `trading.mode` 改为 `paper`，流水线会走 `PaperExecutor`，记录写入 `trade_paper_*.json` 及 DB；后续在 `PaperExecutor.execute()` 内调用券商模拟盘接口即可实现真实模拟盘闭环。

---

### 2. 止盈止损（实现思路）

- **持仓来源**：当前无统一「持仓」数据源。可选：① 仅用本系统产生的 `data/trades/*.json` 汇总为模拟持仓；② 实盘后从券商接口拉取持仓。
- **规则配置**：建议在 `settings.yaml` 中增加一段，例如：
  - `stop_profit_pct`: 单票盈利达到该比例触发止盈（如 0.10 表示 10%）
  - `stop_loss_pct`: 单票亏损达到该比例触发止损（如 -0.05 表示 -5%）
  - 可选：`hold_days_min`（最短持仓天数，避免刚买就卖）
- **执行方式**：在定时任务中增加「持仓检查」步骤：读取当前持仓 → 逐只计算盈亏比例 → 若触及止盈/止损则生成卖出信号 → 走现有通知 + 交易执行（模拟或实盘）。
- **代码位置**：可新增 `src/trading/position_manager.py`（持仓汇总 + 止盈止损判断），在 `main.py` 或 scheduler 中在「买入」之后调用。

---

### 3. 回测模块（选型建议）

- **目标**：用历史行情 + 历史信号（或历史新闻→LLM→筛选结果）验证策略收益与回撤。
- **方案一（推荐）**：使用 **Backtrader**（`pip install backtrader`）。将历史 K 线（可用 akshare 拉取）灌入，把本系统的「买入/卖出」信号按日对齐成 Backtrader 的 signal，回测收益曲线、夏普、最大回撤等。
- **方案二**：自写简单回测：用 akshare 取标的历史日线，按时间顺序遍历，遇到「信号日」按开盘/收盘价模拟成交，维护持仓与现金，最后统计收益率与回撤。适合先做最小可行回测，再考虑接入 Backtrader。
- **数据**：标的列表与信号时间来自现有流水线产出（或从 `data/trades/*.json` + 筛选结果反推）；行情统一用 akshare 历史接口即可。

---

### 4. 数据库存储选型推荐

| 选型 | 适用场景 | 优点 | 注意 |
|------|----------|------|------|
| **SQLite** | 单机、轻量、先落地 | 零配置、单文件、Python 内置，适合交易记录、去重库、新闻/标的缓存 | 并发写多时锁竞争，不适合多进程同时写；可后续迁到 PostgreSQL。 |
| **PostgreSQL** | 正式环境、多端/远程、需稳定与扩展 | 功能强、支持 JSON 字段、适合做分析查询与后续 Web/API | 需单独部署与配置连接串。 |
| **MySQL** | 已有 MySQL 基础设施 | 生态熟、运维多 | 与 PostgreSQL 二选一即可，无特别偏好时更推荐 PostgreSQL。 |

- **建议**：当前阶段用 **SQLite** 即可（路径如 `data/stock_flash.db`），表可先设计：
  - **trades**：交易记录（与现有 `TradeRecord` 对应，可加 id、created_at）
  - **positions**：持仓快照（可选，为止盈止损服务）
  - **news_seen**：替代或补充现有 `data/seen_news.json`，用于去重
  - **targets / signals**：可选，存储每次流水线产出的标的或信号，便于回测与统计
- 使用 **SQLAlchemy** 或 **peewee** 做 ORM，便于以后切换 PostgreSQL（改连接串即可）。

### 🐛 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| akshare 字段名 | ⚠️ 待验证 | akshare 不同版本字段名可能不同，需实际运行验证 |
| ~~金十API限流~~ | ✅ 已解决 | 金十免费API已停服(2025.12)，已替换为新浪+东方财富 |
| LLM幻觉 | ⚠️ 注意 | 大模型可能编造股票代码，需校验 |

---

## 完整流水线（全程）

```
定时/命令触发
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 1  拉取新闻 (sina + eastmoney)                                      │
│ Step 2  去重 (news_id 文件持久化，24h 过期)                               │
│ Step 3  预处理 → 关键词/分类(7种)/情绪 → 预筛选(should_analyze)           │
│ Step 4  LLM 分析 (利好 + 利空 并行) → 利好标的 + 大盘/行业利空报告         │
│ Step 5  链式筛选 board→可买→异动→基本面→机构(含龙虎榜)→技术              │
│ Step 6  大盘判断 (上证+参考指数)                                          │
│ Step 7  通知 (邮件 / 企微 webhook / PushPlus 个微)                        │
│ Step 8  交易执行 (大盘可交易时模拟下单 → JSON 记录)                       │
└─────────────────────────────────────────────────────────────────────────┘
```

## 新闻处理流程（Step 3 明细）

```
拉取(sina/eastmoney) → 去重(news_id) → 预处理 → LLM分析
                                         │
                         ┌───────────────┼───────────────┐
                         ▼               ▼               ▼
                     关键词提取       分类(7种)       情绪判断
                         │               │               │
                         └───────────────┼───────────────┘
                                         ▼
                                    预筛选(should_analyze)
                                         │
                           通过条件(满足任一):
                           ├─ 有关联股票(related_stocks)
                           ├─ 有关键词 + 情绪非中性
                           ├─ 重要性 >= 2
                           └─ 分类为公司/行业/政策/科技 + 有关键词
                                         │
                                         ▼
                                   送 LLM 分析
```

---

## 使用说明

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量 (复制 .env.example 为 .env)
cp .env.example .env
# 编辑 .env 填入你的 API Key 和邮箱配置

# 3. 执行一次
python run.py

# 4. 定时调度模式
python run.py --schedule

# 5. 通知（当前：邮箱；PushPlus 已关闭）
# 邮箱：发件人显示名「量化小龙虾」，收件人 1271573554@qq.com；.env 填 EMAIL_SENDER=1271573554@qq.com、EMAIL_PASSWORD=QQ邮箱授权码
# 测试邮箱：python run.py --test-email
# 企微：群设置 -> 添加群机器人 -> 复制 webhook，在 settings.yaml 中 notification.wechat 填写并 enabled: true
# 个微：见下方「个人微信(PushPlus)接入」（当前已关闭）
```

### 邮箱通知（当前默认）

| 配置项 | 说明 |
|--------|------|
| **发件人显示名** | 量化小龙虾（在 settings.yaml 的 `notification.email.sender_name`） |
| **收件人** | 1271573554@qq.com（在 settings.yaml 的 `notification.email.receivers`） |
| **.env** | `EMAIL_SENDER=1271573554@qq.com`，`EMAIL_PASSWORD=QQ 邮箱授权码`（不是登录密码，在 QQ 邮箱 设置→账户→POP3/SMTP 中生成） |

测试命令：`python run.py --test-email`（会发一封测试邮件到 1271573554@qq.com）。

### 个人微信(PushPlus)接入 — 要配置什么（当前已关闭，改用邮箱）

只需 **2 步**：

| 步骤 | 做什么 |
|------|--------|
| **1. 获取 Token** | 打开 [pushplus.plus](https://www.pushplus.plus) → 登录 → 进入「一对一推送」→ 扫码绑定微信 → 在页面复制你的 **Token**（一长串字符） |
| **2. 写入配置** | 在项目根目录的 **`.env`** 里新增一行：<br>`PUSHPLUS_TOKEN=你复制的Token`<br>在 **`config/settings.yaml`** 里找到 `notification.pushplus`，把 `enabled` 改为 `true` |

无需改代码。配置好后，每次流水线执行到 Step 7 通知时会往你微信推一条消息（大盘 + 信号摘要）。

```yaml
# config/settings.yaml 片段
notification:
  pushplus:
    enabled: true
    token: "${PUSHPLUS_TOKEN:}"
```

```bash
# .env 中增加（把 xxx 换成真实 token）
PUSHPLUS_TOKEN=xxx
```

## 扩展指南

### 新增新闻源
1. 在 `src/news/` 下新建文件，继承 `BaseNewsFetcher`
2. 类上加 `@register("source_name")` 装饰器
3. fetch() 返回 `NewsItem` 时务必填充 `news_id`（格式 `source:原始id`）
4. 尽量提取源站的标签→`raw_tags` 和关联股票→`related_stocks`
5. 在 `config/settings.yaml` 的 `news` 下添加对应配置并设置 `enabled: true`

### 新增 LLM Provider
1. 在 `src/llm_provider/` 下新建文件，继承 `BaseLLMProvider`，实现 `chat()` 方法
2. 类上加 `@register("provider_name")` 装饰器
3. 在 `config/settings.yaml` 的 `llm.providers` 下添加对应配置
4. 修改 `llm.active_provider` 切换使用

### 新增筛选器
1. 在 `src/filters/` 下新建文件，实现 `name` 属性和 `async apply()` 方法
2. 类上加 `@register("filter_name")` 装饰器
3. 在 `config/settings.yaml` 的 `filters` 下添加对应配置并设置 `enabled: true`

### 修改 Prompt
1. 编辑 `config/prompts/analyze_system.txt`（系统 Prompt）或 `analyze_user.txt`（用户 Prompt 模板）
2. 用户模板支持 `{count}`（新闻条数）和 `{news_block}`（结构化新闻内容）变量
3. 无需修改代码，重启即生效
