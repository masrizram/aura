# Finding Validation Sequence — AURA v3.5

> **Verified from:** `src/aura/state_machine.py`, `src/aura/evidence.py`, `src/aura/engine.py:636-749`

## Sequence: Evidence-Based Finding Validation

```mermaid
sequenceDiagram
    participant Engine as Engine
    participant SM as State Machine
    participant Validator as EvidenceValidator
    participant Chain as EvidenceChain
    participant DB as Database
    
    Note over Engine: During CONVERGENCE phase
    
    Engine->>DB: get_findings(cycle_number)
    DB-->>Engine: findings list
    
    Engine->>SM: evaluate_all_gates(findings, cn, consecutive, audits_sf)
    
    Note over SM: For each gate:
    SM->>SM: P0_zero: check open P0 with active statuses
    SM->>SM: P1_zero: check open P1 with active statuses
    SM->>SM: P2_zero: check open P2 with active statuses
    SM->>SM: critical_security: all P0-P2 SECURITY in resolved statuses
    SM->>SM: critical_correctness: all P0-P2 CORRECTNESS resolved
    SM->>SM: data_integrity: all P0-P2 DATA_INTEGRITY resolved
    SM->>SM: regression: check reappeared findings
    SM->>SM: verification: no findings in FIXED status (unverified)
    SM->>SM: no_material_new: check new P0-P3 vs previous cycle
    SM->>SM: limitations_documented: file validation
    SM->>SM: consecutive_clean: ≥2 consecutive + ≥2 audits since finding
    SM->>SM: module_dependency_integrity: always true (PASS)
    
    SM->>SM: compute_convergence_score(findings, weights, gates)
    Note over SM: gate_score = passed/12 × 60
    Note over SM: penalty = P0×15 + P1×8 + P2×3 + P3+×1
    Note over SM: finding_score = max(0, 40 - min(penalty, 40))
    Note over SM: score = min(100, gate_score + finding_score)
    
    SM-->>Engine: gates dict + score
    
    Note over Engine: Subclass-aware overrides
    Engine->>Engine: is_blocking_for_gate(rule, gate) per finding
    Engine->>Engine: Override P2_zero: only CODE_DEFECT counts
    Engine->>Engine: Override critical_security: only CODE_DEFECT SECURITY
    
    Engine->>Engine: blended = score×0.6 + code_quality×0.4
    
    Engine->>DB: upsert_gate() × 12 (with subclass info)
    Engine->>DB: upsert_convergence(cn, converged, classification, score)
    
    Note over Validator: Independent validation (separate flow)
    Validator->>Chain: verify_chain() — hash integrity
    Chain-->>Validator: (ok, violations[])
    
    Validator->>Validator: validate_verified_finding(finding, evidence_list)
    Note over Validator: Checks: VERIFIED evidence exists,
    Note over Validator: exit_code==0, source≠remediator
    
    Validator->>Validator: validate_convergence_claim(gates, evidence_list)
    Note over Validator: Checks: all gates true, verified entries > 0
    
    Validator->>Validator: grade_evidence_quality(evidence_list)
    Note over Validator: Grade: A(≥90), B(≥70), C(≥50), D(≥30), F(<30)
```

## Cross-Check: Finding Transition Validity

```mermaid
sequenceDiagram
    participant SM as State Machine
    participant Validator as EvidenceValidator
    
    Note over SM: validate_finding_state_integrity()
    
    SM->>SM: For each proposed finding:
    
    alt New finding (no existing)
        SM->>SM: status must be OPEN
    else Existing finding
        SM->>SM: Check forbidden transitions
        Note over SM: OPEN→VERIFIED: blocked
        Note over SM: OPEN→FIXED: blocked
        Note over SM: IN_PROGRESS→VERIFIED: blocked
        Note over SM: FIXED→VERIFIED: blocked
        Note over SM: VERIFYING→CLOSED: blocked
        
        SM->>SM: Check valid transitions
        Note over SM: OPEN→IN_PROGRESS: valid
        Note over SM: IN_PROGRESS→FIXED: valid
        Note over SM: FIXED→VERIFYING: valid
        Note over SM: VERIFYING→VERIFIED: valid
        Note over SM: VERIFIED→OPEN: valid (regression)
    end
    
    SM->>SM: validate_gate_evidence_integrity()
    Note over SM: Gate flip false→true: requires documented evidence
    Note over SM: Gate flip true→false: requires documented finding
    Note over SM: Score decrease: rejected
    Note over SM: Score spike >15: rejected
    Note over SM: Counter regression: rejected
    Note over SM: Counter jump >1: rejected
```