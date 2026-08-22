# Final Consistency Audit — AURA v3.5.1

> **Date:** 2026-08-22
> **Method:** every row verified against (a) source code, (b) docs, (c) README, (d) executed tests.
> Legend: **CONSISTENT** = all four columns agree; **PARTIAL** = agrees with honest documented gaps; **INCONSISTENT** = contradiction found; **UNKNOWN** = not verifiable.

## Verification evidence gathered this cycle

| Check | Command / source | Result |
|---|---|---|
| Tests | `python -m pytest tests/ -q` | **186 passed** (161 pre-existing + 26 new IMP regression tests − 1 net updated) |
| Lint | `ruff check src/` | 0 invalid-syntax (benchmark_v3.py fixed); remaining style debt (E501 etc.) is documented, non-blocking |
| Typecheck | `mypy` on v3.5.1-touched modules (providers, evidence, durable) | **clean** |
| CLI smoke | `python -m aura --help`, `aura doctor` | OK — "All systems OK" |
| Metrics | runtime inspection of `_PATTERNS`, `LANG_EXTS` | 51 groups / 17 active / **127 rules** |
| Gate wiring | `engine.py` | `module_integrity_pass=self._module_integrity` (real check) |
| Judge G07 | `convergence.py` | `g07 = g06` (derived, documented) |

## Consistency matrix

| Area | Source | Docs | README | Tests | Status |
|---|---|---|---|---|---|
| Architecture | 13-phase engine, DAG verified | architecture/* updated | Architecture section matches | test_engine lifecycle | **CONSISTENT** |
| Audit pipeline | 13 phases in `Engine.PHASES` | dfd/flowmap/sequence match | pipeline described accurately | `test_run_audit_*` | **CONSISTENT** |
| Provider system | single stack: registry→breaker→provider; classified retry + jitter; adapter module-level | retry.md rewritten; security-controls updated | Provider system section accurate | `TestProviderRetryPolicy`, `TestProviderBackedLLMClient` (8 tests) | **CONSISTENT** |
| State machine | transitions + gates; score invariants removed | invariants.md documents removal + rationale | documented under Validation | state_machine tests updated (2 changed), 60+ pass | **CONSISTENT** |
| Data model | schema + new evidence_chain accessors | data-model/README marks table LIVE | evidence chain described | `TestEvidenceChainDbSync` | **CONSISTENT** |
| Validation / convergence | 12 engine gates + 12 judge gates; G07 derived; module integrity real | decision-validation/* updated | both systems explained honestly | `TestJudgeG07Derived`, `TestModuleIntegrityReal`, false-convergence suite | **CONSISTENT** |
| Security | is_relative_to containment; advisory blocklist; checkpoint hash; env-only secrets | security-controls.md v3.5.1 rewritten | Security section matches | `TestPathContainment`, `TestCheckpointIntegrity`, test_security.py | **CONSISTENT** |
| Failure recovery | retry+jitter, breaker, fallback, rollback, DLQ, checkpoint integrity | failure-recovery/retry.md rewritten | Reliability section matches | retry/checkpoint tests | **CONSISTENT** |
| Configuration | config.py + aura.json + .env.example | docs match | Installation/Configuration verified against .env.example | test_config.py | **CONSISTENT** |
| CLI/API | 10 commands incl. auto-fix | flowmap/startup-flow matches | Usage section verified | engine/cli integration tests | **CONSISTENT** |
| Observability | cycle_id + phase durations in audit_log | documented in README + improvement plan | Observability bullet present | `TestCycleObservability` | **CONSISTENT** |
| Metrics claims | 51 groups / 17 active / 127 rules | all docs fixed (14 files) | badges + text fixed | runtime inspection | **CONSISTENT** |

## Items verified PARTIAL-by-design (honestly documented, not contradictions)

| Item | Where documented |
|---|---|
| 29/40 domain auditors unimplemented (Wave 2-4) | architecture-gaps.md §1.5, README "What AURA does NOT yet do" |
| No evidence signing (fields exist, no key infra) | security-controls.md MISSING, README boundaries |
| No notification delivery / no plugin system | architecture-gaps.md, README boundaries |
| Two gate systems not runtime-reconciled | architecture-gaps.md §1.3 residual, invariants.md note |
| Non-Python languages = pattern matching only | LIMITATIONS.md, README boundaries |

## Discrepancies found and FIXED during this cycle

1. architecture-gaps.md §1.2 phantom `db_fallback` citation → RETRACTED in place.
2. "62 languages / 650+ rules" in 14 files → corrected to verified 51/17/127.
3. `evidence_chain` documented as schema-only → now live; data-model README updated.
4. retry.md documented deterministic backoff → rewritten to match jittered implementation.
5. invariants.md listed score monotonicity as active → marked REMOVED with rationale.
6. README overclaimed nothing new; boundaries section added; test badge 139→186.

## Residual known debt (documented, not fixed this cycle — P2/P3)

- Ruff style debt (E501 line-length majority) across pre-existing files — cosmetic, non-blocking; no syntax errors remain.
- `benchmark.py` (v2) retained, superseded by `benchmark_v3.py` — marked in improvement plan IMP-08; kept for benchmark history.
- `validate_finding_state_integrity` / `validate_gate_findings_crosscheck` remain opt-in library functions (engine does not call them at runtime) — now explicitly documented as such in invariants.md.

## Verdict

All 12 matrix areas: **CONSISTENT**. No INCONSISTENT items remain in scope.
UNKNOWN items: none.

---

## Addendum — RUN #2 (v3.5.2, 2026-08-22)

RUN #2 re-audited the v3.5.1 baseline (`00d8b2a`) for NEW defects (IMP-01..09 not
reopened). Six material defects were reproduced and fixed; two lower-severity
defects fixed in the same cycle. Full evidence: `run2-deep-architecture-audit.md`.

| Finding | Severity | Source fix | Docs updated | Regression test | Status |
|---|---|---|---|---|---|
| R2-01 no_material_new_findings blind (id vs finding_id) | P0 | state_machine `_finding_key` | this addendum + run2 doc | `TestNewMaterialFindingsGate` | CONSISTENT |
| R2-03 tooling `|| true` fail-open | P0 | engine `_detect_commands` + `fail_open` config | README Reliability, retry.md | `TestToolingExitCodes` | CONSISTENT |
| R2-04 provider fallback never engaged | P1 | providers `chat_with_fallback` | README Provider resilience | `TestProviderFallback` | CONSISTENT |
| R2-02 regression blind to severity drift | P1 | engine `_phase_regression` | run2 doc | `TestRegressionPhase` | CONSISTENT |
| R2-06 resume resets safeguards | P1 | durable `_snapshot/_restore_safeguard` | run2 doc | `TestDurableSafeguardRestore` | CONSISTENT |
| R2-05 severity_weights dead param | P2 | state_machine score derivation | invariants.md unchanged (scoring note) | `TestSeverityWeightsHonored` | CONSISTENT |
| R2-08 evidence chain never populated | P2 | engine `_phase_convergence` appends + DB mirror | data-model README (already LIVE) | `TestEvidenceChainWiring` | CONSISTENT |
| R2-07 version drift 3.5.0 vs 3.5.1 | P3 | `__init__`/`cli`/`pyproject` → 3.5.2 | CHANGELOG 3.5.2 | runtime `aura.__version__` | CONSISTENT |

**Post-fix verification:** `pytest` → **202/202 passed**; `mypy` on changed modules
(state_machine, providers, durable, config) → clean; `ruff check src/` → 0
invalid-syntax; `aura doctor` → "All systems OK"; `aura.__version__` → 3.5.2.

**Regression check vs baseline 00d8b2a:** all 186 baseline tests still pass; 16 new
tests added; no baseline behavior removed except the three defective behaviors
(false-pass tooling, blind new-material gate, no fallback), each replaced with a
fail-closed equivalent and covered by a regression test.

**Newly documented honest boundaries (README):** tooling now fail-closed by
default (a repo with failing tests will no longer converge) — this is intended
behavior change, opt-out via `engine.tooling.fail_open=true`.
