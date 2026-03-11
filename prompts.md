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
