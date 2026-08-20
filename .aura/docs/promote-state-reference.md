# PROMOTE-STATE ACTION — DETAILED REFERENCE

## What It Does

`-Action promote-state` is the **validation gatekeeper** that takes proposed state files written by an AI agent (LLM), validates every transition and claim against strict state-machine rules, and either **commits** validated changes to actual state files or **rejects** them with specific violation details.

```
powershell -NoProfile -ExecutionPolicy Bypass -File "src\engine\run-audit.ps1" -Action promote-state -TargetProject "C:\laraenv\www\aura"
```

---

## The Overall Workflow

```
  [Human]  -Action run        → generates prompt for AI agent
  [AI Agent]                  → reads repo, produces findings, writes proposed-*.json
  [Human]  -Action promote-state  → validates & commits (THIS ACTION)
  [Human]  -Action run        → next cycle
```

> **promote-state MUST run before the next `-Action run`.** The engine blocks new cycles when proposed files exist.

---

## Step-by-Step Breakdown

### Pre-condition: Proposed Files

The action expects these files in `.aura/state/`:

| File | Purpose |
|------|---------|
| `proposed-findings.json` | Findings (new + status updates) the AI wrote |
| `proposed-convergence.json` | Convergence gates + classification the AI claimed |
| `proposed-cycle.json` | Cycle state (audited_file_count, phase, etc.) |

If **none** of these exist → **REJECTED** immediately. Nothing to promote.

---

### [1/4] Finding State Transition Validation

Validates that every finding status change follows the **legal state machine**:

```
OPEN         → IN_PROGRESS, DEFERRED, BLOCKED
IN_PROGRESS  → FIXED, DEFERRED, BLOCKED, OPEN
FIXED        → VERIFYING, OPEN (regression)
VERIFYING    → VERIFIED, REJECTED, FIXED (retry)
VERIFIED     → OPEN (recurrence)
REJECTED     → OPEN, FIXED
DEFERRED     → OPEN
BLOCKED      → OPEN
UNVERIFIED   → OPEN
```

**Strictly forbidden transitions:**
- `OPEN → VERIFIED` — must go through FIXED + VERIFYING
- `OPEN → FIXED` — must go through IN_PROGRESS
- `IN_PROGRESS → VERIFIED` — must go through FIXED + VERIFYING
- `FIXED → VERIFIED` — must go through VERIFYING
- New findings MUST start as `OPEN`

---

### [2/4] Convergence Gate Evidence Validation

Validates 5 categories of gate integrity:

#### a) Gate Flip Evidence
When any gate flips `false → true`, proof is required:
| Gate | Required Evidence |
|------|-------------------|
| `P0_zero` | All P0 findings VERIFIED or DEFERRED |
| `P1_zero` | All P1 findings VERIFIED or DEFERRED |
| `P2_zero` | All P2 findings VERIFIED or DEFERRED |
| `critical_security` | All SECURITY P0-P2 findings VERIFIED |
| `critical_correctness` | All CORRECTNESS P0-P2 findings VERIFIED |
| `data_integrity` | All DATA_INTEGRITY findings VERIFIED |
| `regression` | Regression audit: zero re-appeared findings |
| `verification` | All FIXED findings have verifier evidence (not self-verified) |
| `no_material_new_findings` | 2 consecutive cycles with zero new P0-P3 findings |
| `consecutive_clean_independent_audits` | consecutive_converged_cycles ≥ 2 AND audits_since_last_finding ≥ 2 |
| `module_dependency_integrity` | All required modules exist, loaded, no dependency failures |

#### b) Gate Regression Detection
If any gate flips `true → false` → **REGRESSION VIOLATION** (must have documented finding explaining why)

#### c) Convergence Invariant
If `converged=true` → **ALL 12 gates MUST be true** (checked unconditionally, not just on transition). Violation = **CONVERGENCE INVARIANT VIOLATION**.

#### d) Score Rules
- `overall_score` cannot decrease between cycles (SCORE REGRESSION)
- `overall_score` cannot increase more than 15 points per cycle (SCORE SPIKE)

#### e) Counter Rules
- `consecutive_converged_cycles` cannot decrease (COUNTER REGRESSION)
- `consecutive_converged_cycles` can only increase by 0 or 1 per cycle (COUNTER JUMP)

#### f) Classification Transitions
Only legal paths:
```
NOT_READY           → CONDITIONALLY_READY, HUMAN_BLOCKED
CONDITIONALLY_READY → PRODUCTION_READY, NOT_READY, HUMAN_BLOCKED
PRODUCTION_READY    → NOT_READY, HUMAN_BLOCKED
HUMAN_BLOCKED       → NOT_READY, CONDITIONALLY_READY
```

---

### [2b/4] Gate-Findings Cross-Validation

Checks that **gate values are consistent with actual findings**. If a gate is `true` but corresponding findings are still open, it's a violation:

| Gate | Cross-checked against |
|------|----------------------|
| `P0_zero` | No OPEN/IN_PROGRESS/FIXED/VERIFYING P0 findings |
| `P1_zero` | No OPEN/IN_PROGRESS/FIXED/VERIFYING P1 findings |
| `P2_zero` | No OPEN/IN_PROGRESS/FIXED/VERIFYING P2 findings |
| `critical_security` | No non-VERIFIED SECURITY P0-P2 findings |
| `critical_correctness` | No non-VERIFIED CORRECTNESS P0-P2 findings |
| `data_integrity` | No non-VERIFIED DATA_INTEGRITY findings |
| `no_material_new_findings` | No new P0-P3 findings added this cycle |

---

### [3/4] Tooling Evidence Validation

If any findings are proposed `VERIFIED`, the engine checks:

1. `tooling-evidence.json` **must exist** (orchestrator-captured, not LLM-claimed)
2. All tooling commands in the evidence **must have passed**
3. If commands failed → WARNING (non-blocking unless combined with other violations)

> **LLM-claimed test results without orchestrator exit codes are REJECTED.**

---

### [4/4] Audit Scope Validation

Checks the `audited_file_count` in proposed-cycle against actual git-tracked files:
- < 50% coverage → **SCOPE WARNING** (convergence may be invalid)
- > 500 tracked files total → **SCALE WARNING** (full audit unlikely in single context)

---

### [5/6] Module Dependency Integrity

This is an **orchestrator-only check** (the LLM cannot influence it):

| Check | Effect |
|-------|--------|
| Required module failed to load | `module_dependency_integrity` gate **forced to FALSE** |
| Required module failed + `converged=true` | `converged` **forced to FALSE** |
| Required module failed + `PRODUCTION_READY` | Classification **downgraded to NOT_READY** |

The engine inspects whether real `.ps1` module files in `src/modules/` actually loaded at startup.

---

## Final Decision

### If Violations Exist (and no `-ForceValidation`):

```
=== PROMOTION REJECTED ===
[X] violation(s) found:
  FINDING: F2: OPEN -> VERIFIED. Must pass through FIXED and VERIFYING
  GATE: GATE FLIP: P0_zero : false -> true. Evidence required: All P0 findings must be VERIFIED...
  ...

Fix violations and re-run promote-state. Proposed files preserved at:
  .aura/state/proposed-findings.json
  .aura/state/proposed-convergence.json
  .aura/state/proposed-cycle.json
  Use -ForceValidation to bypass (UNSAFE).
```

**No state is modified.** Proposed files remain on disk for the AI agent to fix.

### If All Validations Pass:

```
=== PROMOTION ACCEPTED ===
All validations passed. Committing proposed state...
  [COMMITTED] .aura/state/findings.json
  [COMMITTED] .aura/state/convergence.json
  [COMMITTED] .aura/state/cycle.json

[SUCCESS] State promoted: findings.json, convergence.json, cycle.json
```

**What gets committed:**
1. `proposed-findings.json` → overwrites `findings.json`
2. `proposed-convergence.json` → overwrites `convergence.json`
3. `proposed-cycle.json` → overwrites `cycle.json`
4. Proposed files archived with timestamp to `.aura/archive/`
5. `cycles_without_progress` updated (reset to 0 if new P0-P3 findings, incremented otherwise)
6. If `cycles_without_progress >= max_cycles_without_progress` → status set to `STALLED`

---

## Force Validation (Unsafe Override)

```
powershell ... -Action promote-state -ForceValidation
```

Bypasses **all violations** and promotes regardless. Use only when:
- You understand the state machine rules being violated
- You intentionally want to accept invalid state
- The LLM made a legitimate claim but the validator is being overly strict

Violations are still logged as `[BYPASSED]`.

---

## Common Errors & Fixes

| Error | Root Cause | Fix |
|-------|-----------|-----|
| `OPEN -> VERIFIED must pass through FIXED and VERIFYING` | AI skipped intermediate states | Ask AI to follow state machine transitions |
| `GATE FLIP: P0_zero requires evidence` | AI set gate true without verifying P0 findings | AI must set P0 findings to VERIFIED first |
| `SCORE REGRESSION: score decreased` | AI lowered the overall score | Score can only stay same or increase |
| `COUNTER JUMP: consecutive_converged_cycles +2` | AI incremented counter by more than 1 | Counter max +1 per cycle |
| `no_material_new_findings is TRUE but new P0-P3 findings created` | AI set gate true while adding new findings | Either remove new findings or keep gate false |
| `TOOLING: VERIFIED findings but tooling-evidence.json missing` | AI claimed verification without running tools | Run `-Action run-tooling` before promoting |
| `MODULE_INTEGRITY: Required modules failed` | `.ps1` module files missing in `src/modules/` | Create the missing module files |
| `CONVERGENCE INVARIANT: converged=true but gates failing` | AI set converged without all 12 gates true | Fix gates or set converged=false |

---

## Files Involved

| File | Role |
|------|------|
| `.aura/state/proposed-findings.json` | **Input** — AI's proposed finding changes |
| `.aura/state/proposed-convergence.json` | **Input** — AI's proposed convergence state |
| `.aura/state/proposed-cycle.json` | **Input** — AI's proposed cycle state |
| `.aura/state/tooling-evidence.json` | **Input** — Orchestrator-captured test results |
| `.aura/state/findings.json` | **Output** — Promoted findings (overwritten) |
| `.aura/state/convergence.json` | **Output** — Promoted convergence (overwritten) |
| `.aura/state/cycle.json` | **Output** — Promoted cycle state (overwritten) |
| `.aura/archive/proposed-findings-{timestamp}.json` | **Audit trail** — Archived before delete |
| `.aura/archive/proposed-convergence-{timestamp}.json` | **Audit trail** — Archived before delete |
| `.aura/archive/proposed-cycle-{timestamp}.json` | **Audit trail** — Archived before delete |

---

## Related Actions

| Action | When to Use |
|--------|-------------|
| `-Action run` | Start new cycle (generates prompt for AI) |
| `-Action validate-state` | Check state integrity without promoting |
| `-Action run-tooling` | Execute project test/lint/build before verification |
| `-Action reset` | Full engine reset (archive + reinitialize) |
| `-Action status` | View convergence status, gates, open findings |
| `-Action push -Approve` | Commit engine files to git after promotion |