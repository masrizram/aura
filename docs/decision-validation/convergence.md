# Convergence Decision

> **Two independent 12-gate systems exist.** Both are documented here; neither validates the other's choice at runtime.

## System A — user-facing 12 gates (state_machine)

GATE_NAMES (state_machine.py:50-63):

```
P0_zero, P1_zero, P2_zero,
critical_security, critical_correctness, data_integrity,
regression, verification, no_material_new_findings,
limitations_documented, consecutive_clean_independent_audits,
module_dependency_integrity
```

### evaluate_all_gates (state_machine.py:370-435) — as invoked by engine

- ACTIVE statuses for P0/P1/P2 gates: {OPEN, IN_PROGRESS, FIXED, VERIFYING, BLOCKED}.
- RESOLVED statuses (used by critical_* and data_integrity): {VERIFIED, DEFERRED, WAIVED, ACCEPTED_RISK, OUT_OF_SCOPE}.
- `verification` passes when NO finding is in FIXED.
- `no_material_new_findings` compares current vs previous via `_finding_key` (id OR finding_id) across P0-P3.
- `consecutive_clean_independent_audits`: `consecutive_converged_cycles >= 2 AND audits_since_finding >= 2`.
- `limitations_documented`: supplied by engine's LIMITATIONS.md validator.
- `module_dependency_integrity`: supplied by `_check_module_integrity`.
- `regression`: `regression_pass` from `_phase_regression` (resolved ∩ current = ∅).

### Engine subclass override (engine.py:738-754)

After the base evaluation, the engine **overrides** `P2_zero` and `critical_security`
by recomputing with `is_blocking_for_gate(rule, gate)` — only CODE_DEFECT findings count.
This means a P2 finding whose rule classifies as CODE_QUALITY (e.g. `PY-TYPE-IGNORE`)
does not block `P2_zero`, even though the base gate evaluator said otherwise.

### Final classification (engine.py:764-772)

```
if all 12 gates pass                      → PRODUCTION_READY, converged=True
elif open CODE_DEFECT P0 == 0 AND P1 == 0 → CONDITIONALLY_READY, converged=False
else                                      → NOT_READY, converged=False
```

**Investigation-verified truth table (live evaluation 2026-08-22):**

| scenario | gates | score | blended | classification |
|---|---|---|---|---|
| no findings, cons=2, audits=2, lim ok | 12 | 100 | 100 | PRODUCTION_READY |
| no findings, cons=0 | 11 | 95 | 95 | CONDITIONALLY_READY |
| no findings, cons=2, no LIMITATIONS.md | 11 | 95 | 95 | CONDITIONALLY_READY |
| 1× P0 OPEN (SECURITY, CODE_DEFECT) | 10 | 75 | ~89 (blended) | NOT_READY |
| 1× P1 OPEN (SECURITY) | 10 | 82 | ~89 | NOT_READY |
| 1× P2 OPEN (CORRECTNESS, CODE_DEFECT) | 10 | 87 | ~92 | **CONDITIONALLY_READY** |
| 5× P2 OPEN (CODE_DEFECT) | 10 | — | — | CONDITIONALLY_READY |
| 1× P2 OPEN (CODE_QUALITY rule) | 11 | — | — | CONDITIONALLY_READY |
| 1× P3 OPEN | 12 | 99 | 99 | **PRODUCTION_READY** |
| 5× P3 OPEN | 12 | 95 | 95 | PRODUCTION_READY |

Reality captured as-is: P3-P5 and even P2 findings do not force NOT_READY;
only P0/P1 CODE_DEFECTs do. Score is the only pressure against large P3 counts.

## System B — internal judge gates G01–G12 (convergence.ConvergenceJudge)

| Gate | Input | PASS when |
|---|---|---|
| G01_audit_completed | `phase` | in {COMPLETE, CONVERGENCE} |
| G02_p0_zero | `open_p0` | == 0 |
| G03_p1_zero | `open_p1` | == 0 |
| G04_p2_zero | `open_p2` | == 0 |
| G05_verification_complete | `verified_count`, `findings_count`, `open_p3-5` | verified >= total − open(P3,P4,P5) |
| G06_tooling_pass | `tooling_passed` "x/y" | x == y |
| G07_typecheck_pass | (derived from G06; no separate signal) | == G06 — documented as not-independent |
| G08_no_regression | `overall_score` ≥ previous | non-decreasing |
| G09_no_new_findings | `findings_count` ≤ previous | non-increasing |
| G10_security_invariants | `open_p0`, `open_p1` | both == 0 |
| G11_no_progress_stall | recent scores | not (identical for 3+ AND score<90) |
| G12_evidence_integrity | `evidence_complete` flag | True |

Decides: all pass → PRODUCTION_READY + converged; elif G01+G06+G10 → CONDITIONALLY_READY; else NOT_READY.

### Divergence proof (measured 2026-08-22)

State: `{cycle_number:2, phase:'CONVERGENCE', overall_score:100, findings_count:0, open_p0=0, open_p1=0, open_p2=0, verified_count:0, tooling_passed:'0/0', evidence_complete:True}`.

- System B (judge) → **converged=True** (no LIMITATIONS.md input signal exists).
- System A (engine) on the same repo without LIMITATIONS.md → **limitations_documented=False ⇒ CONDITIONALLY_READY**.

The two systems *can and do* disagree on the same underlying state. This is documented in
LIMITATIONS.md (§3 "Dual gate systems") and is *accepted behaviour* — the autonomous loop
(`remediation.py:299-331`) only invokes the judge on a cycle the ENGINE already declared
PRODUCTION_READY, so the judge cannot independently converge a repo from zero.

## Counter rules (upsert_convergence, engine.py:781-783)
- `consecutive_converged_cycles = prev + (1 if converged OR classification == CONDITIONALLY_READY else 0)`.
- `audits_since_last_finding = prev + 1` (always).
- `state_machine.validate_gate_evidence_integrity` would REJECT counter rewind/jump>1 — but that validator is not re-invoked by the engine on this write path (opt-in).
