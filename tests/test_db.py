"""Tests for the SQLite database layer — schema, CRUD operations,
transaction handling, and integrity."""

from __future__ import annotations

from aura.db import Database


class TestDatabaseInitialization:
    def test_initialize_creates_schema(self, db: Database) -> None:
        """Initialization should create all tables without error."""
        version = db._get_schema_version()
        assert version == 1

    def test_initialize_idempotent(self, db: Database) -> None:
        """Calling initialize twice should not error."""
        db.initialize()
        db.initialize()
        assert db._get_schema_version() == 1

    def test_integrity_check_passes(self, db: Database) -> None:
        """Fresh database should pass integrity check."""
        result = db.integrity_check()
        assert result == ["ok"]


class TestCycles:
    def test_insert_and_get_cycle(self, db: Database) -> None:
        db.insert_cycle(1, phase="AUDIT", classification="NOT_READY")
        cycle = db.get_cycle(1)
        assert cycle is not None
        assert cycle["cycle_number"] == 1
        assert cycle["phase"] == "AUDIT"
        assert cycle["classification"] == "NOT_READY"

    def test_get_latest_cycle(self, db: Database) -> None:
        db.insert_cycle(1)
        db.insert_cycle(2)
        latest = db.get_latest_cycle()
        assert latest is not None
        assert latest["cycle_number"] == 2

    def test_get_nonexistent_cycle(self, db: Database) -> None:
        assert db.get_cycle(999) is None

    def test_update_cycle(self, db: Database) -> None:
        db.insert_cycle(1, phase="INIT")
        db.update_cycle(1, phase="AUDIT", classification="CONDITIONALLY_READY")
        cycle = db.get_cycle(1)
        assert cycle["phase"] == "AUDIT"
        assert cycle["classification"] == "CONDITIONALLY_READY"

    def test_insert_cycle_defaults(self, db: Database) -> None:
        db.insert_cycle(1)
        cycle = db.get_cycle(1)
        assert cycle["phase"] == "INIT"
        assert cycle["status"] == "RUNNING"
        assert cycle["classification"] == "NOT_READY"
        assert cycle["overall_score"] == 0


class TestFindings:
    def test_insert_finding(self, db: Database) -> None:
        db.insert_cycle(1)
        finding = {
            "finding_id": "TEST-001",
            "cycle_number": 1,
            "severity": "P0",
            "category": "SECURITY",
            "status": "OPEN",
            "problem": "Test finding",
        }
        rowid = db.insert_finding(finding)
        assert rowid is not None

    def test_get_findings_by_cycle(self, db: Database) -> None:
        db.insert_cycle(1)
        db.insert_finding({"finding_id": "F-001", "cycle_number": 1, "severity": "P0", "category": "SECURITY", "problem": "Bug"})
        db.insert_finding({"finding_id": "F-002", "cycle_number": 1, "severity": "P2", "category": "CORRECTNESS", "problem": "Issue"})
        findings = db.get_findings(cycle_number=1)
        assert len(findings) == 2

    def test_get_findings_by_status(self, db: Database) -> None:
        db.insert_cycle(1)
        db.insert_finding({"finding_id": "F-OPEN", "cycle_number": 1, "severity": "P0", "category": "SECURITY", "problem": "Bug", "status": "OPEN"})
        db.insert_finding({"finding_id": "F-VER", "cycle_number": 1, "severity": "P1", "category": "SECURITY", "problem": "Fixed Bug", "status": "VERIFIED"})
        open_findings = db.get_findings(cycle_number=1, status="OPEN")
        assert len(open_findings) == 1
        assert open_findings[0]["finding_id"] == "F-OPEN"

    def test_get_open_findings_by_severity(self, db: Database) -> None:
        db.insert_cycle(1)
        db.insert_finding({"finding_id": "F-P0", "cycle_number": 1, "severity": "P0", "category": "SECURITY", "problem": "Critical", "status": "OPEN"})
        db.insert_finding({"finding_id": "F-P1", "cycle_number": 1, "severity": "P1", "category": "SECURITY", "problem": "High", "status": "OPEN"})
        db.insert_finding({"finding_id": "F-P2", "cycle_number": 1, "severity": "P2", "category": "SECURITY", "problem": "Medium", "status": "VERIFIED"})
        open_p0_p1 = db.get_open_findings_by_severity(["P0", "P1"])
        assert len(open_p0_p1) == 2

    def test_update_finding_status(self, db: Database) -> None:
        db.insert_cycle(1)
        db.insert_finding({"finding_id": "F-STAT", "cycle_number": 1, "severity": "P1", "category": "SECURITY", "problem": "Bug", "status": "OPEN"})
        db.update_finding_status("F-STAT", "IN_PROGRESS", "Assigned to engineer")
        findings = db.get_findings(cycle_number=1, status="IN_PROGRESS")
        assert len(findings) == 1
        assert findings[0]["status"] == "IN_PROGRESS"


class TestConvergence:
    def test_upsert_convergence_creates(self, db: Database) -> None:
        db.insert_cycle(1)
        db.upsert_convergence(1, classification="NOT_READY", converged=0, overall_score=50)
        conv = db.get_convergence(1)
        assert conv is not None
        assert conv["classification"] == "NOT_READY"
        assert conv["overall_score"] == 50

    def test_upsert_convergence_updates(self, db: Database) -> None:
        db.insert_cycle(1)
        db.upsert_convergence(1, classification="NOT_READY", overall_score=50)
        db.upsert_convergence(1, classification="CONDITIONALLY_READY", overall_score=70)
        conv = db.get_convergence(1)
        assert conv["classification"] == "CONDITIONALLY_READY"
        assert conv["overall_score"] == 70


class TestGates:
    def test_upsert_and_get_gates(self, db: Database) -> None:
        db.insert_cycle(1)
        db.upsert_gate(1, "P0_zero", True, "All P0s fixed")
        db.upsert_gate(1, "P1_zero", False, "")
        gates = db.get_gates(1)
        assert gates["P0_zero"] is True
        assert gates["P1_zero"] is False

    def test_gate_overwrite(self, db: Database) -> None:
        db.insert_cycle(1)
        db.upsert_gate(1, "P0_zero", False, "")
        db.upsert_gate(1, "P0_zero", True, "Fixed")
        gates = db.get_gates(1)
        assert gates["P0_zero"] is True


class TestToolingEvidence:
    def test_insert_and_get_tooling(self, db: Database) -> None:
        db.insert_cycle(1)
        db.insert_tooling_evidence(1, "pytest", 0, True, "All tests passed")
        db.insert_tooling_evidence(1, "ruff", 0, True, "No lint issues")
        evidence = db.get_tooling_evidence(1)
        assert len(evidence) == 2
        assert all(e["success"] for e in evidence)


class TestAuditLog:
    def test_insert_and_get_log(self, db: Database) -> None:
        db.insert_cycle(1)
        db.insert_audit_log("CYCLE_START", "Starting audit cycle 1", 1)
        db.insert_audit_log("FINDING_CREATED", "New P0 finding", 1, "F-001")
        entries = db.get_audit_log(cycle_number=1)
        assert len(entries) == 2

    def test_log_without_finding_id(self, db: Database) -> None:
        db.insert_cycle(1)
        db.insert_audit_log("DISCOVER", "Repository scanned", 1)
        entries = db.get_audit_log(limit=1)
        assert len(entries) == 1
        assert entries[0]["event_type"] == "DISCOVER"


class TestTransactions:
    def test_transaction_rollback_on_error(self, db: Database) -> None:
        db.insert_cycle(1)
        try:
            with db.transaction():
                db.insert_finding({"finding_id": "F-ROLL", "cycle_number": 1, "severity": "P0", "category": "SECURITY", "problem": "Bug"})
                raise ValueError("Simulated error")
        except ValueError:
            pass
        # Finding should not exist (rolled back)
        findings = db.get_findings(cycle_number=1)
        assert len(findings) == 0

    def test_transaction_commit_on_success(self, db: Database) -> None:
        db.insert_cycle(1)
        with db.transaction():
            db.insert_finding({"finding_id": "F-COMMIT", "cycle_number": 1, "severity": "P1", "category": "SECURITY", "problem": "Bug"})
        findings = db.get_findings(cycle_number=1)
        assert len(findings) == 1


class TestBackup:
    def test_backup_creates_file(self, db: Database, tmp_path) -> None:
        db.insert_cycle(1)
        db.insert_finding({"finding_id": "F-BACK", "cycle_number": 1, "severity": "P0", "category": "SECURITY", "problem": "Bug"})
        backup_path = tmp_path / "backup.db"
        db.backup(str(backup_path))
        assert backup_path.exists()
        assert backup_path.stat().st_size > 0
