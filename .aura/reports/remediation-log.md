# Remediation Log

## Cycle 7 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C7-001 | P1 | action.yml:90-93 | .state field mismatch with findings.json .status | Changed $_.state to $_.status | LOW |
| AUDIT-C7-002 | P1 | action.yml:104 | Invalid PowerShell ternary ?: syntax | Replaced with if/else expression | LOW |
| AUDIT-C7-003 | P1 | aura-audit.yml:102 | convergence_achieved field doesn't exist in convergence.json | Changed to converged | LOW |
| AUDIT-C7-004 | P1 | aura-audit.yml:135-137 | JS script uses .state instead of .status | Changed f.state to f.status | LOW |
| AUDIT-C7-005 | P1 | aura-audit.yml:291-295 | Convergence-check uses .state instead of .status | Changed $_.state to $_.status | LOW |
| AUDIT-C7-006 | P1 | business-invariants.ps1:92-96 | BI-STATE-009 agent paths are bare (agents/*) | Changed to src/agents/ paths | LOW |
| AUDIT-C7-007 | P1 | business-invariants.ps1:64 | BI-STATE-005 accepts MERGED not in state machine | Removed MERGED from valid_values | LOW |
| AUDIT-C7-008 | P2 | aura-audit.yml:168-170 | JS reads gate_status; actual field is gates | Changed to conv.gates with boolean display | LOW |
| AUDIT-C7-009 | P2 | .aura/config.json | Optional modules truncated (7 vs 13 entries) | Synced optional modules + config sections | LOW |

## Cycle 6 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C6-001 | P0 | config/aura.json:163-169 | Agent paths reference stale .aura/agents/ | Changed to src/agents/; synced .aura/agents/ directory | LOW |
| AUDIT-C6-002 | P0 | business-invariants.ps1:312 | no_cross_cycle_evidence checks wrong data structure | Fixed to read replay_attempts at registry root level | LOW |
| AUDIT-C6-003 | P0 | git-safety.ps1:69 | Path safety only guards existing-path deletion | Moved safety checks outside Test-Path for unconditional validation | LOW |
| AUDIT-C6-004 | P0 | git-safety.ps1:123 | Remove-GitWorktree has no path safety | Added path resolution and dangerous-paths checks before Remove-Item | LOW |
| AUDIT-C6-005 | P0 | security-scan.ps1:322 | ConvertFrom-Json flagged as unsafe deserialization | Removed ConvertFrom-Json; narrowed to Invoke-Expression patterns | LOW |
| AUDIT-C6-006 | P0 | independent-verifier.ps1:156 | Deterministic invariant checks always pass (stub) | Changed to return passed=false with explanatory detail | LOW |
| AUDIT-C6-007 | P0 | independent-verifier.ps1:141 | Tooling correlation accepts null exit_code as success | Added null guard with AND logic (success=true AND exit_code=0) | LOW |
| AUDIT-C6-008 | P1 | convergence-judge.md:29 | Direct writes to convergence.json | Changed to proposed-convergence.json with orchestrator note | LOW |
| AUDIT-C6-009 | P1 | convergence-judge.md:48 | module_dependency_integrity hardcoded true | Changed template default to false | LOW |
| AUDIT-C6-010 | P1 | .aura/docs/cycle.md:70 | UPDATE_STATE writes to authoritative files | Changed to proposed-*.json with orchestrator promotion | LOW |
| AUDIT-C6-011 | P1 | .aura/docs/cycle.md:114 | Hard-stop rule missing Module Dependency Integrity | Added gate to hard-stop rule | LOW |
| AUDIT-C6-012 | P1 | .aura/docs/adversarial.md:49 | Instructs MITIGATED status | Changed to DEFERRED with state machine note | LOW |
| AUDIT-C6-013 | P1 | .aura/docs/master.md:691 | Status list missing VERIFYING/REJECTED | Added both to status list | LOW |

## Cycle 5 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C5-001 | P1 | .aura/config.json | Config file divergence from config/aura.json: missing modules, locale, language, convergence gate keys | Synchronized .aura/config.json to match config/aura.json | LOW |
| AUDIT-C5-002 | P1 | .aura/config.json:51-58 | Missing 'Module Dependency Integrity = PASS' from convergence_gate.require | Added to require array | LOW |
| AUDIT-C5-007 | P1 | src/agents/verifier.md:22 | Verifier agent instructs direct writes to findings.json vs state authority isolation | Updated to write to proposed-findings.json | LOW |
| AUDIT-C5-012 | P2 | src/agents/remediator.md:7,22 | Remediator implies direct state writes without proposed-*.json | Added proposed-findings.json references to mandate and handoff | LOW |
| AUDIT-C5-011 | P2 | src/agents/regression-auditor.md:8 | Missing -Action run-tooling requirement | Added run-tooling to mandate | LOW |
| AUDIT-C5-013 | P2 | src/lang/en.json:111-117, src/lang/id.json:111-117 | Multi-agent path references .aura/agents/ instead of src/agents/ | Updated both locale files to src/agents/ | LOW |
| AUDIT-C5-008 | P2 | .githooks/prepare-commit-msg:9 | Missing 'commit' source guard; git --amend overwrites message | Added 'commit' to source guard | LOW |
| AUDIT-C5-003 | P2 | .gitmessage:15-20 | Indonesian-language placeholders contradict 'use English' directive | Replaced all 5W placeholders with English | LOW |
| AUDIT-C5-005 | P2 | bin/aura.sh:34 | Raw $@ passthrough vs named -Action parameter | Changed to pass -Action named parameter | LOW |
| AUDIT-C5-009 | P4 | .aura/docs/adversarial.md:1 | Header references wrong filename 'ADVERSARIAL_PROMPT.md' | Changed to '# adversarial.md' | LOW |
| AUDIT-C5-010 | P3 | .gitattributes:1-2 | No * text=auto or text file entries beyond .sh/.ps1 | Added .md, .json, .yml, .yaml with eol=lf | LOW |
| AUDIT-C5-004 | P3 | run-audit.sh:76 | Silent default to 'run' action with no arguments | Changed ACTION default to empty; added missing-action error | LOW |

## Cycle 4 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C4-001 | P2 | README.md:410 | Self-test header claims fabricated "Cycle 14" | Changed to "Cycle 4" | LOW |
| AUDIT-C4-002 | P1 | business-invariants.ps1:79 | BI-STATE-007 checks for nonexistent config.json | Changed to "config/aura.json" | LOW |
| AUDIT-C4-003 | P1 | business-invariants.ps1:87 | BI-STATE-008 checks bootstrap proxy not engine | Changed to "src/engine/run-audit.ps1" | LOW |
| AUDIT-C4-004 | P2 | security-scan.ps1:76..335 | 8 instances of O(n) line counting pattern | Replaced all with -split .Count pattern | LOW |

## Cycle 3 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C3-001 | P1 | false-convergence-extended.ps1:540 | Build-PSCopy shallow copy corrupts attack state | Replaced with JSON round-trip deep copy | LOW |
| AUDIT-C3-003 | P1 | mutation-testing.ps1:431 | MUT-02 empty if-block doesn't populate violations | Added SCORE SPIKE violation message | LOW |
| AUDIT-C2-007 | P1 | independent-verifier.ps1:97 | Test-FindingTransitionLegality null-unsafe checks | Added conditional guards | LOW |
| AUDIT-C2-011 | P2 | repo-graph.ps1:182 | Function name regex fails on hyphenated names | Changed to 'function\\s+([\\w\\-]+)' | LOW |
| AUDIT-C2-015 | P2 | repo-graph.ps1:183-212 | O(n) array allocation for line numbers | Replaced all 6 with -split .Count | LOW |
| AUDIT-C1-010 | P1 | evidence-integrity.ps1:7 | $Script:EvidenceRegistryFile uninitialized | Added init tracking flag | LOW |
| AUDIT-C2-010 | P2 | README.md:28-32 | Gate map shows 10 symbols for 12 gates | Replaced with 12-symbol layout | LOW |
| AUDIT-C1-015 | P2 | README.md:19-22 | README claims 15 cycles, 65/100 score | Updated to actual Cycle 3 state | LOW |

## Cycle 2 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C2-001 | P1 | convergence-judge.md | Only 10/12 gates in mandate | Added missing gates | LOW |
| AUDIT-C2-002 | P1 | cycle.md:78 | States "11 gates" instead of 12 | Changed to "12 gates" | LOW |
| AUDIT-C2-003 | P1 | business-invariants.ps1:53 | BI-STATE-004 expects 11 gates | Updated to 12 | LOW |
| AUDIT-C2-004 | P1 | master.md:850-860 | Convergence rule omits module_dependency_integrity | Added gate | LOW |
| AUDIT-C2-005 | P1 | evidence-integrity.ps1:98 | Canonical hash missing 3 fields | Added all 3 fields with escaping | LOW |
| AUDIT-C2-012 | P2 | .gitignore:3-4 | Comment references wrong config path | Updated to config/aura.json | LOW |
| AUDIT-C2-013 | P2 | .gitmessage:7 | Typo "semi-colons" | Fixed to "semicolons" | LOW |
| AUDIT-C2-014 | P2 | adversarial-auditor.md:15 | MITIGATED status not in state machine | Changed to DEFERRED | LOW |
| AUDIT-C1-021 | P2 | evidence-integrity.ps1:98 | Hash collision via newline injection | Newline escaping + full coverage | LOW |

## Cycle 1 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C1-001 | P0 | run-audit.ps1:2490 | Undefined $ScriptRoot variable | Replaced $ScriptRoot -> $EngineRoot/$RepoRoot | LOW |
| AUDIT-C1-002 | P0 | run-audit.ps1:655 | Convergence invariant missing | Added unconditional gate validation | LOW |
| AUDIT-C1-003 | P0 | evidence-integrity.ps1:175 | Evidence fabricated undetected | Added SHA + timestamp validation | LOW |
| AUDIT-C1-004 | P0 | git-safety-adversarial.ps1:103 | Git config mutation | Removed 3x core.autocrlf mutations | LOW |
| AUDIT-C1-005 | P0 | git-safety-adversarial.ps1:74 | Undefined Write-TextFile | Replaced with System.IO.File::WriteAllText | LOW |
| AUDIT-C1-006 | P0 | run-audit.ps1:1390 | $Amend dead parameter | Added to function signature + pass-through | LOW |
| AUDIT-C1-008 | P1 | run-audit.ps1:26 | ForceValidation bypass plumbing | Added ForceValidation check | LOW |
| AUDIT-C1-009 | P1 | sandbox.ps1:11 | Dead sandbox parameters | Updated module header docs | LOW |

## Cumulative Fix Summary

| Cycle | Fixes | Files Changed | Risk Profile |
|---|---|---|---|---|
| 1 | 8 | run-audit.ps1, evidence-integrity.ps1, git-safety-adversarial.ps1, sandbox.ps1 | LOW |
| 2 | 9 | convergence-judge.md, cycle.md, business-invariants.ps1, master.md, evidence-integrity.ps1, .gitignore, .gitmessage, adversarial-auditor.md, remediator.md, verifier.md | LOW |
| 3 | 8 | false-convergence-extended.ps1, mutation-testing.ps1, independent-verifier.ps1, repo-graph.ps1, evidence-integrity.ps1, README.md | LOW |
| 4 | 4 | README.md, business-invariants.ps1, security-scan.ps1 | LOW |
| 5 | 12 | .aura/config.json, verifier.md, remediator.md, regression-auditor.md, en.json, id.json, .githooks/prepare-commit-msg, .gitmessage, bin/aura.sh, .aura/docs/adversarial.md, .gitattributes, run-audit.sh | LOW |
| 6 | 13 | config/aura.json, .aura/agents/*.md (6), convergence-judge.md, cycle.md, adversarial.md, master.md, business-invariants.ps1, git-safety.ps1, security-scan.ps1, independent-verifier.ps1 | LOW |

| 7 | 9 | action.yml, aura-audit.yml, business-invariants.ps1, .aura/config.json | LOW |

*Updated: Cycle 7, 2026-08-20*