# Sequence — Finding Validation & Verification

> Sources: `evidence.py:164-236` (validators — opt-in), `remediation.py:58-588`,
> `llm.py:133-224`, `engine.py:510-530`, `db.py:340-373`.

## Intended verification model (as documented by docstrings)

A finding is VERIFIED only when ALL of these hold:
1. The orchestrator (not the LLM) ran the verification tooling.
2. Real exit codes were captured.
3. An **independent verifier** (not the remediator) confirmed the fix.
4. Regression audit confirms no re-introduction.
5. State transition passed through FIXED → VERIFYING → VERIFIED (`state_machine.py`).

## Actual runtime flow (as implemented)

```mermaid
sequenceDiagram
    participant RM as AutonomousRemediationLoop
    participant LLM as LLMClient/Provider
    participant FX as AutoFixer
    participant DB as Database
    participant EN as engine.Engine (next cycle)

    RM->>EN: run_audit() (cycle cn)
    EN-->>RM: result + findings list
    Note over RM: fixable = findings where<br/>status∈{OPEN,IN_PROGRESS,FIXED,REJECTED}<br/>AND file_path AND line_number
    loop up to max_fixes_per_cycle=20
        RM->>LLM: fix_prompt(finding) → candidate JSON (untrusted)
        LLM-->>RM: fix_data (may be bogus)
        RM->>FX: apply_fix(file, lines, old_code, new_code)
        FX->>FX: sandbox check (is_relative_to repo)<br/>dangerous-pattern advisory scan<br/>old_code fuzzy match
        alt success
            FX-->>RM: FixResult(success=True, diff=…)
            RM->>DB: insert_remediation_attempt(APPLIED)
            RM->>DB: update_finding_status(fid, FIXED)
        else code mismatch
            FX-->>RM: FixResult(success=False, err=old_code-not-found)
            RM->>LLM: retry once w/ actual file context
            LLM-->>RM: fix_data2
            RM->>FX: apply_fix(...) again
            FX-->>RM: FixResult
            RM->>DB: insert_remediation_attempt + status update
        else LLM JSON parse failure
            RM->>DB: insert_dead_letter(UNPARSEABLE, raw_response)
        end
    end
    Note over RM,DB: next audit cycle: a finding that no longer appears<br/>in the new scan is treated as resolved by absence<br/>(no dedicated VERIFYING step)
    RM->>EN: run_audit() (cycle cn+1)
    EN-->>RM: fresh findings list
    Note over RM: regression = resolved∩current — guard against come-back
    RM->>DB: update_finding_status(..., VERIFIED) — only after clean re-audit
```

## Where `EvidenceValidator` fits

`evidence.py:164-236` provides three opt-in helpers: `validate_verified_finding`,
`validate_convergence_claim`, `grade_evidence_quality`. They are **NOT invoked by
`engine.run_audit()`** (verified by grep; only callers are adversarial self-test
campaigns `adversarial.py:702-710` and tests). The runtime verification signal is:

- `tooling_evidence.exit_code == 0` recorded per cycle,
- re-audit absence of the finding (identity no longer in `current_ids`),
- `regressions ∩ current_ids == ∅`,
- explicit DB `status=VERIFIED` updates by the remediation loop only after a clean
  re-audit has no regression.

## Observability

- Every applied/rejected attempt persists in `remediation_attempts`.
- Unparseable LLM outputs persist in `dead_letter`.
- Rollback on batch failure: `AutoFixer.rollback()` restores file backup bytes then
  marks those `FixResult` entries `rolled_back=True,success=False` (`remediation.py:212-228`).
