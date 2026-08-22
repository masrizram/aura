# Data Model — README

Complete data model documentation for AURA.

| Document | Scope |
|---|---|
| [erd.md](erd.md) | Entity-Relationship Diagram (Mermaid), all 12 tables with columns |
| [data-dictionary.md](data-dictionary.md) | Every column with type, constraints, and description |
| [data-lifecycle.md](data-lifecycle.md) | CRUD patterns, INSERT/UPDATE/UPSERT flows, persistence boundaries |

## Storage Summary

| Storage | Type | Location |
|---|---|---|
| Primary database | SQLite file | `.aura/state/aura.db` |
| Checkpoint state | JSON file | `.aura/checkpoint.json` |
| Cycle evidence | JSON + patch files | `.aura/evidence/cycle-NNN/` |
| Convergence proof | JSON file | `.aura/evidence/convergence_proof.json` |

## Table Summary

| Table | Rows per cycle | Key operations |
|---|---|---|
| `cycles` | 1 | INSERT, UPDATE |
| `findings` | 0-N | INSERT/UPSERT, SELECT, UPDATE |
| `convergence` | 1 | UPSERT |
| `gates` | 12 | UPSERT |
| `tooling_evidence` | 0-N | INSERT |
| `audit_log` | 14+ | INSERT |
| `evidence_chain` | 0-N | LIVE (v3.5.1) — JSON file is source of truth; table is a queryable mirror via `insert_evidence_entry()` |
| `remediation_attempts` | 0-N | INSERT |
| `dead_letter` | 0-N | INSERT, UPDATE |
| `convergence_confidence` | 1 | UPSERT |