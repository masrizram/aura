# AURA Documentation — Blind Reconstruction Index

> This entire `docs/` tree was rebuilt **2026-08-22** by blind reverse engineering (Rule 3→5):
> only source code, tests, configuration, database schema, dependencies, runtime probes,
> and the CLI were consulted. Prior documentation was deleted first (Rule 3) and is
> preserved separately in `docs/history/` untouched.

Each file cites its implementing source locations inline. Claims that could not be
verified from the implementation are marked **UNKNOWN** or **UNVERIFIED** rather than asserted.

## Current-state documentation

| Area | Entry point |
|---|---|
| System architecture (single source) | `architecture/README.md` |
| Context diagram (system boundary) | `context/context-diagram.md` |
| Data flow diagrams | `dfd/level-0.md`, `dfd/level-1.md` |
| Phase flowmaps | `flowmap/audit-flow.md`, `flowmap/startup-flow.md` |
| Sequence diagrams | `sequence/audit-execution.md`, `sequence/finding-validation.md`, `sequence/provider-request.md` |
| State machines | `state/audit-state.md`, `state/finding-state.md`, `state/circuit-breaker-state.md`, `state/provider-state.md` |
| Components & dependencies | `component/component-diagram.md`, `component/dependency-graph.md` |
| Data model | `data-model/README.md` (schema), `data-model/data-dictionary.md`, `data-model/data-lifecycle.md`, `data-model/erd.md` |
| Decision & convergence validation | `decision-validation/README.md` (index), `decision-validation/convergence.md`, `decision-validation/finding-validation.md`, `decision-validation/invariants.md`, `decision-validation/audit-decision-flow.md` |
| Security | `security/README.md` (index), `security/threat-model.md`, `security/trust-boundaries.md`, `security/attack-surface.md`, `security/security-controls.md` |
| Failure & recovery | `failure-recovery/README.md` (index), `failure-recovery/retry.md`, `failure-recovery/circuit-breaker.md`, `failure-recovery/provider-failover.md`, `failure-recovery/error-flow.md`, `failure-recovery/recovery-matrix.md` |

## Historical evidence (preserved, never edited)

- `history/run2-deep-architecture-audit.md`, `history/run3-adversarial-final-audit.md`
- `history/architecture-gaps.md`, `history/architecture-improvement-plan.md`
- `history/documentation-audit.md`, `history/final-consistency-audit.md`
- `history/repository-external-analysis.md`, `history/q-external-analysis-prompt.md`
- `LIMITATIONS.md` (repo root) — **load-bearing runtime input** (gate `limitations_documented` reads it every cycle, `engine.py:594`).

## Verification artifacts

- `BASELINE.md` (repo root) — pre-rebuild quality-gate record.
- Consistency matrix: `docs/decision-validation/README.md` §matrix + `docs/component/dependency-graph.md`.
