# Verification Matrix

## Cycle 3

| Command | Status | Exit Code | Notes |
|---|---|---|---|
| PowerShell syntax check (17 files) | PASS | 0 | All 17 *.ps1 files pass PSParser tokenization — 0 errors |
| Code review verification | PASS | — | All 8 fixes verified by code inspection + grep |
| grep for $ScriptRoot in run-audit.ps1 | PASS | 0 matches | All references replaced |
| grep for core.autocrlf in git-safety-adversarial.ps1 | PASS | 0 matches | All config mutations removed |
| grep for Write-TextFile in git-safety-adversarial.ps1 | PASS | 0 matches | Replaced with System.IO.File::WriteAllText |
| Convergence invariant logic | PASS | — | Unconditional gate validation block present after transition check |
| Register-Evidence SHA + timestamp validation | PASS | — | Regex ^[0-9A-Fa-f]{40}$ + future timestamp rejection |
| $Amend parameter plumbing | PASS | — | Signature updated + pass-through chain complete |
| ForceValidation flow control | PASS | — | Check added in promote-state violation block |
| Sandbox documentation | PASS | — | Header updated with limitations note |
| Build-PSCopy deep copy (C3-001) | PASS | — | JSON round-trip deep copy replaces shallow NoteProperty copy |
| MUT-02 empty if-block (C3-003) | PASS | — | SCORE SPIKE violation message added in mock function |
| Test-FindingTransitionLegality (C2-007) | PASS | — | $hasVerification/$hasImplementFix conditional null-safe guards |
| Function name regex (C2-011) | PASS | — | Pattern changed to [\w\-]+ to match hyphenated names |
| O(n) line number calculation (C2-015) | PASS | — | All 6 instances use -split .Count without array allocation |
| EvidenceRegistryFile init tracking (C1-010) | PASS | — | $_evidenceEngineInitialized flag added |
| README gate map + cycle count (C2-010, C1-015) | PASS | — | Gate map shows 12 symbols; cycle/score/opens updated |

## Cycle 2

| Command | Status | Exit Code | Notes |
|---|---|---|---|
| PowerShell syntax check (17 files) | PASS | 0 | All *.ps1 files syntax-valid |
| CI workflow | N/A | — | Placeholder stubs only |

## Cycle 1

| Command | Status | Exit Code | Notes |
|---|---|---|---|
| Detected tooling | NONE | — | PowerShell project, no package.json/pyproject.toml/Makefile |
| CI workflow | N/A | — | .github/workflows/ci.yml uses inline PS syntax check only |

## Tooling Evidence

**Tooling type:** PowerShell PSParser syntax validation
**Reason:** AURA is a PowerShell-only project with no build system manifests. The CI workflow uses inline PowerShell syntax validation. Self-test campaigns require explicit -Action flags.

**Evidence file:** .aura/state/tooling-evidence.json

## Verification Summary

| Cycle | Fixes Verified | Rejected | Deferred | Tooling Pass Rate |
|---|---|---|---|---|
| 1 | 8 | 0 | 0 | N/A (no tooling detected) |
| 2 | 9 | 0 | 0 | 17/17 syntax pass |
| 3 | 8 | 0 | 0 | 17/17 syntax pass |

*Updated: Cycle 3, 2026-08-19*