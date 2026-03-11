"""智谱 AI (Zhipu) LLM Provider — 支持官方 API 及 AutoDL 自部署"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from src.config import get
from src.llm_provider.base import BaseLLMProvider, ChatMessage, ChatResponse
from src.llm_provider.factory import register

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"


@register("zhipu")
class ZhipuProvider(BaseLLMProvider):
    """智谱 AI — 支持官方 API 和 AutoDL 自部署端点

    官方 API: base_url = https://open.bigmodel.cn/api/paas/v4/
    AutoDL 自部署: base_url 配置为 AutoDL 实例地址 (如 http://xxx:8000/v1)
    """

    provider_name = "zhipu"

    def __init__(self) -> None:
        cfg = (get("llm", "providers") or {}).get("zhipu", {})
        self.model = cfg.get("model", "glm-4-flash")
        self._client = AsyncOpenAI(
            api_key=cfg.get("api_key", ""),
            base_url=cfg.get("base_url", _DEFAULT_BASE_URL),
        )

    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> ChatResponse:
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
            choice = resp.choices[0]
            return ChatResponse(
                content=choice.message.content or "",
                model=resp.model or self.model,
                usage=resp.usage.model_dump() if resp.usage else None,
            )
        except Exception:
            logger.exception("智谱AI调用失败 (model=%s)", self.model)
            raise
