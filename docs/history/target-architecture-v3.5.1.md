# AURA Target Architecture — v3.5.x

> Defines the improved architecture that the implementation phase realizes.
> Every TARGET row maps to an IMP item in `architecture-improvement-plan.md`.

## 1. Provider architecture (IMP-01, IMP-05)

```text
CURRENT:
  cli.auto_fix ── inline _RegistryLLMWrapper (defined per-invocation)
  engine ─────── LLMClient (no resilience, no circuit breaker)
  providers.py ─ OpenAICompatibleProvider (retry, no jitter, no error taxonomy)
  → Two competing stacks; resilience absent from engine path.

PROBLEM:
  Duplicated logic, untestable inline class, retry amplification,
  no jitter, non-retryable errors retried.

TARGET:
  ┌───────────────────────────────────────────────────────────┐
  │ Engine / AutonomousLoop / cli                             │
  │        │  depends on protocol (chat() → LLMResponse)      │
  │        ▼                                                  │
  │ ProviderBackedLLMClient  (llm.py, named, testable)        │
  │        │  adapts ProviderResponse → LLMResponse           │
  │        ▼                                                  │
  │ ProviderRegistry (health, fallback order)                 │
  │        ▼                                                  │
  │ BaseProvider (CircuitBreaker: CLOSED→OPEN→HALF_OPEN)      │
  │        ▼                                                  │
  │ OpenAICompatibleProvider                                  │
  │   retry policy: full jitter, classified errors            │
  │   429/5xx/timeout/network → RETRY (≤3, jittered backoff)  │
  │   4xx auth/validation     → NO_RETRY (fail fast)          │
  │   callers MUST NOT retry above this layer                 │
  └───────────────────────────────────────────────────────────┘

MIGRATION:
  1. llm.py: add ProviderBackedLLMClient (module-level, public).
  2. cli.py: delete inline wrapper; construct ProviderBackedLLMClient.
  3. providers.py: rewrite retry loop (jitter + classification).
  4. LLMClient kept as deprecated alias for backward compat.

IMPLEMENTATION: IMP-01, IMP-05 (this cycle).
```

## 2. Convergence & validation (IMP-02, IMP-03)

```text
CURRENT:
  ConvergenceJudge.G07 = True (hardcoded)
  Engine module_integrity_pass = True (hardcoded)
  validate_gate_evidence_integrity: SCORE REGRESSION / SCORE SPIKE
    violations that punish legitimate new-finding cycles; validator
    itself never called by engine (dead invariant).

PROBLEM:
  False convergence possible; invariants contradict remediation reality.

TARGET:
  G07 := G06 (tooling pass) until a real typecheck signal exists —
         documented as derived, never independent.
  module_dependency_integrity := real import check of required
         aura.* modules at engine init (fail-closed).
  Score monotonicity violations REMOVED from validator;
  counter-jump invariants KEPT (they are genuine).
  Validator remains a library function (not wired into engine) —
  documented as opt-in strict mode.

MIGRATION: convergence.py, engine.py, state_machine.py edits;
           test expectations updated.
IMPLEMENTATION: IMP-02, IMP-03 (this cycle).
```

## 3. Evidence integrity (IMP-04)

```text
CURRENT:
  EvidenceChain → JSON file only; hashes are self-contained
  (no previous_hash linkage → deletions undetectable).
  evidence_chain SQL table → zero readers/writers (dead schema).

TARGET:
  Evidence { chain_index, previous_hash } — real hash chain.
  verify_chain() walks linkage: genesis = "0"*64, each entry's
  previous_hash == prior entry's hash.
  Optional Database sync: same entries persisted to evidence_chain
  table when a Database is attached (single logical store, two
  persistence backends, JSON remains source of truth this cycle).

MIGRATION: evidence.py fields + append/verify; db.sync method;
           tamper tests.
IMPLEMENTATION: IMP-04 (this cycle).
```

## 4. Security boundaries (IMP-06)

```text
CURRENT:
  Path check: str(resolved).startswith(str(repo_root))  ← prefix bug
  Blocklist: substring match on new_code (bypassable, false-positive)

TARGET:
  Path check: resolved.is_relative_to(repo_root_resolved) — correct
    containment primitive; rejects /a/repo-evil siblings and symlink
    escapes.
  Blocklist: retained as ADVISORY signal (logged); the documented
    real controls are --dry-run, old_code verification, automatic
    rollback on tooling failure, and re-audit. Security docs state
    this boundary honestly.

MIGRATION: remediation.py apply_fix path guard + tests.
IMPLEMENTATION: IMP-06 (this cycle).
```

## 5. Reliability extras (IMP-07)

```text
TARGET:
  CheckpointManager: state_hash (SHA-256 over canonical state JSON)
  embedded on save, verified on load; mismatch → refuse resume.
IMPLEMENTATION: IMP-07 (this cycle).
```

## 6. Hygiene (IMP-08, IMP-09, IMP-10)

```text
TARGET:
  benchmark_v3.py parses cleanly (syntax fixed).
  Numeric claims unified: 51 language groups / 17 with rules / 127 rules.
  Per-cycle observability: cycle_id bound to logs, phase durations
  recorded into audit_log metadata, provider request_id in responses.
IMPLEMENTATION: IMP-08, IMP-09, IMP-10 (this cycle).
```

## Dependency direction (unchanged, verified DAG)

```text
cli ──► engine ──► analyzer / adversarial / domain_auditor / semantic
  │       │────► state_machine / convergence / evidence
  │       │────► llm ──► providers ──► errors
  │       └────► db ──► config ──► errors
  └──► remediation ──► convergence
logging ◄── all modules (leaf)
No circular imports. Preserved by all changes above.
```
