# Changelog

All notable changes to the AURA Audit Engine.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — Final targeted technical-debt remediation

### Fixed

- **GAP-SILENT-FALLBACK-05** (engine.py:_phase_adversarial): domain
  orchestrator → legacy 12-role fallback was invisible to the audit log.
  Now both paths write an ``ADVERSARIAL_PATH`` audit_log entry —
  success path records ``domain orchestrator succeeded (N keys)``,
  fallback path records ``LEGACY FALLBACK triggered — orchestrator raised
  <Type>: <msg>``. Post-hoc audits can now distinguish which path ran.
  Regression tests: ``TestGAPSilentFallback05::test_fallback_writes_audit_log_entry``
  and ``test_success_path_writes_audit_log_entry``.

### Removed

- **GAP-UNUSED-ASYNC-STACK-07** (pyproject.toml): removed unused
  ``pytest-asyncio`` (dev extra) and ``aiosqlite`` (db extra) — no
  ``async def`` exists anywhere in src/ or tests/. Dropped the ``db``
  optional-dependencies section and folded ``all = [dev, signing]``.

### Changed

- **GAP-VALIDATORS-OFFLINE-04** (state_machine.py, __init__.py): the three
  ``validate_*`` integrity functions (``validate_finding_state_integrity``,
  ``validate_gate_evidence_integrity``, ``validate_gate_findings_crosscheck``)
  are now explicitly exported in ``__init__.py`` and declared in the module
  docstring as an opt-in public library API. Engine continues to enforce
  these invariants by construction (not by calling the validators at
  runtime); they are exercised by test_state_machine.py,
  test_run2_regressions.py, and test_false_convergence.py.

### Code quality

- **ruff**: 892 → 675 errors (-217) via safe autofix only (F401 unused-import
  resolved by adding explicit ``__all__`` to ``src/aura/__init__.py``;
  F541, I001, W292, UP045, UP017, C408, etc.). One unsafe autofix reverted
  in engine.py:_run_tooling to preserve the source-string assertion in
  tests/test_security.py::test_tooling_commands_not_shell_interpreted.
- **mypy**: 116 → 107 errors (-9). Removed 3 stale ``# type: ignore[attr-defined]``
  in cli.py:auto_fix that were masking real type drift; the underlying
  ``ProviderBackedLLMClient`` and ``AutonomousRemediationLoop`` duck-type
  assignments are now made explicit via ``typing.cast`` with a comment
  explaining the structural-typing contract.

### Residual (documented, accepted)

- 675 ruff errors remain — dominated by E501 line-too-long (423),
  PLC0415 import-outside-top-level (59), and E701/E702 multi-statement
  lines (42). These are structural and require case-by-case refactoring;
  unsafe bulk-fix risks regression.
- 107 mypy errors remain — dominated by ``type-arg`` (51, mostly
  ``dict`` → ``dict[str, Any]``) and ``no-untyped-call`` (22). These are
  type-completeness annotations, not contract violations.

---

## [3.5.3] — 2026-08-22

### RUN #3 — Adversarial final audit against baseline `83a1f33` (v3.5.2)

Falsification-driven cycle: attempted to break provider fallback, convergence
gates, evidence chain, sandbox, and state machine. Primary attack vectors
SURVIVED (no P0/P1 reproducible). Two P3 defects found, fixed, regression-tested.
Evidence: `docs/run3-adversarial-final-audit.md`.

### Fixed

- **R3-01 (P3 scoring proportionality):** `_compute_quality` zeroed the quality
  score for tiny repos — `kloc = max(total_lines/1000, 0.1)` amplified a single
  P0+P1 penalty 10× (23/0.1 → 230 → clamped to 0). kloc floor raised to 1.0 and
  penalty contribution capped at 100. Quality now reflects defect density and is
  monotonic in repo size. Classification correctness was never affected.
- **R3-02 (P3 test integrity):** removed a tautological test
  (`assert True  # Verified via code inspection`) in `test_security.py`; replaced
  with a real introspection test asserting `subprocess.run` + `shell=False` +
  `timeout=300` and the absence of `os.system`/`shell=True` in `_run_tooling`.
  Added `TestNoTautologicalTests` guard that fails if placeholder tests reappear.

### Verified (falsification attempts that failed — no change needed)

- Provider fallback: no retry amplification, provenance intact, OPEN circuits skipped.
- Subclass classification: fail-closed (unknown rules → CODE_DEFECT).
- Live false-convergence attempt: repo with `eval()` + `os.system()` → `NOT_READY`,
  `P0_zero=False`, `critical_security=False` (7/12 gates).
- Evidence chain: tamper / deletion / reorder / forged-genesis all detected; reload safe.
- Sandbox: sibling-prefix, absolute-path escapes blocked; dry-run side-effect free.

### Added (tests)

- 3 quality-proportionality tests + 1 tautology guard. Suite: 202 → **206 passing**.
- mypy clean on `analyzer.py` (also fixed a pre-existing `dict` type-arg gap).

---

## [3.5.2] — 2026-08-22

### RUN #2 — Deep architecture audit against baseline `00d8b2a` (v3.5.1)

Evidence-driven cycle: every finding reproduced before fix. No speculative
refactors; IMP-01..IMP-09 not reopened. Artifacts:
`docs/run2-deep-architecture-audit.md`, `tests/test_run2_regressions.py`.

### Fixed

- **R2-01 (P0 false convergence):** `no_material_new_findings` gate was blind —
  `evaluate_all_gates` / crosscheck / finding-integrity validators read
  `f.get("id")` while the engine/DB emit `finding_id`, so identity sets were
  always empty and the gate never fired. Added a canonical `_finding_key()`
  accessor (accepts both) used by all three validators. A new P0 now correctly
  fails the gate (reproduced live pre-fix).
- **R2-03 (P0 false pass):** auto-detected tooling commands ended with
  `|| true`, forcing shell exit code 0 → TEST phase recorded success even when
  pytest/tsc/lint failed, and the `verification` gate inherited the pass.
  Commands now capture real exit codes; informational mode is opt-in via new
  config `engine.tooling.fail_open` (default `false`).
- **R2-04 (P1 provider reliability):** `ProviderRegistry.chat_with_fallback`
  never fell back — a transient primary error was returned without consulting
  a healthy fallback. Now routes across up to 3 providers in priority order on
  error, without duplicating the per-provider retry layer.
- **R2-02 (P1 validation):** regression detection filtered current findings to
  P0-P2, so a previously-VERIFIED finding reappearing at P3 (severity drift)
  was invisible. Regression intersection now covers all severities.
- **R2-06 (P1 safeguard bypass):** `DurableAutonomousLoop` resume reset
  `LoopSafeguard` counters (iteration / scores / finding_attempts) to zero,
  defeating MAX_SAME_FINDING_ATTEMPTS across resumes. Safeguard state is now
  snapshotted into the checkpoint and restored on resume.
- **R2-05 (P2 correctness):** `compute_convergence_score` accepted but ignored
  `severity_weights` (config silently had no effect). Penalties are now derived
  from the configured weights, normalized so the default config reproduces
  historical scores exactly (no scoring regression).
- **R2-08 (P2 wiring):** `Engine.evidence_chain` was constructed but never
  populated. The CONVERGENCE phase now appends a tamper-evident evidence entry
  per cycle and mirrors it to the `evidence_chain` SQL table.
- **R2-07 (P3 drift):** version strings unified to 3.5.2 (`__init__.py`,
  `cli.py`, `pyproject.toml`) — code, packaging, and CHANGELOG now agree.

### Added (tests)

- `tests/test_run2_regressions.py` — 16 regression tests covering R2-01..R2-08.
- Test suite: 186 → **202 tests**, all passing. mypy clean on changed modules;
  0 syntax errors; `aura doctor` green.

---

## [3.5.1] — 2026-08-22

### Architecture hardening cycle (IMP-01..IMP-09)

**Full lifecycle:** reverse-engineering → documentation audit → architecture
improvement plan → implementation → regression tests → docs/README sync.
Artifacts: `docs/documentation-audit.md`, `docs/architecture-improvement-plan.md`,
`docs/target-architecture.md`, `docs/final-consistency-audit.md`.

### Fixed

- **IMP-02 (P0 false convergence):** `ConvergenceJudge` gate G07 was hardcoded
  `True` even when tooling failed; now derived from G06 (tooling pass).
  `module_dependency_integrity` gate was hardcoded `True`; now computed by a real
  import check of required `aura.*` modules at engine init (fail-closed).
- **IMP-03 (P1 wrong invariant):** removed "SCORE REGRESSION" / "SCORE SPIKE"
  violations from gate-evidence validation — discovering new findings legitimately
  lowers the score; penalizing it rewarded hiding findings. Validator was also
  never invoked at runtime.
- **IMP-04 (P1 evidence integrity):** `EvidenceChain` entries now carry
  `chain_index` + `previous_hash` (real hash chain, genesis `"0"*64`);
  `verify_chain()` detects tampering, deletion, and reordering. The
  `evidence_chain` SQL table is no longer dead schema — `insert_evidence_entry()`
  / `get_evidence_chain()` mirror the JSON store.
- **IMP-05 (P1 retry storm):** provider retry rewritten — error classification
  (4xx auth/validation = NO_RETRY, fail fast; 429/5xx/network = RETRY),
  full-jitter backoff `uniform(0, min(cap, base·2^attempt))`, `Retry-After`
  header honored (capped). Provider layer is the single retry layer.
- **IMP-06 (P1 sandbox):** path containment now uses
  `Path.is_relative_to()` — the old `str.startswith()` check accepted
  sibling-prefix escapes (`/a/repo` → `/a/repo-evil/x`). Dangerous-pattern
  blocklist reframed as advisory; real controls documented as dry-run +
  old_code verification + rollback + re-audit.
- **IMP-07 (P2 checkpoint integrity):** `.aura/checkpoint.json` carries a
  `state_hash` (SHA-256 over canonical state); tampered or truncated
  checkpoints are refused on load.
- **IMP-08 (P2 hygiene):** fixed invalid syntax in `benchmark_v3.py`
  (JS template literal in Python source — module did not parse; 8 ruff
  invalid-syntax errors → 0). Unified stale metrics: actual is
  **51 language groups / 17 with active rules / 127 rules** (was claimed as
  62 groups / 650+ rules in docs and docstrings).
- **IMP-09 (P2 observability):** every audit cycle gets a `cycle_id` bound to
  structured logs; per-phase durations are recorded into the audit log as a
  `CYCLE_OBSERVABILITY` entry with JSON metadata.

### Changed

- **IMP-01 (P1 provider architecture):** single canonical provider stack.
  New module-level `ProviderBackedLLMClient` adapter (llm.py) replaces the
  inline `_RegistryLLMWrapper` class previously defined per-invocation in
  `cli.py:auto_fix`. `providers.py` is the resilience home (circuit breaker,
  classified retry, jitter, fallback); the adapter converts types only and
  adds no retry of its own.

### Added (tests)

- `tests/test_architecture_improvements.py` — 26 regression tests covering
  every IMP item (adapter mapping, retry classification + jitter bounds,
  Retry-After, G07 derivation, module-integrity fail-closed, evidence-chain
  linkage incl. deletion/reorder detection, DB evidence sync, sibling-prefix
  path escape, checkpoint tamper/legacy handling, cycle observability).
- Test suite: 161 → **186 tests**, all passing. mypy clean on changed modules.

---

## [3.5.0] — 2026-08-21

### Added

- **Semantic Code Intelligence** — AST parsing, taint analysis (source→sanitizer→sink), data-flow tracking, and sanitizer capability matrix for 25+ sanitizers × 6 sink types.
- **Expression-Aware Detection** — f-string SQLi, qualified method calls (`hashlib.md5`), string concatenation SQLi, PHP variable interpolation, Go string concat SQLi, and string-concat path traversal.
- **Execution Context Layer** — classifies every file (PRODUCTION_CODE, TEST_CODE, MIGRATION_CODE, DOCUMENTATION, GENERATED_CODE, THIRD_PARTY, INFRASTRUCTURE, etc.) with confidence modifiers per context.
- **Finding Subclass System** — separates CODE_DEFECT, SECURITY_ADVISORY, ENVIRONMENT_BLOCKER, GOVERNANCE_FINDING, TEST_QUALITY, CODE_QUALITY, and INFORMATIONAL for gate-aware scoring.
- **40-Domain Audit Registry** — 11 active domain auditors (DEPENDENCY, CONFIGURATION, SECRET, CRYPTOGRAPHY, INJECTION, PATH_AND_FILE, DESERIALIZATION, AUTHENTICATION, AUTHORIZATION, SESSION, INPUT_VALIDATION) with shared intelligence layer.
- **Shared Intelligence Layer** — pre-built file index, dependency manifest parsers (7 formats), and framework detection shared across all domain auditors.
- **Repository Memory** — learns project sanitizers, framework primitives, and safe patterns across audit cycles for higher precision.
- **Confidence Classification** — TRUE_POSITIVE, LIKELY_TRUE, UNCERTAIN, LIKELY_FALSE_POSITIVE, FALSE_POSITIVE, MITIGATED with per-finding evidence graphs.
- **CWE/OWASP/CVSS Knowledge Base** — 21+ CWE entries mapped to detection rules with severity and exploitability scoring.
- **Framework-Aware Scoring** — Laravel, Django, FastAPI, Flask, Express, Spring, Rails security primitives recognized and weighted.
- **Directional Taint Analysis** — sanitizer capability matrix checks per sink type (HTML≠SQL≠SHELL≠URL≠JS≠PATH).
- **Benchmark v3 Framework** — 500+ case generation, mutation engine (6 operators), metamorphic testing, capability registry, CI regression gate.
- **Benchmark v2 Results** — Recall 100%, F1 96.8%, Precision 93.8% on 25-case, 6-language ground-truth benchmark.
- **Multi-Language Analyzer** — 62 language groups, 650+ rules, 130+ file extension mappings, expression-aware patterns.
- **`.env.example`** with comprehensive template (no real credentials).

### Changed

- **Engine core** — 5 bugs fixed (remediation table schema, adversarial count accuracy, git status None guard, Haskell glob detection, json import optimization).
- **Convergence gates** — P2_zero and critical_security now use finding subclass (advisories don't block).
- **Score computation** — normalized per-severity penalty (P0=15, P1=8, P2=3, P3+=1) with floor score for large projects.
- **Project type detection** — composer.json checked before package.json for PHP projects.
- **Test coverage detection** — project-aware source directories (app/, src/, lib/, includes/, modules/, routes/).
- **Type checking** — `# type: ignore[code]` → P4 (acceptable), bare `# type: ignore` → P2.
- **Context-aware suppression** — findings in docs/tests/migrations automatically suppressed (unless P0).
- **Version** — bumped from 1.0.0 to 3.5.0.

### Fixed

- **Data lineage invariant** — `combined_raw - intra_dupes - cross_overlap = unique` now always holds.
- **Circular convergence dependency** — consecutive_clean gate reads previous cycle convergence, not current.
- **CONDITIONALLY_READY counter** — consecutive_converged_cycles now increments for CONDITIONALLY_READY, not just PRODUCTION_READY.
- **Test coverage double-counting** — test coverage computed once in `_to_finding_dicts`, not duplicated in ancillary.
- **Scanner skip-dir completeness** — `.tools/`, `.terraform/`, `bower_components/`, and 15+ other patterns added.
- **AUTHZ false positives** — SQLAlchemy model definitions (Mapped, ForeignKey) excluded from authorization scan.
- **PATH false positives** — `__DIR__`-based paths and `dirname()` recognized as safe in context.
- **Remediation table** — SQL schema with real newlines (not literal `\n\n`), table now creates correctly on fresh DBs.
- **139/139 tests pass** — zero unexpected failures.

### Verified

- **External convergence proof** — Vidbro (FastAPI) reached PRODUCTION_READY at cycle 4, 12/12 gates, 91/100.
- **Regression resurrection** — injected P0 correctly detected, NOT_READY → fix → re-converged to PRODUCTION_READY.
- **Cross-repository** — Klinik (raw PHP) 42/100, Laravel 88/100, Vidbro 89/100, Benchmark recall 100%.
- **Semantic memory** — learned sanitizers across cycles improved score stability.

---

## [1.0.0] — 2026-08-14

### Added

- Autonomous remediation engine (`aura auto-fix`).
- 12 deterministic convergence gates with zero LLM involvement.
- 7 safeguards (A-G): infinite loop protection, no-progress detection, same-finding attempt cap.
- 12 finding statuses including terminal states.
- Durable checkpointing (`--resume` flag).
- Evidence chain per cycle with cryptographic hash chain.
- `remediation_attempts` table for persistent LLM fix tracking.
- Whitespace-normalized fuzzy matching for robust patch application.
- 10 CLI commands.
- 139 automated tests + 16/16 self-test adversarial campaigns.
- `.env` configuration via python-dotenv.

### Security

- LLM API key loaded from `AURA_LLM_KEY` environment variable.
- `.gitignore` blocks `.env`, `.aura/state/`, and runtime artifacts.

[3.5.0]: https://github.com/aura/aura-audit/releases/tag/v3.5.0
[1.0.0]: https://github.com/aura/aura-audit/releases/tag/v1.0.0