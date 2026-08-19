# Risk Register

## Active Risks (Cycle 1)

| ID | Risk | Severity | Likelihood | Impact | Exposure | Detectability | Score | Status |
|---|---|---|---|---|---|---|---|---|
| RSK-001 | Fabricated evidence enters trusted registry undetected | CRITICAL | HIGH (5) | HIGH (5) | HIGH (5) | LOW (4) | 500 | PARTIALLY MITIGATED |
| RSK-002 | Converged=true declares production-ready with failing gates | CRITICAL | HIGH (4) | HIGH (5) | HIGH (5) | LOW (4) | 400 | MITIGATED |
| RSK-003 | Test code permanently mutates user git config | CRITICAL | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED |
| RSK-004 | Undefined function crashes production test scenario | CRITICAL | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED |
| RSK-005 | Zero test files, no test framework | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | HIGH (5) | 500 | OPEN |
| RSK-006 | Sandbox parameters stored but never enforced | HIGH | HIGH (5) | MEDIUM (3) | HIGH (4) | LOW (3) | 180 | PARTIALLY MITIGATED |
| RSK-007 | Worktree creation deletes arbitrary paths without validation | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | MEDIUM (3) | 135 | OPEN |
| RSK-008 | Dynamic script block creation from string interpolation | HIGH | LOW (2) | HIGH (5) | MEDIUM (3) | LOW (2) | 60 | OPEN |
| RSK-009 | README claims uncommitted/unsupported project status | MEDIUM | HIGH (5) | MEDIUM (3) | HIGH (4) | HIGH (5) | 300 | OPEN |
| RSK-010 | Mutation test executes real code injection on host | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN |
| RSK-011 | Evidence canonical format allows hash collision via newline injection | HIGH | LOW (2) | HIGH (5) | LOW (2) | LOW (3) | 60 | OPEN |

## Mitigated Risks

| ID | Risk | Mitigation | Cycle |
|---|---|---|---|
| RSK-002 | Converged=true with failing gates | Added unconditional invariant check in Validate-GateEvidenceIntegrity | 1 |
| RSK-003 | Git config mutation | Removed all git config core.autocrlf mutations from test scenarios | 1 |
| RSK-004 | Undefined Write-TextFile function | Replaced with System.IO.File::WriteAllText | 1 |
| RSK-006 | Sandbox dead parameters | Updated module documentation to note limitations | 1 |

*Updated: Cycle 1, 2026-08-19*