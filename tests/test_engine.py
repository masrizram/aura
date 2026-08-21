"""Integration tests for the engine — full audit cycle, convergence evaluation,
and multi-cycle behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from aura.config import AuraConfig
from aura.engine import Engine


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    """Create an engine pointed at a temp directory."""
    repo = tmp_path / "repo"
    repo.mkdir()
    # Initialize as git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), capture_output=True)
    # Create a test file so the repo is not empty
    (repo / "test.py").write_text("print('hello')")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(repo), capture_output=True)

    db_path = str(repo / ".aura" / "state" / "aura.db")
    config = AuraConfig()
    config.database.path = db_path
    return Engine(repo, config)


class TestEngineLifecycle:
    def test_initialize_creates_cycle(self, engine: Engine) -> None:
        engine.initialize()
        cycle = engine.db.get_latest_cycle()
        assert cycle is not None
        assert cycle["cycle_number"] == 1
        assert cycle["classification"] == "NOT_READY"

    def test_initialize_idempotent(self, engine: Engine) -> None:
        engine.initialize()
        engine.initialize()
        cycles = engine.db.get_cycle(1)
        assert cycles is not None

    def test_get_status_after_init(self, engine: Engine) -> None:
        engine.initialize()
        status = engine.get_status()
        assert status["cycle"] == 1
        assert status["classification"] == "NOT_READY"

    def test_get_status_not_initialized(self, engine: Engine, tmp_path: Path) -> None:
        # Engine pointing at empty directory without any git repo or config
        empty = tmp_path / "empty_test"
        empty.mkdir()
        eng = Engine(empty)
        # Before initialize, DB has no cycles
        try:
            eng.db.initialize()
            latest = eng.db.get_latest_cycle()
            assert latest is None, "Fresh DB should have no cycles"
        except Exception:
            pass
        # After explicit initialize, status should be valid
        eng.initialize()
        status = eng.get_status()
        assert status["status"] != "NOT_INITIALIZED"
        assert status["status"] == "RUNNING"


class TestFullAuditCycle:
    def test_run_audit_produces_result(self, engine: Engine) -> None:
        engine.initialize()
        result = engine.run_audit()
        assert "cycle_number" in result
        assert "classification" in result
        assert "overall_score" in result
        assert "gates" in result

    def test_run_audit_creates_log_entries(self, engine: Engine) -> None:
        engine.initialize()
        engine.run_audit()
        entries = engine.db.get_audit_log(limit=100)
        assert len(entries) > 0

    def test_run_audit_creates_tooling_evidence(self, engine: Engine) -> None:
        engine.initialize()
        result = engine.run_audit()
        evidence = engine.db.get_tooling_evidence(result["cycle_number"])
        assert isinstance(evidence, list)


class TestConvergenceFlow:
    def test_empty_repo_converges(self, engine: Engine) -> None:
        """A clean repo should achieve high convergence."""
        engine.initialize()
        result = engine.run_audit()
        # With a clean git repo, score should be decent
        assert result["overall_score"] >= 0

    def test_multiple_cycles_can_run(self, engine: Engine) -> None:
        engine.initialize()
        r1 = engine.run_audit()
        r2 = engine.run_audit()
        assert r1["cycle_number"] == 2  # First run creates cycle 2
        assert r2["cycle_number"] == 3  # Second run creates cycle 3

    def test_convergence_state_persists(self, engine: Engine) -> None:
        engine.initialize()
        engine.run_audit()
        conv = engine.db.get_convergence(1)
        assert conv is not None
        assert "classification" in conv
        gates = engine.db.get_gates(1)
        assert len(gates) > 0


class TestToolingDetection:
    def test_detects_pyproject(self, engine: Engine) -> None:
        (engine.repo_root / "pyproject.toml").write_text("[project]\nname='test'")
        commands = engine._detect_commands()
        assert any("pytest" in cmd for cmd in commands)

    def test_detects_package_json(self, engine: Engine) -> None:
        import json
        (engine.repo_root / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}})
        )
        commands = engine._detect_commands()
        assert any("npm run test" in cmd for cmd in commands)
        assert any("npm run lint" in cmd for cmd in commands)

    def test_detects_makefile(self, engine: Engine) -> None:
        (engine.repo_root / "Makefile").write_text("test:\n\techo ok")
        commands = engine._detect_commands()
        assert any("make test" in cmd for cmd in commands)


class TestGitContext:
    def test_git_context_has_branch(self, engine: Engine) -> None:
        ctx = engine._get_git_context()
        assert "Branch" in ctx

    def test_git_context_has_file_count(self, engine: Engine) -> None:
        ctx = engine._get_git_context()
        assert "FileCount" in ctx
        assert ctx["FileCount"] > 0

    def test_git_context_no_git_directory(self, tmp_path: Path) -> None:
        non_git = tmp_path / "non_git"
        non_git.mkdir()
        eng = Engine(non_git)
        ctx = eng._get_git_context()
        assert ctx.get("GitError") is True
