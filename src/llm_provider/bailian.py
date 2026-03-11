"""阿里百炼 (DashScope) LLM Provider — OpenAI 兼容接口"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from src.config import get
from src.llm_provider.base import BaseLLMProvider, ChatMessage, ChatResponse
from src.llm_provider.factory import register

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@register("bailian")
class BailianProvider(BaseLLMProvider):
    """阿里百炼 — 通过 DashScope OpenAI 兼容接口调用"""

    provider_name = "bailian"

    def __init__(self) -> None:
        cfg = (get("llm", "providers") or {}).get("bailian", {})
        self.model = cfg.get("model", "qwen-plus")
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
            logger.exception("阿里百炼调用失败 (model=%s)", self.model)
            raise
