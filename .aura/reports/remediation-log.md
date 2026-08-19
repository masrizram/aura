# Remediation Log

| Cycle | Finding ID | File(s) Changed | Change Summary | Risk | Verified By |
|-------|------------|-----------------|----------------|------|-------------|
| 1 | FIND-1-01 | run-audit.ps1 | Added Sanitize-PromptString function | low | Verifier |
| 1 | FIND-1-02 | run-audit.ps1 | Read-JsonFile: added try/catch | low | Verifier |
| 1 | FIND-1-03 | run-audit.ps1 | MAIN run action: null-guard on config | low | Verifier |
| 1 | FIND-1-04 | run-audit.ps1 | Changed Resolve-Path to -LiteralPath (2 locations) | low | Verifier |
| 1 | FIND-1-05 | run-audit.ps1 | Get-Command git availability check | low | Verifier |
| 1 | FIND-1-06 | run-audit.ps1 | Write-JsonFile: -Depth 100 | low | Verifier |
| 1 | FIND-1-07 | run-audit.ps1 | Write-JsonFile: atomic temp-file + Move-Item | low | Verifier |
| 1 | FIND-1-08 | run-audit.ps1 | Added Safe-Int function | low | Verifier |
| 1 | FIND-1-09 | run-audit.ps1 | cycles_without_progress Safe-Int fallback 0 | low | Verifier |
| 1 | FIND-1-10 | run-audit.ps1 | #requires -Version 5.1 | low | Verifier |
| 1 | FIND-1-11 | run-audit.ps1 | package.json parse wrapped in try/catch | low | Verifier |
| 1 | FIND-1-12 | run-audit.ps1 | IsNullOrWhiteSpace check before parse | low | Verifier |
| 1 | FIND-1-13 | run-audit.ps1 | Explicit $null -ne check on current_cycle | low | Verifier |
| 1 | FIND-1-14 | run-audit.ps1 | context action state init check | low | Verifier |
| 2 | FIND-1-15 through FIND-1-22 | run-audit.ps1, README.md, docs/master.md | P2-P5 refactor: dead code removal, doc fixes | low | Code review |
| 3 | FIND-1-23 through FIND-3-05 | run-audit.ps1, docs/cycle.md, state/findings.json, reports/*.md | Phase list reconciliation, BOM-free, path dedup, report sync | low | Cycle 3 verifier |
| 4 | FIND-4-01 | agents/ (5 files) | 9 path references corrected to .aura/ prefix | low | Cycle 4 verifier |
| 5 | FIND-1-28, FIND-1-29, FIND-3-05 | config.json | Removed dead verification_commands section (11 lines), resolving 3 OPEN P3s | low | Cycle 5 verifier |
| 6 | FIND-6-01 through FIND-6-04 | state/cycle.json, state/convergence.json, config.json | State/config integrity: version fix, field additions, dead config removal | low | Cycle 6 verifier |
| 7 | FIND-7-01 | agents/convergence-judge.md | Added 11th gate to output schema (consecutive_clean_independent_audits) | low | Cycle 7 verifier |
| 7 | FIND-7-02 | docs/cycle.md | HARD STOP RULE expanded to 11 conditions | low | Cycle 7 verifier |
| 7 | FIND-7-03 | config.json | require array expanded to 6 items | low | Cycle 7 verifier |
| 7 | FIND-7-04 | run-audit.ps1 | $minIndependent wired into convergence halt (both cycles and consecutive must pass) | low | Cycle 7 verifier |
| 7 | FIND-7-05 | config.json | Removed dead consecutive_clean_audits_required from convergence_gate | low | Cycle 7 verifier |
| 7 | FIND-7-06 | docs/master.md | CONVERGENCE RULE updated with all 11 gate conditions | low | Cycle 7 verifier |
| 7 | FIND-7-07 | .gitignore | Added .aura/archive/ exclusion | low | Cycle 7 verifier |
| 8 | FIND-8-12 | run-audit.ps1 | Added agents/ directory enumeration to Get-PushWorkingSet; updated push prompt template to reference .aura/agents/ | low | Cycle 8 verifier |
| 8 | FIND-8-01 | run-audit.ps1 | Sanitize-PromptString: added U+202A-U+2069 bidi char stripping | low | Cycle 8 verifier |
| 8 | FIND-8-07 | README.md | Convergence mermaid updated to 11-node flow with consecutive clean audits gate | low | Cycle 8 verifier |
| 8 | FIND-8-11 | run-audit.ps1 | git add switched from backtick escaping to :(literal) pathspec | low | Cycle 8 verifier |
| 8 | FIND-8-03 | (documentation) | Orphan temp file risk documented; mitigated by *.tmp.* gitignore exclusion | low | Cycle 8 verifier |
| 8 | FIND-8-08 | .gitignore | Added *.tmp.* glob exclusion | low | Cycle 8 verifier |
| 8 | FIND-8-10 | run-audit.ps1 | Sanitize-PromptString: surrogate pair check on truncation boundary | low | Cycle 8 verifier |
| 8 | FIND-8-09 | run-audit.ps1 | Reset-Engine: archive and remove generated-cycle-prompt.md | low | Cycle 8 verifier |
| 9 | FIND-9-01 | run-audit.ps1 | Two residual raw [int] casts (max_push_retries, min_independent_cycles) replaced with Safe-Int | low | Cycle 9 verifier |
| 9 | FIND-9-02 | (documentation) | .githooks/.gitmessage documented as inert templates; activation commands recorded | low | Cycle 9 verifier |
| 10 | FIND-10-01 | run-audit.ps1 | Added halt branch for max_cycles_without_progress in MAIN; prompt now shows 'Cycles without progress: N / max M' | low | Cycle 10 verifier |
| 10 | FIND-10-02 | run-audit.ps1 | Removed '.github/workflows' string from manifestFiles; added directory enumeration for *.yml/*.yaml workflow files | low | Cycle 10 verifier |

---

## Cycle 10 Summary
- 2 new findings discovered (1 P3, 1 P5), both fixed and verified
- run-audit.ps1: max_cycles_without_progress halt gate wired into MAIN run action (was dead code)
- run-audit.ps1: .github/workflows directory enumeration added (was dead literal string)
- 1 file changed (run-audit.ps1), ~15 lines added
- Correctness 92 (+1), Reliability 63 (+1)
- All prior 65 findings intact; no regressions
- consecutive_clean_independent_audits reset by P3 material finding (FIND-10-01)

## Cycle 9 Summary
- 2 new findings (1 P4, 1 P5), both fixed and verified
- run-audit.ps1: two residual [int] casts -> Safe-Int (completes FIND-1-08 hardening)
- .githooks/prepare-commit-msg + .gitmessage: inert (no core.hooksPath/commit.template); documented with activation commands
- 1 file changed (run-audit.ps1), 2 lines modified
- All prior 61 findings intact; no regressions
- Correctness 91 (+1); Overall 62; Confidence 95

## Cycle 8 Summary
- 9 new findings discovered (1 P2, 3 P3, 3 P4, 2 P5), all fixed and verified
- 3 files changed across orchestrator, documentation, and .gitignore
- Sanitize-PromptString hardened with bidi char stripping + surrogate-safe truncation
- Get-PushWorkingSet now includes agents/ (was missing: P2 data loss risk)
- git add uses :(literal) pathspec (eliminates bracket escaping issues)
- Reset-Engine now cleans all runtime artifacts
- All 9 findings VERIFIED; P0=0, P1=0, P2=0
- Overall score: 62 (+2); Confidence: 95
- run-audit.ps1: 855 lines (+22 from Cycle 7 adjustments), all prior hardening intact

## Cycle 14 Remediations
- 14 findings fixed in-cycle (FIND-14-01 through FIND-14-15)
- **Critical:** FIND-14-01/14-02 (P1): src/modules/ and src/agents/ populated; convergence.json override cleared
- src/modules/: 15 .ps1 modules copied from .aura/modules/ (adversarial-campaign, business-invariants, capability-scoring, evidence-integrity, failure-recovery, false-convergence-extended, false-evidence-attacks, git-safety, git-safety-adversarial, independent-verifier, mutation-testing, repo-graph, sandbox, scale-benchmark, security-scan)
- src/agents/: 6 .md agent role definitions copied from .aura/agents/
- .aura/run-audit.ps1: replaced 2179-line engine duplicate with 25-line proxy script
- src/engine/run-audit.ps1: Get-PushWorkingSet now enumerates src/modules/, src/agents/, .aura/run-audit.ps1 proxy
- run-audit.sh: PS1_SCRIPT path updated to src/engine/run-audit.ps1
- README.md: updated to Cycle 14 stats, 12-gate diagram, src/bin/config architecture layout
- AURA-COMMERCIAL-ONE-PAGER.md: corrected fabricated claims (70->65 findings, PRODUCTION_READY->NOT_READY, 11/11->11/12 gates)
- .github/workflows/ci.yml: created with 3 CI jobs
- bin/aura.ps1 + bin/aura.sh: created as entry-point scripts
- 9 stale/fabricated state files deleted (proposed-*, evidence-registry, invariant-definitions, baseline-snapshot, repo-graph, capability-score, force-validation-log, REFERENCE-CASE-001)
- 9 files changed, 15 files created, 9 files deleted

## Cycle 14 Summary
- 15 new findings discovered (2 P1, 4 P2, 3 P3, 2 P4, 4 P5); all P1-P4 remediated in-cycle
- Module dependency integrity gate restored to TRUE (all 15 modules load; stale override cleared)
- Source layout reconciled: src/modules/, src/agents/, .aura/run-audit.ps1 proxy, bin/ entry points
- Fabricated evidence from cycles 12-13 purged; 9 stale files deleted
- 6 P0-P2 findings remain OPEN per state machine (require IN_PROGRESS->FIXED->VERIFYING->VERIFIED)
- Classification: NOT_READY; consecutive_clean_independent_audits: reset to 0