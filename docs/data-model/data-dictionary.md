# Data Dictionary — AURA v3.5

> **Verified from:** `src/aura/db.py:23-193`

## Table: `cycles`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | Internal row ID |
| cycle_number | INTEGER | NOT NULL, UNIQUE | Sequential cycle number (1-based) |
| phase | TEXT | NOT NULL, DEFAULT 'INIT' | Current phase name |
| status | TEXT | NOT NULL, DEFAULT 'RUNNING' | RUNNING / COMPLETED |
| classification | TEXT | NOT NULL, DEFAULT 'NOT_READY' | NOT_READY / CONDITIONALLY_READY / PRODUCTION_READY |
| overall_score | INTEGER | NOT NULL, DEFAULT 0 | 0-100 score |
| cycles_without_progress | INTEGER | NOT NULL, DEFAULT 0 | Stale cycle counter |
| consecutive_converged_cycles | INTEGER | NOT NULL, DEFAULT 0 | How many cycles converged in a row |
| started_at | TEXT | NOT NULL | ISO timestamp |
| completed_at | TEXT | NULLABLE | ISO timestamp (null until COMPLETE) |
| last_change_hash | TEXT | NULLABLE | Git commit hash |
| created_at | TEXT | NOT NULL, DEFAULT now | |
| updated_at | TEXT | NOT NULL, DEFAULT now | |

## Table: `findings`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | Internal row ID |
| finding_id | TEXT | NOT NULL, UNIQUE | Stable SHA-256 based ID |
| cycle_number | INTEGER | NOT NULL, FK → cycles.cycle_number | Origin cycle |
| severity | TEXT | NOT NULL, CHECK IN (P0,P1,P2,P3,P4,P5) | Severity level |
| category | TEXT | NOT NULL | SECURITY, CORRECTNESS, etc. |
| status | TEXT | NOT NULL, DEFAULT 'OPEN', CHECK IN (11+3 values) | Finding lifecycle status |
| problem | TEXT | NOT NULL | Description of the issue |
| file_path | TEXT | NULLABLE | Relative file path |
| line_number | INTEGER | NULLABLE | Line where issue was found |
| remediation | TEXT | NULLABLE | Suggested fix |
| evidence | TEXT | NULLABLE | Supporting evidence (code snippet, tool output) |
| assigned_to | TEXT | NULLABLE | Who is working on it |
| reviewed_by | TEXT | NULLABLE | Who reviewed the fix |
| created_at | TEXT | NOT NULL, DEFAULT now | |
| updated_at | TEXT | NOT NULL, DEFAULT now | |

### Finding ID Generation

```python
# engine.py:60-68
def _stable_finding_id(file, line, rule, prefix="F"):
    content = f"{file}:{line}:{rule}"
    digest = hashlib.sha256(content.encode()).hexdigest()[:12]
    return f"{prefix}-{digest}"
```

Stable IDs ensure regression detection works across cycles — same (file, line, rule) always produces the same ID.

## Table: `convergence`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | |
| cycle_number | INTEGER | NOT NULL, UNIQUE, FK | |
| converged | INTEGER | NOT NULL, DEFAULT 0 | 0/1 boolean |
| classification | TEXT | NOT NULL, DEFAULT 'NOT_READY' | |
| reason | TEXT | NOT NULL, DEFAULT '' | Human-readable convergence reason |
| overall_score | INTEGER | NOT NULL, DEFAULT 0 | 0-100 |
| consecutive_converged_cycles | INTEGER | NOT NULL, DEFAULT 0 | Counter |
| audits_since_last_finding | INTEGER | NOT NULL, DEFAULT 0 | Counter |
| created_at | TEXT | NOT NULL, DEFAULT now | |

## Table: `gates`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | |
| cycle_number | INTEGER | NOT NULL, FK | |
| gate_name | TEXT | NOT NULL | One of 12 gate names |
| passed | INTEGER | NOT NULL, DEFAULT 0 | 0/1 boolean |
| evidence | TEXT | NULLABLE | Evidence for gate state |
| created_at | TEXT | NOT NULL, DEFAULT now | |

UNIQUE constraint on (cycle_number, gate_name).

## Table: `tooling_evidence`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | |
| cycle_number | INTEGER | NOT NULL, FK | |
| command | TEXT | NOT NULL | Shell command executed |
| exit_code | INTEGER | NOT NULL | Process exit code |
| success | INTEGER | NOT NULL, DEFAULT 0 | 0/1 derived from exit_code |
| output | TEXT | NULLABLE | Combined stdout+stderr (first 2000 chars) |
| executed_at | TEXT | NOT NULL, DEFAULT now | |

## Table: `audit_log`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | |
| event_type | TEXT | NOT NULL | Phase name or event type |
| cycle_number | INTEGER | NULLABLE | Associated cycle |
| finding_id | TEXT | NULLABLE | Associated finding |
| actor | TEXT | NOT NULL, DEFAULT 'system' | Who triggered the event |
| detail | TEXT | NOT NULL | Human-readable detail |
| metadata | TEXT | NULLABLE | JSON blob for structured data |
| created_at | TEXT | NOT NULL, DEFAULT now | |

## Table: `evidence_chain`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | |
| evidence_id | TEXT | NOT NULL, UNIQUE | Hash-based evidence ID |
| content_hash | TEXT | NOT NULL | SHA-256 of evidence content |
| signature | TEXT | NOT NULL | Cryptographic signature |
| signer | TEXT | NOT NULL | Identity of signer |
| public_key_fingerprint | TEXT | NOT NULL | Key fingerprint |
| chain_index | INTEGER | NOT NULL | Position in chain |
| previous_hash | TEXT | NOT NULL | Hash of previous entry |
| payload | TEXT | NOT NULL | Evidence payload |
| created_at | TEXT | NOT NULL, DEFAULT now | |

`INTENDED`: This table's schema exists but `EvidenceChain` currently stores entries in-memory and persists to a JSON file, not to this table. The table is PLANNED for future use.

## Table: `remediation_attempts`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | |
| attempt_id | TEXT | NOT NULL, UNIQUE | Generated attempt ID |
| cycle_number | INTEGER | NOT NULL, FK | |
| finding_id | TEXT | NOT NULL | Finding being fixed |
| file_path | TEXT | NOT NULL | File being modified |
| line_start | INTEGER | NULLABLE | |
| line_end | INTEGER | NULLABLE | |
| status | TEXT | NOT NULL, CHECK IN (PENDING,APPLIED,REJECTED,FAILED,ROLLED_BACK) | |
| patch_content | TEXT | NULLABLE | JSON of fix data |
| error_message | TEXT | NULLABLE | Error if failed |
| duration_ms | INTEGER | NULLABLE | |
| created_at | TEXT | NOT NULL, DEFAULT now | |

## Table: `dead_letter`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | |
| finding_id | TEXT | NOT NULL | |
| cycle_number | INTEGER | NOT NULL, FK | |
| attempt_number | INTEGER | NOT NULL, DEFAULT 1 | |
| error_type | TEXT | NOT NULL, CHECK IN (UNPARSEABLE,TIMEOUT,PROVIDER_ERROR,INVALID_FIX,SANDBOX_REJECTED,UNKNOWN) | |
| raw_response | TEXT | NULLABLE | Raw LLM response (first 5000 chars) |
| recovery_hint | TEXT | NULLABLE | Human-readable hint |
| status | TEXT | NOT NULL, DEFAULT 'PENDING', CHECK IN (PENDING,RETRIED,RESOLVED,ABANDONED) | |
| created_at | TEXT | NOT NULL, DEFAULT now | |

## Table: `convergence_confidence`

| Column | Type | Constraints | Description |
|---|---|---|---|
| id | INTEGER | PK, AUTOINCREMENT | |
| cycle_number | INTEGER | NOT NULL, UNIQUE, FK | |
| verification_confidence | INTEGER | NOT NULL, DEFAULT 0 | 0-100 |
| detection_confidence | INTEGER | NOT NULL, DEFAULT 0 | 0-100 |
| test_confidence | INTEGER | NOT NULL, DEFAULT 0 | 0-100 |
| tooling_pass_ratio | REAL | NOT NULL, DEFAULT 0.0 | |
| file_coverage_ratio | REAL | NOT NULL, DEFAULT 0.0 | |
| verified_findings_ratio | REAL | NOT NULL, DEFAULT 0.0 | |
| created_at | TEXT | NOT NULL, DEFAULT now | |

## Table: `_schema_version`

| Column | Type | Constraints | Description |
|---|---|---|---|
| version | INTEGER | PK | Schema version number |
| applied_at | TEXT | NOT NULL | ISO timestamp |