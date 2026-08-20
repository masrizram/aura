"""
LLM Manager — provider factory, auto-detection, and cycle orchestration.

Resolves providers from environment variables or configuration files and
provides convenience methods for running AURA audit cycles through any LLM.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseLLMProvider, LLMConfig, LLMResponse


class LLMManagerError(Exception):
    """Raised when the LLM Manager cannot resolve a provider."""


class LLMManager:
    """Factory for LLM providers with automatic detection.

    Resolution order when not given an explicit provider name:

    1. ``AURA_LLM_PROVIDER`` environment variable
    2. ``OPENAI_API_KEY`` → OpenAI
    3. ``ANTHROPIC_API_KEY`` → Anthropic
    4. ``OLLAMA_HOST`` or localhost:11434 reachable → Ollama
    5. Fall back to config file at ``.aura/llm-config.json``

    Attributes:
        config_path: Path to the LLM configuration file.
        _config: Loaded configuration dict.
        _providers: Cache of previously created providers keyed by name.
    """

    _DEFAULT_CONFIG_PATHS = [
        ".aura/llm-config.json",
        "config/llm-config.json",
    ]

    _DEFAULT_MODELS: Dict[str, str] = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-20250514",
        "ollama": "llama3.1",
        "openrouter": "openai/gpt-4o",
    }

    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialise the LLM Manager.

        Args:
            config_path: Path to the JSON config file. If ``None``, the manager
                searches ``.aura/llm-config.json`` and ``config/llm-config.json``.
        """
        self._config: Dict[str, Any] = {}
        self._providers: Dict[str, BaseLLMProvider] = {}

        if config_path:
            self._load_config(config_path)
        else:
            for candidate in self._DEFAULT_CONFIG_PATHS:
                abs_path = self._resolve_project_path(candidate)
                if abs_path and abs_path.exists():
                    self._load_config(str(abs_path))
                    break

    # ------------------------------------------------------------------
    # Provider factory
    # ------------------------------------------------------------------

    def get_provider(
        self,
        provider_name: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> BaseLLMProvider:
        """Return a provider instance for the given name or auto-detect.

        Args:
            provider_name: ``openai``, ``anthropic``, ``ollama``, or
                ``openrouter``. Auto-detected if ``None``.
            model_override: Override the default model for the detected provider.

        Returns:
            A concrete ``BaseLLMProvider`` instance.

        Raises:
            LLMManagerError: If no provider can be resolved.
        """
        if provider_name is None:
            provider_name = self.auto_detect_provider_name()

        cache_key = f"{provider_name}:{model_override or ''}"
        if cache_key in self._providers:
            return self._providers[cache_key]

        config = self._build_config(provider_name, model_override)
        provider = self._instantiate_provider(config)
        self._providers[cache_key] = provider
        return provider

    def auto_detect(self) -> BaseLLMProvider:
        """Auto-detect the best available provider and return it.

        Returns:
            A concrete ``BaseLLMProvider`` instance.

        Raises:
            LLMManagerError: If no provider can be detected.
        """
        return self.get_provider(provider_name=None)

    def auto_detect_provider_name(self) -> str:
        """Return the name of the best available provider without constructing it.

        Returns:
            One of ``openai``, ``anthropic``, ``ollama``, ``openrouter``.
        """
        if os.environ.get("AURA_LLM_PROVIDER"):
            return os.environ["AURA_LLM_PROVIDER"].strip().lower()

        if self._config.get("provider"):
            return str(self._config["provider"]).strip().lower()

        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("OPENROUTER_API_KEY"):
            return "openrouter"

        ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        if self._host_reachable(ollama_host):
            return "ollama"

        raise LLMManagerError(
            "No LLM provider detected. Set AURA_LLM_PROVIDER, "
            "OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY, "
            "or ensure Ollama is running at localhost:11434."
        )

    # ------------------------------------------------------------------
    # Agent and cycle helpers
    # ------------------------------------------------------------------

    def run_cycle(
        self,
        prompt: str,
        provider_name: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> LLMResponse:
        """Send a complete audit cycle prompt to the LLM.

        This is the primary entry point for single-agent (non-multi-agent)
        audit cycles.

        Args:
            prompt: The full generated cycle prompt (from ``Generate-CyclePrompt``).
            provider_name: Optional explicit provider.
            model_override: Optional model override.

        Returns:
            The LLM's ``LLMResponse``.
        """
        provider = self.get_provider(provider_name, model_override)
        system = (
            "You are an autonomous repository audit and remediation agent "
            "executing one cycle of a continuous engineering audit loop. "
            "Follow all instructions in the prompt precisely. "
            "Do not fabricate evidence. Use evidence-based language. "
            "Do not claim 100% anything."
        )
        return provider.complete(prompt, system_prompt=system)

    def run_agent(
        self,
        agent_file: str,
        context: Dict[str, Any],
        provider_name: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> LLMResponse:
        """Load an agent definition from a ``.md`` file, inject context, and
        send it to the LLM.

        The agent file is a Markdown file (e.g. ``src/agents/independent-auditor.md``)
        that defines the agent's role, mandate, method, and output format.

        Args:
            agent_file: Path to the agent ``.md`` file (relative to repo root).
            context: Dict of context variables to inject (e.g. ``findings``,
                ``git_status``, ``cycle_info``).
            provider_name: Optional explicit provider.
            model_override: Optional model override.

        Returns:
            The LLM's ``LLMResponse``.
        """
        resolved = self._resolve_project_path(agent_file)
        if resolved is None or not resolved.exists():
            raise LLMManagerError(f"Agent file not found: {agent_file}")

        system_prompt = resolved.read_text(encoding="utf-8")

        if context:
            lines = ["", "## INJECTED CONTEXT", ""]
            for key, value in context.items():
                lines.append(f"### {key}")
                if isinstance(value, str):
                    lines.append(value)
                else:
                    lines.append(json.dumps(value, indent=2))
                lines.append("")
            system_prompt += "\n".join(lines)

        provider = self.get_provider(provider_name, model_override)
        return provider.complete("Execute your audit mandate on the provided context.", system_prompt=system_prompt)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _load_config(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self._config = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            raise LLMManagerError(f"Failed to load LLM config from {path}: {exc}") from exc

    @staticmethod
    def _resolve_project_path(relative: str) -> Optional[Path]:
        repo_root = os.environ.get("AURA_REPO_ROOT")
        if repo_root:
            return Path(repo_root) / relative

        for root_candidate in (Path.cwd(), Path(__file__).resolve().parent.parent.parent.parent):
            candidate = root_candidate / relative
            if candidate.exists():
                return candidate

        return Path(relative)

    @staticmethod
    def _host_reachable(url: str) -> bool:
        import urllib.request as _ur

        try:
            req = _ur.Request(url, method="HEAD")
            _ur.urlopen(req, timeout=1.0)
            return True
        except Exception:
            return False

    def _build_config(
        self,
        provider_name: str,
        model_override: Optional[str],
    ) -> LLMConfig:
        provider_section = self._config.get("providers", {}).get(provider_name, {})
        multi_agent = self._config.get("multi_agent", {})

        api_key = provider_section.get("api_key") or self._config.get("api_key")
        api_base = provider_section.get("api_base") or self._config.get("api_base")

        rate_limit = self._config.get("rate_limit", {})
        max_retries = rate_limit.get("max_retries", 3)

        if max_retries is not None and max_retries > 0:
            pass

        return LLMConfig(
            provider=provider_name,
            model=model_override
            or provider_section.get("model")
            or self._config.get("model")
            or self._DEFAULT_MODELS.get(provider_name, "gpt-4o"),
            api_key=api_key,
            api_base=api_base,
            temperature=float(
                provider_section.get("temperature", self._config.get("temperature", 0.0))
            ),
            max_tokens=int(
                provider_section.get("max_tokens", self._config.get("max_tokens", 4096))
            ),
            timeout_seconds=int(
                provider_section.get("timeout_seconds", self._config.get("timeout_seconds", 300))
            ),
        )

    def _instantiate_provider(self, config: LLMConfig) -> BaseLLMProvider:
        if config.provider == "openai":
            from .providers.openai import OpenAIProvider
            return OpenAIProvider(config)
        elif config.provider == "anthropic":
            from .providers.anthropic import AnthropicProvider
            return AnthropicProvider(config)
        elif config.provider == "ollama":
            from .providers.ollama import OllamaProvider
            return OllamaProvider(config)
        elif config.provider == "openrouter":
            from .providers.openrouter import OpenRouterProvider
            return OpenRouterProvider(config)
        else:
            raise LLMManagerError(
                f"Unknown provider: {config.provider}. "
                f"Supported: openai, anthropic, ollama, openrouter."
            )