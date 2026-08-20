"""
AURA LLM Provider Abstraction Layer.

Provides a unified interface for multiple AI providers (OpenAI, Anthropic,
Ollama, OpenRouter) with automatic provider detection, cost tracking, and
multi-agent orchestration support for the AURA audit engine.
"""

from .base import BaseLLMProvider, LLMConfig, LLMResponse, ModelCapability
from .manager import LLMManager
from .cost_tracker import CostTracker

__all__ = [
    "BaseLLMProvider",
    "LLMConfig",
    "LLMResponse",
    "ModelCapability",
    "LLMManager",
    "CostTracker",
]