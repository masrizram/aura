# Risk Register

| ID | Severity | Category | Risk Score | Confidence | Status | Problem | Root Cause | Impact |
|----|----------|----------|------------|------------|--------|---------|------------|--------|
| FIND-1-01 | P0 | SECURITY | 625 | HIGH | VERIFIED | Prompt injection via unsanitized inputs | No sanitization of externally-sourced strings | AI agent prompt hijacking |
| FIND-1-02 | P0 | CORRECTNESS | 625 | HIGH | VERIFIED | Crash on corrupt JSON state files | No try/catch on ConvertFrom-Json | Engine bricked; all state lost |
| FIND-1-03 | P0 | CORRECTNESS | 625 | HIGH | VERIFIED | Missing config causes silent halt | Null config to [int]0 to max cycles 0 | Engine dead with misleading message |
| FIND-1-04 | P1 | CORRECTNESS | 405 | HIGH | VERIFIED | Resolve-Path wildcard mode | Missing -LiteralPath | Wrong directory resolved |
| FIND-1-05 | P1 | RELIABILITY | 405 | HIGH | VERIFIED | No git availability check | git commands run without prior check | Error messages in prompt |
| FIND-1-06 | P1 | DATA_INTEGRITY | 405 | HIGH | VERIFIED | -Depth 10 truncation | Insufficient serialization depth | Deep data silently lost |
| FIND-1-07 | P1 | DATA_INTEGRITY | 405 | HIGH | VERIFIED | Non-atomic state writes | Direct Set-Content without temp file | Corrupt state on crash |
| FIND-1-08 | P1 | CORRECTNESS | 405 | HIGH | VERIFIED | Unsafe [int] casts | No type validation on JSON values | Crash on non-numeric input |
| FIND-1-09 | P1 | RELIABILITY | 405 | HIGH | VERIFIED | Null cycles_without_progress | No null-coalescing | Stall detection fails |
| FIND-1-10 | P1 | RELIABILITY | 405 | HIGH | VERIFIED | No PS version check | Missing #requires | Cryptic errors on old PS |
| FIND-1-11 | P1 | RELIABILITY | 60 | HIGH | VERIFIED | package.json parse crash | No try/catch on external JSON | Engine crashes on malformed project |
| FIND-1-12 | P1 | CORRECTNESS | 72 | HIGH | VERIFIED | Missing/empty file conflated | Same return for both conditions | Silently overwrites state |
| FIND-1-13 | P1 | CORRECTNESS | 54 | HIGH | VERIFIED | 0 is falsy for cycle check | Boolean coercion on integer | Fragile logic |
| FIND-1-14 | P1 | RELIABILITY | 72 | HIGH | VERIFIED | context action missing init | No state init check | Degraded first prompt |

---

## Critical Risks (P0-P1)
All 14 P0/P1 findings FIXED and VERIFIED in Cycle 1.

## High Risks (P2)
All P2 findings VERIFIED. Cycle 6: FIND-6-04. Cycle 7: FIND-7-01. Cycle 8: FIND-8-12.

## Medium Risks (P3)
All P3 findings VERIFIED. Cycle 6: FIND-6-01, FIND-6-02, FIND-6-03. Cycle 7: FIND-7-02 through FIND-7-06. Cycle 8: FIND-8-01, FIND-8-07, FIND-8-11.

## Low / Polish (P4-P5)
All P4/P5 findings VERIFIED. Cycle 7: FIND-7-07. Cycle 8: FIND-8-03, FIND-8-08, FIND-8-10, FIND-8-09.

### Cycle 10 Additions
| FIND-10-01 | P3 | RELIABILITY | 72 | HIGH | VERIFIED | max_cycles_without_progress was dead halt code | $maxNoProgress computed but never consumed as halt gate | Engine would loop to max_cycles (25) with no stall abort |
| FIND-10-02 | P5 | CORRECTNESS | 12 | HIGH | VERIFIED | .github/workflows was string in file array not directory | Array mixed file paths with directory path; loop never enumerated workflow YML files | CI workflow detection silently missing for target projects |

### Cycle 9 Additions
| FIND-9-01 | P4 | CORRECTNESS | 36 | HIGH | VERIFIED | Two raw [int] casts bypass Safe-Int | [int] used directly on config values at lines 887,982 | Crash on non-numeric config values |
| FIND-9-02 | P5 | OPERATIONS | 12 | HIGH | VERIFIED | Inert git hooks/template | No core.hooksPath or commit.template configured | Auto-message hooks never fire |

### Cycle 8 Additions
| FIND-8-12 | P2 | CORRECTNESS | 216 | HIGH | VERIFIED | agents/ not in push working set | Get-PushWorkingSet enumerates docs/ but not agents/ | Agent files never pushed to git; lost on clone |
| FIND-8-01 | P3 | SECURITY | 72 | HIGH | VERIFIED | Sanitize-PromptString missing bidi char stripping | Bidi override chars (U+202A-U+2069) not in regex | Prompt text reordering/injection via bidi chars |
| FIND-8-07 | P3 | DOCUMENTATION | 54 | HIGH | VERIFIED | README mermaid missing 11th gate | Diagram not updated after consecutive gate added | User sees incomplete convergence criteria |
| FIND-8-11 | P3 | CORRECTNESS | 54 | HIGH | VERIFIED | Git bracket escaping unreliable | PowerShell backtick not respected by git | Files with brackets silently skipped/mismatched |
| FIND-8-03 | P4 | RELIABILITY | 30 | MEDIUM | VERIFIED | Orphan temp files on hard kill | Write-JsonFile temp-write window | Harmless orphan .tmp.* files |
| FIND-8-08 | P4 | MAINTAINABILITY | 20 | HIGH | VERIFIED | *.tmp.* not in .gitignore | No exclusion for atomic-write temp files | Orphan temp files committable |
| FIND-8-10 | P4 | CORRECTNESS | 36 | HIGH | VERIFIED | Surrogate pair split on truncation | Substring(0,4000) splits 2-char surrogates | Invalid UTF-16 at truncation boundary |
| FIND-8-09 | P5 | MAINTAINABILITY | 12 | HIGH | VERIFIED | generated-cycle-prompt.md not cleaned on reset | Cleanup logic was omitted | Stale prompt artifact persists |

### Cycle 14 Additions
| FIND-14-01 | P1 | ARCHITECTURE | 405 | HIGH | OPEN | src/modules/ empty; 15 modules only in .aura/modules/ | Modules persisted only in runtime dir | Fresh clones missing all modules |
| FIND-14-02 | P1 | DATA_INTEGRITY | 405 | HIGH | OPEN | convergence.json stale Cycle 13 override claiming module failure | Prior-cycle override persisted despite modules loading | DEGRADED mode warning; convergence blocked |
| FIND-14-03 | P2 | ARCHITECTURE | 216 | HIGH | OPEN | src/agents/ empty; 6 agent files only in .aura/agents/ | src/agents/ created but never populated | Bootstrap copy from src/agents/ fails silently |
| FIND-14-04 | P2 | DOCUMENTATION | 216 | HIGH | OPEN | README.md stale stats (Cycle 10, CONDITIONALLY_READY, 11 gates) | Not updated after cycles 11-13 | Misleading convergence status |
| FIND-14-05 | P2 | ARCHITECTURE | 216 | HIGH | OPEN | .aura/run-audit.ps1 full 2179-line engine duplicate | Not converted to proxy | Split-maintenance risk |
| FIND-14-06 | P2 | DOCUMENTATION | 216 | HIGH | OPEN | Commercial doc fabricated PRODUCTION_READY/70-finding claims | Written during false convergence cycles 12-13 | Credibility destroyed |
| FIND-14-07 | P3 | CORRECTNESS | 72 | HIGH | OPEN | run-audit.sh stale PS1_SCRIPT path | Not updated for source layout | Extra proxy hop on unix |
| FIND-14-08 | P3 | CORRECTNESS | 72 | HIGH | OPEN | Get-PushWorkingSet missing src/modules/, src/agents/ | Push set not updated for new layout | Source files never pushed |
| FIND-14-09 | P3 | OPERATIONS | 72 | HIGH | OPEN | .github/workflows/ empty; no CI pipeline | Placeholder never populated | No automated validation |
| FIND-14-10 | P4 | MAINTAINABILITY | 36 | HIGH | OPEN | 9 stale state files with fabricated evidence | Prior agents wrote without cleanup | Fabricated evidence persistable |
| FIND-14-11 | P4 | OPERATIONS | 30 | HIGH | OPEN | bin/ empty; no entry-point scripts | Created but never populated | No short cli command |
| FIND-14-12 | P5 | TESTING | 12 | HIGH | OPEN | Test dirs empty; no automated tests | Placeholder structure never filled | No regression test suite |
| FIND-14-13 | P5 | DOCUMENTATION | 6 | HIGH | OPEN | README doc map references .aura/config.json (moved) | Not updated after config move | Wrong config path reference |
| FIND-14-14 | P5 | MAINTAINABILITY | 6 | HIGH | OPEN | Modules duplicated .aura/modules/ + src/modules/ | Load path hardcoded to .aura/modules/ | Dual maintenance burden |
| FIND-14-15 | P5 | DOCUMENTATION | 6 | HIGH | OPEN | README self-test table shows fabricated 100% rates | Campaign results fabricated cycles 12-13 | False confidence claim |

## Blocked
*None.*