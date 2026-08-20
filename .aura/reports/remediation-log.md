# Remediation Log

## Cycle 8 Remediations

| Finding ID | Severity | Location | Problem | Fix Applied | Risk |
|---|---|---|---|---|---|
| AUDIT-C8-001 | P0 | src/engine/run-audit.ps1:2493-2495 | Add-Member on piped hashtable is ephemeral in PS 5.1; module_dependency_integrity gate override silently fails | Convert hashtable to PSCustomObject with Add-Member, then reassign gates property | LOW |
| AUDIT-C8-002 | P0 | src/engine/run-audit.ps1:2876,2887 | $config undefined in sast-scan/dependency-scan switch cases | Added Test-Path variable:config guard with Read-JsonFile fallback | LOW |
| AUDIT-C8-003 | P0 | src/modules/evidence-signing.ps1:47,118,181,259 | All 4 functions use __file__ from temp-written scripts; never resolves engine root | Pass engine root via sys.argv[1]; use sys.path.insert(0, engine_root) | LOW |
| AUDIT-C8-004 | P0 | src/modules/incremental-audit.ps1:428 | Get-AuthorBugRate called but never defined | Defined Get-AuthorBugRate with git log --since=90.days author frequency analysis | LOW |
| AUDIT-C8-005 | P0 | src/modules/incremental-audit.ps1:611 | Get-DependencyImpact called but never defined | Defined Get-DependencyImpact with importers traversal from graph data | LOW |
| AUDIT-C8-006 | P1 | src/modules/plugin-loader.ps1:53-58,179 | $PluginPath interpolated into Python -c without single-quote escaping | Added $pluginPathSafe = $PluginPath -replace "'", "''" before both interpolations | LOW |
| AUDIT-C8-007 | P1 | .githooks/prepare-commit-msg:21,26,41 | python3 doesn't exist on Windows; convergence_achieved wrong field | Added python3/python detection loop; changed to converged field | LOW |
| AUDIT-C8-008 | P1 | .aura/modules/, .aura/agents/ | .aura/modules/ and .aura/agents/ mirror directories stale; C7 BI-STATE-009 fix not reflected | Full sync of all .aura/modules/*.ps1 and .aura/agents/*.md from src/ copies | LOW |
| AUDIT-C8-009 | P2 | .githooks/prepare-commit-msg:41 | .state field used instead of .status in Python findings filter | Changed f.get('state') to f.get('status') | LOW |

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
| AUDIT-C5-001 | P1 | .aura/config.json | Config file divergence from config/aura.json | Synchronized .aura/config.json to match config/aura.json | LOW |
| AUDIT-C5-002 | P1 | .aura/config.json:51-58 | Missing 'Module Dependency Integrity' from convergence_gate.require | Added to require array | LOW |
| AUDIT-C5-007 | P1 | src/agents/verifier.md:22 | Verifier agent instructs direct writes to findings.json | Updated to write to proposed-findings.json | LOW |
| AUDIT-C5-012 | P2 | src/agents/remediator.md:7,22 | Remediator implies direct state writes without proposed-*.json | Added proposed-findings.json references to mandate and handoff | LOW |
| AUDIT-C5-011 | P2 | src/agents/regression-auditor.md:8 | Missing -Action run-tooling requirement | Added run-tooling to mandate | LOW |
| AUDIT-C5-013 | P2 | src/lang/en.json:111-117, src/lang/id.json:111-117 | Multi-agent path references .aura/agents/ instead of src/agents/ | Updated both locale files to src/agents/ | LOW |
| AUDIT-C5-008 | P2 | .githooks/prepare-commit-msg:9 | Missing 'commit' source guard; git --amend overwrites message | Added 'commit' to source guard | LOW |
| AUDIT-C5-003 | P2 | .gitmessage:15-20 | Indonesian-language placeholders contradict 'use English' directive | Replaced all 5W placeholders with English | LOW |
| AUDIT-C5-005 | P2 | bin/aura.sh:34 | Raw $@ passthrough vs named -Action parameter | Changed to pass -Action named parameter | LOW |

## Cumulative Fix Summary

| Cycle | Fixes | Files Changed | Risk Profile |
|---|---|---|---|
| 1 | 8 | run-audit.ps1, evidence-integrity.ps1, git-safety-adversarial.ps1, sandbox.ps1 | LOW |
| 2 | 9 | convergence-judge.md, cycle.md, business-invariants.ps1, master.md, evidence-integrity.ps1, .gitignore, .gitmessage, adversarial-auditor.md, remediator.md, verifier.md | LOW |
| 3 | 8 | false-convergence-extended.ps1, mutation-testing.ps1, independent-verifier.ps1, repo-graph.ps1, evidence-integrity.ps1, README.md | LOW |
| 4 | 4 | README.md, business-invariants.ps1, security-scan.ps1 | LOW |
| 5 | 12 | .aura/config.json, verifier.md, remediator.md, regression-auditor.md, en.json, id.json, .githooks/prepare-commit-msg, .gitmessage, bin/aura.sh, .aura/docs/adversarial.md, .gitattributes, run-audit.sh | LOW |
| 6 | 13 | config/aura.json, .aura/agents/*.md (6), convergence-judge.md, cycle.md, adversarial.md, master.md, business-invariants.ps1, git-safety.ps1, security-scan.ps1, independent-verifier.ps1 | LOW |
| 7 | 9 | action.yml, aura-audit.yml, business-invariants.ps1, .aura/config.json | LOW |
| 8 | 9 | run-audit.ps1, evidence-signing.ps1, incremental-audit.ps1, plugin-loader.ps1, .githooks/prepare-commit-msg, + full sync of .aura/modules/*.ps1 and .aura/agents/*.md | LOW |

*Updated: Cycle 8, 2026-08-20*