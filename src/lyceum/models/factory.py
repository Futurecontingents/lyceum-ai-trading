"""Provider construction with deterministic-by-default behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lyceum.models.base import ModelProvider
from lyceum.models.openai_compatible import OpenAICompatibleProvider

if TYPE_CHECKING:
    from lyceum.config import Settings


def create_model_provider(settings: Settings) -> ModelProvider | None:
    if settings.model_provider == "deterministic":
        return None
    if settings.model_provider == "openai_compatible" and all((settings.model_base_url, settings.model_api_key, settings.model_name)):
        return OpenAICompatibleProvider(
            base_url=settings.model_base_url,
            api_key=settings.model_api_key,
            model_name=settings.model_name,
            timeout_seconds=settings.model_timeout_seconds,
        )
    return None
