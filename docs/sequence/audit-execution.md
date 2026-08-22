# Audit Execution Sequence — AURA v3.5

> **Verified from:** `src/aura/engine.py:50-820`, `src/aura/cli.py:208-224`

## Sequence: Single `aura audit` Cycle

```mermaid
sequenceDiagram
    actor User
    participant CLI as CLI (cli.py)
    participant Engine as Engine (engine.py)
    participant Analyzer as MultiLangAnalyzer
    participant Domain as DomainAuditOrchestrator
    participant Semantic as SemanticAuditor
    participant Context as ExecutionContextClassifier
    participant SM as State Machine
    participant DB as Database
    participant Git as git CLI
    participant Tools as SAST/Tooling
    participant LLM as LLM API
    
    User->>CLI: aura audit --repo .
    CLI->>CLI: load config (AuraConfig.from_env_or_file)
    CLI->>Engine: Engine(repo_root, config)
    CLI->>Engine: engine.initialize()
    Engine->>DB: db.initialize() — WAL, FK, migrations
    DB-->>Engine: ready
    
    Engine->>DB: get_latest_cycle()
    alt No existing cycle
        Engine->>DB: insert_cycle(1, INIT, RUNNING, NOT_READY)
        Engine->>DB: upsert_convergence(1, ...)
        loop 12 gates
            Engine->>DB: upsert_gate(1, name, passed)
        end
    end
    
    Engine->>DB: get_latest_cycle() → cycle_number
    Engine->>DB: insert_cycle(n+1, DISCOVER, RUNNING)
    
    Note over Engine: Phase 1: DISCOVER
    Engine->>Git: git --version, branch, log, status, ls-files
    Git-->>Engine: branch, commits, status, file list
    Engine->>DB: insert_audit_log(DISCOVER, ...)
    
    Note over Engine: Phase 2: MODEL
    Engine->>Engine: _detect_project_type()
    Engine->>DB: insert_audit_log(MODEL, ...)
    
    Note over Engine: Phase 3: AUDIT
    Engine->>Analyzer: analyze() — regex scan 650+ rules
    Analyzer-->>Engine: CodeAudit(findings, files, lines, quality)
    Engine->>DB: insert_audit_log(AUDIT, ...)
    
    Note over Engine: Phase 4: ADVERSARIAL_AUDIT
    Engine->>Domain: run_all_legacy() — 40-domain orchestrator
    Domain->>Domain: SharedIntelligence.build() — index files
    Domain->>Domain: 11 Wave-1 auditors run
    Domain-->>Engine: dict[domain → list[AdversarialFinding]]
    Engine->>DB: insert_audit_log(ADVERSARIAL, ...)
    
    Note over Engine: Phase 5: CORRELATE
    Engine->>Engine: Cross-rule normalization (domain→primary mapping)
    Engine->>Engine: Intra-source dedup (primary, adversarial)
    Engine->>Engine: Cross-source overlap detection
    Engine->>Engine: Global dedup by canonical key
    Engine->>Context: should_suppress_finding(file, rule, severity)
    Context-->>Engine: (suppress?, reason) × N
    Engine->>Semantic: enrich_findings(raw_dicts)
    Semantic-->>Engine: enriched FindingEvidence list
    Engine->>DB: insert_audit_log(CORRELATE, lineage)
    
    Note over Engine: Phase 6: PRIORITIZE
    Engine->>Engine: sort by severity(P0→P5), category
    Engine->>Engine: _to_finding_dicts — convert to DB shape
    Engine->>DB: insert_audit_log(PRIORITIZE, ...)
    
    Note over Engine: Phase 7: REMEDIATE
    loop each finding
        Engine->>DB: insert_finding(dict)
    end
    Engine->>DB: insert_audit_log(REMEDIATE, ...)
    
    Note over Engine: Phase 8: TEST
    Engine->>Engine: _detect_commands() — auto-discover tools
    loop each command
        Engine->>Tools: subprocess.run(cmd)
        Tools-->>Engine: exit_code, stdout, stderr
        Engine->>DB: insert_tooling_evidence(cn, cmd, exit_code, ok, output)
    end
    Engine->>DB: insert_audit_log(TEST, ...)
    
    Note over Engine: Phase 9: VERIFY
    Engine->>DB: insert_audit_log(VERIFY, ...)
    
    Note over Engine: Phase 10: REGRESSION
    Engine->>DB: get_findings(cycle=1..n-1)
    DB-->>Engine: previous findings
    Engine->>Engine: check reappeared P0-P2 findings
    Engine->>DB: insert_audit_log(REGRESSION, ...)
    
    Note over Engine: Phase 11: UPDATE_STATE
    Engine->>DB: insert_audit_log(UPDATE_STATE, ...)
    
    Note over Engine: Phase 12: CONVERGENCE
    Engine->>Engine: _validate_limitations_file()
    Engine->>SM: evaluate_all_gates(findings, cn, consecutive, audits_sf)
    SM-->>Engine: dict[gate → bool]
    Engine->>Engine: classify_finding for subclass-aware overrides
    Engine->>SM: compute_convergence_score(findings, weights, gates)
    SM-->>Engine: score 0-100
    Engine->>Engine: blended = score×0.6 + quality×0.4
    alt All gates pass
        Engine->>Engine: classification = PRODUCTION_READY
    else No P0/P1
        Engine->>Engine: classification = CONDITIONALLY_READY
    else
        Engine->>Engine: classification = NOT_READY
    end
    loop 12 gates
        Engine->>DB: upsert_gate(cn, name, passed)
    end
    Engine->>DB: upsert_convergence(cn, converged, classification, score)
    Engine->>DB: insert_audit_log(CONVERGENCE, ...)
    
    Note over Engine: Phase 13: PUSH_APPROVAL
    Engine->>DB: insert_audit_log(PUSH_APPROVAL, ...)
    
    Engine->>DB: update_cycle(cn, COMPLETE)
    Engine-->>CLI: result dict
    CLI-->>User: Formatted audit result (rich/JSON)
```

## Cross-Correlation Between Diagrams

This sequence directly reflects:
- **DFD Level 1:** Same 13 phases, same data store interactions
- **State Machine:** `evaluate_all_gates` and `compute_convergence_score` from `state_machine.py`
- **Context Diagram:** git CLI, SAST tools, LLM API, DB — all shown as actors
- **Component Diagram:** Engine owns Analyzer, DomainAuditOrchestrator, Semantic, Context, DB