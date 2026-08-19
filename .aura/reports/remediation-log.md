# Remediation Log

## Cycle 1 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C1-001 | P0 | run-audit.ps1:2490 | Undefined $ScriptRoot variable | Replaced $ScriptRoot → $EngineRoot/$RepoRoot | LOW |
| AUDIT-C1-002 | P0 | run-audit.ps1:655 | Convergence invariant missing | Added unconditional gate validation block | LOW |
| AUDIT-C1-003 | P0 | evidence-integrity.ps1:175 | Evidence fabricated undetected | Added SHA format + future timestamp validation | LOW |
| AUDIT-C1-004 | P0 | git-safety-adversarial.ps1:103 | Git config mutation | Removed 3x core.autocrlf mutations | LOW |
| AUDIT-C1-005 | P0 | git-safety-adversarial.ps1:74 | Undefined Write-TextFile | Replaced with System.IO.File::WriteAllText | LOW |
| AUDIT-C1-006 | P0 | run-audit.ps1:1390 | $Amend dead parameter | Added $Amend to function signature + pass-through | LOW |
| AUDIT-C1-008 | P1 | run-audit.ps1:26 | ForceValidation bypass plumbing | Added ForceValidation check in promote-state | LOW |
| AUDIT-C1-009 | P1 | sandbox.ps1:11 | Dead sandbox parameters | Updated module header documentation | LOW |

### Changes Summary

| File | Change | Reason |
|---|---|---|
| src/engine/run-audit.ps1:2490,2495,2521 | $ScriptRoot → $EngineRoot/$EngineRoot/$EngineRoot | Undefined variable bug |
| src/engine/run-audit.ps1:672-686 | Added convergence invariant check | P0: converged=true could bypass gate validation |
| src/engine/run-audit.ps1:1245 | Added $Amend parameter to Invoke-EnginePush | P0: dead unreachable code |
| src/engine/run-audit.ps1:1806 | Passed -Amend:$Amend to Invoke-EnginePush | P0: amend plumbing |
| src/engine/run-audit.ps1:2261-2265 | Added ForceValidation bypass logic | P1: misleading documentation |
| src/modules/git-safety-adversarial.ps1:103,409,463 | Removed git config core.autocrlf true | P0: permanent user config mutation |
| src/modules/git-safety-adversarial.ps1:74 | Write-TextFile → [System.IO.File]::WriteAllText | P0: undefined function crash |
| src/modules/evidence-integrity.ps1:185-197 | Added SHA format + future timestamp validation | P0: fabricated evidence accepted |
| src/modules/sandbox.ps1:1-8 | Updated header documentation | P1: false security claims |

*Updated: Cycle 1, 2026-08-19*