"""
Anthropic (Claude) LLM provider.

Communicates with the Anthropic Messages API for Claude models.
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

_API_BASE = "https://api.anthropic.com/v1"
_API_VERSION = "2023-06-01"
_MAX_RETRIES = 3
_BASE_DELAY = 1.0
_MAX_DELAY = 60.0


def _env_key(name: str) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    return value if value else None


class AnthropicProvider(BaseLLMProvider):
    """Provider for Anthropic Claude models via the Messages API.

    Config fields honoured:
        - ``api_key``: Anthropic API key (falls back to ``ANTHROPIC_API_KEY``).
        - ``model``: Model name (e.g. ``claude-sonnet-4-20250514``).
        - ``temperature``, ``max_tokens``, ``timeout_seconds``.
    """

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self._api_key = config.api_key or _env_key("ANTHROPIC_API_KEY")
        self._headers = {
            "x-api-key": self._api_key or "",
            "anthropic-version": _API_VERSION,
            "Content-Type": "application/json",
        }

    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": prompt},
        ]
        return self._messages_api(messages, system_prompt)

    def chat(self, messages: List[Dict[str, str]]) -> LLMResponse:
        anthropic_messages: List[Dict[str, Any]] = []
        system_prompt: Optional[str] = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                if system_prompt is None:
                    system_prompt = content
                else:
                    system_prompt += "\n\n" + content
            else:
                anthropic_messages.append({"role": role, "content": content})

        return self._messages_api(anthropic_messages, system_prompt)

    def supports(self, capability: ModelCapability) -> bool:
        if capability == ModelCapability.TEXT:
            return True
        if capability == ModelCapability.CODE:
            return True
        if capability == ModelCapability.TOOL_USE:
            return True
        if capability == ModelCapability.VISION:
            return "claude-3" in self.config.model or "claude-sonnet-4" in self.config.model
        return False

    def list_models(self) -> List[str]:
        return [self.config.model]

    def _messages_api(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        body: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if system_prompt:
            body["system"] = system_prompt

        payload = json.dumps(body).encode("utf-8")
        url = f"{_API_BASE}/messages"

        start = time.perf_counter()
        try:
            data = self._request_with_retry(url, payload)
        finally:
            latency_ms = (time.perf_counter() - start) * 1000.0

        content_blocks = data.get("content", [])
        text = ""
        for block in content_blocks:
            if block.get("type") == "text":
                text += block.get("text", "")

        usage = data.get("usage", {})
        tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        return LLMResponse(
            content=text,
            model=data.get("model", self.config.model),
            provider="anthropic",
            tokens_used=tokens_used,
            stop_reason=data.get("stop_reason", ""),
            latency_ms=latency_ms,
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

        error_block = detail.get("error", {})
        msg = error_block.get("message", str(exc))

        if status in (401, 403):
            raise LLMAuthError(f"Authentication failed: {msg}") from exc
        if status == 429:
            raise LLMRateLimitError(f"Rate limited: {msg}") from exc
        if status == 400 and any(
            kw in msg.lower() for kw in ("context", "token", "length", "too long")
        ):
            raise LLMContextLengthError(f"Context length exceeded: {msg}") from exc
        if status >= 500:
            raise LLMProviderError(f"Provider error {status}: {msg}") from exc

        raise LLMError(f"HTTP {status}: {msg}") from exc