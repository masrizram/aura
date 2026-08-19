# Risk Register

## Active Risks (Cycle 4)

| ID | Risk | Severity | Likelihood | Impact | Exposure | Detectability | Score | Status |
|---|---|---|---|---|---|---|---|---|
| RSK-001 | Fabricated evidence enters trusted registry undetected | CRITICAL | HIGH (5) | HIGH (5) | HIGH (5) | LOW (3) | 375 | MITIGATED |
| RSK-002 | Converged=true declares production-ready with failing gates | CRITICAL | HIGH (4) | HIGH (5) | HIGH (5) | LOW (3) | 300 | MITIGATED |
| RSK-003 | Test code permanently mutates user git config | CRITICAL | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED |
| RSK-004 | Undefined function crashes production test scenario | CRITICAL | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED |
| RSK-005 | Zero test files, no test framework | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | HIGH (5) | 500 | OPEN |
| RSK-006 | Sandbox parameters stored but never enforced | HIGH | HIGH (5) | MEDIUM (3) | HIGH (4) | LOW (3) | 180 | PARTIALLY MITIGATED |
| RSK-007 | Worktree creation deletes arbitrary paths without validation | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | MEDIUM (2) | 90 | MITIGATED |
| RSK-008 | Dynamic script block creation from string interpolation | HIGH | LOW (2) | HIGH (5) | MEDIUM (3) | LOW (2) | 60 | OPEN — severity upgraded (P1 in C3-005) |
| RSK-009 | README claims uncommitted/unsupported project status | MEDIUM | HIGH (5) | MEDIUM (3) | HIGH (4) | HIGH (5) | 300 | MITIGATED — C3 fix committed |
| RSK-010 | Mutation test executes real code injection on host | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN |
| RSK-011 | Evidence canonical format allows hash collision via newline injection | HIGH | LOW (2) | HIGH (5) | LOW (2) | LOW (2) | 40 | MITIGATED |
| RSK-012 | Convergence gate count inconsistent (10/11/12) across docs | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | LOW (3) | 300 | MITIGATED |
| RSK-013 | Convergence judge missing 2 of 12 required gates | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | LOW (3) | 300 | MITIGATED |
| RSK-014 | BI-STATE-004 invariant perpetually fails (11 vs 12) | MEDIUM | HIGH (5) | MEDIUM (3) | MEDIUM (3) | HIGH (4) | 180 | MITIGATED |
| RSK-015 | Agent definitions unaware of IN_PROGRESS/VERIFYING states | HIGH | HIGH (5) | HIGH (5) | MEDIUM (3) | MEDIUM (3) | 225 | MITIGATED |
| RSK-016 | All relative config paths resolve to nonexistent dirs | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | LOW (2) | 90 | OPEN |
| RSK-017 | CI state machine tests are placebo stubs | MEDIUM | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | HIGH (5) | 135 | OPEN |
| RSK-018 | Two competing scoring systems (severity weight vs risk score) | MEDIUM | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | 81 | OPEN |
| RSK-019 | Build-PSCopy shallow copy corrupts FCX attack state | HIGH | HIGH (5) | MEDIUM (3) | MEDIUM (3) | HIGH (4) | 180 | MITIGATED — C3 deep copy fix |
| RSK-020 | Tautological validation in validate-state (compares against itself) | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | HIGH (4) | 180 | OPEN (C3-002) |
| RSK-021 | Always-return-DETECTED fallback in all mutation tests | HIGH | HIGH (5) | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | 135 | OPEN (C3-004) |
| RSK-022 | Non-atomic three-phase state promotion | MEDIUM | MEDIUM (3) | HIGH (5) | LOW (2) | MEDIUM (3) | 90 | OPEN (C3-010) |
| RSK-023 | Evidence registry pollution by test campaigns | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN (C3-011) |
| RSK-024 | Function name regex misses hyphenated PS functions | LOW | HIGH (5) | LOW (2) | LOW (2) | HIGH (5) | 100 | MITIGATED — C3 regex fix |
| RSK-025 | O(n) array allocation in line number calculation | LOW | HIGH (5) | LOW (2) | LOW (2) | HIGH (5) | 100 | MITIGATED — C3 + C4 O(1) fix (all modules) |
| RSK-026 | GS-01 git-safety test operates on wrong file paths | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN (C3-007) |
| RSK-027 | BI-STATE-007 invariant checks nonexistent config path | MEDIUM | HIGH (5) | MEDIUM (3) | LOW (2) | HIGH (4) | 120 | MITIGATED — C4 fix applied |
| RSK-028 | BI-STATE-008 invariant checks bootstrap proxy not engine | MEDIUM | HIGH (5) | MEDIUM (3) | LOW (2) | HIGH (4) | 120 | MITIGATED — C4 fix applied |

*Updated: Cycle 4, 2026-08-20*