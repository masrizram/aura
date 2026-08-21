"""AURA configuration system — typed, validated, fail-fast.

All configuration is loaded from aura.json (or environment overrides)
and validated at startup. Invalid config causes immediate exit.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

# ── Severity ────────────────────────────────────────────────────────────────


class SeverityConfig(BaseModel):
    label: str
    weight: int


# ── Dimension ───────────────────────────────────────────────────────────────


class DimensionConfig(BaseModel):
    Architecture: float = 0.14
    Correctness: float = 0.16
    Security: float = 0.18
    Reliability: float = 0.12
    Performance: float = 0.08
    Testing: float = 0.12
    Observability: float = 0.06
    Operations: float = 0.06
    Maintainability: float = 0.04
    Documentation: float = 0.04


# ── State Machine Config ────────────────────────────────────────────────────


class ForbiddenTransition(BaseModel):
    from_: str = Field(alias="from")
    to: str
    reason: str


class StateMachineConfig(BaseModel):
    enabled: bool = True
    enforce_finding_transitions: bool = True
    enforce_gate_transitions: bool = True
    enforce_classification_transitions: bool = True
    max_score_increase_per_cycle: int = 15
    require_evidence_for_gate_flip: bool = True
    max_consecutive_counter_increase: int = 1
    forbidden_direct_transitions: list[ForbiddenTransition] = Field(default_factory=list)


# ── Engine Config ───────────────────────────────────────────────────────────


class ScaleConfig(BaseModel):
    warn_file_count: int = 500
    require_chunked_audit_above: int = 2000
    require_prioritized_audit_above: int = 5000
    track_audited_file_count: bool = True


class ToolingConfig(BaseModel):
    execute_before_verification: bool = True
    capture_exit_codes: bool = True
    auto_detect_commands: bool = True
    required_pass_commands: list[str] = Field(default_factory=list)


class ScopeConfig(BaseModel):
    validate_audit_scope: bool = True
    min_audit_pct_for_convergence: int = 80
    warn_below_pct: int = 50


class AuditConfig(BaseModel):
    enforce_full_audit_every_cycle: bool = True
    require_fresh_adversarial_review_every_cycle: bool = True
    require_independent_discovery_every_cycle: bool = True
    zero_open_findings_does_not_prove_zero_undiscovered: bool = True


class ConvergenceGateConfig(BaseModel):
    P0: int = 0
    P1: int = 0
    P2: int = 0
    require: list[str] = Field(default_factory=list)
    require_all_required_modules_loaded: bool = True
    allow_experimental_missing: bool = True
    allow_optional_missing: bool = True


class EngineConfig(BaseModel):
    name: str = "Continuous Autonomous Engineering Audit Engine"
    version: str = "3.0.0"
    default_language: str = "en"
    languages: dict[str, str] = Field(
        default_factory=lambda: {
            "en": "English",
            "id": "Bahasa Indonesia",
            "ja": "日本語",
            "zh-CN": "简体中文",
        }
    )
    max_cycles: int = 25
    max_cycles_without_progress: int = 3
    min_independent_cycles_for_convergence: int = 3
    consecutive_converged_cycles_required: int = 2
    state_machine: StateMachineConfig = Field(default_factory=StateMachineConfig)
    scale: ScaleConfig = Field(default_factory=ScaleConfig)
    tooling: ToolingConfig = Field(default_factory=ToolingConfig)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    convergence_gate: ConvergenceGateConfig = Field(default_factory=ConvergenceGateConfig)


# ── Database Config ─────────────────────────────────────────────────────────


class DatabaseConfig(BaseModel):
    path: str = ".aura/state/aura.db"
    wal_mode: bool = True
    foreign_keys: bool = True
    journal_mode: str = "wal"


# ── Notifications Config ────────────────────────────────────────────────────


class NotificationsConfig(BaseModel):
    enabled: bool = True
    config_path: str = ".aura/notifications-config.json"
    rate_limit_seconds: int = 300
    generate_status_badge: bool = True
    status_badge_output: str = "STATUS.md"


# ── Root Config ─────────────────────────────────────────────────────────────


class AuraConfig(BaseModel):
    """Root configuration model — validated at startup."""

    engine: EngineConfig = Field(default_factory=EngineConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    severity: dict[str, SeverityConfig] = Field(default_factory=dict)
    dimensions: DimensionConfig = Field(default_factory=DimensionConfig)

    @model_validator(mode="after")
    def validate_severity_weights(self) -> AuraConfig:
        if not self.severity:
            self.severity = {
                "P0": SeverityConfig(label="Catastrophic / Immediate Blocker", weight=625),
                "P1": SeverityConfig(label="Critical", weight=405),
                "P2": SeverityConfig(label="High", weight=216),
                "P3": SeverityConfig(label="Medium", weight=90),
                "P4": SeverityConfig(label="Low", weight=30),
                "P5": SeverityConfig(label="Optimization / Polish", weight=6),
            }
        return self

    @classmethod
    def from_file(cls, path: str | Path) -> AuraConfig:
        """Load and validate configuration from a JSON file."""
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in {config_path}: {exc}") from exc

        # Merge the nested structure into our flat model
        merged: dict[str, Any] = {}

        # Engine
        engine_raw = raw.get("engine", {})
        merged["engine"] = engine_raw

        # Database
        merged["database"] = {
            "path": raw.get("database", {}).get("path", ".aura/state/aura.db"),
            "wal_mode": raw.get("database", {}).get("wal_mode", True),
            "foreign_keys": raw.get("database", {}).get("foreign_keys", True),
        }

        # Notifications
        merged["notifications"] = raw.get("notifications", {})

        # Severity
        severity_raw = raw.get("severity", {})
        merged["severity"] = {
            k: {"label": v.get("label", k), "weight": v.get("weight", 0)}
            for k, v in severity_raw.items()
        }

        # Dimensions
        merged["dimensions"] = raw.get("dimensions", {})

        try:
            return cls.model_validate(merged)
        except ValidationError as exc:
            raise ConfigError(f"Configuration validation failed: {exc}") from exc

    @classmethod
    def from_env_or_file(cls, repo_root: str | Path) -> AuraConfig:
        """Load config from standard locations, with env overrides."""
        root = Path(repo_root)
        aura_config_env = os.environ.get("AURA_CONFIG_PATH", "")
        if aura_config_env:
            config_path = aura_config_env
        elif (root / "config" / "aura.json").exists():
            config_path = str(root / "config" / "aura.json")
        elif (root / "aura.json").exists():
            config_path = str(root / "aura.json")
        else:
            config_path = str(root / "config" / "aura.json")
        return cls.from_file(config_path)


from .errors import ConfigError as _CfgErr

# Re-export for convenience
ConfigError = _CfgErr
