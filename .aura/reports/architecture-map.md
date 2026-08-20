# Architecture Map

## Repository: AURA — Autonomous Engineering Audit Engine v2.1.0

### Architectural Layers

```
Entry Points (bin/)
    ├── aura.ps1 → delegates to src/engine/run-audit.ps1 (Python-first, PS fallback)
    └── aura.sh  → delegates to src/engine/run-audit.ps1 via pwsh/powershell
         ↓
Engine Layer (src/engine/)
    └── run-audit.ps1 (2895 lines) — Orchestrator
         ├── State management (Initialize-State, Reset-Engine)
         ├── State machine enforcement (Validate-FindingStateIntegrity, Validate-GateEvidenceIntegrity)
         ├── Cycle generation (Generate-CyclePrompt)
         ├── State promotion (promote-state handler with proposed-file isolation)
         ├── Git push (Invoke-EnginePush with transactional staging)
         ├── Tooling execution (Invoke-ProjectTooling, run-tooling handler)
         └── Module loading (dot-sources 22 .ps1 modules at script scope)
              ↓
Module Layer (src/modules/) — 22 Pluggable Modules
    ├── Required: business-invariants, evidence-integrity, independent-verifier, security-scan, git-safety
    ├── Optional: evidence-signing, repo-graph, sandbox, capability-scoring, scale-benchmark, mutation-testing, failure-recovery, plugin-loader, incremental-audit, smart-prioritization, team-workflow, sast-integration, dependency-scan
    └── Experimental: git-safety-adversarial, false-evidence-attacks, adversarial-campaign, false-convergence-extended
         ↓
Agent Layer (src/agents/) — 6 Role Definitions (.md)
    ├── independent-auditor.md — full-spectrum audit
    ├── adversarial-auditor.md — 6-role attack review
    ├── remediator.md — fix root causes (+IN_PROGRESS state awareness)
    ├── verifier.md — independent fix verification (+VERIFYING state awareness)
    ├── regression-auditor.md — regression protection
    └── convergence-judge.md — gate evaluation (covers all 12 gates)
         ↓
Configuration (config/)
    └── aura.json — engine config, module classification, severity weights, dimensions
         ↓
State/Reports (.aura/)
    ├── state/ — cycle.json, findings.json, convergence.json (authoritative)
    └── reports/ — architecture-map, audit-ledger, risk-register, verification-matrix, remediation-log
```

### Critical Data Flow

```
LLM Agent
    ↓ writes proposed-*.json (UNTRUSTED)
Orchestrator (run-audit.ps1)
    ↓ promote-state: validates against state machine → commits to actual state
.aura/state/*.json (TRUSTED after promotion)
    ↓ read by cycle generation
Generated cycle prompt → LLM Agent (next cycle)
```

### Key Dependencies

| Component | Depends On |
|---|---|
| run-audit.ps1 | All 22 modules (dot-sourced), git CLI, config/aura.json |
| evidence-integrity | SHA256 crypto, filesystem registry (+initialization tracking) |
| evidence-signing | Python + src.evidence.signing module (+path injection fix C8) |
| plugin-loader | Python + yaml module (+$PluginPath escaping fix C8) |
| incremental-audit | git CLI, findings.json (+Get-AuthorBugRate, Get-DependencyImpact defined C8) |
| capability-scoring | All 22 modules (dynamic invocation), repo state files |
| git-safety | git CLI, filesystem worktree isolation (+path prefix validation) |
| false-convergence-extended | State machine validators, evidence registry (+deep copy via JSON round-trip) |
| adversarial-campaign | State machine validators, evidence registry |
| repo-graph | Filesystem scanner, regex-based symbol indexing (+fixed hyphenated function names) |
| mutation-testing | All engine validators, evidence registry |

### Entry Points

1. `bin/aura.ps1 -Action run` — generate next cycle prompt
2. `bin/aura.ps1 -Action status` — show convergence status
3. `bin/aura.ps1 -Action promote-state` — validate & commit proposed state
4. `bin/aura.ps1 -Action push` — stage engine files, commit, push

### Known Architecture Issues (Cycle 8)

| Issue | Severity | Status |
|---|---|
| Tautological validation in validate-state | P1 | OPEN (C3-002) |
| Non-atomic three-phase state promotion | P2 | OPEN (C3-010) |
| Module loading treats unclassified as REQUIRED | P2 | OPEN (C3-008) |
| All 20 capability definitions use [scriptblock]::Create() injection | P1 | OPEN (C1-012/C3-005) |
| Always-return-DETECTED fallback in mutation tests | P1 | OPEN (C3-004) |
| Sandbox Invoke-Expression on unsanitized input | P2 | OPEN (C8-010) |
| cmd /c double-quote injection in tooling | P2 | OPEN (C8-011) |
| git status CRLF split breaks Windows path matching | P2 | OPEN (C8-012) |
| Substring crash on path case mismatch | P2 | OPEN (C8-013) |
| Evidence-signing __file__ path bug | P0 | FIXED (C8-003) |
| Add-Member hashtable gate override fails | P0 | FIXED (C8-001) |
| $config undefined in sast-scan/dependency-scan | P0 | FIXED (C8-002) |
| incremental-audit Get-AuthorBugRate missing | P0 | FIXED (C8-004) |
| incremental-audit Get-DependencyImpact missing | P0 | FIXED (C8-005) |
| plugin-loader $PluginPath injection | P1 | FIXED (C8-006) |
| prepare-commit-msg python3+field bugs | P1 | FIXED (C8-007, C8-009) |
| .aura/modules stale mirror | P1 | FIXED (C8-008) |

### Cycle 8 Architecture Notes

**Module Mirror Sync**: `.aura/modules/*.ps1` and `.aura/agents/*.md` fully synced from `src/` copies. Byte-identical across all files. Previous cycles' fixes to business-invariants.ps1 (BI-STATE-009 paths, BI-STATE-005 MERGED removal) were applied in src/ but the .aura/ mirror was stale.

**New Module Functions Defined**: `Get-AuthorBugRate` and `Get-DependencyImpact` defined in incremental-audit.ps1. These were design-phase functions referenced but never implemented, causing runtime crashes in Get-AuditPriority and Get-AuditScopeForCycle.

**Evidence-Signing Python Path Fix**: All 4 functions (New-EvidenceKeypair, Sign-EvidenceEntry, Test-EvidenceChainIntegrity, Export-AuditLog) now pass engine root via sys.argv and sys.path.insert instead of relying on __file__ which resolves to TEMP directory.

**Gate Override Bugfix**: promote-state module_dependency_integrity gate override changed from piping hashtable to Add-Member (ephemeral in PS 5.1) to converting hashtable to PSCustomObject first.

**6 FIXED findings advanced to proposed-FIXED status** (verified by 8-cycle code inspection + 23/23 syntax PASS).

*Updated: Cycle 8, 2026-08-20*