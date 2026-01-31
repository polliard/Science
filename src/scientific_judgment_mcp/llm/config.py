"""Configuration models for LLM usage.

We keep model choice explicit per agent to avoid monoculture bias.
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    openai = "openai"
    anthropic = "anthropic"


class AgentModelConfig(BaseModel):
    provider: LLMProvider
    model: str
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1200, ge=64, le=8192)


class ReviewModelsConfig(BaseModel):
    """Config mapping agent role -> model config.

    Keys should match AgentRole values (e.g. "moderator").
    """

    agents: dict[str, AgentModelConfig]

    @staticmethod
    def load_from_path(path: Path) -> "ReviewModelsConfig":
        data = json.loads(path.read_text())
        return ReviewModelsConfig.model_validate(data)


def load_models_config_from_env(default: ReviewModelsConfig) -> ReviewModelsConfig:
    """Optionally load model config from a JSON file path.

    Env var: `SCIJUDGE_MODELS_CONFIG`.

    If not set, returns `default`.
    """

    config_path = os.environ.get("SCIJUDGE_MODELS_CONFIG")
    if not config_path:
        return default

    path = Path(config_path).expanduser().resolve()
    return ReviewModelsConfig.load_from_path(path)


def redact_secrets(obj: Any) -> Any:
    """Best-effort redaction for logs."""

    if isinstance(obj, dict):
        return {k: ("***" if "key" in k.lower() else redact_secrets(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    return obj
