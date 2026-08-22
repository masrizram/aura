"""Pytest configuration and fixtures for AURA tests."""

from __future__ import annotations

import contextlib
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from aura.config import AuraConfig, DatabaseConfig
from aura.db import Database


@pytest.fixture
def tmp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield Path(tmpdir) / "test_aura.db"


@pytest.fixture
def db_config(tmp_db_path: Path) -> DatabaseConfig:
    """Create a test database configuration."""
    return DatabaseConfig(
        path=str(tmp_db_path),
        wal_mode=True,
        foreign_keys=True,
    )


@pytest.fixture
def db(db_config: DatabaseConfig) -> Generator[Database, None, None]:
    """Create an initialized test database."""
    database = Database(db_config)
    database.initialize()
    yield database
    with contextlib.suppress(Exception):
        database.close()


@pytest.fixture
def sample_findings() -> list[dict]:
    """Return a set of sample findings for testing."""
    return [
        {
            "finding_id": "F-001",
            "cycle_number": 1,
            "severity": "P0",
            "category": "SECURITY",
            "status": "OPEN",
            "problem": "SQL injection vulnerability in login handler",
            "file_path": "src/auth/login.py",
            "line_number": 42,
        },
        {
            "finding_id": "F-002",
            "cycle_number": 1,
            "severity": "P1",
            "category": "CORRECTNESS",
            "status": "OPEN",
            "problem": "Null pointer dereference in payment processor",
            "file_path": "src/pay/processor.py",
            "line_number": 128,
        },
        {
            "finding_id": "F-003",
            "cycle_number": 1,
            "severity": "P2",
            "category": "SECURITY",
            "status": "IN_PROGRESS",
            "problem": "Missing CSRF token on admin forms",
            "file_path": "src/admin/forms.py",
            "line_number": 15,
        },
        {
            "finding_id": "F-004",
            "cycle_number": 1,
            "severity": "P3",
            "category": "PERFORMANCE",
            "status": "OPEN",
            "problem": "N+1 query in user listing",
            "file_path": "src/users/views.py",
            "line_number": 89,
        },
        {
            "finding_id": "F-005",
            "cycle_number": 1,
            "severity": "P4",
            "category": "MAINTAINABILITY",
            "status": "OPEN",
            "problem": "Function too long — 200+ lines",
            "file_path": "src/utils/helpers.py",
            "line_number": 50,
        },
    ]


@pytest.fixture
def config() -> AuraConfig:
    """Return a default AuraConfig for testing."""
    return AuraConfig()
