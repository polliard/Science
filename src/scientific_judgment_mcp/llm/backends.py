"""LLM backend factory.

Supports multiple providers to reduce monoculture bias.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel

from .config import AgentModelConfig, LLMProvider


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model: str
    temperature: float
    max_tokens: int


def create_chat_model(cfg: AgentModelConfig) -> BaseChatModel:
    """Create a LangChain chat model from config.

    Env vars are standard for providers:
    - OpenAI: `OPENAI_API_KEY`
    - Anthropic: `ANTHROPIC_API_KEY`
    """

    if cfg.provider == LLMProvider.openai:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )

    if cfg.provider == LLMProvider.anthropic:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=cfg.model,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )

    raise ValueError(f"Unsupported provider: {cfg.provider}")


def identity_from_config(cfg: AgentModelConfig) -> ModelIdentity:
    return ModelIdentity(
        provider=str(cfg.provider.value),
        model=cfg.model,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )
