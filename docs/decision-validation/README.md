# Decision & Validation — README

This section documents how AURA determines whether findings are valid and whether convergence is achieved.

| Document | Scope |
|---|---|
| [audit-decision-flow.md](audit-decision-flow.md) | Decision gates for the audit pipeline |
| [finding-validation.md](finding-validation.md) | How individual findings are validated |
| [convergence.md](convergence.md) | Convergence criteria, gate evaluation, scoring |
| [invariants.md](invariants.md) | Mathematical/structural invariants enforced by the state machine |

## Decision Gates Summary

The system has two parallel gate systems:

### 12 User-Facing Gates (Engine)
Used in CLI output, stored in `gates` table, evaluated by `evaluate_all_gates()`.

| Gate | Condition | Evidence Required |
|---|---|---|
| P0_zero | Zero OPEN/IN_PROGRESS P0 findings | All P0 VERIFIED or DEFERRED |
| P1_zero | Zero OPEN/IN_PROGRESS P1 findings | All P1 VERIFIED or DEFERRED |
| P2_zero | Zero CODE_DEFECT P2 findings | All P2 VERIFIED or DEFERRED |
| critical_security | All P0-P2 SECURITY VERIFIED | Independent verification |
| critical_correctness | All P0-P2 CORRECTNESS VERIFIED | Independent verification |
| data_integrity | All P0-P2 DATA_INTEGRITY VERIFIED | Independent verification |
| regression | Zero re-appeared findings | Regression audit |
| verification | No findings in FIXED (unverified) state | All FIXED have verifier evidence |
| no_material_new_findings | No new P0-P3 for 2 cycles | Cross-cycle comparison |
| limitations_documented | LIMITATIONS.md with structured content | File existence + content validation |
| consecutive_clean_independent_audits | ≥2 consecutive converged + ≥2 audits since finding | Counters |
| module_dependency_integrity | All required modules loaded | Always PASS |

### 12 Internal Gates (ConvergenceJudge)
Used by the autonomous loop, evaluated by `ConvergenceJudge.evaluate()`.

| Gate | Internal name | Condition |
|---|---|---|
| G01 | audit_completed | Phase in (COMPLETE, CONVERGENCE) |
| G02 | p0_zero | open_p0 == 0 |
| G03 | p1_zero | open_p1 == 0 |
| G04 | p2_zero | open_p2 == 0 |
| G05 | verification_complete | verified >= (total - p3 - p4 - p5) |
| G06 | tooling_pass | passed/total tooling = 100% |
| G07 | typecheck_pass | Always true |
| G08 | no_regression | Score not decreased |
| G09 | no_new_findings | Current findings ≤ previous |
| G10 | security_invariants | P0==0 AND P1==0 |
| G11 | no_progress_stall | Not stalled for 3+ cycles |
| G12 | evidence_integrity | Full evidence chain |