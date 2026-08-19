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

### Known Architecture Issues (Cycle 3)

| Issue | Severity | Status |
|---|---|---|
| Tautological validation in validate-state | P1 | OPEN (C3-002) |
| Non-atomic three-phase state promotion | P2 | OPEN (C3-010) |
| Module loading treats unclassified as REQUIRED | P2 | OPEN (C3-008) |
| Build-PSCopy shallow copy in FCX | P1 | FIXED (C3-001) |
| Test-FindingTransitionLegality null-unsafe checks | P1 | FIXED (C2-007) |

*Updated: Cycle 3, 2026-08-19*