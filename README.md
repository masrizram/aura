# AURA v3.5.3 — Autonomous Software Reliability Engine

[![Tests](https://img.shields.io/badge/tests-210%2F210-brightgreen?style=flat-square)](tests/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue?style=flat-square)](pyproject.toml)
[![Build](https://img.shields.io/badge/build-passing-brightgreen?style=flat-square)](dist/)
[![Convergence](https://img.shields.io/badge/convergence-deterministic-blueviolet?style=flat-square)](#convergence-model)

AURA is a **CLI-first, cyclic audit→remediate→verify engine for source repositories**.
Each cycle runs a fixed 13-phase pipeline, detects issues from multi-source pattern
matching + 12 adversarial heuristic roles + an 11-auditor domain wave (40-domain
registry), enriches findings with a semantic layer (Python real AST; PHP/JS structural
regex; ±20-line heuristic taint; framework awareness), persists everything to SQLite,
and decides convergence **deterministically** against 12 user-facing gates — never from
LLM output, which is treated as **untrusted candidate input** end-to-end.

This README is synchronized with the blind-rebuilt documentation in `docs/` (2026-08-22).
Claims below cite the implementing modules. Anything not implemented is called out in
[LIMITATIONS.md](LIMITATIONS.md) — which is itself a load-bearing input: the
`limitations_documented` convergence gate reads it every cycle.

---

## Quick Start

```bash
pip install dist/aura_audit-3.5.3-py3-none-any.whl   # or: pip install -e .
aura init            # create .aura/state/aura.db + cycle 1
aura audit           # run one 13-phase cycle
aura status          # current classification + gate tally
aura trend           # cycle history
aura verify          # list open findings grouped by severity
aura verify --fix    # remediation guidance
aura report          # markdown report
aura doctor          # system diagnostics
aura auto-fix        # autonomous loop (LLM required; see LLM Setup)
```

Exit semantics: configuration error or engine AuraError → exit(1); success → exit(0).

## Architecture (from code, not aspiration)

```
┌ cli.py ─ 10 commands ────────────────────────────────────────────┐
│ init audit status health doctor log verify report trend auto-fix │
└──────────────┬───────────────────────────────────────────────────┘
               ▼
        engine.py — 13-phase pipeline (sequential, single-threaded)
               │
   ┌───────────┼──────────────────────────────────────────┐
   ▼           ▼                                          ▼
 analyzer   domain_auditor ──► SharedIntelligence ──► 11 concrete auditors
 (51 lang    (40 domains,    (deps, framework,         (Wave-1; per-auditor
  groups;    Wave-1 active)   secrets inventory)        exception-isolated)
  127 rules)                                            
   │           ▲                                         
   ▼           │                                         
 adversarial ──┘ (legacy 12-role fallback on orchestrator error)
               │
        ┌──────▼─────────┐
        │ CORRELATE: dedupe (canonical primary-key rule map) +
        │ context-suppression (execution_context) +
        │ semantic enrich (semantic.py: AST/taint/framework/memory)
        └──────┬─────────┘
               ▼
        PRIORITIZE (severity sort) → REMEDIATE (log-only)
               │
               ▼
        TEST (_run_tooling auto-detect; real exit codes)
               │
               ▼
        VERIFY (independently-verified only) → REGRESSION (resolved∩current)
               │
               ▼
        UPDATE_STATE → CONVERGENCE ──► 12 user gates (state_machine.py)
               │                       + LIMITATIONS.md validation
               │                       + subclass CODE_DEFECT override
               │                       + score blend 0.6*score + 0.4*quality
               ▼
        PUSH_APPROVAL (log; converged ⇒ ready-for-approval marker)
               │
               ▼
        SQLite .aura/state/aura.db (WAL, FK, BEGIN IMMEDIATE)
```

Module dependency graph is a DAG (no cycles) — verified by AST import analysis.

## The 13 phases (fixed order)

1. **DISCOVER** — git context + per-language file counts
2. **MODEL** — project type + language model
3. **AUDIT** — `MultiLangAnalyzer.analyze()` (regex rules per file; skips test files, lockfiles, vendor dirs; comment lines suppressed)
4. **ADVERSARIAL_AUDIT** — `DomainAuditOrchestrator.run_all_legacy()` (11 live auditors + `_framework` + `_synthesis`); on exception → silent fallback to 12-role legacy
5. **CORRELATE** — cross-source dedupe, context suppression, semantic enrichment; writes lineage invariants to audit_log
6. **PRIORITIZE** — severity sort, stable `F-<sha256[:12]>` ids
7. **REMEDIATE** — logs all findings into the DB (does NOT apply fixes here)
8. **TEST** — auto-detect pytest/tsc/semgrep/bandit/gitleaks/npm/make/go/cargo; capture exit codes
9. **VERIFY** — count independently-verified findings only
10. **REGRESSION** — previously-resolved findings that reappear (any severity)
11. **UPDATE_STATE** — severity counts, quality, tooling pass/total
12. **CONVERGENCE** — evaluate 12 gates; subclass override; score blend; classification
13. **PUSH_APPROVAL** — final audit-log entry + semantic memory write

## Detection layers (what is actually scanned)

| Layer | Where | Coverage |
|---|---|---|
| Regex pattern matching | `analyzer.py` | 127 rules across **17** of 51 language groups (34 groups are extension-mapped but pattern-empty) |
| Adversarial heuristics | `adversarial.py` | 12 roles (dependency, configuration, network, injection, secret, logic, architecture, performance, reliability, observability, testing, compliance) |
| Domain auditors | `domain_auditor.py` | 11 concrete `BaseDomainAuditor` subclasses in Wave 1 (DEPENDENCY, CONFIGURATION, SECRET, CRYPTOGRAPHY, INJECTION, PATH_AND_FILE, DESERIALIZATION, AUTHENTICATION, AUTHORIZATION, SESSION, INPUT_VALIDATION) — 29 registered domains remain Wave 2-4 |
| Semantic intelligence | `semantic.py` | Real AST for Python; tokenizer-based structural for PHP; regex-based structural for JS/TS; ±20-line heuristic taint with sanitizer matrix |
| Execution context | `execution_context.py` | 10-context classifier; suppresses non-P0 findings in TEST/DOCUMENTATION/GENERATED/THIRD_PARTY/MIGRATION |
| Finding subclass | `finding_subclass.py` | CODE_DEFECT vs 7 advisory/other subclasses; only CODE_DEFECT blocks gates |

## Convergence model

Two co-existing gate systems (documented divergence accepted; judge only runs after the
engine already declares PRODUCTION_READY):

- **User-facing 12 gates** (`state_machine.evaluate_all_gates`):
  `P0_zero, P1_zero, P2_zero, critical_security, critical_correctness, data_integrity,
  regression, verification, no_material_new_findings, limitations_documented,
  consecutive_clean_independent_audits, module_dependency_integrity`.

- **Internal judge G01–G12** (`convergence.ConvergenceJudge`): independent criteria for
  the autonomous loop, with G07 deliberately derived from G06 (not claimed independent).

**Classification (engine.py:764-772):**
- `PRODUCTION_READY` iff **all 12** user gates pass.
- Else `CONDITIONALLY_READY` iff **no open CODE_DEFECT P0 and no open CODE_DEFECT P1**.
- Else `NOT_READY`.

Live-verified behavior (2026-08-22 probes):
- 1× P3 OPEN finding → PRODUCTION_READY (score 99). P3-P5 never block by gates alone.
- 1× P2 OPEN CODE_DEFECT → CONDITIONALLY_READY (P2 blocks only via `P2_zero` gate;
  classification path only checks P0/P1).
- 1× P0 or P1 OPEN CODE_DEFECT → NOT_READY.
- Missing/placeholder LIMITATIONS.md → `limitations_documented=False` ⇒ cannot be
  PRODUCTION_READY, regardless of finding counts.

**Score** = `min(100, int(0.6 * compute_convergence_score + 0.4 * code_quality))`
where `compute_convergence_score = gate_score (≤60) + finding_score (≤40, penalty-based)`.
Severity weights from config are normalized to historical penalties (P0:15, P1:8, P2:3,
P3-5:1) so custom weights actually change the score (R2-05).

**Counters** (per cycle): `consecutive_converged_cycles` increments when converged OR
CONDITIONALLY_READY; `audits_since_last_finding` increments unconditionally.
`consecutive_clean_independent_audits` requires `≥2` and `≥2`.

## LLM subsystem (optional; always untrusted)

- `llm.LLMClient` — single-shot OpenAI-compatible call (no retries).
- `providers.OpenAICompatibleProvider` — canonical transport resilience: classified
  retries (non-retryable 4xx → fail-fast; 429/5xx/network → full-jitter backoff honoring
  `Retry-After`), circuit breaker (3 failures / 30 s cooldown / 1 half-open probe / 120 s
  rolling window defaults), health derivation.
- `providers.ProviderRegistry` — failover across up to 3 non-OPEN providers, no retry
  duplication on top of a provider (R2-04).
- `llm.ProviderBackedLLMClient` — adapter that adds no retries of its own.
- Every LLM response carries `untrusted=True` at every construction site; convergence
  never consumes LLM content.

## Autonomous remediation loop

`remediation.AutonomousRemediationLoop` (used by `aura auto-fix`):
- Per cycle: run `engine.run_audit()` → if PRODUCTION_READY, run ConvergenceJudge for
  confirmation + build `convergence_proof.json`; otherwise apply up to 20 fixes/cycle.
- Fix application (`AutoFixer`): repo-containment check (`Path.is_relative_to`),
  dangerous-pattern advisory blocklist, whitespace-tolerant `old_code` match verification,
  one business retry with actual file context, dead-letter queue for unparseable/sandbox-
  rejected patches, full rollback on batch failure.
- Safeguards: `MAX_ITERATIONS=10`, `MAX_SAME_FINDING_ATTEMPTS=3`, `NO_PROGRESS_CYCLES=3`,
  `REGRESSION_THRESHOLD=-10` (`convergence.LoopSafeguard`).
- Durable resume: `durable.CheckpointManager` with SHA-256 state integrity; tampered
  checkpoints are refused (fresh run); legacy 1.0.0 checkpoints are flagged
  `_integrity="legacy-unverified"`.

## Persistence

SQLite at `<repo>/.aura/state/aura.db` — 11 tables, WAL mode, foreign keys, busy_timeout
5000 ms, `BEGIN IMMEDIATE` transactions. Relative database paths are resolved against
the target repository root, not the process CWD (RULE-10 fix in this rebuild); absolute
paths are honored unchanged.

| Table | Purpose |
|---|---|
| `_schema_version` | forward-only migrations (current v1) |
| `cycles` | one row per audit cycle (phase, status, classification, score, counters) |
| `findings` | one row per stable finding_id; 12-status CHECK; severity CHECK |
| `convergence` | per-cycle converged flag, classification, counters |
| `gates` | 12 rows per cycle with pass/fail + evidence |
| `tooling_evidence` | every subprocess command, exit_code, success, 2 KB output tail |
| `evidence_chain` | tamper-evident hash-linked evidence entries |
| `remediation_attempts` | every fix attempt with status + patch + error |
| `audit_log` | immutable-by-convention phase/event log |
| `dead_letter` | failed/unparseable LLM remediation attempts |
| `convergence_confidence` | per-cycle verification/detection/test confidence + ratios |

Out-of-band state: `.aura/checkpoint.json` (sha256-protected), `.aura/memory.json`
(repository memory), `.aura/evidence/convergence_proof.json` (final proof).

## Security model (abridged)

- Parametric SQL only; no string-interpolated values anywhere.
- Tooling subprocesses spawn with `shell=False` and fixed command templates owned by
  `_detect_commands` (the repository cannot inject a command).
- HTTP retry policy is exactly one layer (`providers.py`); `tenacity` is declared but
  never imported.
- Bearer tokens live only in the Authorization header; never logged.
- Evidence and checkpoints are tamper-evident (hash chain / sha256 state hash), not
  tamper-proof — AURA does not sandbox the target repository.
- Full model: `docs/security/`.

## Reliability & failure handling

- Real subprocess exit codes by default (`ToolingConfig.fail_open=False`); `fail_open=True`
  is an explicit opt-in documented as not suitable for convergence decisions.
- Circuit breaker per provider (CLOSED → OPEN → HALF_OPEN → CLOSED); fail-fast when OPEN.
- Provider failover across up to 3 registered providers, no retry amplification.
- Automatic rollback of failed fix batches; dead-letter queue with typed error classes.
- Checkpoint/resume across multi-cycle autonomous runs with safeguard state restored.
- Full matrix: `docs/failure-recovery/recovery-matrix.md`.

## Configuration

`config/aura.json` (validated by pydantic at startup; fatal on invalid):

- `engine.state_machine.*` — enforcement toggles + forbidden direct transitions.
- `engine.tooling.*` — `execute_before_verification`, `auto_detect_commands`,
  `required_pass_commands`, `fail_open` (default False).
- `engine.convergence_gate.*` — severity thresholds + module-loading strictness.
- `severity.P0..P5` — labels + weights (defaults 625/405/216/90/30/6).
- `dimensions.*` — 10-dimension weights (Architecture .14, Correctness .16, Security .18, ...).
- `database.*` — path, wal_mode, foreign_keys.
- `notifications.*` — present but inert in code (no producer).
- Env: `AURA_CONFIG_PATH`, `AURA_LLM_URL`, `AURA_LLM_KEY`, `AURA_LLM_MODEL`.

## Testing

```
python -m pytest tests/ -q     # 210 tests, all passing
```

Suite composition: engine, state machine (finding + classification + gates), db,
config, errors, false-convergence, architecture improvements, RUN #2 regressions,
security, and architecture-gap regressions (RULE 10: DB path anchoring + CLI banner).

## Quality gates (measured 2026-08-22)

| Gate | Command | Result |
|---|---|---|
| Unit+Integration tests | `python -m pytest tests/ -q` | 210 passed, 0 failed |
| Build | `uv build` | sdist + wheel produced |
| Typecheck | `mypy src/aura` (strict) | 116 errors (pre-existing; unchanged from baseline) |
| Lint | `ruff check src tests` | 892 errors (pre-existing; unchanged from baseline) |
| Diagnostics | `python -m aura doctor` | All systems OK |
| Packaging | `pyproject.toml` | v3.5.3, scripts `aura`/`aura-audit` |

Pre-existing ruff/mypy counts are documented here for transparency — they are not
introduced by this release and are tracked in `docs/history/` for future hardening.

## Project structure

```
├── src/aura/           23 modules (see docs/component/dependency-graph.md)
│   ├── cli.py          10 Click commands; config bootstrap; logging setup
│   ├── engine.py       13-phase pipeline orchestrator
│   ├── analyzer.py     51-group pattern tables (17 with rules; 127 regex rules)
│   ├── adversarial.py  12 heuristic roles + self-test campaigns
│   ├── domain_auditor.py 40-domain registry; 11 concrete auditors (Wave 1)
│   ├── semantic.py     AST/taint/framework/evidence-graph/memory
│   ├── execution_context.py 10-context file classifier + suppression
│   ├── finding_subclass.py  CODE_DEFECT vs 7 other subclasses
│   ├── state_machine.py     12 gates + transition rules (pure fns)
│   ├── convergence.py       Judge G01-G12 + LoopSafeguard + IdentityTracker
│   ├── evidence.py          hash-chained evidence entries + validators
│   ├── remediation.py       AutoFixer + AutonomousRemediationLoop
│   ├── llm.py               LLMClient + prompts + AutonomousLoop + adapter
│   ├── providers.py         OpenAICompatibleProvider + CircuitBreaker + Registry
│   ├── durable.py           CheckpointManager + DurableAutonomousLoop
│   ├── db.py                SQLite schema + repository methods
│   ├── config.py            pydantic config models
│   ├── errors.py            typed error taxonomy
│   ├── logging.py           structlog stderr setup
│   ├── benchmark.py         legacy 25-case benchmark
│   └── benchmark_v3.py      500+ case generator + mutation/metamorphic + CI gate
├── tests/              10 test modules, 210 tests
├── config/aura.json    engine configuration (pydantic-validated)
├── docs/               blind-rebuilt documentation
│   ├── architecture/  context/  dfd/  flowmap/  sequence/  state/
│   ├── component/     data-model/  decision-validation/  security/
│   ├── failure-recovery/  history/   architecture-gaps-current.md
├── BASELINE.md         pre-rebuild quality-gate record
├── LIMITATIONS.md      known-limitations (validated by `limitations_documented` gate)
├── CHANGELOG.md        versioned change history
└── pyproject.toml      v3.5.3, package aura-audit, Python ≥3.11
```

## Limitations

AURA's self-knowledge file is [LIMITATIONS.md](LIMITATIONS.md) — required reading.
Highlights:
- Regex-based detection, not true SAST. Real AST only for Python.
- ±20-line heuristic taint window; no inter-procedural dataflow.
- 29/40 registered domains have no concrete auditor yet (Wave 2-4 roadmap).
- Dual gate systems documented as potentially divergent (by construction the judge
  cannot converge a repo the engine hasn't already declared PRODUCTION_READY).
- No sandboxing of the target repository; auto-fix writes run with operator privileges.
- SQLite single-writer; no concurrent engines on the same repo.

## Production readiness

AURA v3.5.3 is **BETA** (`Development Status :: 4 - Beta`) per pyproject classifiers.
210/210 tests pass; build, diagnostics, and packaging gates pass; deterministic
convergence model is verified by live probes. External validation remains self-reported
(CHANGELOG: Laravel 88, Vidbro 91, Klinik 42 — third-party validation has not been
performed). See `docs/decision-validation/convergence.md` for the truth table.

---

Built with a "LLM output is an UNTRUSTED CLAIM" philosophy: every finding, every fix,
every gate decision is backed by observable evidence — real exit codes, hash-chained
entries, deterministic counters — never by an LLM's say-so.
