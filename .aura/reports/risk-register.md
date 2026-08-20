# Risk Register

## Active Risks (Cycle 5)

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
| RSK-009 | README claims uncommitted/unsupported project status | MEDIUM | HIGH (5) | MEDIUM (3) | HIGH (4) | HIGH (5) | 300 | MITIGATED |
| RSK-010 | Mutation test executes real code injection on host | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN |
| RSK-011 | Evidence canonical format allows hash collision via newline injection | HIGH | LOW (2) | HIGH (5) | LOW (2) | LOW (2) | 40 | MITIGATED |
| RSK-012 | Convergence gate count inconsistent (10/11/12) across docs | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | LOW (3) | 300 | MITIGATED |
| RSK-013 | Convergence judge missing 2 of 12 required gates | HIGH | HIGH (5) | HIGH (5) | HIGH (4) | LOW (3) | 300 | MITIGATED |
| RSK-014 | BI-STATE-004 invariant perpetually fails (11 vs 12) | MEDIUM | HIGH (5) | MEDIUM (3) | MEDIUM (3) | HIGH (4) | 180 | MITIGATED |
| RSK-015 | Agent definitions unaware of IN_PROGRESS/VERIFYING states | HIGH | HIGH (5) | HIGH (5) | MEDIUM (3) | MEDIUM (3) | 225 | MITIGATED — C5 update added proposed-*.json references |
| RSK-016 | All relative config paths resolve to nonexistent dirs | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | LOW (2) | 90 | OPEN |
| RSK-017 | CI state machine tests are placebo stubs | MEDIUM | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | HIGH (5) | 135 | OPEN |
| RSK-018 | Two competing scoring systems (severity weight vs risk score) | MEDIUM | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | 81 | OPEN |
| RSK-019 | Build-PSCopy shallow copy corrupts FCX attack state | HIGH | HIGH (5) | MEDIUM (3) | MEDIUM (3) | HIGH (4) | 180 | OPEN |
| RSK-020 | Tautological validation in validate-state (compares against itself) | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | HIGH (4) | 180 | OPEN (C3-002) |
| RSK-021 | Always-return-DETECTED fallback in all mutation tests | HIGH | HIGH (5) | MEDIUM (3) | MEDIUM (3) | MEDIUM (3) | 135 | OPEN (C3-004) |
| RSK-022 | Non-atomic three-phase state promotion | MEDIUM | MEDIUM (3) | HIGH (5) | LOW (2) | MEDIUM (3) | 90 | OPEN (C3-010) |
| RSK-023 | Evidence registry pollution by test campaigns | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN (C3-011) |
| RSK-024 | Function name regex misses hyphenated PS functions | LOW | HIGH (5) | LOW (2) | LOW (2) | HIGH (5) | 100 | MITIGATED |
| RSK-025 | O(n) array allocation in line number calculation | LOW | HIGH (5) | LOW (2) | LOW (2) | HIGH (5) | 100 | MITIGATED — C3 + C4 + C5 O(1) fix |
| RSK-026 | GS-01 git-safety test operates on wrong file paths | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | OPEN (C3-007) |
| RSK-027 | BI-STATE-007 invariant checks wrong config path | MEDIUM | HIGH (5) | MEDIUM (3) | LOW (2) | HIGH (4) | 120 | MITIGATED — C4 fix applied; C5 verified |
| RSK-028 | BI-STATE-008 invariant checks bootstrap proxy not engine | MEDIUM | HIGH (5) | MEDIUM (3) | LOW (2) | HIGH (4) | 120 | MITIGATED — C4 fix applied; C5 verified |
| RSK-029 | Config file divergence between .aura/config.json and config/aura.json | HIGH | MEDIUM (3) | HIGH (5) | MEDIUM (3) | MEDIUM (3) | 135 | MITIGATED — C5 sync applied |
| RSK-030 | Agent state authority isolation violations (direct writes) | HIGH | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED — C5 agent docs updated |
| RSK-031 | Multi-agent mode points to wrong agent paths | MEDIUM | HIGH (5) | MEDIUM (3) | LOW (2) | HIGH (4) | 120 | MITIGATED — C5 paths fixed |
| RSK-032 | git commit --amend overwrites message template | LOW | MEDIUM (3) | LOW (2) | LOW (2) | HIGH (4) | 48 | MITIGATED — C5 git hook fix |
| RSK-033 | Stale agent copies bypass C2/C5 state machine fixes | HIGH | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED — C6 config path fix |
| RSK-034 | Business invariant never detects cross-cycle evidence reuse | HIGH | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED — C6 invariant fix |
| RSK-035 | Worktree creation with no path safety validation | HIGH | MEDIUM (3) | HIGH (5) | LOW (2) | MEDIUM (2) | 60 | MITIGATED — C6 git-safety fix |
| RSK-036 | Arbitrary recursive deletion via Remove-GitWorktree | HIGH | MEDIUM (3) | HIGH (5) | LOW (2) | MEDIUM (2) | 60 | MITIGATED — C6 git-safety fix |
| RSK-037 | Security scanner produces massive false positives (ConvertFrom-Json) | MEDIUM | HIGH (5) | MEDIUM (3) | HIGH (4) | HIGH (5) | 300 | MITIGATED — C6 security-scan fix |
| RSK-038 | Deterministic invariant verification is a no-op stub | HIGH | HIGH (5) | HIGH (5) | MEDIUM (3) | HIGH (4) | 300 | MITIGATED — C6 verifier fix |
| RSK-039 | Broken tooling treated as successful verification | HIGH | HIGH (5) | MEDIUM (3) | MEDIUM (3) | HIGH (4) | 180 | MITIGATED — C6 verifier null-guard fix |

### Cycle 7 Risk Discoveries

| ID | Risk | Severity | Likelihood | Impact | Exposure | Detectability | Score | Status |
|---|---|---|---|---|---|---|---|---|
| RSK-045 | CI silently reports zero findings due to .state/.status mismatch | HIGH | HIGH (5) | HIGH (5) | HIGH (5) | LOW (2) | 250 | MITIGATED |
| RSK-046 | CI convergence gate always passes due to field name bugs | HIGH | HIGH (5) | HIGH (5) | HIGH (5) | LOW (2) | 250 | MITIGATED |
| RSK-047 | BI-STATE-009 agent path invariant perpetually fails | MEDIUM | HIGH (5) | LOW (2) | LOW (2) | HIGH (5) | 100 | MITIGATED |
| RSK-048 | BI-STATE-005 accepts phantom MERGED status | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | MEDIUM (3) | 54 | MITIGATED |
| RSK-049 | .aura/config.json optional modules missing 6 entries | MEDIUM | MEDIUM (3) | MEDIUM (3) | LOW (2) | HIGH (4) | 72 | MITIGATED |

*Updated: Cycle 7, 2026-08-20*