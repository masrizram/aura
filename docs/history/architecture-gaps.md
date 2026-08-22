# Architecture Gaps — AURA v3.5

> **Generated from:** Full repository analysis of `src/aura/*.py`
> **Date:** August 2026
> **Version:** v3.5.0

This document identifies gaps between intended architecture and actual implementation, as well as architectural weaknesses, missing components, and areas of concern.

---

## 1. MISSING ARCHITECTURE

### 1.1 No Plugin System
**Declared:** `registry.json` has a `plugins` key with schema version 1.0.
**Actual:** Plugin count is 0. No plugin loading mechanism exists. `registry.json` is a placeholder file.
**Impact:** Extension mechanism is declared but not implemented. No way to add custom analyzers, auditors, or domains.
**Files:** `registry.json`

### 1.2 ~~Missing `db_fallback` Module~~ — RETRACTED (2026-08-22 audit)
**Status:** RETRACTED. The original claim that `state_machine.py:200-201` references a
`db_fallback` module was **incorrect** — direct source inspection shows no such
reference exists. This entry is preserved (struck through) as a documentation-integrity
record: earlier gap analysis contained a fabricated file:line citation. Current source
has no `db_fallback` reference; no such module is needed since the engine uses stdlib
`sqlite3` directly with no native-module fallback path.

### 1.3 Two Parallel Gate Systems — PARTIALLY RESOLVED (v3.5.x)
**Declared:** One convergence gate system.
**Actual:** Two separate 12-gate systems exist — user-facing (`state_machine.py`) and internal/judge (`convergence.py`). They are correlated but NOT identical, and the ConvergenceJudge does NOT apply the subclass-aware overrides that the Engine does.
**Fix applied (IMP-02):** Judge gate G07 is no longer hardcoded `True` — it is now derived from G06 (tooling pass), eliminating the contradictory G06=False/G07=True state. The two systems remain intentionally separate (judge = autonomous-loop proof; engine = user-facing actionable gates), and are now documented as such in `docs/decision-validation/`.
**Residual:** Cross-system reconciliation is still not enforced at runtime — documented limitation.

### 1.4 `evidence_chain` Table — RESOLVED (v3.5.x)
**Was:** Table defined in schema with zero readers/writers; EvidenceChain persisted to JSON only, hashes self-contained (deletion undetectable).
**Fix applied (IMP-04):** `Evidence` now carries `chain_index` + `previous_hash` (real hash chain, genesis = `"0"*64`). `verify_chain()` detects tampering, deletion, and reordering. `Database.insert_evidence_entry()` / `get_evidence_chain()` make the SQL table a live, queryable mirror.

### 1.5 Domain Auditor Wave 2-4
**Declared:** 40 domain metadata entries, 6 levels.
**Actual:** Only 11 Wave-1 auditors are implemented. Waves 2-4 (remaining 29 domains) are registered in `WAVE_REGISTRY` but have no implementation classes.
**Search:** `WAVE_REGISTRY` shows only key `1` with 11 classes.
**Impact:** 29 of 40 domains (72.5%) are PLANNED but NOT IMPLEMENTED.

---

## 2. INCOMPLETE IMPLEMENTATION

### 2.1 Shared Intelligence Layer — Partial
**Declared:** `SharedContext` has `call_graph`, `import_graph`, `ast_cache` fields for L4-L5 analysis.
**Actual:** These fields are declared with TODO comments but never populated. The `build()` method indexes files and parses dependencies but does NOT build the call graph or import graph.
**Files:** `domain_auditor.py:213-228`
**Impact:** Cross-file correlation (L4) and full evidence validation (L5) are stub implementations.

### 2.2 Repository Memory — Partial
**Declared:** `RepositoryMemory` class referenced in `__init__.py` and `engine.py` docstring.
**Actual:** `store_cycle_memory()` is called in Phase 13 (`engine.py:757`) but the implementation in `semantic.py` is not fully verified. The memory system is referenced but its actual persistence and cross-cycle retrieval mechanisms are minimal.
**Impact:** "Learns across cycles" is a stated principle but the implementation is light.

### 2.3 Evidence Chain Cryptographic Signing
**Declared:** `EvidenceChain` with `signature`, `signer`, `public_key_fingerprint` fields.
**Actual:** The `Evidence.compute_hash()` method uses SHA-256, but no cryptographic signing is performed. The `evidence_chain` table has signature fields but no signing key infrastructure.
**Impact:** Evidence chain provides hash integrity but not non-repudiation. Anyone with access to the DB can forge evidence entries.

### 2.4 Notification System
**Declared:** `NotificationsConfig` in `config.py` with `rate_limit_seconds`, `generate_status_badge`, `status_badge_output`.
**Actual:** No notification delivery mechanism is implemented. Status badge generation is declared but no code generates it.
**Impact:** Configuration exists but feature is NOT IMPLEMENTED.

---

## 3. UNUSED COMPONENTS

| Component | Location | Status |
|---|---|---|
| `evidence_chain` SQL table | `db.py:112-123` | Schema exists, zero code writes to it |
| `registry.json` plugins array | `registry.json` | Empty, no plugin loading code |
| `finding_subclass.py` `SECURITY_ADVISORY`, `TOOLING_FAILURE`, `ENVIRONMENT_BLOCKER`, `GOVERNANCE_FINDING`, `TEST_QUALITY`, `CODE_QUALITY`, `INFORMATIONAL` enums | `finding_subclass.py:23-30` | All defined but only CODE_DEFECT and SECURITY_ADVISORY have rule mappings |
| `DomainLevel.RUNTIME_RESILIENCE`, `DATA_DISTRIBUTED`, `DELIVERY_OPS`, `QUALITY_GOVERNANCE` | `domain_auditor.py:44-50` | Defined but no auditors exist for these levels |
| `benchmark.py` (v2) | `benchmark.py` | Superseded by `benchmark_v3.py` — likely dead code |
| `FindingStatus` enum (semantic lifecycle) | `semantic.py:34-44` | RAW→LOCATED→ANALYZED→... defined but NOT enforced or used in state machine |

---

## 4. CIRCULAR DEPENDENCIES

**NONE DETECTED.** The import graph is a strict DAG. All modules import downward from `cli.py`/`engine.py` to simpler modules.

---

## 5. INCORRECT ASSUMPTIONS

### 5.1 ~~"All module dependencies loaded"~~ — RESOLVED (v3.5.x)
The `module_dependency_integrity` gate previously always received `True` (`engine.py`).
**Fix applied (IMP-02):** `Engine._check_module_integrity()` now performs a real
import check of all required `aura.*` modules at engine init (fail-closed) and feeds
the result into gate evaluation.

### 5.2 ~~"typecheck_pass" in ConvergenceJudge~~ — RESOLVED (v3.5.x)
G07 (`typecheck_pass`) in `ConvergenceJudge.evaluate()` previously returned `True`
unconditionally. **Fix applied (IMP-02):** G07 is now derived from G06 (tooling pass)
— it no longer claims an independent signal that does not exist.

### 5.3 Test Coverage Scanning
Test coverage is computed twice — once in CORRELATE (`engine.py:358-374`, commented as "NOT re-added here") and again in PRIORITIZE (`_to_finding_dicts`). The comment acknowledges the "36+4=41 bug" but the architecture of ancillary findings is fragile.

---

## 6. DOCUMENTATION/IMPLEMENTATION MISMATCH

| Claim | Source | Actual |
|---|---|---|
| "12 independent adversarial roles" | `adversarial.py` docstring | 12 roles exist but are legacy; the primary path uses DomainAuditOrchestrator |
| "62 language groups / 650+ rules" (older docs) | docs | Actually **51 language groups / 17 with rules / 127 rules** (verified by runtime inspection, 2026-08-22) |
| "pytest-asyncio>=0.24" | `pyproject.toml` dev deps | No async code exists; pytest-asyncio is declared but unused |
| "cryptography>=42.0" | `pyproject.toml` signing extras | No actual cryptographic signing implementation |
| "aiosqlite>=0.20" | `pyproject.toml` db extras | No async DB code exists; standard sqlite3 is used |

---

## 7. SECURITY GAPS

See [docs/security/security-controls.md](security/security-controls.md) for the full inventory. Key gaps:
- No DB encryption
- No checkpoint integrity verification
- Subprocess tooling executes arbitrary npm scripts
- Block list for AutoFixer is not comprehensive

---

## 8. RELIABILITY GAPS

| Gap | Impact |
|---|---|
| No partial cycle recovery | Crash mid-cycle = restart from scratch |
| Evidence chain JSON files not synced with DB table | Two parallel storage mechanisms, possible divergence |
| No filesystem snapshot before AutoFixer | Rollback failure = permanent file damage |
| Checkpoint has no integrity hash | Resume from corrupted checkpoint undetected |

---

## 9. OBSERVABILITY GAPS

| Gap | Impact |
|---|---|
| No metrics export | No Prometheus/OpenTelemetry integration |
| No structured health endpoint | `aura health` is CLI-only, no HTTP endpoint |
| No alerting | No notification of convergence/non-convergence |
| No performance tracing | No duration tracking for individual phases |

---

## 10. SCALABILITY BOTTLENECKS

| Bottleneck | Impact |
|---|---|
| Synchronous single-threaded execution | All 13 phases run sequentially in one process |
| Full repository `rglob` per cycle | Every cycle re-scans the entire filesystem |
| SQLite in-process | No concurrent access, no separate DB server |
| LLM calls are blocking | `auto-fix` blocks on LLM response (up to 120s timeout) |
| No chunked audit | Scale config declares `require_chunked_audit_above: 2000` but no chunking is implemented |

---

## 11. SINGLE POINTS OF FAILURE

| SPOF | Description |
|---|---|
| SQLite file | All state in one file; corruption = total state loss |
| LLM API | `auto-fix` requires LLM; without it, no autonomous remediation |
| In-process memory | All context dictionaries live in process memory |
| git CLI | git context (branch, commits, file list) requires git |

---

## 12. DATA CONSISTENCY RISKS

| Risk | Description |
|---|---|
| Stable ID collision | SHA-256 truncated to 12 hex chars = 48 bits; collision probability low but non-zero |
| Finding status preservation race | ON CONFLICT DO UPDATE preserves terminal statuses but does not prevent concurrent cycle writes |
| Evidence chain / DB table divergence | Evidence stored in both JSON files and SQL table but never synced |
| Cycle counter inconsistency | `consecutive_converged_cycles` and `audits_since_last_finding` are manually incremented; desync possible if convergence phase is interrupted |

---

## 13. VALIDATION WEAKNESSES

| Weakness | Description |
|---|---|
| No cross-cycle finding ID tracking in state machine | `validate_finding_state_integrity` checks transitions but not cross-cycle identity |
| Gate findings cross-check is limited | `validate_gate_findings_crosscheck` only checks 6 of 12 gates |
| ConvergenceJudge and Engine use different gate systems | Result: autonomous loop may disagree with CLI about convergence |
| LIMITATIONS.md validation is structural only | Checks format, not whether documented limitations are honest |
| Regex-only scanner for non-Python languages | PHP/JS/Go use regex patterns, not real parsers; false positive rate unmeasured |

---

## 14. FALSE-CONVERGENCE RISKS

| Risk | Description |
|---|---|
| CLAIM: "All gates pass" ≠ ACTUAL: "All defects fixed" | Gates can pass with DEFERRED/WAIVED findings |
| Semantic mitigation filter can mask real findings | If a P0 is misclassified as MITIGATED, it's removed from gate evaluation |
| Subclass-aware override: only CODE_DEFECT blocks | An injection vulnerability incorrectly classified as SECURITY_ADVISORY would NOT block |
| Two-gate-system divergence | ConvergenceJudge may disagree with Engine — no reconciliation mechanism |

---

## 15. PROVIDER-ROUTING WEAKNESSES

| Weakness | Description |
|---|---|
| No provider health persistence | Circuit breaker state is in-memory; process restart resets to CLOSED |
| Ollama auto-discovery is one-shot | If Ollama starts after AURA, it won't be detected |
| No request-level fallback | If primary provider fails mid-request, there's no transparent retry with fallback for that same request |
| Provider response is always `untrusted=True` | This is by design for LLM responses, but means the system has no trustworthy data source |