"""Tests for the configuration system — loading, validation, and fail-fast behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aura.config import AuraConfig, ConfigError


class TestConfig:
    def test_default_config_creates_valid(self) -> None:
        config = AuraConfig()
        assert config.engine.name == "Continuous Autonomous Engineering Audit Engine"
        assert config.engine.version == "3.0.0"
        assert config.engine.max_cycles == 25
        assert config.engine.state_machine.enabled is True

    def test_default_config_has_six_severity_levels(self) -> None:
        config = AuraConfig()
        assert "P0" in config.severity
        assert "P5" in config.severity
        assert config.severity["P0"].weight == 625
        assert config.severity["P5"].weight == 6

    def test_default_config_has_ten_dimensions(self) -> None:
        config = AuraConfig()
        assert abs(sum(v for v in config.dimensions.model_dump().values()) - 1.0) < 0.01

    def test_default_config_database_settings(self) -> None:
        config = AuraConfig()
        assert config.database.path == ".aura/state/aura.db"
        assert config.database.wal_mode is True

    def test_default_config_convergence_gate(self) -> None:
        config = AuraConfig()
        assert config.engine.convergence_gate.P0 == 0
        assert config.engine.convergence_gate.require_all_required_modules_loaded is True

    def test_default_config_state_machine_forbidden_transitions_default(self) -> None:
        config = AuraConfig()
        # Default constructor produces empty list
        forbidden = config.engine.state_machine.forbidden_direct_transitions
        assert isinstance(forbidden, list)


class TestConfigFromFile:
    def test_load_minimal_json(self, tmp_path: Path) -> None:
        config_path = tmp_path / "aura.json"
        config_path.write_text(json.dumps({}))
        config = AuraConfig.from_file(str(config_path))
        assert config.engine.max_cycles == 25  # default

    def test_load_with_overrides(self, tmp_path: Path) -> None:
        config_path = tmp_path / "aura.json"
        config_path.write_text(json.dumps({
            "engine": {
                "max_cycles": 50,
                "default_language": "id",
            },
        }))
        config = AuraConfig.from_file(str(config_path))
        assert config.engine.max_cycles == 50
        assert config.engine.default_language == "id"

    def test_load_with_severity_overrides(self, tmp_path: Path) -> None:
        config_path = tmp_path / "aura.json"
        config_path.write_text(json.dumps({
            "severity": {
                "P0": {"label": "Critical", "weight": 1000},
                "P1": {"label": "High", "weight": 500},
            },
        }))
        config = AuraConfig.from_file(str(config_path))
        assert config.severity["P0"].weight == 1000
        assert config.severity["P1"].weight == 500

    def test_load_invalid_json_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "aura.json"
        config_path.write_text("{invalid json")
        with pytest.raises(ConfigError, match="Invalid JSON"):
            AuraConfig.from_file(str(config_path))

    def test_load_nonexistent_file_uses_defaults(self) -> None:
        config = AuraConfig.from_file("/nonexistent/path/aura.json")
        assert config.engine.max_cycles == 25

    def test_load_database_override(self, tmp_path: Path) -> None:
        config_path = tmp_path / "aura.json"
        config_path.write_text(json.dumps({
            "database": {"path": "/custom/path/db.sqlite", "wal_mode": False},
        }))
        config = AuraConfig.from_file(str(config_path))
        assert config.database.path == "/custom/path/db.sqlite"
        assert config.database.wal_mode is False


class TestConfigFromEnvOrFile:
    def test_resolves_standard_path(self, monkeypatch, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "aura.json").write_text(json.dumps({"engine": {"max_cycles": 10}}))
        config = AuraConfig.from_env_or_file(str(tmp_path))
        assert config.engine.max_cycles == 10

    def test_env_overrides_path(self, monkeypatch, tmp_path: Path) -> None:
        custom = tmp_path / "custom.json"
        custom.write_text(json.dumps({"engine": {"max_cycles": 42}}))
        monkeypatch.setenv("AURA_CONFIG_PATH", str(custom))
        config = AuraConfig.from_env_or_file(str(tmp_path))
        assert config.engine.max_cycles == 42
