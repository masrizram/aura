# Remediation Log

## Cycle 2 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C2-001 | P1 | convergence-judge.md | Only 10/12 gates in mandate; JSON missing 1 gate | Added consecutive_clean + module_dependency_integrity to mandate and JSON schema | LOW |
| AUDIT-C2-002 | P1 | cycle.md:78 | States "11 gates" but system has 12 | Changed to "12 gates" | LOW |
| AUDIT-C2-003 | P1 | business-invariants.ps1:53 | BI-STATE-004 expects 11 gates | Updated expected_count to 12, name/description updated | LOW |
| AUDIT-C2-004 | P1 | master.md:850-860 | Convergence rule omits module_dependency_integrity | Added gate to convergence rule | LOW |
| AUDIT-C2-005 | P1 | evidence-integrity.ps1:98 | Canonical hash missing 3 fields; newline injection | Added COMMAND_ARGS, ARTIFACT_PATH, ARTIFACT_HASH fields; newline escaping on all text fields | LOW |
| AUDIT-C2-012 | P2 | .gitignore:3-4 | Comment references wrong config path | Updated to reference config/aura.json | LOW |
| AUDIT-C2-013 | P2 | .gitmessage:7 | Typo "semi-colons" | Fixed to "semicolons" | LOW |
| AUDIT-C2-014 | P2 | adversarial-auditor.md:15 | MITIGATED status not in state machine | Changed to use DEFERRED with warning about MITIGATED | LOW |
| AUDIT-C1-021 | P2 | evidence-integrity.ps1:98 | Hash collision via newline injection | Newline escaping + full field coverage (combined with C2-005) | LOW |

## Cycle 1 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C1-001 | P0 | run-audit.ps1:2490 | Undefined $ScriptRoot variable | Replaced $ScriptRoot -> $EngineRoot/$RepoRoot | LOW |
| AUDIT-C1-002 | P0 | run-audit.ps1:655 | Convergence invariant missing | Added unconditional gate validation block | LOW |
| AUDIT-C1-003 | P0 | evidence-integrity.ps1:175 | Evidence fabricated undetected | Added SHA format + future timestamp validation | LOW |
| AUDIT-C1-004 | P0 | git-safety-adversarial.ps1:103 | Git config mutation | Removed 3x core.autocrlf mutations | LOW |
| AUDIT-C1-005 | P0 | git-safety-adversarial.ps1:74 | Undefined Write-TextFile | Replaced with System.IO.File::WriteAllText | LOW |
| AUDIT-C1-006 | P0 | run-audit.ps1:1390 | $Amend dead parameter | Added $Amend to function signature + pass-through | LOW |
| AUDIT-C1-008 | P1 | run-audit.ps1:26 | ForceValidation bypass plumbing | Added ForceValidation check in promote-state | LOW |
| AUDIT-C1-009 | P1 | sandbox.ps1:11 | Dead sandbox parameters | Updated module header documentation | LOW |

## Uncommitted Working Tree Fixes (Cycle 2)

| Finding ID | Severity | Location | Problem | Fix | Status |
|---|---|---|---|---|---|
| AUDIT-C1-011 | P1 | git-safety.ps1:69 | Worktree path safety | Path prefix validation + dangerous path blacklist | In working tree |
| AUDIT-C1-013 | P2 | failure-recovery.ps1:614 | Corrupt JSON to live file | Backup-before-corrupt + restore-after-test | In working tree |
| AUDIT-C1-022 | P2 | run-audit.ps1:1718 | Git fetch no exit check | $LASTEXITCODE check after fetch | In working tree |
| AUDIT-C1-023 | P2 | business-invariants.ps1:250 | No-op invariant rules | Implemented monotonic + audit trail checks | In working tree |

## Agent Documentation Fixes (Cycle 2)

| Agent File | Change |
|---|---|
| src/agents/remediator.md | Added IN_PROGRESS state transition (step 2), FIXED handoff instruction |
| src/agents/verifier.md | Added VERIFYING state transition (step 1), -Action run-tooling reference |
| src/agents/adversarial-auditor.md | Changed MITIGATED to DEFERRED; added warning |
| src/agents/convergence-judge.md | Added all 12 gates; added module_dependency_integrity to JSON schema |

## Changes Summary (Cycle 2)

| File | Change | Reason |
|---|---|---|
| src/modules/business-invariants.ps1:53 | expected_count 11->12 | BI-STATE-004 invariant gate count fix |
| src/agents/convergence-judge.md | +2 gates in mandate, +1 gate in JSON | Missing gates bug |
| .aura/docs/cycle.md:78 | "11 gates" -> "12 gates" | Off-by-one error |
| .aura/docs/master.md:850-860 | +module_dependency_integrity gate | Missing gate in convergence rule |
| src/modules/evidence-integrity.ps1:98-107 | +3 fields + newline escaping | Hash collision + completeness |
| src/agents/remediator.md | +IN_PROGRESS state, +FIXED handoff | State machine awareness |
| src/agents/verifier.md | +VERIFYING state, +run-tooling ref | State machine awareness |
| src/agents/adversarial-auditor.md | MITIGATED->DEFERRED | Invalid state machine status |
| .gitignore:3-4 | config.json -> config/aura.json | Misleading comment |
| .gitmessage:7 | semi-colons -> semicolons | Typo fix |

*Updated: Cycle 2, 2026-08-19*