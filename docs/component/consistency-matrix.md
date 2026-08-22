# Documentation ↔ Code Consistency Matrix

> Built from source evidence, tests, and live probes (2026-08-22). Each row maps a
> claim → implementing module → verifying test/probe → documenting file → classification.

## Core claims

| # | Claim | Module(s) | Verified by | Doc | Status |
|---|---|---|---|---|---|
| C-01 | 13-phase fixed pipeline per cycle | engine.py:53-57,135-183 | tests/test_engine.py + live probe | architecture/README.md §5; flowmap/audit-flow.md; dfd/level-0.md | ACCURATE |
| C-02 | CLI = 10 commands | cli.py:89-632 | `aura --help` lists 10; `doctor` runs | architecture/README.md; context/context-diagram.md | ACCURATE |
| C-03 | 51 language groups | analyzer.LANG_EXTS | runtime probe | architecture/README.md §6 | ACCURATE |
| C-04 | 127 regex rules across 17 groups | analyzer._PATTERNS | runtime probe | architecture/README.md §6 | ACCURATE |
| C-05 | 12 adversarial heuristic roles | adversarial.AdversarialAuditor._roles | runtime probe | architecture/README.md §5 row 4 | ACCURATE |
| C-06 | 40-domain registry; 11 concrete auditors (Wave 1) | domain_auditor.DOMAIN_REGISTRY + WAVE_REGISTRY | AST count + live probe + in-source comment "Wave 2-4 to be populated" | architecture/README.md §8; architecture-gaps-current.md GAP-03 | ACCURATE |
| C-07 | run_all_legacy returns 13 keys (11 live + `_framework` + `_synthesis`) | domain_auditor.DomainAuditOrchestrator.run_all_legacy | live probe on temp repo | dfd/level-0.md; architecture/README.md §6 | ACCURATE |
| C-08 | Silent fallback to legacy 12 roles on orchestrator exception | engine.py:226-232 | source inspection; no log entry exists | architecture/README.md §4; failure-recovery/error-flow.md §9 | ACCURATE (gap logged GAP-05) |
| C-09 | Dedupe uses canonical primary-key rule map | engine._phase_correlate `_DOMAIN_TO_PRIMARY` / `_PRIMARY_TO_DOMAIN` | source inspection; lineage invariant recomputed | dfd/level-1.md; decision-validation/invariants.md I-16..I-18 | ACCURATE |
| C-10 | Context suppression drops findings pre-persistence | execution_context.should_suppress_finding + engine L417-435 | tests/test_engine.py | architecture/README.md §4; decision-validation/finding-validation.md | ACCURATE |
| C-11 | Semantic-enrichment failure continues with `semantic_enriched=[]` | engine L446-464 | source inspection | failure-recovery/error-flow.md §10 | ACCURATE |
| C-12 | REMEDIATE phase only logs findings (no auto-fix in `aura audit`) | engine._phase_remediate L476-501 | tests/test_engine.py | architecture/README.md §5 row 7 | ACCURATE |
| C-13 | TEST phase runs `_run_tooling`; real exit codes by default | engine._run_tooling L973-1000 + ToolingConfig.fail_open=False | tests/test_run2_regressions.py | decision-validation/convergence.md; failure-recovery/retry.md | ACCURATE |
| C-14 | VERIFY never auto-verifies from tooling pass | engine._phase_verify L510-530 | source inspection | sequence/finding-validation.md | ACCURATE |
| C-15 | REGRESSION checks resolved∩current at any severity (R2-02) | engine._phase_regression L532-553 | tests/test_run2_regressions.py | decision-validation/convergence.md | ACCURATE |
| C-16 | 12 user gates pass → PRODUCTION_READY; else CONDITIONALLY_READY iff open CODE_DEFECT P0==0 AND P1==0; else NOT_READY | engine.py:764-772 | tests/test_state_machine.py + measured truth table | state/finding-state.md; decision-validation/convergence.md | ACCURATE |
| C-17 | 1×P3 OPEN yields PRODUCTION_READY (score 99) | measured live via evaluate_all_gates + compute_convergence_score | probe 2026-08-22 | state/finding-state.md; decision-validation/convergence.md | ACCURATE |
| C-18 | Dual gate systems can disagree on same state (judge converges w/o LIMITATIONS signal) | convergence.ConvergenceJudge vs engine._phase_convergence | probe 2026-08-22 | decision-validation/convergence.md "Divergence proof" | ACCURATE |
| C-19 | Subclass override recomputes P2_zero & critical_security CODE_DEFECT-only | engine.py:738-754 + finding_subclass.is_blocking_for_gate | tests/test_state_machine.py | decision-validation/convergence.md | ACCURATE |
| C-20 | `validate_*` integrity validators are opt-in library functions (engine does not call them) | grep engine.py for validator names | tests/test_state_machine.py invoke them directly | decision-validation/README.md "Decision owners"; invariants.md L-01..L-07 | ACCURATE |
| C-21 | LIMITATIONS.md is a runtime input (re-read every cycle) | engine._validate_limitations_file L580-676 | tests/test_false_convergence.py | context/context-diagram.md; decision-validation/convergence.md | ACCURATE |
| C-22 | `module_dependency_integrity` is a fail-closed import probe (15 modules) | engine._check_module_integrity L86-106 | tests/test_engine.py presence | decision-validation/invariants.md I-13 | ACCURATE |
| C-23 | Evidence chain is hash-linked; tamper-evident | evidence.EvidenceChain.append + verify_chain | adversarial self-tests use validators | security/security-controls.md "Detective"; dfd/level-1.md | ACCURATE |
| C-24 | Checkpoint carries sha256 state hash; tampered → refuse resume; legacy flagged | durable.CheckpointManager.save/load | tests/test_architecture_improvements.py (IMP-07) | security/security-controls.md; failure-recovery/recovery-matrix.md #12-13 | ACCURATE |
| C-25 | Provider retry lives only in providers.py (full jitter, ≤3, classified 4xx) | providers.OpenAICompatibleProvider | tests/test_architecture_improvements.py | failure-recovery/retry.md | ACCURATE |
| C-26 | CircuitBreaker defaults threshold=3, cooldown=30 s, half_open_max=1, window=120 s; health derived | providers.CircuitBreaker + BaseProvider.status | tests/test_state_machine.py | state/circuit-breaker-state.md; failure-recovery/circuit-breaker.md | ACCURATE |
| C-27 | ProviderRegistry failover visits up to 3 non-OPEN providers; does not add retries | providers.ProviderRegistry.chat_with_fallback | security controls doc + R2-04 note | failure-recovery/provider-failover.md | ACCURATE |
| C-28 | Every LLM/Provider response constructor sets `untrusted=True` | grep all constructor sites in llm.py + providers.py | source inspection (no site omits the flag) | security/trust-boundaries.md B4; sequence/provider-request.md | ACCURATE |
| C-29 | DB schema = 11 tables, WAL + FK + busy_timeout | db.SCHEMA_SQL + Database.initialize | live probe creates exactly 11 non-sqlite tables | data-model/README.md | ACCURATE |
| C-30 | findings.finding_id = sha256(file:line:rule)[:12] (stable) | engine._stable_finding_id | R2-01 + tests | decision-validation/finding-validation.md "Identity rule" | ACCURATE |
| C-31 | AutoFixer sandbox containment + advisory blocklist + old_code match + rollback | remediation.AutoFixer.apply_fix + rollback | tests/test_architecture_improvements.py | security/security-controls.md; sequence/finding-validation.md | ACCURATE |
| C-32 | LoopSafeguard caps: MAX_ITERATIONS=10, SAME_FINDING=3, NO_PROGRESS=3, REGRESSION=-10 | convergence.LoopSafeguard constants | tests/test_false_convergence.py | failure-recovery/retry.md; decision-validation/audit-decision-flow.md | ACCURATE |
| C-33 | `consecutive_converged_cycles` increments on CONDITIONALLY_READY too | engine.py:781 | CHANGELOG statement + code read | state/audit-state.md; decision-validation/convergence.md | ACCURATE |
| C-34 | `audits_since_last_finding` increments unconditionally | engine.py:782 | code read | state/audit-state.md | ACCURATE |
| C-35 | `tenacity` declared in pyproject but never imported in src/aura | grep "import tenacity" absent in src/aura/*.py | grep | failure-recovery/retry.md note | ACCURATE |
| C-36 | `registry.json` plugin mechanism inert (plugin_count=0) | registry.json | file read | context/context-diagram.md; architecture/README.md §8 | ACCURATE |
| C-37 | Async stack (`aiosqlite`, `pytest-asyncio`) declared but no `async def` in src/aura | grep "async def" src/aura → none | grep | architecture-gaps-current.md GAP-07 | ACCURATE |
| C-38 | DB path resolves against repo_root (relative configs) | db.Database ctor + engine.py:74 wiring | tests/test_architecture_gaps.py (4 tests incl. regression) | architecture-gaps-current.md GAP-01 (marked FIXED) | ACCURATE — **implemented** |
| C-39 | CLI banner matches package version | cli.py docstring uses `v3.5.3` + module `VERSION` | tests/test_architecture_gaps.py | architecture-gaps-current.md GAP-02 (marked FIXED) | ACCURATE — **implemented** |
| C-40 | Quality gates match or beat baseline (206→210 tests; ruff 892→892; mypy 116→116; build PASS; doctor PASS) | pytest + uv build + ruff + mypy + aura doctor | BASELINE.md vs this final gate | FINAL OUTPUT (this mission's reply) | ACCURATE |

## Notes

- No material claim fell into INCOMPLETE / INCORRECT / UNVERIFIED / OUTDATED at close of this audit.
- Non-material micro-claims (e.g. exact `generate_benchmark_cases` counts per family inside
  benchmark_v3) are covered by docstring+signature, not enumerated per case here.
