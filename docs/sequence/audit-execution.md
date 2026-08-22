# Sequence — One Audit Cycle (`aura audit`)

> Source: `engine.py:135-183` + `_phase_*` handlers. Each numbered block = one DB audit_log insert.

```mermaid
sequenceDiagram
    actor U as User
    participant CLI as cli.py
    participant E as engine.Engine
    participant AN as MultiLangAnalyzer
    participant DO as DomainAuditOrchestrator
    participant EC as ExecutionContextClassifier
    participant SE as SemanticAuditor
    participant SM as state_machine
    participant DB as Database
    participant FS as Filesystem(.aura)

    U->>CLI: aura audit --repo .
    CLI->>CLI: load config (pydantic)
    CLI->>E: Engine(repo_root, config)
    E->>DB: __init__ (uninitialized)
    CLI->>E: run_audit()
    E->>DB: initialize() + get_latest_cycle()<br/>+ insert_cycle(cn+1) + upsert_convergence
    Note over E,DB: cycle_id = uuid4[:12]; phase_durations = {}

    rect rgb(245,245,245)
    Note over E,DB: 1 DISCOVER
    E->>E: _get_git_context(); _detect_languages()
    E->>DB: audit_log("DISCOVER", repo/files/langs)
    end
    rect rgb(245,245,245)
    Note over E,DB: 2 MODEL
    E->>E: _detect_project_type()
    E->>DB: audit_log("MODEL", proj type + lang count)
    end
    rect rgb(245,245,245)
    Note over E,AN: 3 AUDIT
    E->>AN: analyze() (rglob files, skip test/vendor)
    AN-->>E: CodeAudit{files, lines, findings, quality_score}
    E->>DB: audit_log("AUDIT", counts+quality)
    end
    rect rgb(245,245,245)
    Note over E,DO: 4 ADVERSARIAL_AUDIT
    E->>DO: run_all_legacy()
    DO->>DO: SharedIntelligence.build() (deps, framework, secrets scan)
    loop Wave-1 only — 11 auditors
        DO->>DO: auditor(ctx).audit() (exception-isolated per domain)
    end
    DO->>DO: DomainCorrelator.correlate(...)
    DO-->>E: {domain: [AdversarialFinding], _synthesis, _framework}
    alt on exception
        E->>E: adversarial.run_all(repo_root) legacy 12 roles
    end
    E->>DB: audit_log("ADVERSARIAL", roles+counts)
    end
    rect rgb(245,245,245)
    Note over E,EC: 5 CORRELATE
    E->>E: dedupe (canonical primary-key map; cross-overlap)
    E->>EC: should_suppress_finding(file, rule, sev) per finding
    E->>E: filter → context_suppressed count
    E->>SE: enrich_findings(raw_dicts)  (AST/taint/framework)
    SE-->>E: enriched (or [] on failure)
    E->>DB: audit_log("CORRELATE", lineage string)
    end
    rect rgb(245,245,245)
    Note over E,DB: 6 PRIORITIZE → 7 REMEDIATE → 8 TEST
    E->>E: sort + stable F-ids → findings_list
    E->>DB: insert_finding (each) + ancillary inserts
    E->>E: _run_tooling() → subprocess each detected cmd
    E->>DB: insert_tooling_evidence (exit code + 2KB tail)
    end
    rect rgb(245,245,245)
    Note over E,DB: 9 VERIFY → 10 REGRESSION → 11 UPDATE_STATE
    E->>DB: get_findings(cycles 1..cn-1) → resolved∩current ids
    E->>DB: audit_log("VERIFY"/"REGRESSION"/"UPDATE_STATE")
    end
    rect rgb(245,245,245)
    Note over E,SM: 12 CONVERGENCE
    E->>FS: read LIMITATIONS.md → _validate_limitations_file()
    E->>E: apply semantic-mitigation filter (omit MITIGATED/FALSE_POSITIVE)
    E->>SM: evaluate_all_gates(active_findings, ...)
    E->>E: subclass override for P2_zero & critical_security
    E->>SM: compute_convergence_score(...) → blended = 0.6*score + 0.4*quality
    E->>E: decide classification (see finding-state truth-table)
    E->>DB: upsert_gate ×12 + upsert_convergence
    E->>FS: append Evidence(level=CONVERGED|ASSERTED) → evidence_chain (hash-linked) + SQL mirror
    end
    rect rgb(245,245,245)
    Note over E,DB: 13 PUSH_APPROVAL
    E->>DB: audit_log("PUSH_APPROVAL", converged|classification)
    E->>DB: insert_audit_log("CYCLE_OBSERVABILITY", phase_durations)
    E-->>CLI: result dict {cycle_number, classification, gates, ...}
    CLI-->>U: formatted panel (or JSON)
```

## Failure edges visible at runtime (verified)

- `ADVERSARIAL_AUDIT` catches *any* exception from the domain orchestrator and silently
  falls back to 12-role legacy scan (`engine.py:226-232`) — the fallback event is not logged.
- `Semantic` enrichment wrapped in try/except → on failure `semantic_enriched=[]`, pipeline continues (L446-464).
- `_run_tooling` never raises: each subprocess exception is recorded as `exit_code=-1, success=False`.
- Phase durations are recorded even if the run converges; per-phase duration lives in `audit_log`
  event `CYCLE_OBSERVABILITY`.
