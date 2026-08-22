"""SQLite database layer with schema, migrations, and repository pattern.

Uses WAL mode, foreign keys, and transactional writes.
Designed so migration to PostgreSQL later requires minimal changes.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import DatabaseConfig

# ── Schema version ──────────────────────────────────────────────────────────

SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Schema version tracking
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Engine cycles
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number INTEGER NOT NULL UNIQUE,
    phase TEXT NOT NULL DEFAULT 'INIT',
    status TEXT NOT NULL DEFAULT 'RUNNING',
    classification TEXT NOT NULL DEFAULT 'NOT_READY',
    overall_score INTEGER NOT NULL DEFAULT 0,
    cycles_without_progress INTEGER NOT NULL DEFAULT 0,
    consecutive_converged_cycles INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    last_change_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Findings
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT NOT NULL UNIQUE,
    cycle_number INTEGER NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('P0','P1','P2','P3','P4','P5')),
    category TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK(status IN ('OPEN','IN_PROGRESS','FIXED','VERIFYING','VERIFIED',
                          'REJECTED','DEFERRED','BLOCKED','UNVERIFIED',
                          'WAIVED','ACCEPTED_RISK','OUT_OF_SCOPE')),
    problem TEXT NOT NULL,
    file_path TEXT,
    line_number INTEGER,
    remediation TEXT,
    evidence TEXT,
    assigned_to TEXT,
    reviewed_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cycle_number) REFERENCES cycles(cycle_number)
);

-- Convergence state
CREATE TABLE IF NOT EXISTS convergence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number INTEGER NOT NULL UNIQUE,
    converged INTEGER NOT NULL DEFAULT 0,
    classification TEXT NOT NULL DEFAULT 'NOT_READY',
    reason TEXT NOT NULL DEFAULT '',
    overall_score INTEGER NOT NULL DEFAULT 0,
    consecutive_converged_cycles INTEGER NOT NULL DEFAULT 0,
    audits_since_last_finding INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cycle_number) REFERENCES cycles(cycle_number)
);

-- Gates (one row per gate per cycle)
CREATE TABLE IF NOT EXISTS gates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number INTEGER NOT NULL,
    gate_name TEXT NOT NULL,
    passed INTEGER NOT NULL DEFAULT 0,
    evidence TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(cycle_number, gate_name),
    FOREIGN KEY (cycle_number) REFERENCES cycles(cycle_number)
);

-- Tooling evidence
CREATE TABLE IF NOT EXISTS tooling_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number INTEGER NOT NULL,
    command TEXT NOT NULL,
    exit_code INTEGER NOT NULL,
    success INTEGER NOT NULL DEFAULT 0,
    output TEXT,
    executed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cycle_number) REFERENCES cycles(cycle_number)
);

-- Evidence chain (immutable audit log)
CREATE TABLE IF NOT EXISTS evidence_chain (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    signature TEXT NOT NULL,
    signer TEXT NOT NULL,
    public_key_fingerprint TEXT NOT NULL,
    chain_index INTEGER NOT NULL,
    previous_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Remediation attempts (one row per attempted fix) (one row per attempted fix)
CREATE TABLE IF NOT EXISTS remediation_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id TEXT NOT NULL UNIQUE,
    cycle_number INTEGER NOT NULL,
    finding_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    status TEXT NOT NULL CHECK(status IN ('PENDING','APPLIED','REJECTED','FAILED','ROLLED_BACK')),
    patch_content TEXT,
    error_message TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cycle_number) REFERENCES cycles(cycle_number)
);

CREATE INDEX IF NOT EXISTS idx_remediation_cycle ON remediation_attempts(cycle_number);

-- Audit log (immutable)
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    cycle_number INTEGER,
    finding_id TEXT,
    actor TEXT NOT NULL DEFAULT 'system',
    detail TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Dead letter queue — failed/unparseable remediation attempts
CREATE TABLE IF NOT EXISTS dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id TEXT NOT NULL,
    cycle_number INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    error_type TEXT NOT NULL CHECK(error_type IN ('UNPARSEABLE','TIMEOUT','PROVIDER_ERROR','INVALID_FIX','SANDBOX_REJECTED','UNKNOWN')),
    raw_response TEXT,
    recovery_hint TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RETRIED','RESOLVED','ABANDONED')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cycle_number) REFERENCES cycles(cycle_number)
);

-- Convergence confidence tracking
CREATE TABLE IF NOT EXISTS convergence_confidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_number INTEGER NOT NULL UNIQUE,
    verification_confidence INTEGER NOT NULL DEFAULT 0,  -- 0-100
    detection_confidence INTEGER NOT NULL DEFAULT 0,    -- 0-100
    test_confidence INTEGER NOT NULL DEFAULT 0,         -- 0-100
    tooling_pass_ratio REAL NOT NULL DEFAULT 0.0,
    file_coverage_ratio REAL NOT NULL DEFAULT 0.0,
    verified_findings_ratio REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (cycle_number) REFERENCES cycles(cycle_number)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_findings_cycle ON findings(cycle_number);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_gates_cycle ON gates(cycle_number);
CREATE INDEX IF NOT EXISTS idx_gates_name ON gates(gate_name);
CREATE INDEX IF NOT EXISTS idx_evidence_chain_index ON evidence_chain(chain_index);
CREATE INDEX IF NOT EXISTS idx_audit_log_cycle ON audit_log(cycle_number);
CREATE INDEX IF NOT EXISTS idx_audit_log_event ON audit_log(event_type);
"""


class Database:
    """SQLite database manager with migration support."""

    def __init__(self, config: DatabaseConfig, repo_root: str | Path | None = None) -> None:
        self.config = config
        self._conn: sqlite3.Connection | None = None
        # Resolve the database path against the owning repository root, not the
        # process CWD (GAP-DB-PATH-RESOLUTION-01). Relative config paths like
        # `.aura/state/aura.db` live inside the audited repository; absolute
        # paths (used by tests) are honored unchanged.
        raw = Path(config.path)
        if not raw.is_absolute() and repo_root is not None:
            raw = Path(repo_root) / raw
        self._path = raw

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    def initialize(self) -> None:
        """Create database, apply schema, and run migrations."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        current = self._get_schema_version()
        if current >= SCHEMA_VERSION:
            return
        self.conn.executescript(SCHEMA_SQL)
        self.conn.execute(
            "INSERT OR REPLACE INTO _schema_version (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now(UTC).isoformat()),
        )

    def _get_schema_version(self) -> int:
        try:
            row = self.conn.execute(
                "SELECT MAX(version) FROM _schema_version"
            ).fetchone()
            return row[0] if row and row[0] else 0
        except sqlite3.OperationalError:
            return 0

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Execute a block within a transaction. Rolls back on exception."""
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            yield
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def vacuum(self) -> None:
        self.conn.execute("VACUUM")

    def integrity_check(self) -> list[str]:
        rows = self.conn.execute("PRAGMA integrity_check").fetchall()
        return [row[0] for row in rows]

    def backup(self, target_path: str | Path) -> None:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        backup_conn = sqlite3.connect(str(target))
        self.conn.backup(backup_conn)
        backup_conn.close()

    # ── Repository helpers ───────────────────────────────────────────────

    def insert_cycle(
        self,
        cycle_number: int,
        phase: str = "INIT",
        status: str = "RUNNING",
        classification: str = "NOT_READY",
    ) -> int:
        with self.transaction():
            cursor = self.conn.execute(
                """INSERT INTO cycles (cycle_number, phase, status, classification,
                   started_at) VALUES (?, ?, ?, ?, ?)""",
                (cycle_number, phase, status, classification,
                 datetime.now(UTC).isoformat()),
            )
            return cursor.lastrowid

    def get_latest_cycle(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM cycles ORDER BY cycle_number DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def get_cycle(self, cycle_number: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM cycles WHERE cycle_number = ?", (cycle_number,)
        ).fetchone()
        return dict(row) if row else None

    def update_cycle(self, cycle_number: int, **kwargs: Any) -> None:
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.now(UTC).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [cycle_number]
        self.conn.execute(
            f"UPDATE cycles SET {set_clause} WHERE cycle_number = ?", values
        )

    def insert_finding(self, finding: dict[str, Any]) -> int:
            cursor = self.conn.execute(
                """INSERT INTO findings
                   (finding_id, cycle_number, severity, category, status, problem,
                    file_path, line_number, remediation, evidence, assigned_to)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(finding_id) DO UPDATE SET
                   cycle_number = excluded.cycle_number,
                   severity = excluded.severity,
                   category = excluded.category,
                   status = CASE WHEN findings.status IN ('VERIFIED','WAIVED','ACCEPTED_RISK','OUT_OF_SCOPE')
                                  THEN findings.status ELSE excluded.status END,
                   problem = excluded.problem,
                   file_path = excluded.file_path,
                   line_number = excluded.line_number,
                   remediation = excluded.remediation,
                   evidence = excluded.evidence,
                   updated_at = datetime('now')""",
                (
                    finding["finding_id"],
                    finding["cycle_number"],
                    finding["severity"],
                    finding["category"],
                    finding.get("status", "OPEN"),
                    finding["problem"],
                    finding.get("file_path"),
                    finding.get("line_number"),
                    finding.get("remediation"),
                    finding.get("evidence"),
                    finding.get("assigned_to"),
                ),
            )
            return cursor.lastrowid

    def update_finding_status(
        self, finding_id: str, new_status: str, evidence: str | None = None
    ) -> None:
        params: dict[str, Any] = {"status": new_status, "updated_at": datetime.now(UTC).isoformat()}
        if evidence:
            params["evidence"] = evidence
        set_clause = ", ".join(f"{k} = ?" for k in params)
        values = list(params.values()) + [finding_id]
        self.conn.execute(
            f"UPDATE findings SET {set_clause} WHERE finding_id = ?", values
        )

    def get_findings(
        self,
        cycle_number: int | None = None,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM findings WHERE 1=1"
        params: list[Any] = []
        if cycle_number is not None:
            query += " AND cycle_number = ?"
            params.append(cycle_number)
        if status:
            query += " AND status = ?"
            params.append(status)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_open_findings_by_severity(
        self, severities: list[str]
    ) -> list[dict[str, Any]]:
        placeholders = ", ".join("?" for _ in severities)
        rows = self.conn.execute(
            f"""SELECT * FROM findings
                WHERE severity IN ({placeholders})
                AND status IN ('OPEN', 'IN_PROGRESS')""",
            severities,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_convergence(self, cycle_number: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM convergence WHERE cycle_number = ?", (cycle_number,)
        ).fetchone()
        return dict(row) if row else None

    def upsert_convergence(self, cycle_number: int, **kwargs: Any) -> None:
        with self.transaction():
            existing = self.get_convergence(cycle_number)
            if existing:
                set_clause = ", ".join(f"{k} = ?" for k in kwargs)
                values = list(kwargs.values()) + [cycle_number]
                self.conn.execute(
                    f"UPDATE convergence SET {set_clause} WHERE cycle_number = ?", values
                )
            else:
                kwargs["cycle_number"] = cycle_number
                columns = ", ".join(kwargs.keys())
                placeholders = ", ".join("?" for _ in kwargs)
                self.conn.execute(
                    f"INSERT INTO convergence ({columns}) VALUES ({placeholders})",
                    list(kwargs.values()),
                )

    def upsert_gate(self, cycle_number: int, gate_name: str, passed: bool, evidence: str = "") -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO gates (cycle_number, gate_name, passed, evidence)
               VALUES (?, ?, ?, ?)""",
            (cycle_number, gate_name, int(passed), evidence),
        )

    def get_gates(self, cycle_number: int) -> dict[str, bool]:
        rows = self.conn.execute(
            "SELECT gate_name, passed FROM gates WHERE cycle_number = ?",
            (cycle_number,),
        ).fetchall()
        return {row["gate_name"]: bool(row["passed"]) for row in rows}

    def insert_tooling_evidence(
        self, cycle_number: int, command: str, exit_code: int, success: bool, output: str = ""
    ) -> None:
        self.conn.execute(
            """INSERT INTO tooling_evidence (cycle_number, command, exit_code, success, output)
               VALUES (?, ?, ?, ?, ?)""",
            (cycle_number, command, exit_code, int(success), output),
        )

    def get_tooling_evidence(self, cycle_number: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM tooling_evidence WHERE cycle_number = ?", (cycle_number,)
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_audit_log(
        self,
        event_type: str,
        detail: str,
        cycle_number: int | None = None,
        finding_id: str | None = None,
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """INSERT INTO audit_log (event_type, cycle_number, finding_id, actor, detail, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_type, cycle_number, finding_id, actor, detail,
             json.dumps(metadata) if metadata else None),
        )

    def get_audit_log(
        self, cycle_number: int | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        if cycle_number is not None:
            rows = self.conn.execute(
                "SELECT * FROM audit_log WHERE cycle_number = ? ORDER BY id DESC LIMIT ?",
                (cycle_number, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def insert_remediation_attempt(self, attempt: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT INTO remediation_attempts
               (attempt_id, cycle_number, finding_id, file_path,
                line_start, line_end, status, patch_content, error_message, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (attempt["attempt_id"], attempt["cycle_number"], attempt["finding_id"],
             attempt["file_path"], attempt.get("line_start"), attempt.get("line_end"),
             attempt["status"], attempt.get("patch_content"),
             attempt.get("error_message"), attempt.get("duration_ms")),
        )

    def get_remediation_attempts(self, cycle_number: int | None = None) -> list[dict[str, Any]]:
        if cycle_number is not None:
            rows = self.conn.execute(
                "SELECT * FROM remediation_attempts WHERE cycle_number = ? ORDER BY id",
                (cycle_number,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM remediation_attempts ORDER BY id",
            ).fetchall()
        return [dict(row) for row in rows]

    def get_cycle_stats(self, cycle_number: int) -> dict[str, Any]:
        attempts = self.get_remediation_attempts(cycle_number)
        findings = self.get_findings(cycle_number=cycle_number)
        return {
            "cycle_number": cycle_number,
            "total_attempts": len(attempts),
            "attempts_applied": len([a for a in attempts if a["status"] == "APPLIED"]),
            "attempts_rejected": len([a for a in attempts if a["status"] == "REJECTED"]),
            "attempts_failed": len([a for a in attempts if a["status"] == "FAILED"]),
            "attempts_rolled_back": len([a for a in attempts if a["status"] == "ROLLED_BACK"]),
            "total_findings": len(findings),
            "findings_fixed": len([f for f in findings if f["status"] == "FIXED"]),
            "findings_verified": len([f for f in findings if f["status"] == "VERIFIED"]),
            "findings_open": len([f for f in findings if f["status"] in ("OPEN", "IN_PROGRESS")]),
        }

    # ── Dead Letter Queue ───────────────────────────────────────────────

    def insert_dead_letter(
        self,
        finding_id: str,
        cycle_number: int,
        error_type: str,
        raw_response: str = "",
        recovery_hint: str = "",
        attempt_number: int = 1,
    ) -> int:
        """Record an unparseable or failed remediation attempt."""
        cursor = self.conn.execute(
            """INSERT INTO dead_letter
               (finding_id, cycle_number, attempt_number, error_type,
                raw_response, recovery_hint, status)
               VALUES (?, ?, ?, ?, ?, ?, 'PENDING')""",
            (finding_id, cycle_number, attempt_number, error_type,
             raw_response[:5000], recovery_hint),
        )
        return cursor.lastrowid

    def get_dead_letters(
        self,
        cycle_number: int | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve dead letter entries, optionally filtered."""
        query = "SELECT * FROM dead_letter WHERE 1=1"
        params: list[Any] = []
        if cycle_number is not None:
            query += " AND cycle_number = ?"
            params.append(cycle_number)
        if status:
            query += " AND status = ?"
            params.append(status)
        rows = self.conn.execute(query + " ORDER BY id DESC", params).fetchall()
        return [dict(row) for row in rows]

    def purge_dead_letter(self, dl_id: int) -> None:
        """Mark a dead letter entry as resolved/abandoned."""
        self.conn.execute(
            "UPDATE dead_letter SET status = 'RESOLVED' WHERE id = ?",
            (dl_id,),
        )

    # ── Evidence chain persistence (IMP-04) ──────────────────────────────

    def insert_evidence_entry(
        self,
        evidence_id: str,
        content_hash: str,
        chain_index: int,
        previous_hash: str,
        payload: str,
        signer: str = "local",
        signature: str = "",
        public_key_fingerprint: str = "",
    ) -> None:
        """Persist one evidence-chain entry into the evidence_chain table.

        JSON file remains the source of truth this cycle; the table is a
        queryable mirror so the schema is no longer dead (IMP-04).
        """
        self.conn.execute(
            """INSERT OR REPLACE INTO evidence_chain
               (evidence_id, content_hash, signature, signer,
                public_key_fingerprint, chain_index, previous_hash, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (evidence_id, content_hash, signature, signer,
             public_key_fingerprint, chain_index, previous_hash, payload),
        )

    def get_evidence_chain(self) -> list[dict[str, Any]]:
        """Read all persisted evidence-chain entries, in chain order."""
        rows = self.conn.execute(
            "SELECT * FROM evidence_chain ORDER BY chain_index"
        ).fetchall()
        return [dict(row) for row in rows]

    # ── Convergence Confidence ──────────────────────────────────────────

    def upsert_convergence_confidence(
        self,
        cycle_number: int,
        verification_confidence: int = 0,
        detection_confidence: int = 0,
        test_confidence: int = 0,
        tooling_pass_ratio: float = 0.0,
        file_coverage_ratio: float = 0.0,
        verified_findings_ratio: float = 0.0,
    ) -> None:
        """Record confidence metrics for a cycle's convergence decision."""
        self.conn.execute(
            """INSERT OR REPLACE INTO convergence_confidence
               (cycle_number, verification_confidence, detection_confidence,
                test_confidence, tooling_pass_ratio, file_coverage_ratio,
                verified_findings_ratio)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cycle_number, verification_confidence, detection_confidence,
             test_confidence, tooling_pass_ratio, file_coverage_ratio,
             verified_findings_ratio),
        )

    def get_convergence_confidence(
        self, cycle_number: int
    ) -> dict[str, Any] | None:
        """Get convergence confidence for a cycle."""
        row = self.conn.execute(
            "SELECT * FROM convergence_confidence WHERE cycle_number = ?",
            (cycle_number,),
        ).fetchone()
        return dict(row) if row else None

    def compute_convergence_confidence(
        self, cycle_number: int, files_analyzed: int, total_files: int,
        tooling_passed: int, tooling_total: int, verified_count: int,
        total_findings: int,
    ) -> dict[str, int]:
        """Compute and persist confidence metrics for a cycle."""
        vc_tooling = min(100, int((tooling_passed / max(tooling_total, 1)) * 50))
        vc_findings = min(50, int((verified_count / max(total_findings, 1)) * 50))
        verification_confidence = vc_tooling + vc_findings
        file_coverage = files_analyzed / max(total_files, 1)
        detection_confidence = min(100, int(file_coverage * 100))
        tooling_ratio = tooling_passed / max(tooling_total, 1)
        test_confidence = min(100, int(tooling_ratio * 100))
        self.upsert_convergence_confidence(
            cycle_number=cycle_number,
            verification_confidence=verification_confidence,
            detection_confidence=detection_confidence,
            test_confidence=test_confidence,
            tooling_pass_ratio=tooling_ratio,
            file_coverage_ratio=file_coverage,
            verified_findings_ratio=verified_count / max(total_findings, 1),
        )
        return {
            "verification_confidence": verification_confidence,
            "detection_confidence": detection_confidence,
            "test_confidence": test_confidence,
        }
