# Risk Register

## Active Risks (Cycle 8)

| ID | Risk | Severity | Likelihood | Impact | Exposure | Detectability | Score | Status |
|---|---|---|---|---|---|---|---|---|
| RSK-001 | Fabricated evidence enters trusted registry undetected | CRITICAL | HIGH (5) | HIGH (5) | HIGH (5) | LOW (3) | 375 | MITIGATED |
| RSK-002 | Converged=true declares production-ready with failing gates | CRITICAL | HIGH (4) | HIGH (5) | HIGH (5) | LOW (3) | 300 | MITIGATED |
| RSK-005 | Zero test files, no test framework | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | HIGH (5) | 500 | OPEN |
| RSK-008 | Dynamic script block creation from string interpolation | HIGH | LOW (2) | HIGH (5) | MEDIUM (3) | LOW (2) | 60 | OPEN |
| RSK-010 | Mutation test executes real code injection on host | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN |
| RSK-016 | All relative config paths resolve to nonexistent dirs | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | LOW (2) | 90 | OPEN |
| RSK-018 | Two competing scoring systems (severity weight vs risk score) | MEDIUM | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | 81 | OPEN |
| RSK-020 | Tautological validation in validate-state | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | HIGH (4) | 180 | OPEN |
| RSK-021 | Always-return-DETECTED fallback in all mutation tests | HIGH | HIGH (5) | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | 135 | OPEN |
| RSK-022 | Non-atomic three-phase state promotion | MEDIUM | MEDIUM (3) | HIGH (5) | LOW (2) | MEDIUM (3) | 90 | OPEN |
| RSK-023 | Evidence registry pollution by test campaigns | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN |
| RSK-026 | GS-01 git-safety test operates on wrong file paths | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN |

### Cycle 8 Risk Discoveries

| ID | Risk | Severity | Likelihood | Impact | Exposure | Detectability | Score | Status |
|---|---|---|---|---|---|---|---|---|
| RSK-050 | Add-Member on hashtable silently fails gate override | HIGH | HIGH (5) | HIGH (5) | LOW (2) | HIGH (4) | 200 | MITIGATED |
| RSK-051 | $config undefined crashes sast-scan/dependency-scan actions | HIGH | HIGH (5) | MEDIUM (3) | LOW (2) | HIGH (4) | 120 | MITIGATED |
| RSK-052 | Evidence-signing all 4 functions non-functional (temp path) | HIGH | HIGH (5) | MEDIUM (3) | LOW (2) | HIGH (4) | 120 | MITIGATED |
| RSK-053 | incremental-audit 2 undefined functions crash audit pipeline | HIGH | HIGH (5) | MEDIUM (3) | LOW (2) | HIGH (4) | 120 | MITIGATED |
| RSK-054 | Plugin-loader path injection via single quotes | HIGH | MEDIUM (3) | HIGH (5) | LOW (2) | HIGH (4) | 120 | MITIGATED |
| RSK-055 | Git hook non-functional on Windows (python3) | MEDIUM | HIGH (5) | LOW (2) | LOW (2) | HIGH (4) | 80 | MITIGATED |
| RSK-056 | .aura/ mirror stale divergence from src/ | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | MITIGATED |
| RSK-057 | Sandbox Invoke-Expression on unsanitized input | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN |
| RSK-058 | cmd /c double-quote injection in tooling | MEDIUM | LOW (2) | MEDIUM (3) | LOW (2) | MEDIUM (3) | 36 | OPEN |
| RSK-059 | git status CRLF split breaks Windows path matching | MEDIUM | HIGH (5) | LOW (2) | LOW (2) | HIGH (5) | 100 | OPEN |
| RSK-060 | Substring crash on path case mismatch | LOW | MEDIUM (3) | LOW (2) | LOW (2) | HIGH (5) | 60 | OPEN |
| RSK-061 | Index-Symbols Remove() crash on missing property | LOW | LOW (2) | LOW (2) | LOW (2) | HIGH (5) | 40 | OPEN |

*Updated: Cycle 8, 2026-08-20*