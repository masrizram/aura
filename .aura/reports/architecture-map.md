# Architecture Map

## Repository: AURA — Autonomous Engineering Audit Engine v2.1.0

### Architectural Layers

```
Entry Points (bin/)
    ├── aura.ps1 → delegates to src/engine/run-audit.ps1
    └── aura.sh  → delegates to src/engine/run-audit.ps1 via pwsh/powershell
         ↓
Engine Layer (src/engine/)
    └── run-audit.ps1 (2860 lines) — Orchestrator
         ├── State management (Initialize-State, Reset-Engine)
         ├── State machine enforcement (Validate-FindingStateIntegrity, Validate-GateEvidenceIntegrity)
         ├── Cycle generation (Generate-CyclePrompt)
         ├── State promotion (promote-state handler with proposed-file isolation)
         ├── Git push (Invoke-EnginePush with transactional staging)
         ├── Tooling execution (Invoke-ProjectTooling, run-tooling handler)
         └── Module loading (dot-sources 15 .ps1 modules at script scope)
              ↓
Module Layer (src/modules/) — 15 Pluggable Modules
    ├── Required: business-invariants, evidence-integrity, independent-verifier, security-scan, git-safety
    ├── Optional: repo-graph, sandbox, capability-scoring, scale-benchmark, mutation-testing, failure-recovery
    └── Experimental: git-safety-adversarial, false-evidence-attacks, adversarial-campaign, false-convergence-extended
         ↓
Agent Layer (src/agents/) — 6 Role Definitions (.md)
    ├── independent-auditor.md — full-spectrum audit
    ├── adversarial-auditor.md — 6-role attack review
    ├── remediator.md — fix root causes (+IN_PROGRESS state awareness)
    ├── verifier.md — independent fix verification (+VERIFYING state awareness)
    ├── regression-auditor.md — regression protection
    └── convergence-judge.md — gate evaluation (now covers all 12 gates)
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
| run-audit.ps1 | All 15 modules (dot-sourced), git CLI, config/aura.json |
| evidence-integrity | SHA256 crypto, filesystem registry (+initialization tracking) |
| capability-scoring | All 15 modules (dynamic invocation), repo state files |
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

### Repo Structure

| Directory | Files | Purpose |
|---|---|---|
| bin/ | 2 (.ps1, .sh) | CLI entry points |
| config/ | 1 (.json) | Engine configuration |
| src/engine/ | 1 (.ps1) | Orchestrator |
| src/modules/ | 15 (.ps1) | Engine modules |
| src/agents/ | 6 (.md) | Agent role definitions |
| src/lang/ | 2 (.json) | Locale files |
| tests/ | 0 | Empty directories (no tests) |
| .aura/state/ | 3 (.json) | Engine state |
| .aura/reports/ | 5 (.md) | Audit artifacts |
| .aura/docs/ | 3 (.md) | Agent documentation |
| .aura/agents/ | 6 (.md) | Agent definitions (mirror) |
| .aura/modules/ | 15 (.ps1) | Module definitions (mirror) |
| .aura/lang/ | 2 (.json) | Locale files (mirror) |
| .githooks/ | 1 | prepare-commit-msg hook |
| .github/workflows/ | 1 (.yml) | CI pipeline |
| reference/ | 1 (.md) | Reference case |

### Known Architecture Issues (Cycle 5)

| Issue | Severity | Status |
|---|---|---|
| Tautological validation in validate-state | P1 | OPEN (C3-002) |
| Non-atomic three-phase state promotion | P2 | OPEN (C3-010) |
| Module loading treats unclassified as REQUIRED | P2 | OPEN (C3-008) |
| Build-PSCopy shallow copy in FCX | P1 | OPEN (C3-001) |
| Test-FindingTransitionLegality null-unsafe checks | P1 | FIXED (C2-007) |
| BI-STATE-007 references wrong config path | P1 | IN_PROGRESS (C4-002) |
| BI-STATE-008 references bootstrap proxy not engine | P1 | IN_PROGRESS (C4-003) |
| Security-scan O(n) line counting across 8 functions | P2 | IN_PROGRESS (C4-004) |
| Config file divergence (.aura/config.json vs config/aura.json) | P1 | IN_PROGRESS (C5-001) |
| Missing module_dependency_integrity in .aura/config.json | P1 | IN_PROGRESS (C5-002) |
| Config agent paths reference stale .aura/agents/ not src/agents/ | P0 | IN_PROGRESS (C6-001) |
| Tautological business invariant (no_cross_cycle_evidence) | P0 | IN_PROGRESS (C6-002) |
| New-GitWorktree path safety only guards deletion not creation | P0 | IN_PROGRESS (C6-003) |
| Remove-GitWorktree has no path safety validation | P0 | IN_PROGRESS (C6-004) |
| Security scan ConvertFrom-Json false positive | P0 | IN_PROGRESS (C6-005) |
| Deterministic invariant verification is a no-op stub | P0 | IN_PROGRESS (C6-006) |
| Tooling correlation accepts null exit_code as success | P0 | IN_PROGRESS (C6-007) |

### Cycle 6 Architecture Notes

**Agent Directory Unified**: `config/aura.json` agent paths now reference `src/agents/` instead of `src/agents/`. The `.aura/agents/` directory was synced from `src/agents/` to fix all C2/C5 silent bypasses.

**Module Changes**:
- `business-invariants.ps1`: no_cross_cycle_evidence now reads `$reg.replay_attempts` at root level
- `git-safety.ps1`: Path safety checks now unconditional (both New-GitWorktree and Remove-GitWorktree)
- `security-scan.ps1`: Removed ConvertFrom-Json from UNSAFE_DESERIALIZATION patterns
- `independent-verifier.ps1`: Test-DeterministicInvariant no longer unconditional pass; tooling correlation null-safe

**Documentation Changes**:
- `convergence-judge.md`: Writes to proposed-convergence.json; module_dependency_integrity defaults false
- `cycle.md`: UPDATE_STATE references proposed-*.json; hard-stop rule has all 12 gates
- `adversarial.md`: MITIGATED changed to DEFERRED
- `master.md`: VERIFYING and REJECTED added to status list

*Updated: Cycle 7, 2026-08-20*

### Cycle 7 Architecture Notes

**CI/CD Field Name Bugs Discovered**: Multiple CI workflows (action.yml, aura-audit.yml) contain field name mismatches with the findings.json schema:
- `.state` used instead of `.status` for finding filtering (3 locations)
- `convergence_achieved` used instead of `converged` (1 location)
- `gate_status` used instead of `gates` (1 location)
- Invalid PowerShell ternary `?:` syntax in action.yml (1 location)
All 6 instances fixed. These bugs caused CI pipelines to silently report zero open findings regardless of actual state.

**Config Sync Gap**: `.aura/config.json` optional modules list was truncated (7 entries vs 13 in config/aura.json). Missing: evidence-signing, incremental-audit, smart-prioritization, team-workflow, sast-integration, dependency-scan. Synced to match.

**BI-STATE-009 Agent Paths**: Default invariant checked `agents/*.md` instead of `src/agents/*.md`. Fixed to use actual agent paths matching config/aura.json.

**BI-STATE-005 Phantom Status**: `MERGED` was in valid_values array but not registered in state machine. Removed.

**37 Legacy Findings Advanced**: Multi-cycle code inspection + 23/23 syntax check verified 37 prior IN_PROGRESS/OPEN findings as FIXED in source code.