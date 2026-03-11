"""LLM Provider 基类"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str  # system / user / assistant
    content: str


@dataclass
class ChatResponse:
    content: str
    model: str = ""
    usage: dict | None = None


class BaseLLMProvider(abc.ABC):
    """所有 LLM Provider 的抽象基类"""

    provider_name: str = "unknown"

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> ChatResponse:
        """发送对话请求，返回模型回复"""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider={self.provider_name}>"
