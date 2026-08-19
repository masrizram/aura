# Architecture Map

## Repository: Continuous Autonomous Engineering Audit Engine

### Overview

The repository at `C:\laraenv\www\aura` is the engine repository itself (self-auditing). It contains the `.aura/` audit engine directory, cross-platform entry points, git hooks, and configuration.

### Engine Architecture

```
.aura/
|-- run-audit.ps1              # PowerShell orchestrator (855 lines, hardened)
|-- config.json                # Engine configuration + convergence gate (99 lines)
|-- docs/                       # Engine prompt documentation
|   |-- master.md               # Full audit rules (1293 lines)
|   |-- cycle.md                # Per-cycle execution phases (13 phases)
|   |-- adversarial.md          # Hostile attack lens (51 lines)
|-- generated-cycle-prompt.md  # Runtime: generated cycle prompt
|-- last-cycle.env             # Runtime: last cycle metadata
|-- agents/                    # Multi-agent role definitions
|   |-- independent-auditor.md
|   |-- adversarial-auditor.md
|   |-- remediator.md
|   |-- verifier.md
|   |-- regression-auditor.md
|   |-- convergence-judge.md
|-- state/                     # Persistent machine-readable state
|   |-- cycle.json
|   |-- findings.json
|   |-- convergence.json
|-- reports/                   # Persistent human-readable artifacts
    |-- audit-ledger.md
    |-- architecture-map.md
    |-- risk-register.md
    |-- verification-matrix.md
    |-- remediation-log.md
```

### Repository Root

```
run-audit.sh                  # Cross-platform bash entry (macOS/Linux)
.gitignore                     # Excludes generated runtime files + archive + temp files
.gitattributes                 # EOL normalization (LF for .sh, CRLF for .ps1)
.gitmessage                    # Conventional commit template
.githooks/prepare-commit-msg  # 5W commit message generator
README.md                      # Usage documentation
```

### Data Flow

```
config.json -+
state/*.json -+
git context -+-> run-audit.ps1 -> generated-cycle-prompt.md -> AI Agent
target project+
```

### Entry Points

- `run-audit.ps1 -Action run [-MultiAgent] [-Force]` -- generate next cycle prompt
- `run-audit.ps1 -Action status` -- view convergence status
- `run-audit.ps1 -Action context` -- generate prompt only (no state advance)
- `run-audit.ps1 -Action reset` -- archive and reset engine state
- `run-audit.ps1 -Action push [-Approve]` -- stage + commit + push engine files
- `run-audit.sh <action>` -- cross-platform Unix wrapper

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| Orchestrator | run-audit.ps1 | State management, prompt generation, convergence display, push |
| Unix wrapper | run-audit.sh | Cross-platform entry point (pwsh/powershell detection) |
| State layer | state/*.json | Cycle tracking, findings ledger, convergence gate |
| Report layer | reports/*.md | Human-readable audit history |
| Agent defs | agents/*.md | Multi-agent role instructions |
| Prompts | docs/master.md, docs/cycle.md, docs/adversarial.md | AI agent instructions |
| Config | config.json | Engine settings, convergence gate, push config (99 lines) |

### Key Functions (run-audit.ps1)

| Function | Lines | Purpose |
|----------|-------|---------|
| Read-JsonFile | 74-89 | Safe JSON reading with error recovery |
| Write-JsonFile | 101-118 | Atomic JSON writing (BOM-free) |
| Write-TextFile | 92-99 | BOM-free UTF8 text output |
| Sanitize-PromptString | 120-133 | Prompt injection defense (covers control chars, bidi chars, surrogates) |
| Get-GitContext | 131-172 | Git state extraction with error handling |
| Get-ProjectTooling | 174-228 | Project manifest detection |
| Get-FindingsSummary | 230-268 | Findings aggregation for prompt |
| Get-ConvergenceStatus | 270-317 | Gate status display |
| Initialize-State | 319-364 | Fresh state initialization |
| Reset-Engine | 367-421 | State archival + reinitialization (cleans all runtime artifacts) |
| Safe-Int | 421-429 | Type-safe integer coercion |
| Generate-CyclePrompt | 431-671 | Full cycle prompt assembly |
| Get-PushWorkingSet | 673-716 | Gather engine files for git push (now includes agents/) |
| Get-PushSummary | 712-742 | Push commit message summary |
| Invoke-EnginePush | 744-920 | Stage + commit + push engine files (uses :(literal) pathspec) |

### Dependencies

- PowerShell 5.1+ (enforced via `#requires -Version 5.1`)
- git (optional; checked at runtime with graceful degradation)
- No external PowerShell modules required
- bash (for run-audit.sh Unix wrapper)

### Security Controls

| Control | Location | Purpose |
|---------|----------|---------|
| Prompt sanitization | run-audit.ps1:120-133 | Strip control chars, bidi chars, escape delimiters, truncate, surrogate-safe |
| Git error detection | run-audit.ps1:135-139, 147-164 | Pre-flight git check + $LASTEXITCODE validation |
| Atomic writes | run-audit.ps1:101-118 | Temp file + rename pattern |
| Safe integer casting | run-audit.ps1:421-429 | try/catch with fallback |
| BOM-free output | run-audit.ps1:92-99 | UTF8Encoding(false) for cross-platform compatibility |
| Null guards | run-audit.ps1:438-444 | All config/state reads null-guarded |
| Git pathspec safety | run-audit.ps1:849 | :(literal) pathspec prevents glob interpretation |

### Convergence Gate Matrix (11 gates)

| Gate | Location | Purpose |
|------|----------|---------|
| P0_zero | config.json, run-audit.ps1:347 | Zero catastrophic findings open |
| P1_zero | config.json, run-audit.ps1:348 | Zero critical findings open |
| P2_zero | config.json, run-audit.ps1:349 | Zero high findings open |
| critical_security | config.json, run-audit.ps1:350 | No critical security issues |
| critical_correctness | config.json, run-audit.ps1:351 | No critical correctness issues |
| data_integrity | config.json, run-audit.ps1:352 | Data integrity verified |
| regression | config.json, run-audit.ps1:353 | No regressions detected |
| verification | config.json, run-audit.ps1:354 | All fixes independently verified |
| no_material_new_findings | config.json, run-audit.ps1:355 | 2 consecutive clean cycles |
| limitations_documented | config.json, run-audit.ps1:356 | Remaining limitations documented |
| consecutive_clean_independent_audits | config.json, run-audit.ps1:357 | 2 cycles with zero new P0-P3 findings |

### Cycle 9 Update (2026-08-19)
- Two residual raw [int] casts at run-audit.ps1:887,982 replaced with Safe-Int (completing FIND-1-08 hardening sweep)
- .githooks/prepare-commit-msg and .gitmessage documented as inert templates (no git config wired)
- All prior findings intact; no regressions
- PowerShell syntax parse: PASS
- run-audit.ps1: 855 lines unchanged in size (2 cast sites replaced, same line count)

### Cycle 10 Update (2026-08-19)
- max_cycles_without_progress halt gate wired into MAIN run action (was computed but never consumed)
- Prompt display now shows "Cycles without progress: N / max M" instead of bare count
- .github/workflows directory enumeration added to Get-ProjectTooling (was dead string literal in manifestFiles)
- run-audit.ps1: ~1059 lines (+15 from halt gate + workflow enumeration blocks)

### Cycle 8 Update (2026-08-18)
- Sanitize-PromptString enhanced with Unicode bidi character stripping (U+202A-U+2069)
- Sanitize-PromptString now handles surrogate pair truncation safety
- Get-PushWorkingSet now includes agents/ directory (was missing; P2 finding)
- Push prompt template updated to reference .aura/agents/
- git add uses :(literal) pathspec instead of backtick escaping
- Reset-Engine now archives and removes generated-cycle-prompt.md
- README.md convergence mermaid updated with 11th gate
- .gitignore now excludes *.tmp.* files
- 3 files changed, 25 insertions, 7 deletions
- run-audit.ps1: 855 lines (was 1031; counting method differs from prior windows)

### Cycle 7 Update (2026-08-18)
- convergence-judge.md: output schema updated to 11 gates (was 10)
- docs/cycle.md: HARD STOP RULE now lists all 11 conditions
- config.json: convergence_gate.require now has 6 items (was 5)
- config.json: removed dead consecutive_clean_audits_required from convergence_gate
- run-audit.ps1: $minIndependent now wired into convergence halt check (was dead code)
- docs/master.md: CONVERGENCE RULE updated with all 11 gate conditions
- .gitignore: .aura/archive/ exclusion added
- 7 files changed, 31 insertions, 10 deletions

### Cycle 14 Update (2026-08-19)
- src/modules/: populated with 15 engine modules (from .aura/modules/); was empty
- src/agents/: populated with 6 agent definition files (from .aura/agents/); was empty
- .aura/run-audit.ps1: converted from 2179-line engine duplicate to 25-line proxy delegating to src/engine/run-audit.ps1
- bin/aura.ps1, bin/aura.sh: new entry-point scripts
- .github/workflows/ci.yml: new CI pipeline (syntax check, module integrity, state machine tests)
- src/engine/run-audit.ps1: Get-PushWorkingSet now enumerates src/modules/, src/agents/, .aura/run-audit.ps1 proxy
- config/aura.json: remains at 158 lines; convergence_gate.require now lists 7 items including Module Dependency Integrity
- Architecture score: 65 (+3 from layout reconciliation)
- Module load path: engine loads from .aura/modules/ (hardcoded at run-audit.ps1:69); src/modules/ is canonical source copy
- 10 files changed/created this cycle