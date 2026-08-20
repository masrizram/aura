"""
OpenRouter LLM provider.

OpenRouter provides a unified OpenAI-compatible endpoint that routes
requests to the best available model across multiple providers.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

import urllib.error
import urllib.request

from ..base import (
    BaseLLMProvider,
    LLMConfig,
    LLMResponse,
    ModelCapability,
    LLMAuthError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    LLMProviderError,
)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_MAX_RETRIES = 3
_BASE_DELAY = 1.0
_MAX_DELAY = 60.0


def _env_key(name: str) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    return value if value else None


class OpenRouterProvider(BaseLLMProvider):
    """Provider for OpenRouter, which exposes an OpenAI-compatible API.

    Acts as a multi-model gateway, routing to the specified model regardless
    of the underlying provider.

    Config fields honoured:
        - ``api_key``: OpenRouter API key (falls back to ``OPENROUTER_API_KEY``).
        - ``api_base``: Base URL override (falls back to ``openrouter.ai``).
        - ``model``: Router model string (e.g. ``openai/gpt-4o``).
        - ``temperature``, ``max_tokens``, ``timeout_seconds``.
    """

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self._api_key = config.api_key or _env_key("OPENROUTER_API_KEY")
        self._api_base = (config.api_base or _DEFAULT_BASE_URL).rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {self._api_key or ''}",
            "Content-Type": "application/json",
        }

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)

    def chat(self, messages: List[Dict[str, str]]) -> LLMResponse:
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        payload = json.dumps(body).encode("utf-8")
        url = f"{self._api_base}/chat/completions"

        start = time.perf_counter()
        try:
            data = self._request_with_retry(url, payload)
        finally:
            latency_ms = (time.perf_counter() - start) * 1000.0

        choice = data["choices"][0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        return LLMResponse(
            content=message.get("content", "") or "",
            model=data.get("model", self.config.model),
            provider="openrouter",
            tokens_used=usage.get("total_tokens", 0),
            stop_reason=choice.get("finish_reason", ""),
            latency_ms=latency_ms,
        )

    def supports(self, capability: ModelCapability) -> bool:
        return capability in (
            ModelCapability.TEXT,
            ModelCapability.CODE,
            ModelCapability.TOOL_USE,
            ModelCapability.VISION,
        )

    def _request_with_retry(self, url: str, payload: bytes) -> Dict[str, Any]:
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES):
            try:
                return self._do_request(url, payload)
            except LLMRateLimitError as exc:
                last_exc = exc
                if attempt == _MAX_RETRIES - 1:
                    raise
                delay = min(_BASE_DELAY * (2 ** attempt), _MAX_DELAY)
                time.sleep(delay)
            except (LLMConnectionError, LLMProviderError) as exc:
                last_exc = exc
                if attempt == _MAX_RETRIES - 1:
                    raise
                delay = min(_BASE_DELAY * (2 ** attempt), _MAX_DELAY)
                time.sleep(delay)
        raise last_exc  # type: ignore[misc]

    def _do_request(self, url: str, payload: bytes) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=payload,
            headers=self._headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            return self._handle_http_error(exc)
        except urllib.error.URLError as exc:
            raise LLMConnectionError(f"Connection failed: {exc.reason}") from exc

    @staticmethod
    def _handle_http_error(exc: urllib.error.HTTPError) -> Dict[str, Any]:
        status = exc.code
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except Exception:
            detail = {}

        msg = detail.get("error", {}).get("message", str(exc))

        if status in (401, 402):
            raise LLMAuthError(f"Authentication/credits failed: {msg}") from exc
        if status == 429:
            raise LLMRateLimitError(f"Rate limited: {msg}") from exc
        if status >= 500:
            raise LLMProviderError(f"Provider error {status}: {msg}") from exc

        raise LLMError(f"HTTP {status}: {msg}") from exc