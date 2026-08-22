# Data Lifecycle

> How a finding moves from source-line to terminal state, with all writers.

## Lifecycle

```mermaid
flowchart LR
    SRC[source code line] --> A[AUDIT: regex match<br/>or ADVERSARIAL: role heuristic<br/>or DOMAIN: Wave-1 auditor]
    A --> RAW[list[CodeIssue / AdversarialFinding / DomainFinding]]
    RAW --> COR[CORRELATE<br/>dedupe+context-suppress+semantic]
    COR --> FR[findings_list with stable F-id]
    FR -->|REMEDIATE phase only| DBI[(findings INSERT)]
    FX[AutonomousRemediationLoop cycle n+1] -->|status FIXED| DBU1[(UPDATE)]
    FX -->|next audit: regression ∩ current = ∅| DBV[(UPDATE status VERIFIED)]
    A -->|context suppressed| SUPP[omit — never persisted]
    COR -->|semantic MITIGATED/FALSE_POSITIVE| MIT[filter before gate eval]
    MIT -->|excluded from gates<br/>still inserted into findings| DBI
    DBI --> TR{trend/report users}
    DBU1 --> TR
    DBV --> TR
```

## Writers per state

| finding status | writes happen in |
|---|---|
| OPEN | engine `_phase_remediate` inserts (`status default OPEN`) |
| IN_PROGRESS | never written by engine (manual or external) |
| FIXED | remediation loop `db.update_finding_status(fid, "FIXED")` |
| VERIFYING | never written by engine (transition state reserved) |
| VERIFIED | remediation loop after clean re-audit, or manual `aura` flows |
| REJECTED | remediation loop when verifier fails |
| DEFERRED/BLOCKED | manual (`aura verify` flows) |
| WAIVED/ACCEPTED_RISK/OUT_OF_SCOPE | manual terminal resolutions |
| UNVERIFIED | never written by engine (legacy status allowed by CHECK) |

## Tooling evidence lifecycle

Each TEST phase inserts one row per detected command. `success`/`exit_code` are
immutable once written (no UPDATE path exists in db.py).

## Convergence lifecycle

`upsert_convergence` (INSERT or UPDATE) writes `converged`, `classification`,
`overall_score`, `consecutive_converged_cycles`, `audits_since_last_finding`.
The `audits_since_last_finding` counter increments unconditionally per cycle;
`consecutive_converged_cycles` increments only when converged OR classified
CONDITIONALLY_READY.

## Checkpoint lifecycle (out-of-band)

`CheckpointManager.save` on every cycle-boundary write sha256-hashed snapshot.
`CheckpointManager.load` validates hash on resume (REFUSES to resume from tampered state).
