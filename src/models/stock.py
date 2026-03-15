"""股票相关数据模型"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BoardType(str, Enum):
    MAIN = "main"        # 主板 (60xxxx / 000xxx)
    GEM = "gem"          # 创业板 (300xxx)
    STAR = "star"        # 科创板 (688xxx)
    BSE = "bse"          # 北交所 (8xxxxx / 4xxxxx)


class TradeDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"


class NewsCategory(str, Enum):
    """新闻分类"""
    COMPANY = "company"      # 公司新闻 (财报、高管、并购)
    INDUSTRY = "industry"    # 行业/板块
    POLICY = "policy"        # 政策/监管
    MACRO = "macro"          # 宏观经济
    MARKET = "market"        # 市场行情
    TECH = "tech"            # 科技/创新
    GLOBAL = "global"        # 国际新闻
    OTHER = "other"


class NewsSentiment(str, Enum):
    """新闻情绪"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class NewsItem(BaseModel):
    """新闻条目"""
    news_id: str = ""                   # 唯一标识: "{source}:{原始id}"，用于去重
    source: str
    title: str
    content: str
    url: str = ""                       # 原文链接
    keywords: list[str] = Field(default_factory=list)
    pub_time: datetime
    importance: int = Field(default=0, ge=0, le=5)
    category: NewsCategory = NewsCategory.OTHER
    sentiment: NewsSentiment = NewsSentiment.NEUTRAL
    raw_tags: list[str] = Field(default_factory=list)       # 源站原始标签
    related_stocks: list[dict] = Field(default_factory=list) # 源站关联股票 [{"code":"600519","name":"贵州茅台"}]


class TargetType(str, Enum):
    """标的类型"""
    STOCK = "stock"      # 个股
    ETF = "etf"          # ETF/基金
    INDEX = "index"      # 指数


_BOARD_NOTES: dict[str, str] = {
    "main": "普通账户可买",
    "gem": "需开通创业板权限",
    "star": "需开通科创板权限(50万+2年)",
    "bse": "需开通北交所权限",
}


class StockTarget(BaseModel):
    """分析得出的标的"""
    code: str
    name: str
    board: BoardType
    target_type: TargetType = TargetType.STOCK
    reason: str = ""
    industry_chain: str = ""             # 产业链位置: 上游原材料/中游制造/下游应用/全产业链
    logic: str = ""                      # 深度逻辑: 新闻→行业→公司 的传导路径
    score: float = Field(default=0.0, ge=0, le=100)
    related_news: list[str] = Field(default_factory=list)

    @property
    def tradable(self) -> bool:
        """普通账户是否可直接交易"""
        if self.target_type == TargetType.ETF:
            return True
        return self.board == BoardType.MAIN

    @property
    def tradable_note(self) -> str:
        if self.target_type == TargetType.ETF:
            return "ETF无门槛"
        return _BOARD_NOTES.get(self.board.value, "")


class FilterResult(BaseModel):
    """筛选结果"""
    stock: StockTarget
    passed_filters: list[str] = Field(default_factory=list)
    failed_filters: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)

    @property
    def is_passed(self) -> bool:
        return len(self.failed_filters) == 0


class RiskLevel(str, Enum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class RiskDuration(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class MarketImpact(BaseModel):
    """利空对大盘的影响"""
    level: RiskLevel = RiskLevel.NONE
    description: str = ""
    duration: RiskDuration = RiskDuration.SHORT
    sentiment_shift: str = ""


class IndustryRisk(BaseModel):
    """利空对行业的影响"""
    industry: str
    level: RiskLevel = RiskLevel.MILD
    reason: str = ""
    logic: str = ""
    affected_etfs: list[str] = Field(default_factory=list)
    related_news: list[str] = Field(default_factory=list)


class BearishAnalysis(BaseModel):
    """利空分析结果"""
    market_impact: MarketImpact = Field(default_factory=MarketImpact)
    industry_risks: list[IndustryRisk] = Field(default_factory=list)


class MarketCondition(BaseModel):
    """大盘状况"""
    index_code: str
    index_name: str
    current_price: float
    change_pct: float
    volume_ratio: float = 1.0
    is_tradable: bool = True
    reason: str = ""


class TradeSignal(BaseModel):
    """交易信号"""
    stock: StockTarget
    direction: TradeDirection
    price: Optional[float] = None
    amount: float = 10000
    reason: str = ""
    confidence: float = Field(default=0.0, ge=0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.now)


class TradeRecord(BaseModel):
    """交易记录"""
    signal: TradeSignal
    executed: bool = False
    exec_price: Optional[float] = None
    exec_time: Optional[datetime] = None
    status: str = "pending"
    message: str = ""
    source: Optional[str] = None  # 信号来源：新闻驱动 / 自研池，用于区分两条路线
