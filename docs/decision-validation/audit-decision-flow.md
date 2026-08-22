# Audit Decision Flow

> Sequence of decisions per cycle (not just actions). Each numbered step names the deciding code.

## Single-cycle decisions

```
 1. Load config (cli.py, AuraConfig.from_env_or_file) — FATAL on pydantic ValidationError
 2. Engine.__init__ — module_integrity probe (engine._check_module_integrity)
 3. initialize() — create schema if needed; create cycle 1 if none
 4. run_audit() — insert new cycle row (cn = latest+1)
 5. DISCOVER — does git work? does _detect_commands run?
 6. AUDIT — scan all included files; per-lang FILE_SIZE threshold flags oversized
 7. ADVERSARIAL_AUDIT — choose domain orchestrator vs legacy (try/except)
 8. CORRELATE — dedupe + context-suppress + semantic enrich (silent fallback on exceptions)
 9. PRIORITIZE — sort by severity_rank, category
10. REMEDIATE — persist findings + ancillary to DB
11. TEST — decide which commands to run; capture exit codes
12. VERIFY — count independent verification only
13. REGRESSION — resolved∩current set difference (any severity)
14. UPDATE_STATE — compute counts
15. CONVERGENCE —
    a. LIMITATIONS.md validator (I-12)
    b. Drop MITIGATED/FALSE_POSITIVE ids (I-26)
    c. evaluate_all_gates (System A)
    d. if !tooling_passed: verification=False (I-11)
    e. write gates to DB (raw pass)
    f. compute_convergence_score with normalized severity penalties
    g. blend score = int(0.6*score + 0.4*quality)
    h. subclass override for P2_zero, critical_security (I-10)
    i. write gates again (subclass pass)
    j. classification decision (engine.py:764-772)
    k. upsert_convergence with counter updates (I-19)
    l. append Evidence entry + mirror to SQL (R2-08)
16. PUSH_APPROVAL — audit-log final entry; store semantic memory
17. Return result dict → CLI formats panel (or JSON)
```

## Autonomous remediation loop decisions (per cycle)

```
1. engine.run_audit() → result + findings
2. ConvergenceJudge.evaluate(current, prev_states)  — only on engine-PRODUCTION_READY
3. If converged: build convergence proof; return
4. LoopSafeguard.can_continue(score, findings_count, attempt_id)
   - MAX_ITERATIONS=10
   - MAX_SAME_FINDING_ATTEMPTS=3
   - NO_PROGRESS_CYCLES=3 (score<90)
   - REGRESSION_THRESHOLD=-10
5. fixable = findings where status∈{OPEN,IN_PROGRESS,FIXED,REJECTED} AND file_path AND line_number
6. closure accounting: terminal_verified/waived/blocked/fixed_awaiting_verify
7. If no fixable: decide human_blocker reason (semantic-needed | blocked | all-terminal | none-remain)
8. Sort fixable by severity (P0 first)
9. For each up to 20 fixable:
   a. build fix prompt, call LLM
   b. parse JSON
   c. apply_fix via AutoFixer (sandbox guard, old_code match, write file)
   d. persist remediation_attempt
   e. if success: status=FIXED; else: retry once w/ file context; if still fail: dead_letter
10. Next cycle
```

## Falsifiability hooks (where a decision can be disproven)

| Decision | Disprove via |
|---|---|
| converged=True | `db.gates` rows must all be passed=1 for that cycle |
| LIMITATION gate | LIMITATIONS.md deleted → engine flips to CONDITIONALLY_READY |
| `module_dependency_integrity` | temporary rename of a module → gate=False |
| check counter monotonicity | `consecutive_converged_cycles` must equal non-decreasing sequence over cycles |
| canonical dedupe | correlation_stats must satisfy `primary_raw + adversarial_raw = combined_raw` and `combined_raw - total_duplicates_removed = total_unique` |
| `no_material_new_findings` | a new finding_id in P0-P3 must set this gate False next cycle |
