# Stock Flash

**A 股智能交易助手**：定时或命令触发，自动完成「新闻抓取 → 去重 → 预处理 → LLM 分析 → 链式筛选 → 大盘判断 → 通知 → 模拟交易」全流程。

---

## 总览

- **目标**：从财经快讯中识别利好标的，经多级筛选与大盘判断后，发出交易信号并通知（当前为邮件），支持模拟下单并落盘记录。
- **文档分工**：
  - **本文件 (README.md)**：总览与快速上手。
  - **[todolist_skill.md](todolist_skill.md)**：开发清单与进度、待完善项、后续模块说明与选型（交易/止盈止损/回测/数据库），**须在清单中记录好时间**。
  - **prompts.md**：用户提示词与执行结果记录（脱敏，带日期）。

---

## 流水线（8 步）

```
定时/命令触发
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 1  拉取新闻 (新浪 + 东方财富)                                        │
│ Step 2  去重 (新闻库 DB 或文件 news_id，超时标 expired 生命周期)          │
│ Step 3  预处理 → 分类/情绪/关键词 → 预筛选                               │
│ Step 4  LLM 分析 (利好 + 利空 并行) → 标的 + 大盘/行业利空                 │
│ Step 5  链式筛选 (板块→可买→异动→基本面→机构→技术)                       │
│ Step 6  大盘判断 (上证+参考指数，非交易日用最近交易日数据)                 │
│ Step 7  通知 (邮件 / 企微 / PushPlus，当前默认邮件)                        │
│ Step 8  交易执行 (模拟/模拟盘/CTP：result/trades/日期/ + DB；实盘：占位未实现)  │
└─────────────────────────────────────────────────────────────────────────┘
```

- **流程状态**：Step 1～8 已全部实现（新闻库、复盘 `--review`、止盈止损、模拟/模拟盘/CTP 均可用），仅**实盘 (live)** 为占位未实现。非交易日/非交易时段仍会跑完 Step 1～7（拉取、筛选、入池等），仅 Step 8 不执行交易。
- **两条路线**：**新闻驱动**（默认 `python run.py`）：拉取→去重→预处理→LLM→链式筛选→通知→交易，通过筛选的标的入股票池；**自研池**（`python run.py --research-pool`）：从 `config/settings.yaml` 的 `research_pool.stocks` 出发，只跑链式筛选→大盘判断→通知→交易，不入新闻池。通知与交易记录均会**标明来源**（新闻驱动 / 自研池）。

---

## 股票池（已实现，可选开启）

新闻筛出并通过链式筛选的标的会进入**股票池**，按「观察 → 稳定 → 高位 / 移除」流转，并与新闻生命周期联动。

| 池子     | 含义 |
|----------|------|
| **观察池** | 刚入池，观察一段时间 |
| **稳定池** | 观察满 N 小时且涨跌幅在稳定区间，可作买入候选 |
| **高位池** | 5 日涨幅超阈值，只持有不新开仓 |
| **移除池** | 新闻过期、止盈/止损卖出、或观察超时 |

**如何维护（以代码和配置为准）**：

- **改流转规则 / 阈值**：改 `config/settings.yaml` 里 `stock_pool` 下的 `stable_watch_hours`、`stable_min_1d_pct`、`high_threshold_5d_pct` 等；逻辑在 `src/trading/stock_pool_maintainer.py` 的 `maintain()`。
- **改入池/出池逻辑**：改 `src/db/stock_pool_repository.py`（入池、标移除）和 `maintainer`（观察→稳定→高位→移除）。
- **改表结构**：改 `src/db/models.py` 的 `StockPool`，必要时重建或迁移 DB。

**开启方式**：`config/settings.yaml` 中 `stock_pool.enabled: true`，且 `storage.enabled: true`。当前买入信号仍来自当次链式筛选通过标的，未改为「仅稳定池」。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env：API Key、EMAIL_SENDER、EMAIL_PASSWORD（QQ 邮箱授权码）等

# 3. 执行一次流水线
python run.py

# 4. 测试模式（石油新闻跑通全流程，不拉实时、临时去重）
python run.py --test

# 5. 仅发一封测试邮件
python run.py --test-email

# 6. 简单回测（近期交易记录 + 日线，算收益与回撤）
python run.py --backtest

# 6b. 收盘后复盘（新闻-交易关联、按来源统计准确率与建议，需 storage.enabled）
python run.py --review
python run.py --review --review-days 7

# 6c. 自研池路线（从 config 的 research_pool.stocks 跑链式筛选→通知→交易，来源标明「自研池」）
python run.py --research-pool

# 7. 测试 OpenCTP：仅登录 / 登录+一笔测试报单（需配置 trading.ctp）
python run.py --test-ctp
python run.py --test-ctp --test-ctp-order   # 登录后发一笔低价限价单（验证报单，不会成交）

# 8. 定时调度
python run.py --schedule
```

配置与新闻源/筛选器/LLM 等均通过 **config/settings.yaml** 驱动，新增组件采用工厂 + 注册，详见 [todolist_skill.md](todolist_skill.md) 扩展指南。数据库使用 Python 自带 `sqlite3`，无需单独安装 SQLite，数据文件为 `data/stock_flash.db`。

---

## 计算结果与输出（按日期分组）

所有「计算/运行结果」统一放在 **`result/`** 下，并按**日期分组**：

| 内容 | 路径 |
|------|------|
| 交易记录 JSON | `result/trades/YYYY-MM-DD/trade_*.json`、`trade_paper_*.json` |
| 筛选/LLM 等测试输出 | `result/` 下各文件（如 `filter_result.txt`、`llm_result.txt` 等） |

首次使用新路径时，原 `data/trades/` 下的历史交易文件会在首次执行时自动迁移到 `result/trades/对应日期/`。

---

## 通知（当前默认：邮件）

- **发件人显示名**：量化小龙虾  
- **收件人**：在 `config/settings.yaml` 的 `notification.email.receivers` 中配置（例：1271573554@qq.com）。  
- **.env**：`EMAIL_SENDER`、`EMAIL_PASSWORD`（QQ 邮箱授权码，非登录密码）。  

测试命令：`python run.py --test-email`。企微 / PushPlus 配置与开关见 [todolist_skill.md](todolist_skill.md)。

---

## 后续规划（概要）

| 方向       | 状态 | 说明 |
|------------|------|------|
| 数据库存储 | ✅ 已做 | SQLite + SQLAlchemy，`storage.enabled`，表 `trades`，执行器自动落库。 |
| 止盈止损   | ✅ 已做 | `position_manager` 从 DB 汇总持仓，按 `stop_profit_pct`/`stop_loss_pct`/`hold_days_min` 生成卖出信号，流水线末尾检查并执行。 |
| 回测模块   | ✅ 已做 | `python run.py --backtest`，从 DB/JSON 读交易记录，akshare 日线模拟，输出总盈亏与最大回撤。 |
| 模拟盘交易 | ✅ 接口已实现 | `trading.mode: paper` 使用 `PaperExecutor`，当前落 JSON+DB（status=paper），后续在 executor 内接入券商模拟盘 API 即闭环。 |
| 新闻库与复盘 | ✅ 已做 | 新闻表 pending→processed→analyzed→expired，`--review` 按来源统计准确率与已实现盈亏。 |
| 股票池 | ✅ 已做 | 观察池/稳定池/高位池/移除池，配置 `stock_pool.enabled` 开启，见上文「股票池」小节。 |
| 实盘交易   | 暂不实现 | 真实资金下单，模拟盘闭环后再做。 |

**详细实现与配置见 [todolist_skill.md](todolist_skill.md)。**

---

## 常见问题

**1. 现在能跑通整个流程了吗？**  
能。在配置好 `.env`（API Key、邮箱等）和 `config/settings.yaml` 后：
- **`python run.py`**：拉取实时新闻，走完 8 步（若当日无新新闻会在 Step 2 去重后结束，属正常）。非交易日/非交易时段也会跑完 Step 1～7（拉取、去重、预处理、LLM、链式筛选、大盘判断、通知），通过筛选的标的会入池（若开启股票池），仅 Step 8 不执行交易。
- **`python run.py --test`**：用内置石油新闻跑通全流程，不依赖实时拉取与去重，适合验证整条链路。

**2. 回测模块是干嘛的？**  
用**已有交易记录**（DB 或 `result/trades/*/*.json`）+ **历史日线**（akshare）模拟「按当时信号买卖」的收益与最大回撤，用来**事后评估策略表现**，不是日常交易的一部分。

**3. 回测需要每天跑定时器吗？**  
不需要。回测是**按需手动执行**（例如每周或每月跑一次 `python run.py --backtest` 看近期表现）。定时器（`python run.py --schedule`）只负责**每日扫描→分析→筛选→通知→交易**，不包含回测。

---

## 模拟交易 vs 真实模拟账户

- **当前「模拟交易」**（`trading.mode: simulated`）：只在本地落 JSON（`result/trades/日期/`）+ 数据库，**不连接券商**，不产生真实委托。
- **若要对接真实模拟账户**（券商仿真环境、虚拟资金）：  
  - 将 `trading.mode` 改为 `paper`，使用 `PaperExecutor`；  
  - 在 `PaperExecutor` 内接入券商/平台的**模拟盘 API**，即可形成「信号 → 真实模拟委托 → 回报」闭环。

**好用的 A 股模拟账户推荐**（任选其一，再在代码里对接其 API）：

| 方式 | 说明 |
|------|------|
| **东方财富模拟炒股** | 在东方财富 App 或 pc 端开通「模拟炒股」，资金虚拟、行情与实盘一致，用户多、入口简单；后续可用其开放接口或 QMT 等对接。 |
| **券商 + QMT/miniQMT 模拟** | 部分券商（如华泰、国信等）支持迅投 **QMT** 或 **miniQMT**，在 QMT 里登录券商账号后使用「模拟」环境，再在本地用 miniQMT 的 Python 接口下单，适合量化闭环。 |
| **同花顺模拟炒股** | 官方：在 [forfunds.cn](http://moni.10jqka.com.cn/hezuo/jyzjdbp) 激活模拟账户，下载接口文档与 DLL，用 Python 调用本地接口（仅模拟资金账户）。第三方：如 [ths_trade](https://github.com/skyformat99/ths_trade) 通过同花顺 xiadan.exe 提供 HTTP API。 |

建议：先在本机用 `mode=simulated` 或 `paper`（当前仅落库）跑通策略与止盈止损，再选一个模拟账户（如东方财富模拟、券商+miniQMT 模拟 或 同花顺官方/ths_trade）在 `PaperExecutor` 内对接其 API。

### 只对接模拟 API、不用交易客户端：推荐接口

不想装同花顺 xiadan、QMT 等桌面交易客户端，只要**纯 API（HTTP/SDK）模拟下单**时，可优先考虑下面几种，均为「无桌面交易软件」或「仅本地 DLL/SDK」：

| 方式 | 类型 | 说明 | 你需要提供 |
|------|------|------|------------|
| **同花顺官方模拟接口** | 本地 DLL + Python | [forfunds.cn](https://www.forfunds.cn) 合作激活页申请模拟资金账号，下载接口文档与 `bin/win64/dll`，本地配置账号/密码后**无需打开同花顺客户端**即可用 Python 调下单/撤单/查询。 | 资金账号、密码、官方接口包（含 DLL）、`simple_py_demo.ini` 等配置。 |
| **掘金 MyQuant 线上仿真** | 云端 + Python SDK | [sim.myquant.cn](https://sim.myquant.cn) 仿真交易，本地 `pip install gmtrade`，`set_token` + `set_endpoint("api.myquant.cn:9000")` + 账户登录后纯 API 下单，支持 A 股等。 | 掘金账号、token、账户 ID；无需任何桌面交易客户端。 |
| **宽易 Quantease 模拟交易** | 云端 API + Python | [宽易平台](https://quantease.cn) 提供模拟交易 API，创建虚拟账户、`runStrat(..., 'simu', ...)` 即可，有网页监控；交易由 API 驱动。 | 宽易账号、模拟账户 token；无需桌面交易客户端。 |
| **东财掘金量化终端** | 本地/云端 + API | 东方财富官方量化，支持仿真模拟与程序化下单 API；需安装「东财掘金」终端（偏开发/量化环境，非传统下单客户端）。 | 东财账号、终端安装；若只用其 API 发单，可不依赖传统交易界面。 |
| **OpenCTP 仿真 / 7x24** | CTPAPI + Python | [openctp.cn](http://www.openctp.cn) 提供 CTP 兼容的**股票+期货**模拟环境，纯 API、无需交易客户端。7x24 为全天回放，仿真与实盘时段同步。Python 可用 [openctp-ctp-python](https://github.com/openctp/openctp-ctp-python)。 | 在官网/公众号注册获得的**仿真账号、7x24 账号、密码**；交易/行情前置地址见下。 |

**小结**：  
- **零客户端**：掘金仿真、宽易、**OpenCTP** 均为「账号 + 地址 + SDK」即可，不依赖任何桌面交易客户端。  
- **仅本地 DLL、不依赖同花顺界面**：同花顺官方模拟接口，配置好 DLL 与账号后，日常只调 Python 接口，不用开同花顺软件。

### 对接 OpenCTP 仿真（你已有账号时）

**可以用。** OpenCTP 的仿真与 7x24 环境均支持 **A 股股票**（全市场全品种），适合「只对接模拟 API、不搞交易客户端」。

- **你已有**：注册后收到的 7x24 账号、仿真环境账号及密码（同一微信号下账号共享同一密码）。
- **连接方式**（CTPAPI 标准，TD=交易前置，MD=行情前置）：
  - **7x24 环境**：交易 `tcp://trading.openctp.cn:30001`，行情 `tcp://trading.openctp.cn:30011`。
  - **仿真环境**：交易 `tcp://trading.openctp.cn:30002`（与实盘时段同步，按实盘行情撮合）。
- **对接到本项目**：在 `PaperExecutor` 内用 OpenCTP 提供的 CTPAPI Python 封装（如 `openctp-ctp-python`）连接上述前置，用你的仿真/7x24 账号、密码登录，将本项目的买卖信号转为 CTP 报单即可。无需安装任何交易客户端。
- **官网与帮助**：<http://www.openctp.cn>；入金/重置等指令见注册邮件或官网说明。

### CTP 程序跑不起来？常见原因与排查

若 `python run.py --test-ctp` 一直提示「CTP 登录失败」或「登录未就绪」，并出现 **OnSessionDisconnected（如 nReason=4097）**，可按下面逐项排查：

| 可能原因 | 说明与处理 |
|----------|------------|
| **网络不可达** | 当前环境（公司网络、代理、防火墙）无法访问 `trading.openctp.cn` 的 30001（7x24）或 30002（仿真）端口。**处理**：在本机用 `telnet trading.openctp.cn 30001` 或浏览器访问 openctp 官网，确认能连通；在可访问外网的本机再跑一次 `python run.py --test-ctp`。 |
| **连接后被断开（4097）** | OpenCTP 官方说明：**出现 4097 即表示当前用的是标准 CTP 库，未用 TTS 库**。必须使用 **openctp-tts**（TTS 的 CTPAPI），不能用 openctp-ctp。**处理**：`pip uninstall openctp-ctp` 后 `pip install openctp-tts`，本项目已默认依赖 openctp-tts。 |
| **账号/密码错误** | 仿真与 7x24 账号不同（如 16988 仿真、17572 为 7x24），密码为公众号注册时给的（如 123456）。**处理**：在 config/settings.yaml 的 `trading.ctp` 中填对 `user_id`、`password`；或通过公众号回复「查询」确认账号状态。 |
| **未激活/未入金** | 部分环境要求先「入金」才能正常使用。**处理**：公众号回复「724账户17572入金1000000」或「仿真账户16988入金1000000」后再试。 |
| **仿真时段** | 仿真环境与实盘时段一致，非 A 股交易时段可能无法登录或报单。**处理**：非交易时段改用 7x24 环境（`td_url: tcp://trading.openctp.cn:30001`，`user_id: 17572`）。 |

**建议**：先在本机（非代理/非受限网络）执行 `python run.py --test-ctp`；若仍失败，看日志里是否先出现「CTP 交易前置已连接」再断开（则多为 4097/网络），还是从未出现（则多为网络不通）。

### 测试 CTP 模拟交易（登录成功后）

- **只验证报单接口**（不发真实策略信号）：  
  `python run.py --test-ctp --test-ctp-order`  
  会登录后向 OpenCTP 发一笔**低价限价单**（浦发银行 600000，0.01 元/股、100 股），远低于市价不会成交，仅验证「报单 → 回报」是否正常；可在 [OpenCTP 模拟环境监控](http://openctp.cn/simenv.html) 或 TickTrader 查看挂单。

- **整条流水线走 CTP**（新闻→分析→筛选→通知→CTP 下单）：  
  1. 在 **config/settings.yaml** 中把 `trading.mode` 改为 `ctp`。  
  2. 执行 `python run.py --test`（用内置石油新闻跑通全流程，通过筛选的信号会发给 OpenCTP 报单）。  
  注意：会按策略信号真实向仿真/7x24 报单，可能挂单或撮合成交，请用模拟账号并控制仓位。

若 `--test-ctp-order` 一直显示「等待报单回报超时」，多为 7x24 当前不在回报时段或合约限制；可改用**仿真环境**（`td_url: tcp://trading.openctp.cn:30002`、`user_id: 16988`）在 A 股交易时段再试，或直接做**整条流水线测试**（`mode: ctp` + `python run.py --test`）验证从信号到报单的完整链路。

### 对接同花顺模拟炒股：你需要提供什么

同花顺有两种可程序化对接的方式，任选其一即可。

**方式一：同花顺官方模拟接口（推荐先试）**

- **你需要准备**：  
  1. **模拟资金账户**：在 [同花顺模拟炒股合作激活页](http://moni.10jqka.com.cn/hezuo/jyzjdbp) 激活账户，获得**资金账号**（约 100 万虚拟资产）。  
  2. **同花顺客户端账号与密码**：用该资金账号 + 同花顺登录密码在客户端「模拟炒股」登录。  
  3. **接口文件**：从官方提供的「接口文档下载」获取开发文档、使用手册，以及 `bin/win64/dll` 等接口文件。  
  4. **本地配置**：在接口包里的 `simple_py_demo.ini`（或等价配置）中填入**资金账号、密码**等，并将 DLL 放到 Python 可加载路径。

- **对接到本项目**：在 `PaperExecutor` 中调用同花顺官方 Python 接口（下单、撤单、资产/委托查询），将本项目的买卖信号转为该接口的委托即可。接口**仅支持模拟资金账户**，不涉及实盘。

**方式二：第三方 ths_trade（同花顺 xiadan.exe + HTTP API）**

- **你需要准备**：  
  1. **同花顺客户端**：已安装同花顺，并能在本机运行 **xiadan.exe**（交易客户端），且已登录你的券商或模拟环境。  
  2. **ths_trade 部署**：从 [ths_trade](https://github.com/skyformat99/ths_trade) 拉取代码，安装依赖（如 pywinauto），配置 xiadan.exe 路径与交易参数，运行后会在本机提供 HTTP 服务（如端口 6003）。  
  3. **本机环境**：Windows，Python 3.7+；通过 HTTP 向 ths_trade 发送 JSON 交易指令。

- **对接到本项目**：在 `PaperExecutor` 中向 ths_trade 的 HTTP 接口发起买入/卖出请求（替代直接调券商 API），实现「信号 → ths_trade → 同花顺客户端」的闭环。适合已有同花顺 + 券商、且接受「模拟点击」方式的用户。

**小结**：若只要「模拟资金、纯程序化」，用**方式一**并准备好资金账号、密码与官方接口文件即可；若已用同花顺 xiadan 且希望用现有客户端，用**方式二**并准备好 xiadan 路径与 ths_trade 配置。

---

## 开发规则（摘要）

- 提示词与需求须记录到 **prompts.md**（脱敏、带日期）。  
- 组件通过 **工厂 + 配置** 创建，`main.py` 不直接依赖具体实现类。  
- 用户说「提交」即执行 `git add . && git commit && git push`，提交信息中文、conventional commits 风格。

完整规则与进度表见 [todolist_skill.md](todolist_skill.md)。
