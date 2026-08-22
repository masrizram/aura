# Data Dictionary

> Source: `src/aura/db.py` (schema + repository methods), `semantic.py` (RepositoryMemory),
> `durable.py` (checkpoint), `convergence.py` (proof), `evidence.py` (hash-chain),
> `db.py` dead_letter. Types are Python-side; SQLite storage classes are affinity only.

## `cycles` — one row per audit cycle

| column | type | notes/default | constraint |
|---|---|---|---|
| id | int | PK AUTOINCREMENT | — |
| cycle_number | int | e.g. 1,2,3… | UNIQUE, FK target |
| phase | text | 'INIT'..'PUSH_APPROVAL' | default 'INIT' |
| status | text | RUNNING/COMPLETE/… | default 'RUNNING' |
| classification | text | NOT_READY/CONDITIONALLY_READY/PRODUCTION_READY/HUMAN_BLOCKED | default 'NOT_READY' |
| overall_score | int | 0-100 | default 0 |
| cycles_without_progress | int | | default 0 |
| consecutive_converged_cycles | int | | default 0 |
| started_at | text ISO | set at insert | NOT NULL |
| completed_at | text ISO | nullable | — |
| last_change_hash | text | nullable | — |
| created_at / updated_at | text ISO | datetime('now') | defaults |

## `findings` — one row per unique finding per latest encounter

`finding_id` is **stable across cycles** (sha256 of `file:line:rule[:12]`, `engine.py:60-68`).
The table keeps the LATEST known row per `finding_id`; `cycle_number` is updated on
re-encounter (`INSERT ON CONFLICT(finding_id) DO UPDATE SET cycle_number = excluded.cycle_number`,
`db.py:315-341`). Status is only advanced: if the stored status is terminal
(VERIFIED/WAIVED/ACCEPTED_RISK/OUT_OF_SCOPE) it is preserved; otherwise the
incoming status wins.

| column | type | notes |
|---|---|---|
| finding_id | text | UNIQUE (stable identity) |
| cycle_number | int | FK → cycles |
| severity | text | CHECK in {P0..P5} |
| category | text | free (SECURITY, CORRECTNESS, ARCHITECTURE, …, INFO) |
| status | text | CHECK in 12-status set |
| problem | text | human/LLM description |
| file_path / line_number | text / int | relative path, 1-based line |
| remediation | text | textual suggestion |
| evidence | text | 120-char line excerpt or JSON |
| assigned_to / reviewed_by | text | unused by engine (NULL) |

## `convergence` — one row per cycle

`cycle_number UNIQUE`; carries `converged` (0/1), `classification`, `reason`,
`overall_score`, `consecutive_converged_cycles`, `audits_since_last_finding`.

## `gates` — one row per gate per cycle

`UNIQUE(cycle_number, gate_name)`; `passed` 0/1; `evidence` free text.

## `tooling_evidence`

`command`, `exit_code` (-1 on timeout/exception), `success` (0/1),
`output` truncated to first 2000 chars of stdout+stderr (`engine.py:989`).

## `evidence_chain`

Tamper-evident log entries: `evidence_id UNIQUE`, `content_hash`, `signature`,
`signer`, `public_key_fingerprint`, `chain_index`, `previous_hash`, `payload`.
Engine in-memory chain (`EvidenceChain`) links by sha256 with genesis `'0'*64`;
DB table mirrors persistence when used.

## `remediation_attempts`

`attempt_id UNIQUE`, `cycle_number`, `finding_id`, `file_path`, `line_start/line_end`,
`status` CHECK in {PENDING, APPLIED, REJECTED, FAILED, ROLLED_BACK}, `patch_content`,
`error_message`, `duration_ms`.

## `audit_log` (append-only by convention)

`event_type` (e.g. INIT, DISCOVER, …, PUSH_APPROVAL, CYCLE_OBSERVABILITY), `cycle_number`,
`finding_id`, `actor` (default 'system'), `detail`, `metadata` (JSON). Written via
`db.insert_audit_log` from every phase.

## `dead_letter`

For LLM remediation responses that could not be applied:
`error_type` CHECK in {UNPARSEABLE, TIMEOUT, PROVIDER_ERROR, INVALID_FIX, SANDBOX_REJECTED, UNKNOWN},
`status` CHECK in {PENDING, RETRIED, RESOLVED, ABANDONED}, `raw_response`, `recovery_hint`.

## `convergence_confidence`

Per-cycle dimension scores (0-100 ints + 0.0-1.0 ratios): `verification_confidence`,
`detection_confidence`, `test_confidence`, `tooling_pass_ratio`, `file_coverage_ratio`,
`verified_findings_ratio`.

## File-based state (outside SQLite)

- **`.aura/checkpoint.json`** — `{version:"1.1.0", last_cycle, last_updated, state, state_hash}`
  where `state_hash` = sha256 of canonical JSON of `state` (tamper-evident resume).
  Legacy 1.0.0 without hash is accepted but flagged `_integrity="legacy-unverified"`
  (`durable.py:59-82`).
- **`.aura/memory.json`** — RepositoryMemory persistent note store (see `semantic.py`).
- **`.aura/evidence/convergence_proof.json`** — `{engine, converged_at_cycle, converged,
  classification, gates, all_gates_pass, violations, deterministic:true,
  llm_involvement:"NONE", generated_at}` (`convergence.py:307-324`).
