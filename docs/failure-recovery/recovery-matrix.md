# Failure/Recovery — Recovery Matrix

> **Verification basis:** code paths in `errors.py`, `providers.py`, `durable.py`,
> `remediation.py`, `db.py`, `engine.py`, `evidence.py`. Everything here cites its owner.

| # | Failure | Where detected | First response | Durable recovery | Evidence written | Boundary |
|---|---|---|---|---|---|---|
| 1 | Network error calling LLM | `httpx` exception in provider | retry w/ full jitter (≤3) | circuit `record_failure`, fail to next provider | ProviderResponse error | only 3 tries before surface |
| 2 | HTTP 429 / 5xx | provider chat loop | Retry-After honor or full jitter | same as #1 | ProviderResponse error | max_retries=3 |
| 3 | HTTP 400/401/403/404/422 | provider chat loop | **fail fast** — no retries | failure recorded; next provider may be tried | ProviderResponse error | permanent, deterministic |
| 4 | All providers fail | ProviderRegistry | aggregate error response | surfaces to remediation loop as no-fix | ProviderResponse "All N provider(s) failed" | loop continues sans LLM |
| 5 | LLM output invalid JSON | `AutonomousLoop.audit_with_llm` etc. | markdown → brace-matched fallback | returned as `{findings:[], _untrusted:True}` | in-memory only | caller decides; no crash |
| 6 | LLM fix JSON unparseable | `remediation.AutoFixer` path | `insert_dead_letter(UNPARSEABLE)` | finding stays OPEN; counts toward same-finding attempts | dead_letter row | MAX_SAME_FINDING_ATTEMPTS=3 |
| 7 | LLM `old_code` mismatch | `AutoFixer.apply_fix` | FixResult success=False w/ diff context | one retry with actual file context (only once) | remediation_attempts REJECTED | second mismatch gives up |
| 8 | LLM suggests dangerous patch | `AutoFixer` check | SANDBOX REJECTED | `insert_dead_letter(SANDBOX_REJECTED)` | dead_letter row | old-code-match + rollback + re-audit are the true boundary |
| 9 | LLM patch breaks tests | TEST phase tooling non-zero | `gates["verification"]=False` | convergence blocked until next clean audit | tooling_evidence row | same cycle fails VERIFY |
| 10 | Subprocess timeout (>300s) | `_run_tooling` except | TimeoutExpired → exit_code=-1, success=False | tooling gate signal = fail | tooling_evidence row | no retry of the subprocess |
| 11 | DB locked / IntegrityError | `db.transaction` | rollback; caller decides | caller-level retry policy according to `DatabaseError` mapping | nothing committed | BEGIN IMMEDIATE keeps invariants |
| 12 | Checkpoint file corrupted/tampered | `CheckpointManager.load` | sha256 mismatch → return None | fresh run instead of resume from tampered state | none (refusal is the signal) | never resumes from unverified state |
| 13 | Legacy checkpoint w/o hash | `CheckpointManager.load` | `_integrity="legacy-unverified"` | accepted but flagged | `_integrity` field | explicit transparency |
| 14 | Evidence hash-chain link break | `EvidenceChain.verify_chain` | chain_index / previous_hash mismatch | caller decides (engine doesn't invoke at runtime) | violations list | intended for CLI/self-test |
| 15 | Same finding attempted too often | LoopSafeguard | (False, "Finding X failed N attempts") | stop remediation cycle | cycle_log reason | MAX_SAME_FINDING_ATTEMPTS=3 |
| 16 | No-progress stall | LoopSafeguard | (False, "No progress for N cycles") | stop loop | cycle_log reason | NO_PROGRESS_CYCLES=3, score<90 |
| 17 | Score regression breach | LoopSafeguard | (False, "Score regression of D < threshold") | stop loop | cycle_log reason | REGRESSION_THRESHOLD=-10 |
| 18 | Module import fail at startup | `_check_module_integrity` | logs warning, returns False | `module_dependency_integrity` gate = False | convergence gate evidence | fail-closed (no PRODUCTION_READY) |
| 19 | Semantic enrichment crash | `_phase_correlate` except | `semantic_enriched=[]` | pipeline continues without mitigation | engine log warning | gate eval falls back to raw |
| 20 | Domain orchestrator crash | `_phase_adversarial` except | falls back to legacy 12-role scan | audit continues | not logged (silent fallback) | documented as silent fallback gap |

## Error taxonomy → recovery (from `errors.py`)

- RETRY: `NetworkError`, `RateLimitError` — transient transport.
- RETRY_WITH_FALLBACK: `TimeoutError`, `ProviderError`, `DatabaseError` — local retry, then next resource.
- NO_RETRY: `ConfigError`, `ValidationError`, `StateMachineError`, `NotFoundError` — deterministic; surface immediately.

## Single-writer DB reality

SQLite (WAL) means single-writer-per-file. Engine CLI is a single process; concurrent
`aura audit` runs against the same target repo can contend on `BEGIN IMMEDIATE`.
Mitigation is the caller's: run one engine at a time per repo.
