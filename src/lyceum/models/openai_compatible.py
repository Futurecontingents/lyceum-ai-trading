"""Small OpenAI-compatible chat-completions client using the standard library."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from lyceum.models.base import CompletionResult


class ModelProviderError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(self, *, base_url: str, api_key: str, model_name: str, timeout_seconds: float = 12) -> None:
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("model base URL must be an HTTP(S) endpoint")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    def complete_structured(self, *, system_prompt: str, user_prompt: str) -> CompletionResult:
        body = json.dumps(
            {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
                "max_tokens": 700,
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Futurecontingents/lyceum-ai-trading",
                "X-Title": "Lyceum",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read())
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ModelProviderError("provider returned empty content")
            return CompletionResult(
                content=content,
                provider=self.name,
                model_name=self.model_name,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as exc:
            raise ModelProviderError("model completion failed") from exc
