"""
Ollama LLM provider for locally hosted models.

Communicates with the Ollama REST API for chat completions and model management.
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
    LLMConnectionError,
    LLMError,
    LLMProviderError,
)

_DEFAULT_HOST = "http://localhost:11434"


def _env_host() -> str:
    return os.environ.get("OLLAMA_HOST", _DEFAULT_HOST).rstrip("/")


class OllamaProvider(BaseLLMProvider):
    """Provider for Ollama-based local models.

    Config fields honoured:
        - ``api_base``: Host URL override (falls back to ``OLLAMA_HOST`` or
          ``http://localhost:11434``).
        - ``model``: Model name (e.g. ``llama3.1``, ``codellama``).
        - ``temperature``, ``max_tokens``, ``timeout_seconds``.
    """

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        self._host = (config.api_base or _env_host()).rstrip("/")
        self._headers = {"Content-Type": "application/json"}

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
        self._ensure_model_pulled()

        body = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }

        payload = json.dumps(body).encode("utf-8")
        url = f"{self._host}/api/chat"

        start = time.perf_counter()
        try:
            data = self._do_request(url, payload)
        finally:
            latency_ms = (time.perf_counter() - start) * 1000.0

        message = data.get("message", {})
        tokens_used = (
            data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
        )

        return LLMResponse(
            content=message.get("content", "") or "",
            model=data.get("model", self.config.model),
            provider="ollama",
            tokens_used=tokens_used,
            stop_reason=data.get("done_reason", "stop"),
            latency_ms=latency_ms,
        )

    def supports(self, capability: ModelCapability) -> bool:
        return capability in (ModelCapability.TEXT, ModelCapability.CODE)

    def list_models(self) -> List[str]:
        """Retrieve the list of locally available Ollama models."""
        url = f"{self._host}/api/tags"
        try:
            data = self._do_request(url, None, method="GET")
        except (LLMError, LLMConnectionError):
            return [self.config.model]

        models = data.get("models", [])
        return [m.get("name", m.get("model", "unknown")) for m in models]

    def _ensure_model_pulled(self) -> None:
        """Pull the configured model from Ollama if it is not already available."""
        available = self.list_models()
        if self.config.model in available:
            return

        url = f"{self._host}/api/pull"
        body = json.dumps({"name": self.config.model, "stream": False}).encode("utf-8")
        self._do_request(url, body, method="POST")

    def _do_request(
        self,
        url: str,
        payload: Optional[bytes],
        method: str = "POST",
    ) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=payload,
            headers=self._headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                body = resp.read().decode("utf-8")
                if not body.strip():
                    return {}
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
            except Exception:
                detail = {}
            msg = detail.get("error", str(exc))
            raise LLMProviderError(f"Ollama error {exc.code}: {msg}") from exc
        except urllib.error.URLError as exc:
            raise LLMConnectionError(
                f"Cannot reach Ollama at {self._host}: {exc.reason}"
            ) from exc