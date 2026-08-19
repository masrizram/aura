# Risk Register

## Active Risks (Cycle 2)

| ID | Risk | Severity | Likelihood | Impact | Exposure | Detectability | Score | Status |
|---|---|---|---|---|---|---|---|---|
| RSK-001 | Fabricated evidence enters trusted registry undetected | CRITICAL | HIGH (5) | HIGH (5) | HIGH (5) | LOW (3) | 375 | MITIGATED — SHA validation + timestamp check + hash field completeness |
| RSK-002 | Converged=true declares production-ready with failing gates | CRITICAL | HIGH (4) | HIGH (5) | HIGH (5) | LOW (3) | 300 | MITIGATED — unconditional invariant check |
| RSK-003 | Test code permanently mutates user git config | CRITICAL | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED |
| RSK-004 | Undefined function crashes production test scenario | CRITICAL | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED |
| RSK-005 | Zero test files, no test framework | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | HIGH (5) | 500 | OPEN |
| RSK-006 | Sandbox parameters stored but never enforced | HIGH | HIGH (5) | MEDIUM (3) | HIGH (4) | LOW (3) | 180 | PARTIALLY MITIGATED |
| RSK-007 | Worktree creation deletes arbitrary paths without validation | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | MEDIUM (2) | 90 | MITIGATED — path prefix validation + dangerous path blacklist added |
| RSK-008 | Dynamic script block creation from string interpolation | HIGH | LOW (2) | HIGH (5) | MEDIUM (3) | LOW (2) | 60 | OPEN |
| RSK-009 | README claims uncommitted/unsupported project status | MEDIUM | HIGH (5) | MEDIUM (3) | HIGH (4) | HIGH (5) | 300 | OPEN |
| RSK-010 | Mutation test executes real code injection on host | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN |
| RSK-011 | Evidence canonical format allows hash collision via newline injection | HIGH | LOW (2) | HIGH (5) | LOW (2) | LOW (2) | 40 | MITIGATED — newline escaping + full field coverage |
| RSK-012 | Convergence gate count inconsistent (10/11/12) across docs | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | LOW (3) | 300 | MITIGATED — all 4 locations updated to 12 |
| RSK-013 | Convergence judge missing 2 of 12 required gates | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | LOW (3) | 300 | MITIGATED — convergence-judge.md updated |
| RSK-014 | BI-STATE-004 invariant perpetually fails (11 vs 12) | MEDIUM | HIGH (5) | MEDIUM (3) | MEDIUM (3) | HIGH (4) | 180 | MITIGATED — expected_count updated to 12 |
| RSK-015 | Agent definitions unaware of IN_PROGRESS/VERIFYING states | HIGH | HIGH (5) | HIGH (5) | MEDIUM (3) | MEDIUM (3) | 225 | MITIGATED — remediator/verifier docs updated |
| RSK-016 | All relative config paths resolve to nonexistent dirs | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | LOW (2) | 90 | OPEN — documentation gap; engine handles at runtime |
| RSK-017 | CI state machine tests are placebo stubs | MEDIUM | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | HIGH (5) | 135 | OPEN |
| RSK-018 | Two competing scoring systems (severity weight vs risk score) | MEDIUM | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | 81 | OPEN |

## Mitigated Risks

| ID | Risk | Mitigation | Cycle |
|---|---|---|---|
| RSK-002 | Converged=true with failing gates | Added unconditional invariant check in Validate-GateEvidenceIntegrity | 1 |
| RSK-003 | Git config mutation | Removed all git config core.autocrlf mutations from test scenarios | 1 |
| RSK-004 | Undefined Write-TextFile function | Replaced with System.IO.File::WriteAllText | 1 |
| RSK-006 | Sandbox dead parameters | Updated module documentation to note limitations | 1 |
| RSK-007 | Worktree path deletion | Added path prefix validation + dangerous path blacklist | 2 |
| RSK-011 | Evidence hash collision | Newline escaping + full 11-field canonical content | 2 |
| RSK-012 | Gate count inconsistency | All 4 documentation locations updated to 12 gates | 2 |
| RSK-013 | Convergence judge missing gates | Agent mandate + JSON schema updated for all 12 gates | 2 |
| RSK-014 | BI-STATE-004 invariant failure | expected_count updated from 11 to 12 | 2 |
| RSK-015 | Agent state machine awareness | remediator/verifier docs updated + adversarial-auditor MITIGATED->DEFERRED | 2 |

*Updated: Cycle 2, 2026-08-19*