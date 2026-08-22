# Component — README

Component-level documentation for AURA.

| Document | Scope |
|---|---|
| [component-diagram.md](component-diagram.md) | Full component catalog, dependency graph, coupling analysis, responsibility leakage |
| [dependency-graph.md](dependency-graph.md) | (Consolidated in component-diagram.md) |

## Quick Component Index

| # | Module | Role |
|---|---|---|
| 1 | `engine.py` | Orchestration — 13-phase pipeline coordinator |
| 2 | `analyzer.py` | Detection — 51-language-group/127-rule regex scanner |
| 3 | `adversarial.py` | Adversarial Audit (legacy 12-role) |
| 4 | `domain_auditor.py` | Adversarial Audit (40-domain, enhanced) |
| 5 | `semantic.py` | Intelligence — AST, taint, CWE/CVSS, framework |
| 6 | `state_machine.py` | Enforcement — transitions, invariants, gates |
| 7 | `convergence.py` | Decision — judge, safeguards, identity tracking |
| 8 | `finding_subclass.py` | Classification — CODE_DEFECT vs advisory |
| 9 | `execution_context.py` | Context — file execution context filtering |
| 10 | `evidence.py` | Integrity — hash chain, validator, grader |
| 11 | `providers.py` | Integration — LLM provider registry + circuit breaker |
| 12 | `llm.py` | Integration — LLM client + autonomous audit prompts |
| 13 | `remediation.py` | Remediation — AutoFixer + autonomous loop |
| 14 | `durable.py` | Reliability — checkpoint/resume |
| 15 | `db.py` | Persistence — SQLite with 12 tables |
| 16 | `config.py` | Configuration — Pydantic-validated |
| 17 | `errors.py` | Error handling — 14 categories, 9 types |
| 18 | `cli.py` | Interface — 9 click commands |
| 19 | `logging.py` | Observability — structlog to stderr |
| 20 | `benchmark.py` / `benchmark_v3.py` | Testing — benchmark runners |