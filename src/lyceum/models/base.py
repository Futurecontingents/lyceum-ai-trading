"""Minimal provider contract for optional language-model reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CompletionResult:
    content: str
    provider: str
    model_name: str
    latency_ms: float


class ModelProvider(Protocol):
    name: str
    model_name: str

    def complete_structured(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
        """Return untrusted model text for validation by the caller."""
