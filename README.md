# AURA v3.5.2 — Autonomous Software Reliability Engine

[![Tests](https://img.shields.io/badge/tests-202%2F202-brightgreen?style=flat-square)](tests/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Language groups](https://img.shields.io/badge/language%20groups-51%20(17%20with%20rules)-orange?style=flat-square)](src/aura/analyzer.py)
[![Rules](https://img.shields.io/badge/rules-127-yellow?style=flat-square)](src/aura/analyzer.py)
[![Benchmark](https://img.shields.io/badge/benchmark%20F1-96.8%25-brightgreen?style=flat-square)](src/aura/benchmark_v3.py)

AURA autonomously discovers, analyzes, remediates, independently verifies, regression-tests, and repeatedly re-audits a repository until deterministic evidence satisfies its convergence policy.

[Documentation](docs/README.md) · [Architecture](docs/architecture/system-architecture.md) · [Improvement Plan](docs/architecture-improvement-plan.md) · [Limitations](LIMITATIONS.md) · [Changelog](CHANGELOG.md)

## What AURA is

AURA is a **static audit + autonomous remediation engine** for source-code repositories. It scans a codebase with pattern-based detection (127 rules), layers semantic analysis (Python AST, heuristic taint), attacks the result from specialized adversarial domains, correlates and deduplicates findings, then evaluates a **12-gate deterministic convergence policy** to answer one question with evidence: *is this repository production-ready?*

Optionally, with an LLM provider configured, AURA runs an **autonomous audit → fix → verify → re-audit loop** (`aura auto-fix`) that treats every LLM output as an UNTRUSTED CLAIM until independent tool execution proves it.

## Core capabilities (implemented)

- **13-phase audit cycle** — DISCOVER → MODEL → AUDIT → ADVERSARIAL_AUDIT → CORRELATE → PRIORITIZE → REMEDIATE → TEST → VERIFY → REGRESSION → UPDATE_STATE → CONVERGENCE → PUSH_APPROVAL.
- **Pattern detection** — 51 language groups mapped by extension; 17 groups carry active rules; 127 rules total (verified by runtime inspection, not marketing copy).
- **Semantic intelligence** — real AST parsing for Python (stdlib `ast`); heuristic structural recognition for PHP/JS; ±20-line taint window with a sanitizer capability matrix; CWE/OWASP/CVSS mapping.
- **Execution-context filtering** — findings in tests/docs/migrations/generated/third-party code are suppressed unless P0.
- **Finding subclasses** — CODE_DEFECT vs SECURITY_ADVISORY / GOVERNANCE / TEST_QUALITY / INFORMATIONAL; only CODE_DEFECT blocks P0–P2 gates.
- **12-gate convergence** — deterministic, evidence-backed, fail-closed. Score = 60% gates + 40% findings, blended with code quality.
- **False-convergence prevention** — regression tests prove convergence is *blocked* when P0/P1 open, when FIXED findings lack verification, when regressions reappear, or when consecutive-clean history is insufficient.
- **Autonomous remediation** — LLM-generated patches with dry-run preview, `old_code` match verification, automatic rollback on tooling failure, per-finding attempt caps, no-progress detection, dead-letter queue, and checkpoint/resume with integrity hashing and safeguard-state restore (resume cannot reset attempt counters).
- **Provider resilience** — circuit breaker (CLOSED→OPEN→HALF_OPEN), real per-call priority fallback across providers, classified retry (4xx = fail fast; 429/5xx/network = retry with full jitter, `Retry-After` honored). The provider layer is the only retry layer.
- **Evidence chain** — tamper-evident hash chain (`chain_index` + `previous_hash`, genesis `"0"*64`); detects modification, deletion, and reordering. JSON store with SQL mirror.
- **Trend tracking** — per-cycle score/findings/gates history with direction analysis.
- **Observability** — every cycle gets a `cycle_id` bound to structured logs; per-phase durations are recorded as `CYCLE_OBSERVABILITY` audit-log entries.

## What AURA does NOT yet do (honest boundaries)

- **No cryptographic signing of evidence.** The schema carries `signature`/`signer`/`public_key_fingerprint` fields, but no key-management infrastructure exists. The hash chain gives tamper *evidence*, not non-repudiation.
- **29 of 40 domain auditors are registered but not implemented** (Wave 2–4). 11 Wave-1 domains are active.
- **No notification delivery** — config keys exist; no delivery mechanism is implemented.
- **No plugin system** — `registry.json` is a placeholder; there is no plugin loader.
- **No DB encryption at rest**, no repository file locking during scans (TOCTOU), no HTTP health endpoint (health is CLI-only).
- **Non-Python languages use pattern matching only.** PHP/JS "structural" parsing is regex-based tokenization, not a real parser. AST claims apply to Python only.
- The AutoFixer dangerous-pattern blocklist is an **advisory signal, not a security boundary**. Real remediation safety comes from dry-run + `old_code` verification + rollback + re-audit.

See [LIMITATIONS.md](LIMITATIONS.md) — its content is itself validated by the `limitations_documented` convergence gate.

## Architecture

```text
cli.py (Click) ──► Engine (13 phases)
                     │
                     ├─► MultiLangAnalyzer        127 rules / 51 lang groups
                     ├─► DomainAuditOrchestrator  11 active domains (40 registered)
                     ├─► AdversarialAuditor       12 legacy roles (fallback)
                     ├─► SemanticAuditor          AST/taint/confidence (Python AST real)
                     ├─► ExecutionContextClassifier  suppress test/docs/vendor
                     ├─► state_machine            12 gates + transition validation
                     ├─► EvidenceChain            hash-linked, tamper-evident
                     ├─► Database (SQLite WAL)    cycles/findings/gates/evidence/audit_log
                     └─► (auto-fix) ProviderRegistry → BaseProvider (circuit breaker)
                            → OpenAICompatibleProvider (classified retry + jitter)
                            → ProviderBackedLLMClient → AutonomousRemediationLoop
                               → AutoFixer (dry-run/rollback) → ConvergenceJudge
```

Full detail: [docs/architecture/system-architecture.md](docs/architecture/system-architecture.md), [component diagram](docs/component/component-diagram.md), [dependency graph](docs/component/dependency-graph.md) (verified DAG, no circular imports).

## Audit pipeline & data flow

- [DFD Level 0](docs/dfd/level-0.md) / [Level 1](docs/dfd/level-1.md)
- [Audit flow](docs/flowmap/audit-flow.md) / [startup flow](docs/flowmap/startup-flow.md)
- Sequence diagrams: [audit execution](docs/sequence/audit-execution.md), [provider request](docs/sequence/provider-request.md), [finding validation](docs/sequence/finding-validation.md)

## Validation & convergence

Two gate systems exist, intentionally separate and now documented as such:

1. **Engine gates** (`state_machine.py`, user-facing): `P0_zero`, `P1_zero`, `P2_zero`, `critical_security`, `critical_correctness`, `data_integrity`, `regression`, `verification`, `no_material_new_findings`, `limitations_documented`, `consecutive_clean_independent_audits`, `module_dependency_integrity` (the last is a real import check, fail-closed).
2. **Judge gates** (`convergence.py`, autonomous-loop proof): G01–G12. G07 (typecheck) is derived from G06 (tooling) — it never claims a signal that doesn't exist.

Invariants are documented in [docs/decision-validation/invariants.md](docs/decision-validation/invariants.md). Note: score-monotonicity "invariants" were **removed in v3.5.1** (IMP-03) — discovering new findings legitimately lowers the score, and penalizing that rewarded hiding findings.

## Provider system

```text
ProviderRegistry (health, fallback order)
  └─► BaseProvider — CircuitBreaker + status accounting
        └─► OpenAICompatibleProvider — classified retry, full-jitter backoff,
                                        Retry-After support, non-retryable 4xx
```

`ProviderBackedLLMClient` adapts the registry to the engine's `chat()` protocol without adding a second retry layer. Ollama is auto-detected as a fallback when reachable.

## Installation

Requires Python 3.11+.

```bash
git clone <your-fork-url> aura
cd aura
uv pip install -e ".[dev]"        # or: pip install -e ".[dev]"
```

## Configuration

Static audit needs **no credentials**. Autonomous remediation requires an OpenAI-compatible endpoint:

```bash
cp .env.example .env
# .env:
# AURA_LLM_URL=http://localhost:20128/v1
# AURA_LLM_KEY=sk-...
# AURA_LLM_MODEL=your-model
```

Optional: `AURA_DB_PATH`, `AURA_LOG_LEVEL`, `AURA_CONFIG_PATH`. Full reference: [.env.example](.env.example), [config/aura.json](config/aura.json) (severity weights, gate requirements, scale limits).

`.env` is gitignored. Keys are read from the environment only — never hardcoded.

## Usage

```bash
python -m aura doctor        # system diagnostics
python -m aura init          # initialize DB + cycle 1
python -m aura audit         # run a full 13-phase cycle
python -m aura status        # current cycle, gates, open findings
python -m aura verify        # findings grouped by severity (+ --fix guidance, + <ID> detail)
python -m aura trend         # cross-cycle trajectory
python -m aura report        # markdown audit report
python -m aura health        # DB integrity check
python -m aura log           # 13-phase audit trail

# Autonomous remediation (requires AURA_LLM_KEY)
python -m aura auto-fix --dry-run                # preview only
python -m aura auto-fix --max-cycles 5           # live
python -m aura auto-fix --resume                 # resume from checkpoint
```

## Security

Summary of implemented controls: LLM output is always UNTRUSTED; convergence decisions are deterministic and never LLM-influenced; path containment uses `Path.is_relative_to()`; evidence chain is hash-linked and tamper-evident; checkpoints carry integrity hashes; secrets come from env vars; DB access is parameterized (SQL-injection regression-tested).

Full inventory including PARTIAL and MISSING controls: [docs/security/security-controls.md](docs/security/security-controls.md), [threat model](docs/security/threat-model.md), [trust boundaries](docs/security/trust-boundaries.md), [attack surface](docs/security/attack-surface.md).

## Reliability

Timeout (subprocess 300s, LLM configurable), classified retry with full jitter, circuit breaker with half-open recovery, per-call provider fallback, automatic rollback of failed fixes, dead-letter queue, checkpoint/resume with tamper detection + safeguard restore, real tooling exit codes (fail-closed; `fail_open` is opt-in), transactional DB writes (WAL + foreign keys).

Details: [docs/failure-recovery/](docs/failure-recovery/README.md).

## Testing

```bash
python -m pytest tests/ -q     # 202 tests, all passing
python -m ruff check src/      # lint (style debt documented; 0 syntax errors)
python -m mypy src/aura/       # strict mode; clean on v3.5.1-touched modules
```

Suite includes false-convergence negatives, security (SQL injection, path traversal), state-machine transition tables, and 26 regression tests for the v3.5.1 architecture fixes (`tests/test_architecture_improvements.py`, `tests/test_run2_regressions.py`).

## Project structure

```text
src/aura/            engine, analyzer, semantic, adversarial, domain_auditor,
                     state_machine, convergence, evidence, providers, llm,
                     remediation, durable, db, config, errors, logging, cli
tests/               8 test modules, 186 tests
docs/                architecture, context, dfd, flowmap, sequence, state,
                     component, data-model, decision-validation, security,
                     failure-recovery + audits & improvement plan
config/aura.json     default configuration
.env.example         credential template (no secrets)
```

## Documentation map

Start at [docs/README.md](docs/README.md). Engineering artifacts from the v3.5.1 hardening cycle: [documentation audit](docs/documentation-audit.md), [architecture improvement plan](docs/architecture-improvement-plan.md) (IMP-01..IMP-10 with severity/priority), [target architecture](docs/target-architecture.md), [final consistency audit](docs/final-consistency-audit.md), [architecture gaps](docs/architecture-gaps.md).

## Production readiness

**Production Candidate.**

Evidence for: 202/202 tests passing (including false-convergence negatives and security regression tests), deterministic fail-closed gates, tamper-evident evidence chain, resilient provider stack, honest limitation tracking enforced by a gate.

Evidence against full "Production Ready": no evidence signing, 29/40 domains unimplemented, no DB encryption/TOCTOU protection, pattern-based detection for non-Python languages with unmeasured false-negative rates at scale.

AURA's own convergence verdict on itself is reproducible: run `python -m aura audit` in this repository.

## License

[MIT](LICENSE) © AURA Engineering. See [CHANGELOG.md](CHANGELOG.md) for release history.
