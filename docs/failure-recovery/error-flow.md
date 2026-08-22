# Failure/Recovery — Error Flow

> Trace errors from origin through each layer to what the operator sees.

## 1. Configuration error
- Origin: `AuraConfig.from_file` pydantic ValidationError (or bad JSON).
- Wrap: `ConfigError` (FATAL).
- Surface: cli catches → `console.print [red]Configuration error[/red]` → `sys.exit(1)`.
- DB: no cycle written.

## 2. Engine init failure
- Origin: any AuraError subclass in `Engine.initialize` or its imports.
- Wrap: AuraError retained (`ConfigError`, `DatabaseError`, `StateMachineError`, `NotFoundError`, ...).
- Surface: cli `init|audit|...` handlers catch AuraError → prints → `sys.exit(1)`.
- DB: rollback via `Database.transaction().__exit__` on exception (BEGIN IMMEDIATE / ROLLBACK).

## 3. Phase exception mid-cycle
- Origin: any exception in a `_phase_*` handler not wrapped in try/except.
- Path: `run_audit()` loop does NOT catch; propagates to cli.
- Surface: cli catches → prints → `sys.exit(2)` (from `main()` wrapper when unhandled).
- DB: cycle row stays `RUNNING`, audit_log partial rows for completed phases.
- Recovery: re-run `aura audit` → starts new cycle cn+1 (never resumes a half-cycle).

## 4. Tooling non-zero exit
- Origin: subprocess returncode != 0 or timeout.
- DB: `insert_tooling_evidence(success=False, exit_code=N or -1)`.
- Effect: `gates["verification"]=False` in CONVERGENCE; verification gate blocks converged.
- Recovery: next `aura audit` cycle re-runs tooling fresh.

## 5. LLM transport error
- Path A (LLMClient) → single `LLMResponse("LLM_ERROR: ...", untrusted=True)`; loop logs it.
- Path B (provider) → full-jitter retry (≤3) → circuit `record_failure` → failover to next provider → if all fail: `ProviderResponse(error="All N provider(s) failed")` → ProviderBackedLLMClient translates to `LLMResponse("LLM_ERROR: ...")`.
- Effect: remediation loop treats as no-candidate; finding stays OPEN; attempt count increments.
- Dead-letter only when JSON parse fails after transport OK.

## 6. LLM fix apply error
- Origin: `AutoFixer.apply_fix` returns `FixResult(success=False, error=...)`.
- Paths:
  - old_code mismatch → one retry with file context.
  - sandbox reject → dead_letter(SANDBOX_REJECTED).
  - dangerous pattern → dead_letter + skip.
- Persist: `insert_remediation_attempt(status="REJECTED")`.
- Loop: `MAX_SAME_FINDING_ATTEMPTS` caps at 3; LoopSafeguard decides continue/stop.

## 7. Checkpoint corruption
- Origin: `.aura/checkpoint.json` hash mismatch or bad JSON.
- Recovery: `load()` returns None → fresh run (tampered state never resumed).
- Legacy checkpoint: accepted with `_integrity="legacy-unverified"` marker.

## 8. Evidence chain link break
- Origin: `EvidenceChain.verify_chain()` finds index/previous_hash mismatch.
- Effect: violations list returned to caller (engine does not call this during run_audit).
- Self-test campaigns and tests exercise it; the runtime convergence path does not.

## 9. Domain orchestrator exception
- Origin: any exception from `DomainAuditOrchestrator.run_all_legacy()` inside `_phase_adversarial`.
- Effect: silent fallback to `adversarial.run_all(repo_root)` legacy 12 roles (no log entry).
- Recovery: next cycle retries orchestrator again.

## 10. Semantic enrichment exception
- Origin: any exception in `semantic.enrich_findings`.
- Effect: `semantic_enriched=[]`; gates evaluated on raw findings; a warning is logged.
