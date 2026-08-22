"""AURA v3.5 — Provider abstraction layer for LLM remediation.

Multiple provider support with fallback routing, circuit breaker,
rate limiting, and structured error taxonomy.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .errors import AuraError, ErrorCategory, ErrorSeverity, RetryDecision


class ProviderHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ProviderResponse:
    """Typed response from any LLM provider."""
    content: str
    model: str = ""
    tokens_used: int = 0
    provider_name: str = ""
    latency_ms: int = 0
    untrusted: bool = True
    error: str | None = None


@dataclass
class ProviderStatus:
    name: str
    health: ProviderHealth = ProviderHealth.UNKNOWN
    circuit_state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_success: str = ""
    last_failure: str = ""
    last_failure_reason: str = ""


class CircuitBreaker:
    """Stateful circuit breaker for provider calls."""

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        half_open_max: int = 1,
        rolling_window_seconds: float = 120.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._half_open_max = half_open_max
        self._rolling_window_seconds = rolling_window_seconds
        self._state = CircuitState.CLOSED
        self._failure_timestamps: list[float] = []
        self._last_failure_time: float = 0.0
        self._half_open_attempts: int = 0

    @property
    def state(self) -> CircuitState:
        return self._state

    def record_success(self) -> None:
        self._half_open_attempts = 0
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
        self._failure_timestamps = [
            ts for ts in self._failure_timestamps
            if time.time() - ts < self._rolling_window_seconds
        ]

    def record_failure(self) -> None:
        now = time.time()
        self._last_failure_time = now
        self._failure_timestamps = [
            ts for ts in self._failure_timestamps
            if now - ts < self._rolling_window_seconds
        ]
        self._failure_timestamps.append(now)

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_attempts += 1
            if self._half_open_attempts >= self._half_open_max:
                self._state = CircuitState.OPEN
        elif len(self._failure_timestamps) >= self._failure_threshold:
            self._state = CircuitState.OPEN

    def allow_request(self) -> bool:
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self._cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_attempts = 0
                return True
            return False
        return self._state == CircuitState.HALF_OPEN

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_timestamps.clear()
        self._half_open_attempts = 0


class BaseProvider(ABC):
    """Abstract base for LLM providers."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._circuit = CircuitBreaker()
        self._failure_count = 0
        self._success_count = 0
        self._last_success = ""
        self._last_failure = ""
        self._last_failure_reason = ""

    @property
    def status(self) -> ProviderStatus:
        health = ProviderHealth.HEALTHY
        if self._circuit.state == CircuitState.OPEN:
            health = ProviderHealth.UNHEALTHY
        elif self._circuit.state == CircuitState.HALF_OPEN:
            health = ProviderHealth.DEGRADED
        return ProviderStatus(
            name=self.name,
            health=health,
            circuit_state=self._circuit.state,
            failure_count=self._failure_count,
            success_count=self._success_count,
            last_success=self._last_success,
            last_failure=self._last_failure,
            last_failure_reason=self._last_failure_reason,
        )

    @abstractmethod
    def chat(self, system_prompt: str, user_message: str, max_tokens: int = 4000) -> ProviderResponse:
        ...

    def _wrap_call(self, fn, *args, **kwargs) -> ProviderResponse:
        if not self._circuit.allow_request():
            return ProviderResponse(
                content="",
                provider_name=self.name,
                error=f"Circuit breaker OPEN for provider {self.name}",
                untrusted=True,
            )
        result = fn(*args, **kwargs)
        if result.error:
            self._circuit.record_failure()
            self._failure_count += 1
            self._last_failure = datetime.now(timezone.utc).isoformat()
            self._last_failure_reason = result.error
        else:
            self._circuit.record_success()
            self._success_count += 1
            self._last_success = datetime.now(timezone.utc).isoformat()
        return result


class OpenAICompatibleProvider(BaseProvider):
    """OpenAI-compatible API provider with retry and backoff."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(name)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, system_prompt: str, user_message: str, max_tokens: int = 4000) -> ProviderResponse:
        import httpx
        import json

        def _do_call() -> ProviderResponse:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.1,
                "stream": False,
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            for attempt in range(self.max_retries):
                try:
                    resp = httpx.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers=headers,
                        timeout=self.timeout,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        return ProviderResponse(
                            content=content,
                            model=data.get("model", self.model),
                            tokens_used=data.get("usage", {}).get("total_tokens", 0),
                            provider_name=self.name,
                            latency_ms=0,
                            untrusted=True,
                        )
                    if resp.status_code == 429:
                        if attempt < self.max_retries - 1:
                            time.sleep(min(2 ** attempt, 30))
                            continue
                        return ProviderResponse(
                            content="",
                            provider_name=self.name,
                            error=f"Rate limited after {self.max_retries} retries",
                            untrusted=True,
                        )
                    return ProviderResponse(
                        content="",
                        provider_name=self.name,
                        error=f"HTTP {resp.status_code}: {resp.text[:300]}",
                        untrusted=True,
                    )
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        time.sleep(min(2 ** attempt, 10))
                        continue
                    return ProviderResponse(
                        content="",
                        provider_name=self.name,
                        error=f"Request failed: {e}",
                        untrusted=True,
                    )
            return ProviderResponse(
                content="",
                provider_name=self.name,
                error="Unexpected: exhausted retry loop",
                untrusted=True,
            )

        return self._wrap_call(_do_call)


class ProviderRegistry:
    """Registry of LLM providers with health tracking and fallback routing."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._priority_order: list[str] = []

    def register(self, provider: BaseProvider, priority: int = 0) -> None:
        self._providers[provider.name] = provider
        if provider.name not in self._priority_order:
            self._priority_order.append(provider.name)

    def get_healthy_provider(self) -> BaseProvider | None:
        for name in self._priority_order:
            provider = self._providers.get(name)
            if provider and provider._circuit.state != CircuitState.OPEN:
                return provider
        return None

    def get_all_statuses(self) -> dict[str, ProviderStatus]:
        return {name: p.status for name, p in self._providers.items()}

    def chat_with_fallback(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4000,
    ) -> ProviderResponse:
        provider = self.get_healthy_provider()
        if provider is None:
            return ProviderResponse(
                content="",
                provider_name="all",
                error="All providers unhealthy — no fallback available",
                untrusted=True,
            )
        return provider.chat(system_prompt, user_message, max_tokens)