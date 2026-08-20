"""Shared test fixtures for the AURA Python test suite."""

import pytest
import json
from pathlib import Path


@pytest.fixture
def temp_engine_root(tmp_path):
    root = tmp_path / ".aura"
    (root / "state").mkdir(parents=True)
    (root / "reports").mkdir(parents=True)
    (root / "archive").mkdir(parents=True)
    return root


@pytest.fixture
def sample_findings():
    return {
        "findings": [
            {"id": "F001", "severity": "P0", "status": "OPEN", "category": "SECURITY", "problem": "Hardcoded API key"},
            {"id": "F002", "severity": "P1", "status": "IN_PROGRESS", "category": "CORRECTNESS", "problem": "Null pointer in auth handler"},
            {"id": "F003", "severity": "P2", "status": "VERIFIED", "category": "PERFORMANCE", "problem": "N+1 query in listing endpoint"},
            {"id": "F004", "severity": "P3", "status": "OPEN", "category": "TESTING", "problem": "Missing integration test for login flow"},
            {"id": "F005", "severity": "P4", "status": "DEFERRED", "category": "DOCUMENTATION", "problem": "Update API docs for v2"},
            {"id": "F006", "severity": "P5", "status": "OPEN", "category": "OPTIMIZATION", "problem": "Consider memoizing heavy computation"},
        ],
        "next_id": 7,
    }


@pytest.fixture
def sample_convergence():
    return {
        "cycle": 5,
        "converged": False,
        "overall_score": 55,
        "consecutive_converged_cycles": 0,
        "audits_since_last_finding": 1,
        "classification": "NOT_READY",
        "reason": "Cycle 5 - 2 open P0-P2 findings remain. Not converged.",
        "gates": {
            "P0_zero": False, "P1_zero": False, "P2_zero": True,
            "critical_security": False, "critical_correctness": False,
            "data_integrity": True, "regression": True, "verification": False,
            "no_material_new_findings": True, "limitations_documented": True,
            "consecutive_clean_independent_audits": False, "module_dependency_integrity": True,
        },
    }


@pytest.fixture
def sample_cycle_state():
    return {
        "engine_name": "Continuous Autonomous Engineering Audit Engine",
        "version": "2.1.0",
        "started_at": "2026-01-01T00:00:00.0000000+00:00",
        "current_cycle": 5,
        "current_phase": "AUDIT",
        "status": "RUNNING",
        "classification": "NOT_READY",
        "cycles_completed": 4,
        "cycles_without_progress": 1,
        "consecutive_converged_cycles": 0,
        "last_change_hash": "abc123def456",
    }


@pytest.fixture
def converged_state():
    return {
        "cycle": 10,
        "converged": True,
        "overall_score": 98,
        "consecutive_converged_cycles": 3,
        "audits_since_last_finding": 3,
        "classification": "PRODUCTION_READY",
        "reason": "All gates passed. Consecutive converged threshold met.",
        "gates": {
            "P0_zero": True, "P1_zero": True, "P2_zero": True,
            "critical_security": True, "critical_correctness": True,
            "data_integrity": True, "regression": True, "verification": True,
            "no_material_new_findings": True, "limitations_documented": True,
            "consecutive_clean_independent_audits": True, "module_dependency_integrity": True,
        },
    }


@pytest.fixture
def empty_existing_state():
    return {
        "cycle": 0,
        "converged": False,
        "consecutive_converged_cycles": 0,
        "audits_since_last_finding": 0,
        "overall_score": 0,
        "classification": "NOT_READY",
        "reason": "Cycle 0 - not yet started.",
        "gates": {
            "P0_zero": False, "P1_zero": False, "P2_zero": False,
            "critical_security": False, "critical_correctness": False,
            "data_integrity": False, "regression": False, "verification": False,
            "no_material_new_findings": False, "limitations_documented": False,
            "consecutive_clean_independent_audits": False, "module_dependency_integrity": True,
        },
    }