# AURA v3.5 — Comprehensive Documentation

> **Generated from full repository source-code analysis.**
> **Branch:** main (commit 789d72a)
> **Date:** August 2026

## Documentation Index

### Architecture
- [System Architecture](architecture/system-architecture.md) — Overall system design, layers, subsystems, runtime boundaries
- [Architecture README](architecture/README.md) — Quick reference with module summary table

### Context
- [Context Diagram](context/context-diagram.md) — External actors, data exchange directions
- [Context README](context/README.md) — External entities summary

### Data Flow
- [DFD Level 0](dfd/level-0.md) — Context-level processes, data stores, external entities
- [DFD Level 1](dfd/level-1.md) — 13-phase audit pipeline detail with data flows
- [DFD README](dfd/README.md) — High-level audit data flow diagram

### Execution Flow
- [Audit Flow](flowmap/audit-flow.md) — Full audit pipeline, startup flow, exceptional paths
- [Flowmap README](flowmap/README.md) — 13-phase quick reference table

### Sequence Diagrams
- [Audit Execution](sequence/audit-execution.md) — Complete 13-phase cycle sequence with all actors
- [Provider Request](sequence/provider-request.md) — LLM provider with circuit breaker + autonomous fix loop
- [Finding Validation](sequence/finding-validation.md) — Evidence-based validation + state transition enforcement
- [Sequence README](sequence/README.md)

### State Machines
- [Finding State](state/finding-state.md) — 11 active + 3 terminal statuses, transition rules
- [Provider & Classification State](state/provider-state.md) — Classification (4), Circuit Breaker (3), Provider Health (4)
- [Audit Cycle State](state/audit-state.md) — 13-phase cycle + autonomous loop safeguard states
- [State README](state/README.md)

### Components
- [Component Diagram](component/component-diagram.md) — Full module catalog, dependency analysis, coupling, responsibility leakage
- [Dependency Graph](component/dependency-graph.md) — Import graph, fan-in/fan-out counts
- [Component README](component/README.md) — Quick index

### Data Model
- [ERD](data-model/erd.md) — Entity-Relationship Diagram, all 12 tables
- [Data Dictionary](data-model/data-dictionary.md) — Every column with type, constraints
- [Data Lifecycle](data-model/data-lifecycle.md) — CRUD patterns, persistence boundaries
- [Data Model README](data-model/README.md)

### Decision & Validation
- [Audit Decision Flow](decision-validation/audit-decision-flow.md) — Gate evaluation tree, scoring algorithm, context suppression
- [Finding Validation](decision-validation/finding-validation.md) — Validation pipeline, evidence requirements, subclass classification
- [Convergence Criteria](decision-validation/convergence.md) — Gate conditions, scoring formula, resolved vs active statuses
- [Invariants](decision-validation/invariants.md) — 6 classes of mathematical/structural invariants
- [Decision README](decision-validation/README.md)

### Security
- [Threat Model](security/threat-model.md) — STRIDE analysis across all 6 categories
- [Trust Boundaries](security/trust-boundaries.md) — Trust boundary map + complete controls inventory
- [Attack Surface](security/attack-surface.md) — Attack vectors, dependency supply chain risk
- [Security Controls](security/security-controls.md) — Implemented/Partial/Missing controls
- [Security README](security/README.md)

### Failure & Recovery
- [Error Flow](failure-recovery/error-flow.md) — Error taxonomy, propagation, fail-open vs fail-closed decisions
- [Retry Strategy](failure-recovery/retry.md) — LLM retry, safeguard limits, AutoFixer retry, dead letter queue
- [Circuit Breaker](failure-recovery/circuit-breaker.md) — State machine, provider registry, failover scenarios
- [Recovery Matrix](failure-recovery/recovery-matrix.md) — 40+ failure modes with recovery mechanisms
- [Failure README](failure-recovery/README.md)

### Architecture Gaps
- [Architecture Gaps](architecture-gaps.md) — 15 categories of gaps, missing architecture, incomplete implementation, dead components (with v3.5.1 resolution status)

### Engineering Artifacts (v3.5.1 hardening cycle)
- [Documentation Audit](documentation-audit.md) — per-document ACCURATE/INCORRECT verdicts with evidence
- [Architecture Improvement Plan](architecture-improvement-plan.md) — IMP-01..IMP-10 with severity, root cause, migration risk
- [Target Architecture](target-architecture.md) — CURRENT → PROBLEM → TARGET → MIGRATION per subsystem
- [Final Consistency Audit](final-consistency-audit.md) — source ↔ docs ↔ README ↔ tests matrix (incl. RUN #2 addendum)
- [RUN #2 Deep Architecture Audit](run2-deep-architecture-audit.md) — evidence-driven defect log R2-01..R2-09 with reproduction proof
- [RUN #3 Adversarial Final Audit](run3-adversarial-final-audit.md) — falsification campaign; 2 P3 defects fixed, primary vectors survived

---

## System Summary

### What AURA Is (Verified from Source)
- A **local CLI tool** that runs a 13-phase deterministic audit pipeline on a repository
- Currently **v3.5.3** (23 source modules, **206 passing tests**)
- Primary detection via **regex patterns** (127 rules across 51 language groups, 17 with active rules)
- Enhanced with **semantic intelligence**: real Python AST parsing, PHP/JS structural parsing, taint analysis, CWE/OWASP/CVSS mapping
- **Two adversarial audit systems**: Legacy 12-role auditor + Enhanced 40-domain orchestrator (11 Wave-1 domains active)
- **12-gate convergence model** with 7 safeguards, subclass-aware gate evaluation
- **SQLite persistence** with WAL mode, 12 tables, foreign keys
- **LLM-powered autonomous remediation** with circuit breaker, classified retry + full jitter, provider fallback, AutoFixer sandbox (`is_relative_to` containment), and rollback
- **Deterministic convergence decisions** — LLM output is always UNTRUSTED, gates are measurable
- **Tamper-evident evidence chain** (hash-linked, deletion/reorder detection) and **integrity-hashed checkpoints** (v3.5.1)

### What AURA Is NOT
- Not a SaaS or web service — runs as a local process
- Not a replacement for human code review — regex-based scanning with semantic enrichment only
- Not a full SAST tool — no real data-flow analysis for non-Python languages
- Not fully autonomous — `auto-fix` requires LLM API access
- Not a plugin system — `registry.json` has zero plugins

### Key Numbers
| Metric | Value |
|---|---|
| Source modules | 23 |
| Total Python lines | ~10,900 |
| Language groups declared | 51 (17 with active rules) |
| Pattern rules | 127 |
| Test files | 8 |
| Tests | 206 |
| Database tables | 12 |
| Convergence gates | 12 (user) + 12 (internal) |
| Domain auditors | 40 registered, 11 active |
| Finding statuses | 11 active + 3 terminal |
| Execution contexts | 10 |
| Error categories | 14 |
| CLI commands | 10 |
| Test assertions | 139 passing |

### Entry Points
```bash
python -m aura              # Module entry (__main__.py)
aura init                   # Initialize database
aura audit                  # Run full 13-phase audit
aura auto-fix               # Autonomous audit→fix→verify loop
aura status                 # Show engine status
aura health                 # Health check
aura doctor                 # System diagnostics
aura verify [FINDING_ID]    # Show findings + remediation
aura log                    # Show audit log trail
aura report                 # Generate markdown report
aura trend                  # Show cycle-by-cycle trend
```

---

*Generated by AURA v3.5 documentation agent. All claims verified against source code at `src/aura/*.py`.*