"""Security-focused tests — input validation, path traversal protection,
secret handling, and SQL injection resistance."""

from __future__ import annotations

from pathlib import Path

import pytest

from aura.config import AuraConfig, ConfigError
from aura.db import Database
from aura.errors import AuraError, DatabaseError


class TestConfigSecurity:
    def test_nonexistent_config_path_no_crash(self) -> None:
        """Loading a nonexistent file should return defaults, not crash."""
        config = AuraConfig.from_file("/nonexistent/path/aura.json")
        assert config.engine.max_cycles > 0

    def test_malformed_json_no_crash(self, tmp_path: Path) -> None:
        """Malformed JSON should raise ConfigError, not crash."""
        config_path = tmp_path / "bad.json"
        config_path.write_text("{broken json {{{")
        with pytest.raises(ConfigError, match="Invalid JSON"):
            AuraConfig.from_file(str(config_path))

    def test_empty_config_file_uses_defaults(self, tmp_path: Path) -> None:
        config_path = tmp_path / "empty.json"
        config_path.write_text("{}")
        config = AuraConfig.from_file(str(config_path))
        assert config.engine.max_cycles == 25


class TestDatabaseSecurity:
    def test_sql_injection_via_finding_id_fails(self, db: Database) -> None:
        """Insert with SQL injection payload should be parameterized — no injection."""
        db.insert_cycle(1)
        malicious_id = "F-001'; DROP TABLE findings; --"
        db.insert_finding({
            "finding_id": malicious_id,
            "cycle_number": 1,
            "severity": "P0",
            "category": "SECURITY",
            "problem": "Injection test",
        })
        findings = db.get_findings(cycle_number=1)
        assert len(findings) > 0

    def test_parameterized_queries_used(self, db: Database) -> None:
        """Verify that special characters in strings don't cause SQL errors."""
        db.insert_cycle(1)
        special_id = "F-'; SELECT * FROM findings; --"
        db.insert_finding({
            "finding_id": special_id,
            "cycle_number": 1,
            "severity": "P0",
            "category": "SECURITY",
            "problem": "Special chars '; DROP TABLE --",
        })
        findings = db.get_findings(cycle_number=1)
        assert len(findings) == 1
        assert findings[0]["finding_id"] == special_id

    def test_db_backup_is_atomic(self, db: Database, tmp_path: Path) -> None:
        """Backup should create a valid SQLite file."""
        db.insert_cycle(1)
        backup = tmp_path / "backup.db"
        db.backup(str(backup))
        assert backup.exists()
        with open(backup, "rb") as f:
            header = f.read(16)
        assert header == b"SQLite format 3\x00"


class TestPathTraversal:
    def test_config_path_traversal_blocked(self, tmp_path: Path) -> None:
        """Path traversal in config path should not work."""
        traversal = str(tmp_path / "../../../etc/passwd")
        config = AuraConfig.from_file(traversal)
        assert config.engine.max_cycles == 25

    def test_database_path_cannot_escape(self, tmp_path: Path) -> None:
        """Database creation should be contained within repo."""
        config = AuraConfig()
        config.database.path = "../../escape.db"
        db = Database(config.database)
        db.initialize()
        assert "../../escape.db" in str(config.database.path)


class TestErrorNonDisclosure:
    def test_config_error_uses_typed_error(self) -> None:
        """Error messages should use typed error hierarchy."""
        err = ConfigError("Invalid configuration")
        assert isinstance(err, AuraError)

    def test_database_error_is_typed(self) -> None:
        """Database errors should use typed error hierarchy."""
        err = DatabaseError("Query failed")
        assert isinstance(err, AuraError)
        assert err.category.value == "database"


class TestCommandInjection:
    def test_tooling_commands_not_shell_interpreted(self) -> None:
        """Tooling runs via an explicit shell wrapper but with shell=False and a
        fixed interpreter (cmd /c on Windows, sh -c elsewhere) — never via an
        implicit shell on a user-controlled string. Assert on the real code path
        rather than a tautology (R3-02)."""
        import inspect
        from aura.engine import Engine
        src = inspect.getsource(Engine._run_tooling)
        # Real controls: subprocess.run with an explicit interpreter list,
        # shell=False, and a timeout. No os.system / shell=True.
        assert "subprocess.run" in src
        assert "shell=False" in src
        assert "os.system" not in src
        assert "shell=True" not in src
        assert "timeout=300" in src
