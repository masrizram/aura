"""
SQLite database backend for historical analytics.
Replaces JSON files with ACID-compliant, queryable storage.

Maintains full history across audit cycles including findings lifecycle,
convergence gate transitions, dimension scores, evidence chain entries,
tooling results, and team activity.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class AnalyticsDB:
    SCHEMA_VERSION = 2

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = ".aura/state/analytics.db"
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS _schema_version (
                    version INTEGER PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS cycles (
                    cycle_number INTEGER PRIMARY KEY,
                    started_at TEXT,
                    completed_at TEXT,
                    classification TEXT,
                    overall_score INTEGER,
                    convergence_status BOOLEAN,
                    files_audited INTEGER,
                    findings_new INTEGER,
                    findings_closed INTEGER,
                    duration_seconds REAL,
                    confidence TEXT,
                    reason TEXT,
                    repo_commit_hash TEXT
                );

                CREATE TABLE IF NOT EXISTS findings_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    finding_id TEXT NOT NULL,
                    cycle_number INTEGER NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    category TEXT,
                    risk_score INTEGER,
                    confidence TEXT,
                    location TEXT,
                    problem TEXT,
                    root_cause TEXT,
                    impact TEXT,
                    evidence TEXT,
                    recommended_fix TEXT,
                    implemented_fix TEXT,
                    verification TEXT,
                    time_to_fix_hours REAL,
                    assigned_to TEXT,
                    reviewed_by TEXT,
                    UNIQUE(finding_id, cycle_number)
                );

                CREATE TABLE IF NOT EXISTS convergence_gates (
                    cycle_number INTEGER NOT NULL,
                    gate_name TEXT NOT NULL,
                    passed BOOLEAN NOT NULL,
                    changed_from_previous BOOLEAN,
                    UNIQUE(cycle_number, gate_name)
                );

                CREATE TABLE IF NOT EXISTS dimension_scores (
                    cycle_number INTEGER NOT NULL,
                    dimension TEXT NOT NULL,
                    score REAL NOT NULL,
                    confidence TEXT,
                    UNIQUE(cycle_number, dimension)
                );

                CREATE TABLE IF NOT EXISTS evidence_chain (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evidence_id TEXT UNIQUE,
                    content_hash TEXT,
                    signature TEXT,
                    signer TEXT,
                    timestamp TEXT,
                    chain_index INTEGER,
                    previous_hash TEXT,
                    verified BOOLEAN DEFAULT 0,
                    stored_at TEXT
                );

                CREATE TABLE IF NOT EXISTS tooling_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_number INTEGER NOT NULL,
                    command TEXT NOT NULL,
                    exit_code INTEGER,
                    success BOOLEAN,
                    output_hash TEXT,
                    timestamp TEXT
                );

                CREATE TABLE IF NOT EXISTS team_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_number INTEGER,
                    member_id TEXT,
                    action TEXT,
                    target_type TEXT,
                    target_id TEXT,
                    timestamp TEXT
                );

                CREATE TABLE IF NOT EXISTS compliance_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    finding_id TEXT,
                    standard TEXT NOT NULL,
                    control_id TEXT NOT NULL,
                    UNIQUE(finding_id, standard, control_id)
                );

                CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings_history(severity, status);
                CREATE INDEX IF NOT EXISTS idx_findings_cycle ON findings_history(cycle_number);
                CREATE INDEX IF NOT EXISTS idx_findings_id ON findings_history(finding_id);
                CREATE INDEX IF NOT EXISTS idx_gates_cycle ON convergence_gates(cycle_number);
                CREATE INDEX IF NOT EXISTS idx_dimensions_cycle ON dimension_scores(cycle_number);
                CREATE INDEX IF NOT EXISTS idx_tooling_cycle ON tooling_results(cycle_number);
                CREATE INDEX IF NOT EXISTS idx_evidence_chain_idx ON evidence_chain(chain_index);
            """)

            cur = conn.execute("SELECT version FROM _schema_version")
            row = cur.fetchone()
            if row is None:
                conn.execute("INSERT INTO _schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
                conn.commit()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record_cycle(self, cycle_data: Dict[str, Any]) -> int:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cycles
                    (cycle_number, started_at, completed_at, classification,
                     overall_score, convergence_status, files_audited,
                     findings_new, findings_closed, duration_seconds,
                     confidence, reason, repo_commit_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cycle_data.get("cycle_number", 0),
                cycle_data.get("started_at"),
                cycle_data.get("completed_at", datetime.now(timezone.utc).isoformat()),
                cycle_data.get("classification"),
                cycle_data.get("overall_score"),
                cycle_data.get("convergence_status", False),
                cycle_data.get("files_audited"),
                cycle_data.get("findings_new"),
                cycle_data.get("findings_closed"),
                cycle_data.get("duration_seconds"),
                cycle_data.get("confidence"),
                cycle_data.get("reason"),
                cycle_data.get("repo_commit_hash"),
            ))
            return cycle_data.get("cycle_number", 0)

    def record_finding(self, finding: Dict[str, Any], cycle: int) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO findings_history
                    (finding_id, cycle_number, severity, status, category,
                     risk_score, confidence, location, problem, root_cause,
                     impact, evidence, recommended_fix, implemented_fix,
                     verification, time_to_fix_hours, assigned_to, reviewed_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                finding.get("id", finding.get("finding_id")),
                cycle,
                finding.get("severity"),
                finding.get("status"),
                finding.get("category"),
                finding.get("risk_score"),
                finding.get("confidence"),
                finding.get("location"),
                finding.get("problem"),
                finding.get("root_cause"),
                finding.get("impact"),
                finding.get("evidence"),
                finding.get("recommended_fix"),
                finding.get("implemented_fix"),
                finding.get("verification"),
                finding.get("time_to_fix_hours"),
                finding.get("assigned_to"),
                finding.get("reviewed_by"),
            ))

    def record_gates(self, cycle: int, gates: Dict[str, Any]) -> None:
        with self._conn() as conn:
            prev_cycle = max(cycle - 1, 0)
            prev_gates = {}
            if prev_cycle > 0:
                cur = conn.execute(
                    "SELECT gate_name, passed FROM convergence_gates WHERE cycle_number = ?",
                    (prev_cycle,)
                )
                for row in cur.fetchall():
                    prev_gates[row["gate_name"]] = bool(row["passed"])

            for gate_name, passed in gates.items():
                changed = False
                if gate_name in prev_gates:
                    changed = bool(passed) != prev_gates[gate_name]
                conn.execute("""
                    INSERT OR REPLACE INTO convergence_gates
                        (cycle_number, gate_name, passed, changed_from_previous)
                    VALUES (?, ?, ?, ?)
                """, (cycle, gate_name, bool(passed), changed))

    def record_dimension_scores(self, cycle: int, scores: Dict[str, Any]) -> None:
        with self._conn() as conn:
            for dim, score in scores.items():
                conn.execute("""
                    INSERT OR REPLACE INTO dimension_scores
                        (cycle_number, dimension, score, confidence)
                    VALUES (?, ?, ?, ?)
                """, (cycle, dim, float(score), None))

    def record_tooling(self, cycle: int, results: Dict[str, Any]) -> None:
        import hashlib
        with self._conn() as conn:
            for command, result in results.items():
                if isinstance(result, dict):
                    output_str = str(result.get("output", ""))
                    output_hash = hashlib.sha256(output_str.encode()).hexdigest() if output_str else None
                    conn.execute("""
                        INSERT INTO tooling_results
                            (cycle_number, command, exit_code, success, output_hash, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        cycle,
                        command,
                        result.get("exit_code"),
                        result.get("success", False),
                        output_hash,
                        datetime.now(timezone.utc).isoformat(),
                    ))

    def record_evidence_entry(self, entry: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO evidence_chain
                    (evidence_id, content_hash, signature, signer, timestamp,
                     chain_index, previous_hash, verified, stored_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.get("evidence_id"),
                entry.get("content_hash"),
                entry.get("signature"),
                entry.get("signer"),
                entry.get("timestamp"),
                entry.get("chain_index"),
                entry.get("previous_hash"),
                entry.get("verified", False),
                datetime.now(timezone.utc).isoformat(),
            ))

    def record_team_activity(self, cycle: int, activity: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO team_activity
                    (cycle_number, member_id, action, target_type, target_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                cycle,
                activity.get("member_id"),
                activity.get("action"),
                activity.get("target_type"),
                activity.get("target_id"),
                datetime.now(timezone.utc).isoformat(),
            ))

    def record_compliance_mapping(self, finding_id: str, standard: str, control_id: str) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO compliance_mappings (finding_id, standard, control_id)
                VALUES (?, ?, ?)
            """, (finding_id, standard, control_id))

    def get_cycle_history(self, limit: int = 25) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM cycles ORDER BY cycle_number DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_finding_timeline(self, finding_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT * FROM findings_history WHERE finding_id = ? ORDER BY cycle_number",
                (finding_id,)
            )
            return [dict(row) for row in cur.fetchall()]

    def get_cycle_summary(self, cycle: int) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute("SELECT * FROM cycles WHERE cycle_number = ?", (cycle,))
            row = cur.fetchone()
            if row is None:
                return None

            result = dict(row)
            gates_cur = conn.execute(
                "SELECT gate_name, passed FROM convergence_gates WHERE cycle_number = ?",
                (cycle,)
            )
            result["gates"] = {r["gate_name"]: bool(r["passed"]) for r in gates_cur.fetchall()}

            dims_cur = conn.execute(
                "SELECT dimension, score FROM dimension_scores WHERE cycle_number = ?",
                (cycle,)
            )
            result["dimension_scores"] = {r["dimension"]: r["score"] for r in dims_cur.fetchall()}

            findings_cur = conn.execute(
                "SELECT * FROM findings_history WHERE cycle_number = ?", (cycle,)
            )
            result["findings"] = [dict(r) for r in findings_cur.fetchall()]

            return result

    def get_finding_counts_by_severity(self, cycle: Optional[int] = None) -> Dict[str, int]:
        with self._conn() as conn:
            if cycle:
                cur = conn.execute("""
                    SELECT severity, COUNT(*) as cnt FROM findings_history
                    WHERE cycle_number = ? GROUP BY severity
                """, (cycle,))
            else:
                cur = conn.execute("""
                    SELECT fh.severity, COUNT(*) as cnt FROM findings_history fh
                    INNER JOIN (
                        SELECT finding_id, MAX(cycle_number) as max_cycle
                        FROM findings_history GROUP BY finding_id
                    ) latest ON fh.finding_id = latest.finding_id
                    AND fh.cycle_number = latest.max_cycle
                    WHERE fh.status IN ('OPEN', 'IN_PROGRESS')
                    GROUP BY fh.severity
                """)
            return {row["severity"]: row["cnt"] for row in cur.fetchall()}

    def get_finding_counts_by_status(self, cycle: Optional[int] = None) -> Dict[str, int]:
        with self._conn() as conn:
            if cycle:
                cur = conn.execute("""
                    SELECT status, COUNT(*) as cnt FROM findings_history
                    WHERE cycle_number = ? GROUP BY status
                """, (cycle,))
            else:
                cur = conn.execute("""
                    SELECT fh.status, COUNT(*) as cnt FROM findings_history fh
                    INNER JOIN (
                        SELECT finding_id, MAX(cycle_number) as max_cycle
                        FROM findings_history GROUP BY finding_id
                    ) latest ON fh.finding_id = latest.finding_id
                    AND fh.cycle_number = latest.max_cycle
                    GROUP BY fh.status
                """)
            return {row["status"]: row["cnt"] for row in cur.fetchall()}

    def get_score_trend(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute("""
                SELECT cycle_number, overall_score, classification
                FROM cycles ORDER BY cycle_number DESC LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_dimension_trend(self, dimension: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute("""
                SELECT cycle_number, score, confidence
                FROM dimension_scores
                WHERE dimension = ?
                ORDER BY cycle_number DESC LIMIT ?
            """, (dimension, limit))
            rows = cur.fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_mttr_data(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute("""
                SELECT cycle_number, finding_id, severity, time_to_fix_hours
                FROM findings_history
                WHERE time_to_fix_hours IS NOT NULL AND time_to_fix_hours > 0
                ORDER BY cycle_number DESC LIMIT ?
            """, (limit * 10,))
            return [dict(r) for r in cur.fetchall()]

    def get_category_counts(self, cycle: Optional[int] = None) -> Dict[str, int]:
        with self._conn() as conn:
            if cycle:
                cur = conn.execute("""
                    SELECT category, COUNT(*) as cnt FROM findings_history
                    WHERE cycle_number = ? GROUP BY category
                """, (cycle,))
            else:
                cur = conn.execute("""
                    SELECT category, COUNT(*) as cnt FROM findings_history
                    GROUP BY category
                """)
            return {row["category"] or "UNCATEGORIZED": row["cnt"] for row in cur.fetchall()}

    def get_recurring_findings(self, min_occurrences: int = 2) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute("""
                SELECT finding_id, category, severity, COUNT(*) as occurrences
                FROM findings_history
                GROUP BY finding_id
                HAVING COUNT(*) >= ?
                ORDER BY occurrences DESC
            """, (min_occurrences,))
            return [dict(r) for r in cur.fetchall()]

    def get_gate_flip_history(self) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.execute("""
                SELECT cycle_number, gate_name, passed, changed_from_previous
                FROM convergence_gates
                WHERE changed_from_previous = 1
                ORDER BY cycle_number, gate_name
            """)
            return [dict(r) for r in cur.fetchall()]

    def get_last_cycle_number(self) -> int:
        with self._conn() as conn:
            cur = conn.execute("SELECT MAX(cycle_number) as max_cycle FROM cycles")
            row = cur.fetchone()
            return row["max_cycle"] if row and row["max_cycle"] is not None else 0

    def migrate_from_json(self, state_dir: str) -> int:
        state_path = Path(state_dir)
        total_records = 0

        conv_file = state_path / "convergence.json"
        if conv_file.exists():
            try:
                conv_data = json.loads(conv_file.read_text(encoding="utf-8"))
                cycle_num = conv_data.get("cycle", 0)
                if cycle_num > 0:
                    self.record_cycle({
                        "cycle_number": cycle_num,
                        "started_at": datetime.now(timezone.utc).isoformat(),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "classification": conv_data.get("classification"),
                        "overall_score": conv_data.get("overall_score", 0),
                        "convergence_status": conv_data.get("converged", False),
                        "confidence": conv_data.get("confidence"),
                        "reason": conv_data.get("reason"),
                    })
                    total_records += 1

                    gates = conv_data.get("gates", {})
                    if gates:
                        self.record_gates(cycle_num, gates)
                        total_records += len(gates)

                    dims = conv_data.get("dimension_scores", {})
                    if dims:
                        self.record_dimension_scores(cycle_num, dims)
                        total_records += len(dims)
            except (json.JSONDecodeError, KeyError):
                pass

        findings_file = state_path / "findings.json"
        if findings_file.exists():
            try:
                findings_data = json.loads(findings_file.read_text(encoding="utf-8"))
                findings = findings_data.get("findings", [])
                conv_file2 = state_path / "convergence.json"
                cycle_num = 0
                if conv_file2.exists():
                    try:
                        conv = json.loads(conv_file2.read_text(encoding="utf-8"))
                        cycle_num = conv.get("cycle", 0)
                    except Exception:
                        pass

                for finding in findings:
                    self.record_finding(finding, cycle_num)
                    total_records += 1
            except (json.JSONDecodeError, KeyError):
                pass

        return total_records