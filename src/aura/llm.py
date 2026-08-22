"""AURA LLM client — connects to local LLM providers for autonomous audit.

Supports OpenAI-compatible APIs (9router, vLLM, Ollama, etc).
All LLM output is treated as UNTRUSTED CLAIM until validated by evidence.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class LLMResponse:
    content: str
    model: str
    tokens_used: int = 0
    untrusted: bool = True  # Always UNTRUSTED until evidence validates it


class LLMClient:
    """OpenAI-compatible LLM client for autonomous audit cycles."""

    def __init__(
            self,
            base_url: str | None = None,
            api_key: str | None = None,
            model: str | None = None,
            timeout: float = 120.0,
        ) -> None:
            import os
            self.base_url = (base_url or os.environ.get("AURA_LLM_URL", "")).rstrip("/") if (base_url or os.environ.get("AURA_LLM_URL")) else ""
            self.api_key = api_key or os.environ.get("AURA_LLM_KEY", "")
            self.model = model or os.environ.get("AURA_LLM_MODEL", "")
            self.timeout = timeout

    def chat(self, system_prompt: str, user_message: str, max_tokens: int = 4000) -> LLMResponse:
        """Send a chat completion request. Returns UNTRUSTED response."""
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
                return LLMResponse(
                    content=content,
                    model=data.get("model", self.model),
                    tokens_used=data.get("usage", {}).get("total_tokens", 0),
                    untrusted=True,  # ALWAYS untrusted
                )
            return LLMResponse(content=f"LLM_ERROR: HTTP {resp.status_code}: {resp.text[:200]}",
                               model=self.model, untrusted=True)
        except Exception as e:
            return LLMResponse(content=f"LLM_ERROR: {e}", model=self.model, untrusted=True)


# ── Autonomous Audit Prompts ────────────────────────────────────────────────

AUDIT_SYSTEM_PROMPT = """You are AURA's Autonomous Auditor — a specialized code audit agent.

Your task is to audit a codebase and produce structured findings. You MUST respond
in valid JSON format. Every claim you make must be evidence-backed with specific
file paths and line numbers.

IMPORTANT: Your output is UNTRUSTED until independently verified by tool execution.
Do NOT claim convergence, do NOT claim "production ready", do NOT claim fixes are
complete without evidence.

Respond with this EXACT JSON structure:
{
  "findings": [
    {
      "severity": "P0|P1|P2|P3|P4|P5",
      "category": "SECURITY|CORRECTNESS|ARCHITECTURE|PERFORMANCE|RELIABILITY|OBSERVABILITY|TESTING|MAINTAINABILITY|OPS|DATA_INTEGRITY",
      "file": "path/to/file.ts",
      "line": 42,
      "problem": "Clear description of the issue",
      "evidence": "The exact code or situation that proves this finding",
      "remediation": "Specific steps to fix this issue",
      "confidence": "HIGH|MEDIUM|LOW"
    }
  ],
  "summary": "Brief summary of the audit, including files analyzed and key themes",
  "recommendations": ["List of prioritized recommendations"]
}"""

REMEDIATE_SYSTEM_PROMPT = """You are AURA's Autonomous Remediator.

Given a list of findings, produce specific code fixes. For each finding provide:
- The exact code change needed (old code → new code)
- The file path and line numbers
- How to verify the fix

Respond in JSON:
{
  "fixes": [
    {
      "finding_id": "F-xxx",
      "file": "path/to/file.ts",
      "line_start": 42,
      "line_end": 42,
      "old_code": "the problematic code",
      "new_code": "the fixed code",
      "explanation": "Why this fix works",
      "verification": "How to verify this fix"
    }
  ]
}"""

VERIFY_SYSTEM_PROMPT = """You are AURA's Independent Verifier.

Given a list of claimed fixes, verify EACH one independently. Do NOT trust the
remediator's claims. For each fix, evaluate:
1. Does the fix actually address the root cause?
2. Could this fix introduce new issues?
3. Is the fix complete or partial?

Respond in JSON:
{
  "verifications": [
    {
      "finding_id": "F-xxx",
      "verdict": "VERIFIED|REJECTED|PARTIAL",
      "reason": "Detailed explanation of verification result",
      "confidence": "HIGH|MEDIUM|LOW"
    }
  ]
}"""


# ── LLM-Powered Audit Engine ────────────────────────────────────────────────

class AutonomousLoop:
    """LLM-powered autonomous audit-remediate-verify loop.

    Runs cycles until convergence or human blocker detected.
    All LLM output is treated as UNTRUSTED CLAIM.
    """

    def __init__(self, llm: LLMClient, repo_root: str) -> None:
        self.llm = llm
        self.repo_root = repo_root

    def audit_with_llm(self, context: str) -> dict[str, Any]:
        """Run autonomous audit using LLM. Returns UNTRUSTED findings."""
        resp = self.llm.chat(AUDIT_SYSTEM_PROMPT, context, max_tokens=4000)
        content = resp.content

        # Strategy 1: markdown code block
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if m:
            try:
                parsed: dict[str, Any] = json.loads(m.group(1).strip())
                return parsed
            except json.JSONDecodeError:
                pass

        # Strategy 2: find outermost JSON object
        # Find the first { and match to the last }
        start = content.find('{')
        if start >= 0:
            # Count braces to find the matching closing brace
            depth = 0
            end = start
            for i in range(start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            json_str = content[start:end]
            try:
                parsed = json.loads(json_str)
                return parsed
            except json.JSONDecodeError:
                pass

        return {"findings": [], "summary": f"LLM parse error",
                "recommendations": [], "_untrusted": True, "_raw": content[:300]}

    def remediate_with_llm(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        """Run autonomous remediation using LLM. Returns UNTRUSTED fixes."""
        context = json.dumps({"findings": findings}, indent=2)
        resp = self.llm.chat(REMEDIATE_SYSTEM_PROMPT, context, max_tokens=4000)
        try:
            parsed: dict[str, Any] = json.loads(resp.content)
            return parsed
        except json.JSONDecodeError:
            return {"fixes": [], "_untrusted": True}

    def verify_with_llm(self, findings: list[dict[str, Any]], fixes: list[dict[str, Any]]) -> dict[str, Any]:
        """Run independent verification using LLM. Cross-checks fixes."""
        context = json.dumps({"findings": findings, "fixes": fixes}, indent=2)
        resp = self.llm.chat(VERIFY_SYSTEM_PROMPT, context, max_tokens=4000)
        try:
            parsed = json.loads(resp.content)
            return parsed  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return {"verifications": [], "_untrusted": True}


# ── Provider-backed adapter (canonical LLM client architecture) ─────────────

class ProviderBackedLLMClient:
    """Module-level adapter: ProviderRegistry → LLMResponse protocol.

    Canonical way to give the engine/autonomous loop an LLM: the provider
    layer (retry classification, jitter, circuit breaker, fallback, health)
    is the single place where transport resilience lives. This adapter only
    converts types — it adds NO retry of its own (prevents retry storms).
    """

    def __init__(self, registry: Any, default_model: str = "") -> None:
        self.registry = registry
        self.default_model = default_model

    def chat(self, system_prompt: str, user_message: str, max_tokens: int = 4000) -> LLMResponse:
        resp = self.registry.chat_with_fallback(system_prompt, user_message, max_tokens)
        if resp.error:
            return LLMResponse(
                content=f"LLM_ERROR: {resp.error}",
                model=resp.model or self.default_model,
                tokens_used=0,
                untrusted=True,
            )
        return LLMResponse(
            content=resp.content,
            model=resp.model or self.default_model,
            tokens_used=resp.tokens_used,
            untrusted=True,
        )