# Component Architecture — diagrAAM

> Source AST import analysis 2026-08-22 (23 modules) + live probes. DAG, no cycles.

## Component tiers (as constructed by Engine.__init__, `engine.py:70-84`)

```
┌─────────────────────────────┐  tier‑1 leaves (no aura-internal deps)
│ analyzer · semantic ·        │
│ execution_context ·          │
│ finding_subclass ·           │
│ state_machine · convergence· │
│ evidence · errors · logging· │
│ llm · durable · benchmark_v3 │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐  tier‑2 (depend on leaves)
│ config → errors              │
│ db → config                  │
│ providers → errors           │
│ benchmark → semantic         │
│ remediation → convergence    │
│ adversarial → evidence,state │
│ domain_auditor → adversarial │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐  tier‑3 orchestrators
│ engine → (most of the above)◄─── db, evidence(chain),
│ (Engine object)              │    analyzer, adversarial,
│                              │    domain_orch, semantic,
│                              │    context, llm?, autonomous?
│ cli → engine, config, errors │    semantic.memory
│      llm, providers,         │
│      remediation, durable    │
└──────────────────────────────┘
```

## Component ↔ responsibility (externally observable)

| Component | Responsibility | Collaborators | Evidence |
|---|---|---|---|
| `cli.py` | 10 Click commands; config init; exit semantics | config, engine, errors, llm, providers, remediation, durable | `cli.py:89-632` |
| `engine.py` | 13-phase pipeline orchestration, correlation, gates | almost all tiers | L50-1199 |
| `analyzer.py` | regex pattern scanning, quality score, trend | none | L437-523 |
| `adversarial.py` | 12 role heuristic scanners + self-test campaigns | evidence, state_machine (tests) | L42-733 |
| `domain_auditor.py` | shared-intelligence build; 11 concrete Wave‑1 auditors; correlator | adversarial (shape) | L385-1017 |
| `semantic.py` | AST/taint/framework/evidence graph; confidence; repository memory | none | L25-1429 |
| `execution_context.py` | file context classification, suppression policy | none | L158-296 |
| `finding_subclass.py` | CODE_DEFECT vs 7 other subclasses | none | L22-138 |
| `state_machine.py` | gate evaluation + transition validators (pure fns) | none | L14-482 |
| `convergence.py` | ConvergenceJudge G01–G12, LoopSafeguard, IdentityTracker, EvidenceChainBuilder | none | L38-324 |
| `evidence.py` | hash-chain evidence; validators | none | L31-237 |
| `remediation.py` | AutoFixer, AutonomousRemediationLoop | convergence | L58-588 |
| `llm.py` | LLMClient + prompts + AutonomousLoop + ProviderBackedLLMClient | httpx only | L25-256 |
| `providers.py` | OpenAICompatibleProvider, CircuitBreaker, ProviderRegistry (fallback) | errors | L56-372 |
| `durable.py` | CheckpointManager + DurableAutonomousLoop | none (duck-typed) | L22-216 |
| `db.py` | SQLite schema + repository methods | config | L196-650 |
| `config.py` | pydantic models, from_env_or_file loader | errors | L19-239 |
| `errors.py` | typed error taxonomy | none | L14-201 |
| `logging.py` | structlog config; stderr-only logs | none | L15-69 |
| `benchmark.py` | legacy 25-case benchmark | semantic | L16-541 |
| `benchmark_v3.py` | 500+ case generator, mutation, metamorphic, CI gate | none | L50-1000 |

## Lifecycle wiring (from `Engine.__init__`, `engine.py:70-84`)

```
Engine(repo_root, config|None, llm_client|None)
  ├─ AuraConfig.from_env_or_file(repo_root)      if config is None
  ├─ Database(config.database)                   → .aura/state/aura.db
  ├─ MultiLangAnalyzer(repo_root)                → pure pattern matcher
  ├─ AdversarialAuditor()                        → 12 roles
  ├─ EvidenceChain()                             → in-memory chain (no path ⇒ no persistence)
  ├─ llm_client (optional)                       → AutonomousLoop(llm, repo_root) if provided
  ├─ SemanticAuditor(repo_root)                  → AST/taint/framework/memory
  ├─ DomainAuditOrchestrator(repo_root)          → SharedIntelligence + WAVE_REGISTRY Wave-1 only
  ├─ ExecutionContextClassifier(repo_root)       → cached FileContext per file
  └─ self.module_integrity = _check_module_integrity()  (imports the 15 required aura.* modules)
```

## External-tool auto-detection (drives TEST phase)

`_run_tooling` calls `_detect_commands` which conditionally appends
`semgrep scan`, `bandit`, `gitleaks detect`, `npx tsc --noEmit`,
`python -m pytest --tb=short`, `npm run test|lint|build`, `make test`,
`go test ./...`, `cargo test` — **only if** the corresponding marker exists
(e.g. `shutil.which("semgrep")`, `pyproject.toml`, `package.json`, `Makefile`,
`go.mod`, `Cargo.toml`, `tsconfig.json`). `config.engine.tooling.required_pass_commands`
are appended on top (`engine.py:973-1026`).
