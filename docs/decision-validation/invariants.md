# Invariants — AURA v3.5

> **Verified from:** `src/aura/state_machine.py:183-274`, `src/aura/engine.py:203-405`

## State Machine Invariants

### 1. Finding Transition Invariants

**INV-F1:** New findings MUST start as OPEN.
```python
if existing is None and proposed.status != "OPEN":
    → VIOLATION
```
**Source:** `state_machine.py:134-140`

**INV-F2:** Forbidden transitions MUST be rejected.
```
OPEN → VERIFIED    ❌ "Must pass through FIXED and VERIFYING"
OPEN → FIXED       ❌ "Must pass through IN_PROGRESS"
IN_PROGRESS → VERIFIED ❌ "Must pass through FIXED and VERIFYING"
FIXED → VERIFIED   ❌ "Must pass through VERIFYING"
VERIFYING → CLOSED ❌ "CLOSED is not a valid status"
```
**Source:** `state_machine.py:40-46`

**INV-F3:** Terminal statuses (WAIVED, ACCEPTED_RISK, OUT_OF_SCOPE) have NO outgoing transitions.
**Source:** `state_machine.py:25-27`

### 2. Gate Invariants

**INV-G1:** Gate flip false→true MUST have documented evidence.
```python
if not old_value and new_value:
    → GATE FLIP violation (requires evidence)
```
**Source:** `state_machine.py:201-206`

**INV-G2:** Gate regression true→false MUST have documented finding.
```python
if old_value and not new_value:
    → GATE REGRESSION violation
```
**Source:** `state_machine.py:208-212`

**INV-G3:** Convergence false→true REQUIRES ALL 12 gates to independently pass.
```python
if not old_converged and new_converged:
    if any gate is false:
        → CONVERGENCE BLOCKED
```
**Source:** `state_machine.py:218-230`

**INV-G4:** When converged=true, ALL gates MUST be true.
```python
if new_converged and any gate is false:
    → CONVERGENCE INVARIANT VIOLATION
```
**Source:** `state_machine.py:232-241`

### 3. Score Invariants — REMOVED (v3.5.x, IMP-03)

**INV-S1 / INV-S2 (score monotonicity + spike cap) were removed.** Rationale:

- A cycle that **discovers new real findings** legitimately *lowers* the score.
  Treating that as a "SCORE REGRESSION" violation would reward hiding findings —
  the opposite of the engine's purpose.
- A large remediation cycle can legitimately jump more than +15 points.
- The validator was never invoked by the engine at runtime, so the invariant
  existed only on paper — documentation debt masquerading as a control.

Score changes (up or down) are **not** integrity violations. The genuine
integrity controls are the counter invariants (INV-C1/C2) and the convergence
gate invariants (INV-G1..G4), which are preserved and regression-tested in
`tests/test_state_machine.py::TestValidateGateIntegrity` and
`tests/test_architecture_improvements.py`.

### 4. Counter Invariants

**INV-C1:** `consecutive_converged_cycles` MUST NOT decrease.
```python
if new_consecutive < old_consecutive:
    → COUNTER REGRESSION
```
**Source:** `state_machine.py:262-266`

**INV-C2:** `consecutive_converged_cycles` MUST NOT increase by more than 1 per cycle.
```python
if new_consecutive > old_consecutive + 1:
    → COUNTER JUMP
```
**Source:** `state_machine.py:267-272`

### 5. Correlation Invariants

**INV-CORR1:** `combined_raw - intra_dupes - cross_overlap = unique`
```python
total_duplicates = total_raw - total_unique
# Verified: total_raw = primary_count + adv_count
# total_unique after global dedup
```
**Source:** `engine.py:317-319`

**INV-CORR2:** `primary_dupes + adversarial_dupes = intra_total`
```
intra_total = intra_primary_dupes + intra_adv_dupes
```
**Source:** `engine.py:320`

**INV-CORR3:** Ancillary findings are NOT subject to the correlation dedup pipeline — they are appended separately to prevent double-counting.
**Source:** `engine.py:337-376` (note the comment at line 373: "prevents double-counting in lineage (36+4=41 bug)")

### 6. Occurrence Arithmetic Verification

The engine explicitly guards against the "36+4≠41" class of arithmetic errors in its correlation phase. The lineage string (`engine.py:399-404`) traces every number:

```
Primary: 36 + Adversarial: 4 = 40 combined
  Intra-dupes: primary=2 + adversarial=1 = 3
  Cross-overlap: 2
  Total removed: 5 → 35 unique
```

The invariant `36 + 4 = 40` and `40 - 5 = 35` can be independently verified from the raw data using the `_norm_key()` function and dedup sets.

## Architectural Note: Two Parallel Gate Systems

There are TWO 12-gate systems that are SEPARATE but CORRELATED:

1. **User-facing gates** (`state_machine.py:50-63`): `P0_zero`, `P1_zero`, `P2_zero`, `critical_security`, etc. Displayed in CLI. Stored in `gates` table.

2. **Internal gates** (`convergence.py:120-133`): `G01_audit_completed` through `G12_evidence_integrity`. Used by `ConvergenceJudge` for autonomous loop decisions.

These are NOT the same gate. A finding that passes user gates may fail judge gates and vice versa. The convergence judge is notably stricter — it does NOT have the subclass-aware override that the engine applies to P2_zero and critical_security.

**This is NOT a defect** — the two systems serve different purposes:
- Engine gates: Give users actionable information about what needs fixing
- Judge gates: Prove convergence integrity for the autonomous loop