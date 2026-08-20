"""
Token usage and cost tracking for the AURA audit engine.

Persists per-cycle and cumulative token/cost data to a JSON database so
audit cost transparency is maintained across cycles.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_ESTIMATED_PRICE_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    "openai": {
        "gpt-4o":           (0.0025,  0.0100),
        "gpt-4o-mini":      (0.00015, 0.00060),
        "gpt-4-turbo":      (0.0100,  0.0300),
        "gpt-4":            (0.0300,  0.0600),
        "gpt-4-32k":        (0.0600,  0.1200),
        "gpt-3.5-turbo":    (0.0005,  0.0015),
        "gpt-3.5-turbo-16k":(0.0030,  0.0040),
    },
    "anthropic": {
        "claude-sonnet-4-20250514": (0.003,  0.015),
        "claude-opus-4-20250514":   (0.015,  0.075),
        "claude-3-5-sonnet":        (0.003,  0.015),
        "claude-3-opus":            (0.015,  0.075),
        "claude-3-haiku":           (0.00025,0.00125),
        "claude-3-sonnet":          (0.003,  0.015),
    },
    "openrouter": {
        "_default": (0.002, 0.008),
    },
    "ollama": {
        "_default": (0.0, 0.0),
    },
}


class CostTracker:
    """Tracks token usage and estimated cost across audit cycles.

    Data is persisted to a JSON file so it survives engine resets.

    Attributes:
        db_path: Path to the cost-tracking JSON file.
    """

    def __init__(self, db_path: str = ".aura/state/cost-tracking.json") -> None:
        self._db_path = self._resolve_path(db_path)
        self._data = self._load()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def track_usage(
        self,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cycle: Optional[int] = None,
    ) -> None:
        """Record token usage for one completion call.

        Args:
            provider: Provider key (``openai``, ``anthropic``, etc.).
            model: Model identifier.
            tokens_in: Prompt tokens.
            tokens_out: Completion tokens.
            cycle: Current audit cycle number (optional).
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "tokens_total": tokens_in + tokens_out,
            "estimated_cost": self._estimate_cost(provider, model, tokens_in, tokens_out),
            "cycle": cycle,
        }

        self._data.setdefault("entries", []).append(entry)
        self._data.setdefault("cycles", {})

        if cycle is not None:
            cycle_key = str(cycle)
            cy = self._data["cycles"].setdefault(cycle_key, {
                "tokens_in": 0,
                "tokens_out": 0,
                "tokens_total": 0,
                "cost": 0.0,
                "calls": 0,
                "providers": {},
            })
            cy["tokens_in"] += tokens_in
            cy["tokens_out"] += tokens_out
            cy["tokens_total"] += tokens_in + tokens_out
            cy["cost"] += entry["estimated_cost"]
            cy["calls"] += 1
            pkey = f"{provider}/{model}"
            ps = cy["providers"].setdefault(pkey, {"tokens": 0, "cost": 0.0, "calls": 0})
            ps["tokens"] += tokens_in + tokens_out
            ps["cost"] += entry["estimated_cost"]
            ps["calls"] += 1

        self._save()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_cycle_cost(self, cycle: int) -> float:
        """Return the estimated cost for a specific audit cycle.

        Args:
            cycle: The cycle number (1-based).

        Returns:
            Estimated cost in USD.
        """
        cy = self._data.get("cycles", {}).get(str(cycle))
        return cy["cost"] if cy else 0.0

    def get_total_cost(self) -> float:
        """Return the cumulative estimated cost across all cycles.

        Returns:
            Estimated cost in USD.
        """
        total = 0.0
        for cy in self._data.get("cycles", {}).values():
            total += cy.get("cost", 0.0)
        return total

    def get_total_tokens(self) -> int:
        """Return the cumulative token count across all cycles."""
        total = 0
        for cy in self._data.get("cycles", {}).values():
            total += cy.get("tokens_total", 0)
        return total

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def format_report(self) -> str:
        """Produce a human-readable cost report suitable for the audit ledger.

        Returns:
            A multi-line string with per-cycle and cumulative cost data.
        """
        lines: List[str] = []
        cycles_data = self._data.get("cycles", {})

        if not cycles_data:
            return "No LLM cost data recorded."

        sorted_cycles = sorted(cycles_data.items(), key=lambda x: int(x[0]))
        total_cost = 0.0
        total_tokens = 0
        total_calls = 0

        lines.append("## LLM Cost Report")
        lines.append("")
        lines.append("| Cycle | Tokens In | Tokens Out | Total Tokens | Calls | Cost (USD) |")
        lines.append("|-------|-----------|------------|--------------|-------|------------|")

        for key, cy in sorted_cycles:
            ti = cy.get("tokens_in", 0)
            to = cy.get("tokens_out", 0)
            tt = cy.get("tokens_total", 0)
            calls = cy.get("calls", 0)
            cost = cy.get("cost", 0.0)
            total_cost += cost
            total_tokens += tt
            total_calls += calls
            lines.append(f"| {key} | {ti:,} | {to:,} | {tt:,} | {calls} | ${cost:.4f} |")

        lines.append(f"| **Total** | | | **{total_tokens:,}** | **{total_calls}** | **${total_cost:.4f}** |")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(db_path: str) -> Path:
        repo_root = os.environ.get("AURA_REPO_ROOT")
        if repo_root:
            return Path(repo_root) / db_path
        return Path(db_path)

    def _load(self) -> Dict[str, Any]:
        if self._db_path.exists():
            try:
                return json.loads(self._db_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"entries": [], "cycles": {}}

    def _save(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._db_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, default=str), encoding="utf-8")
        tmp.replace(self._db_path)

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_cost(
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
    ) -> float:
        provider_prices = _ESTIMATED_PRICE_PER_1K_TOKENS.get(provider, {})
        model_prices = provider_prices.get(model, provider_prices.get("_default", (0.0, 0.0)))
        price_in, price_out = model_prices
        return (tokens_in / 1000.0) * price_in + (tokens_out / 1000.0) * price_out