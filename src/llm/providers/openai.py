"""
OpenAI (and OpenAI-compatible) LLM provider.

Supports standard OpenAI, Azure OpenAI, and any OpenAI-compatible API
(local proxies, LiteLLM, vLLM, etc.) through the ``api_base`` config field.
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
    LLMContextLengthError,
    LLMError,
    LLMRateLimitError,
    LLMProviderError,
)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_MAX_RETRIES = 3
_BASE_DELAY = 1.0
_MAX_DELAY = 60.0


def _env_key(name: str) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    return value if value else None


class OpenAIProvider(BaseLLMProvider):
    """Provider for OpenAI and OpenAI-compatible APIs.

    Config fields honoured:
        - ``api_key``: OpenAI / Azure key (falls back to ``OPENAI_API_KEY``).
        - ``api_base``: Base URL override (falls back to ``api.openai.com``).
        - ``model``: Model name (e.g. ``gpt-4o``, ``gpt-4o-mini``).
        - ``temperature``, ``max_tokens``, ``timeout_seconds``.
    """

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self._api_key = config.api_key or _env_key("OPENAI_API_KEY")
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
            provider="openai",
            tokens_used=usage.get("total_tokens", 0),
            stop_reason=choice.get("finish_reason", ""),
            tool_calls=message.get("tool_calls", []),
            latency_ms=latency_ms,
        )

    def supports(self, capability: ModelCapability) -> bool:
        vision_models = {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision"}
        return (
            capability == ModelCapability.TEXT
            or capability == ModelCapability.CODE
            or (capability == ModelCapability.VISION and self.config.model in vision_models)
            or capability == ModelCapability.TOOL_USE
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

        if status == 401:
            raise LLMAuthError(f"Authentication failed: {msg}") from exc
        if status == 429:
            raise LLMRateLimitError(f"Rate limited: {msg}") from exc
        if status == 400 and "context_length" in msg.lower():
            raise LLMContextLengthError(f"Context length exceeded: {msg}") from exc
        if status >= 500:
            raise LLMProviderError(f"Provider error {status}: {msg}") from exc

        raise LLMError(f"HTTP {status}: {msg}") from exc