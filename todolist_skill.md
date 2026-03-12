# Stock Flash 开发进度

## 项目概述
通过定时器或命令触发，自动完成：新闻抓取 → 去重 → 预处理(分类/情绪/筛选) → LLM分析 → 链式筛选 → 大盘判断 → 通知 → 模拟交易

---

## 开发规则

> **提示词记录规则**: 每次用户提出的需求/指令，必须记录到 `prompts.md` 文件中，包含原始提示词和执行结果。此规则自动执行，无需用户提醒。

> **封装规则**: `main.py` 不直接引用任何具体实现类，所有组件通过工厂模式 + 配置文件驱动创建。新增实现只需：1) 写实现类 2) 加 `@register` 装饰器 3) 在 `settings.yaml` 中启用。

> **隐私规则**: `prompts.md` 记录用户提示词时，必须对 API Key、密码、手机号等敏感信息做脱敏处理（如 `sk-****12f9`、`132****0459`）。实际密钥只存放在 `.env` 文件中，绝不出现在代码或文档里。每条记录必须标注日期。

> **提交规则**: 用户说"提交"即表示 `git add . && git commit && git push`。提交信息使用中文，简述本次变更。遵循 conventional commits 风格（feat/fix/chore 等前缀）。

---

## 开发进度

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
| 板块筛选 | `src/filters/board_filter.py` | ✅ | 按代码前缀判断板块 (@register 自注册) |
| 大师选股 | `src/filters/master_filter.py` | ✅ | 价值/成长策略 (@register 自注册) |
| 技术选股 | `src/filters/technical_filter.py` | ✅ | MA/量比/MACD (@register 自注册) |
| 筛选器链 | `src/filters/chain.py` | ✅ | 链式执行，短路机制 |
| 大盘判断 | `src/trading/market_judge.py` | ✅ | 上证指数+参考指数综合判断 |
| 邮件通知 | `src/trading/notifier.py` | ✅ | SMTP邮件，HTML模板 |
| 模拟交易 | `src/trading/executor.py` | ✅ | 模拟执行 + JSON记录持久化 |
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

### 🔨 待完善

| 模块 | 优先级 | 说明 |
|------|--------|------|
| 微信通知 | P2 | 企业微信 webhook / Server酱 |
| 实盘交易 | P2 | 对接 QMT / miniQMT 券商接口 |
| 止盈止损 | P2 | 持仓管理，自动止盈止损 |
| 回测模块 | P3 | 历史数据回测策略有效性 |
| Web Dashboard | P3 | 可视化看板 |
| 数据库存储 | P3 | 交易记录、新闻、标的持久化到数据库 |

### 🐛 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| akshare 字段名 | ⚠️ 待验证 | akshare 不同版本字段名可能不同，需实际运行验证 |
| ~~金十API限流~~ | ✅ 已解决 | 金十免费API已停服(2025.12)，已替换为新浪+东方财富 |
| LLM幻觉 | ⚠️ 注意 | 大模型可能编造股票代码，需校验 |

---

## 新闻处理流程

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
