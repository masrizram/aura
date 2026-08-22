# AURA Documentation Audit — v3.5.0

> **Audit date:** 2026-08-22
> **Method:** Every claim in `docs/` cross-checked against source code (`src/aura/*.py`), tests (`tests/`), and live execution (`pytest`, `ruff`, runtime inspection).
> **Source of truth:** source code + verified runtime behavior.

## Verified baseline numbers (from source, not docs)

| Metric | Verified value | How verified |
|---|---|---|
| Tests | **161 passed** | `pytest tests/ -q` → 161 passed in 12.97s |
| Language groups declared | **51** | `len(LANG_EXTS)` runtime inspection |
| Language groups with rules | **17** | `sum(1 for v in _PATTERNS.values() if v)` |
| Total detection rules | **127** | `sum(len(v) for v in _PATTERNS.values())` |
| Ruff findings | **720 errors** (390 E501, 57 F401, 33 E701, 25 F541, 23 S110, 8 invalid-syntax in benchmark_v3.py, …) | `ruff check src/ --statistics` |
| Convergence gates (engine) | **12** | `GATE_NAMES` in state_machine.py |
| Convergence gates (judge) | **12** (G01–G12, different semantics) | convergence.py |
| Engine phases | **13** | `Engine.PHASES` |
| Audit phases actually run | 13, sequential, in-process | engine.py `run_audit` |

## Per-document verdict

| Document | Verdict | Notes |
|---|---|---|
| docs/README.md | INCOMPLETE | Index only; numbers not re-verified (claims "62 languages" inherited from stale source) |
| architecture/system-architecture.md | ACCURATE (structure) / INCORRECT (metrics) | Layers correct; language/rule counts wrong |
| architecture-gaps.md | PARTIAL | §1.2 `db_fallback` claim is **INCORRECT** — no such reference exists in state_machine.py:200-201 (verified by direct read). §6 "62 language groups / 650+ rules" is **INCORRECT** — actual is 51 groups / 127 rules. §1.3, §1.4, §2.x, §5.x, §13, §14 verified ACCURATE |
| context/context-diagram.md | ACCURATE | Matches actual external entities (CLI, git, FS, SQLite, LLM API, tooling subprocesses) |
| dfd/level-0.md, level-1.md | ACCURATE | Data stores match db.py schema |
| flowmap/audit-flow.md, startup-flow.md | ACCURATE | Matches 13-phase order in engine.py |
| sequence/*.md | ACCURATE | provider-request.md correctly shows circuit breaker wrapper |
| state/*.md | ACCURATE | Matches VALID_FINDING_TRANSITIONS, CircuitState, classification transitions |
| component/*.md | ACCURATE | DAG confirmed — no circular imports (verified) |
| data-model/*.md | ACCURATE (schema) / INCOMPLETE (usage) | ERD matches SCHEMA_SQL; does not note that `evidence_chain` table has zero writers/readers |
| decision-validation/*.md | PARTIAL | invariants.md does not document the SCORE_MONOTONICITY invariant which is **wrong for legitimate remediation cycles** (see improvement plan IMP-03) |
| security/*.md | ACCURATE (inventory) | Controls listed match code; gaps honestly noted |
| failure-recovery/*.md | PARTIAL | retry.md documents provider retry but not the **retry-amplification risk** (in-provider retry × caller retry) or missing jitter |

## Critical documentation defects found

1. **Stale metrics everywhere.** "62 languages / 650+ rules" appears in docs and `__init__.py` docstring; actual is 51 declared / 17 active / 127 rules. README badges already say 51/127 — docs disagree with README.
2. **Phantom `db_fallback` claim** in architecture-gaps.md §1.2 — fabricated reference; file:line does not contain it.
3. **Invariant SCORE_MONOTONICITY undocumented as harmful:** `validate_gate_evidence_integrity` flags any score decrease as a violation. In a remediation loop that introduces new findings (or where semantic re-classification downgrades), score legitimately decreases. This invariant is **not enforced at runtime** (engine never calls the validator) — but documenting it as a rule is misleading.
4. **`evidence_chain` table**: documented as part of data model; in reality the `EvidenceChain` class persists to JSON files only. Schema/code divergence undocumented in data-model docs.
5. **G07 `typecheck_pass`**: documented in sequence/state docs as a real gate; implementation is hardcoded `True`.
6. **`module_dependency_integrity`**: documented as a gate; engine always passes `module_integrity_pass=True`.

## Status summary

- ACCURATE: 14 documents
- PARTIAL: 5 documents
- INCORRECT (localized): 2 documents (architecture-gaps.md §1.2/§6, docs/README.md metrics)
- OUTDATED: metrics across the set
- REDUNDANT: none material
- MISSING: documentation-audit.md (this file), architecture-improvement-plan.md, target-architecture.md, final-consistency-audit.md
