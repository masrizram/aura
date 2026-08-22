# Security Controls (as implemented)

> Controls that actually run, with their locations and class (preventive / detective / corrective).

## Preventive

| Control | Class | Where | Notes |
|---|---|---|---|
| Repo-containment check on patch writes | preventive | `remediation.AutoFixer.apply_fix` (uses `Path.is_relative_to`) | blocks `..` and symlink escapes |
| Dangerous-pattern patch blocklist | advisory | `remediation.AutoFixer.apply_fix` | bypassable by obfuscation; documented as advisory |
| `old_code` match verification before write | preventive | `AutoFixer.apply_fix` | whitespace-tolerant fuzzy fallback |
| Sandbox-reject on patch with banned substring | preventive (advisory layer) | `AutoFixer.apply_fix` | dead-letter on reject |
| LLM output always `untrusted=True` | preventive (informational) | every LLM/Provider response constructor | convergence never consumes content |
| Bearer-token only in Authorization header | preventive | `llm.py`, `providers.py` | not in URL, not in logs |
| `subprocess.run(shell=False, timeout=300)` | preventive | `engine._run_tooling` | avoids shell metacharacter exec; bounded |
| Parameterised SQL | preventive | `db.py` | no interpolation of values |
| `journal_mode=WAL`, `foreign_keys=ON` | preventive | `db.py` | integrity |
| `fail_open=False` default | preventive | `config.ToolingConfig` | real exit codes unless operator opts out |
| `max_retries=3`, `max_tokens=4000`, `timeout=120s` | preventive | `providers.py`, `llm.py` | resource bounds |
| CLI arg parsing only via Click | preventive | `cli.py` | no eval, no RPC |

## Detective

| Control | Where |
|---|---|
| Per-finding stable identity (sha256 of file:line:rule) | engine._stable_finding_id |
| Lineage invariants recomputed per cycle | engine._phase_correlate |
| Tamper-evident evidence hash-chain | evidence.EvidenceChain.append / verify_chain |
| Tamper-evident checkpoint sha256 | durable.CheckpointManager.load |
| `module_dependency_integrity` import probe (fail-closed) | engine._check_module_integrity |
| Regression detector (resolved∩current, any severity) | engine._phase_regression |
| `_check_module_integrity` fail-closed gate input | engine.__init__ |
| Tooling exit codes persisted | `tooling_evidence` |
| `CYCLE_OBSERVABILITY` audit log event with phase durations | engine.run_audit |

## Corrective

| Control | Where |
|---|---|
| `AutoFixer.rollback()` restore originals on batch failure | remediation.py |
| `update_finding_status` reversal allowed via state machine | db.py + state_machine |
| Dead-letter queue for failed LLM fixes | db.dead_letter |
| Circuit-breaker auto-recovery (OPEN→HALF_OPEN→CLOSED) | providers.CircuitBreaker |
| Provider failover | providers.ProviderRegistry.chat_with_fallback |
| Convergence-judge stall/regression stop | convergence.LoopSafeguard |

## Explicitly not a control (documented honesty)

- `llm.py` has **no retry and no circuit breaker** — it is the single-shot path. Resilience
  is only in `providers.py`. Callers mixing them via `ProviderBackedLLMClient` must not
  add their own retry.
- `registry.json` plugin mechanism is inert (`plugin_count: 0`). No plugin trust boundary
  exists until the loader is written.
