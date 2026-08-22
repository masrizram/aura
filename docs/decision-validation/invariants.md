# Invariants

> Hard rules the system enforces, with enforcing location and what happens on breach.
> Separated into RUNTIME-ENFORCED vs LIBRARY-ONLY (declared but not invoked by engine).

## Runtime-enforced invariants

| # | Invariant | Enforced at | On breach |
|---|---|---|---|
| I-01 | Finding ID is deterministic: sha256(file:line:rule)[:12] | engine._stable_finding_id | collisions share identity (accepted risk) |
| I-02 | Finding severity ∈ {P0..P5} | db.findings CHECK | sqlite3.IntegrityError |
| I-03 | Finding status ∈ 12-value set | db.findings CHECK | sqlite3.IntegrityError |
| I-04 | Remediation status ∈ {PENDING, APPLIED, REJECTED, FAILED, ROLLED_BACK} | db.remediation_attempts CHECK | sqlite3.IntegrityError |
| I-05 | Dead-letter error_type ∈ {UNPARSEABLE, TIMEOUT, PROVIDER_ERROR, INVALID_FIX, SANDBOX_REJECTED, UNKNOWN} | db.dead_letter CHECK | sqlite3.IntegrityError |
| I-06 | Dead-letter status ∈ {PENDING, RETRIED, RESOLVED, ABANDONED} | db.dead_letter CHECK | sqlite3.IntegrityError |
| I-07 | Finding transition whitelist + forbidden jumps | engine.write path NOT enforced; DB only constrains values | illegal transition not prevented — accepted |
| I-08 | Classification transition whitelist | state_machine.validate_* (opt-in); engine writes class directly | engine writes any of 4 classes directly |
| I-09 | converged=true ⇒ all 12 user gates pass | compute path (engine: all_pass ⇒ converged=True) | engine logic ensures symmetric construction |
| I-10 | gates(P2_zero) overridden by CODE_DEFECT-only | engine.py:738-754 | overrides base evaluator deliberately |
| I-11 | `verification`=False when tooling_passed=False | engine.py:724-726 | fail-closed (fail_open=False default) |
| I-12 | LIMITATIONS.md must exist, ≥50 chars, non-placeholder, with `## ` section + bullet | engine._validate_limitations_file | limitations_documented=False |
| I-13 | Module dependency integrity (15 modules importable) | engine._check_module_integrity | module_dependency_integrity=False (fail-closed) |
| I-14 | Regression: resolved∩current = ∅ (any severity, R2-02) | engine._phase_regression | regression=False |
| I-15 | `no_material_new_findings` uses `_finding_key` accepting `id` OR `finding_id` | state_machine._finding_key (R2-01) | prevents silent drift between dict shapes |
| I-16 | Cross-source dedupe uses canonical primary-key at file:line | engine._phase_correlate `_DOMAIN_TO_PRIMARY` | domain+primary double-count prevented |
| I-17 | Lineage invariant: p + a = total_raw; total_raw − total_dupes = total_unique | engine._phase_correlate recomputes | written to audit_log as string |
| I-18 | `_norm_key` domain-overlap logic uses canonical primary key at that location | engine._phase_correlate | resolves INJ-* vs PY-*/TS-* aliasing |
| I-19 | concurrent-cycle counter increments by ≤ 1 via engine logic | engine.upsert_convergence | engine never decrements |
| I-20 | circuit breaker must fail fast (no HTTP when OPEN) | providers.CircuitBreaker.allow_request | OPEN: no request issued |
| I-21 | LLM transport retry only in providers; callers must not layer retries | providers docstring + ProviderBackedLLMClient (no retry) | retry amplification prevented by architecture |
| I-22 | LLM responses always untrusted | llm.py + providers.py (untrusted=True at every site) | cannot reach convergence as truth |
| I-23 | Checkpoint resume refuses tampered state | durable.CheckpointManager.load | returns None (fresh run) |
| I-24 | Evidence hash-chain: append sets chain_index + previous_hash; verify checks linkage | evidence.EvidenceChain | verify_chain reports mismatch |
| I-25 | Dangerous-pattern patch advisory + repo-containment check | remediation.AutoFixer.apply_fix | SANDBOX REJECTED dead-letter |
| I-26 | `arbitrary auto-fix writes` require file_path AND line_number | remediation loop fixable predicate | skipped otherwise |

## Library-only invariants (NOT invoked at runtime)

| # | Invariant | Where declared | Why it matters |
|---|---|---|---|
| L-01 | Gate flip false→true requires evidence | validate_gate_evidence_integrity | would detect hand-edited gates DB |
| L-02 | Gate true→false regression documented | same | would detect unjustified re-opens |
| L-03 | Counter must not decrease or jump >1 | same | engine logic guarantees this; validator redundant but never invoked |
| L-04 | Convergence flip F→T requires ALL 12 gates | same | engine constructs it symmetrically anyway |
| L-05 | Gate-findings cross-check P0/P1/P2/critical_* maps to open findings | validate_gate_findings_crosscheck (only 6 of 12 gates) | engine CONVERGENCE phase re-evaluates gates from current findings anyway |
| L-06 | Verified finding requires evidence chain VERIFIED entry + tool exit=0 + independent source | EvidenceValidator.validate_verified_finding | remediation loop uses DB status instead |
| L-07 | Convergence claim requires all 12 gates + ≥1 VERIFIED evidence entry | EvidenceValidator.validate_convergence_claim | engine uses `converged` boolean |

These seven library-only invariants are exercised by `adversarial.py` self-test
campaigns and unit tests, not by `engine.run_audit()`. Calls to them would close the
gap between "library rules" and "runtime rules" — see `docs/architecture/README.md` §4.
