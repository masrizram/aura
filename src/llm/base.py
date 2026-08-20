"""
Abstract base interface for LLM providers.

All providers must implement this interface to be usable by the AURA
LLM Manager. The interface supports text completion, chat, capability
detection, and model listing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ModelCapability(Enum):
    """Capabilities a model or provider may support."""

    TEXT = "text"
    CODE = "code"
    TOOL_USE = "tool_use"
    VISION = "vision"


@dataclass
class LLMResponse:
    """Standardised response from any LLM provider.

    Attributes:
        content: The primary text content of the response.
        model: The model identifier used (e.g. ``gpt-4o``).
        provider: The provider name (e.g. ``openai``).
        tokens_used: Total tokens consumed (prompt + completion).
        stop_reason: Reason the generation stopped (``stop``, ``length``, etc.).
        tool_calls: Structured tool-call records if the model used tools.
        latency_ms: Round-trip latency in milliseconds.
    """

    content: str
    model: str
    provider: str
    tokens_used: int = 0
    stop_reason: str = ""
    tool_calls: List[Dict] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class LLMConfig:
    """Configuration for an LLM provider.

    Attributes:
        provider: Provider key (``openai``, ``anthropic``, ``ollama``, ``openrouter``).
        model: Model name (e.g. ``gpt-4o``, ``claude-sonnet-4-20250514``).
        api_key: API key. If ``None`` the provider resolves it from the environment.
        api_base: Base URL override for OpenAI-compatible APIs or proxies.
        temperature: Sampling temperature (0.0 = deterministic).
        max_tokens: Maximum tokens in the completion.
        timeout_seconds: HTTP request timeout.
    """

    provider: str
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout_seconds: int = 300


class LLMError(Exception):
    """Base exception for all LLM provider errors."""


class LLMAuthError(LLMError):
    """Authentication / invalid API key."""


class LLMRateLimitError(LLMError):
    """Rate limit exceeded."""


class LLMContextLengthError(LLMError):
    """Prompt exceeds the model's context window."""


class LLMConnectionError(LLMError):
    """Network or connectivity issue."""


class LLMProviderError(LLMError):
    """Provider-internal error (5xx or unexpected response)."""


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers.

    Subclasses must implement at minimum :meth:`complete` and :meth:`chat`.
    The :meth:`supports` and :meth:`list_models` methods have default
    implementations that may be overridden for accuracy.
    """

    def __init__(self, config: LLMConfig) -> None:
        """Initialise the provider with its configuration.

        Args:
            config: An ``LLMConfig`` instance with provider, model, and credentials.
        """
        self.config = config

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> LLMResponse:
        """Send a single-turn text completion request.

        Args:
            prompt: The user prompt / instruction.
            system_prompt: Optional system-level instruction.

        Returns:
            A standardised ``LLMResponse``.
        """

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]]) -> LLMResponse:
        """Send a multi-turn chat request.

        Args:
            messages: List of message dicts with ``role`` and ``content`` keys.

        Returns:
            A standardised ``LLMResponse``.
        """

    def supports(self, capability: ModelCapability) -> bool:
        """Check whether this provider/model supports a given capability.

        The default implementation returns ``False`` for all capabilities.
        Override to advertise real capabilities.

        Args:
            capability: The capability to check.

        Returns:
            ``True`` if supported.
        """
        return False

    def list_models(self) -> List[str]:
        """Return the list of available models for this provider.

        The default implementation returns a single-element list containing
        the currently configured model. Override if the provider has a
        model-listing endpoint.

        Returns:
            List of model identifiers.
        """
        return [self.config.model]