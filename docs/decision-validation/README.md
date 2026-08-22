# Decision Validation — Index

> The engine decides convergence, finding transitions, and verification state.
> This section documents WHO decides WHAT, WHERE it is validated, and HOW it is falsified.

## Decision owners (single source of truth)

| Decision | Owner (module) | Entry point | Called at runtime? |
|---|---|---|---|
| 12 user gates pass/fail | `state_machine.evaluate_all_gates` | engine CONVERGENCE phase | ✅ yes (engine.py:713) |
| Convergence score (0-100) | `state_machine.compute_convergence_score` | engine CONVERGENCE phase | ✅ yes (engine.py:729) |
| Final classification | `engine._phase_convergence` | engine CONVERGENCE phase | ✅ yes (engine.py:764-772) |
| Subclass-aware gate override | `engine` + `finding_subclass.is_blocking_for_gate` | engine CONVERGENCE phase | ✅ yes (engine.py:738-754) |
| LIMITATIONS gate validation | `engine._validate_limitations_file` | engine CONVERGENCE phase | ✅ yes (engine.py:692) |
| Finding transition rules | `state_machine.VALID_FINDING_TRANSITIONS` + validators | (library) | ❌ NOT called by engine at runtime |
| Gate evidence integrity | `state_machine.validate_gate_evidence_integrity` | (library) | ❌ NOT called by engine |
| Gate ↔ findings cross-check | `state_machine.validate_gate_findings_crosscheck` | (library) | ❌ NOT called by engine |
| Evidence `validate_verified_finding` | `evidence.EvidenceValidator` | adversarial self-tests, tests | ⚠️ opt-in (NOT engine) |
| Convergence claim (12 gates + evidence) | `evidence.EvidenceValidator.validate_convergence_claim` | (library) | ⚠️ opt-in |
| Autonomous loop convergence | `convergence.ConvergenceJudge.evaluate` (G01-G12) | remediation loop on PRODUCTION_READY | ✅ yes (remediation.py:321) |
| Loop continuation (safeguards) | `convergence.LoopSafeguard.can_continue` | remediation loop each cycle | ✅ yes (remediation.py:334) |
| Fix safety on apply | `remediation.AutoFixer.apply_fix` | remediation each fix | ✅ yes |
| Provider routing | `providers.ProviderRegistry.chat_with_fallback` | (when wired) via llm.ProviderBackedLLMClient | ✅ yes when provider-backed |
| Circuit breaking | `providers.CircuitBreaker.allow_request` | per provider call | ✅ yes |

## Documents in this section

- `convergence.md` — full classification + scoring + dual gate systems + counter rules.
- `finding-validation.md` — subclass rules + transition whitelist + identity rules.
- `invariants.md` — every invariant enforced (and which ones are NOT).
- `audit-decision-flow.md` — the sequence of decisions per cycle.
