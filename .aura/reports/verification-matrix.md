# Verification Matrix

## Cycle 1

| Command | Status | Exit Code | Notes |
|---|---|---|---|
| Detected tooling | NONE | — | PowerShell project, no package.json/pyproject.toml/Makefile |
| CI workflow | N/A | — | .github/workflows/ci.yml uses inline PS syntax check only |
| Self-test campaigns | NOT RUN | — | Requires -Action flags; not auto-detected by tooling |
| Code review verification | PASS | — | All 8 fixes verified by grep + code inspection |
| grep for $ScriptRoot | PASS | 0 matches | All references replaced |
| grep for core.autocrlf | PASS | 0 matches in git-safety-adversarial | All config mutations removed |
| grep for Write-TextFile in git-safety-adversarial | PASS | 0 matches | Replaced with System.IO.File::WriteAllText |
| Convergence invariant logic | PASS | — | Unconditional gate validation block added after transition check |
| Register-Evidence SHA validation | PASS | — | Regex ^[0-9A-Fa-f]{40}$ + future timestamp rejection |
| $Amend parameter plumbing | PASS | — | Signature updated + pass-through chain complete |
| ForceValidation flow control | PASS | — | Check added in promote-state violation block |
| Sandbox documentation | PASS | — | Header updated with limitations note |

## Tooling Evidence

**Tooling type:** None available
**Reason:** AURA is a PowerShell-only project with no build system manifests. The CI workflow uses inline PowerShell syntax validation. Self-test campaigns (adversarial-campaign, false-convergence-campaign, etc.) require explicit -Action flags.

**Evidence file:** .aura/state/tooling-evidence.json

## Verification Summary

| Cycle | Fixes Verified | Rejected | Deferred | Tooling Pass Rate |
|---|---|---|---|---|
| 1 | 8 | 0 | 0 | N/A (no tooling detected) |

*Updated: Cycle 1, 2026-08-19*