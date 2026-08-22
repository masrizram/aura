# DFD Level 0 — AURA End-to-End Data Flow

> Verified against `engine.py:135-183` + `_phase_*` handlers.

```mermaid
flowchart TD
    U([User]) -->|"aura audit --repo ."|P1
    P1["P1 CLI Load Config<br/>(cli.py:89-111)<br/>config/aura.json, .env, AURA_CONFIG_PATH"]
    P1 --> P2{"Engine initialized?<br/>(db.py:210 + engine.py:110)"}
    P2 -- "no → create schema + cycle 1" --> P3
    P2 -- "yes" --> P3
    P3["P3 DISCOVER+MODEL<br/>git ctx, langs, proj type<br/>→ audit_log DISCOVER/MODEL"]
    P3 --> P4["P4 AUDIT<br/>MultiLangAnalyzer.analyze()<br/>regex per-file"]
    P4 --> F1[/findings: list[CodeIssue]/]
    P4 --> P5["P5 ADVERSARIAL_AUDIT<br/>DomainAuditOrchestrator<br/>.run_all_legacy()"]
    P5 --> F2[/11 live domain lists<br/>+ _framework + _synthesis/]
    F1 --> P6
    F2 --> P6
    P6["P6 CORRELATE<br/>dedupe canonical keys<br/>context-suppress<br/>semantic enrich"]
    P6 --> F3[/correlated + lineage stats/]
    F3 --> P7["P7 PRIORITIZE<br/>sort + stable F-ids"]
    F3 --> P8["P8 REMEDIATE<br/>INSERT/UPDATE findings"]
    P8 --> D1[(findings table)]
    P8 --> D1B[(audit_log)]
    P7 --> P9["P9 TEST<br/>_run_tooling<br/>auto-detect; capture exit codes"]
    P9 --> D2[(tooling_evidence)]
    P9 --> P10["P10 VERIFY<br/>count independently-verified only"]
    P10 --> P11["P11 REGRESSION<br/>resolved∩current ids"]
    D1 --> P11
    P11 --> P12["P12 UPDATE_STATE<br/>sev counts, quality"]
    P12 --> P13["P13 CONVERGENCE<br/>evaluate_all_gates<br/>+compute_convergence_score<br/>+ LIMITATIONS.md validation"]
    LIM[/LIMITATIONS.md/] --> P13
    D1 --> P13
    P13 --> D3[(gates, convergence tables)]
    P13 --> P14["P14 PUSH_APPROVAL<br/>log + return result dict"]
    P14 --> U
```

## Data flows (L0)

| Flow | Producer | Consumer | Payload | Persistence |
|---|---|---|---|---|
| Config | file / env | Engine (pydantic) | AuraConfig | in-memory only |
| File stream | repo FS | `MultiLangAnalyzer.analyze()` | CodeIssue list | `code_audit` ctx + audit_log summary |
| Domain findings | 11 auditors | CORRELATE | AdversarialFinding per role | none until correlated |
| Deduped findings | CORRELATE | PRIORITIZE / VERIFY / REGRESSION | list[dict] with F-ids | findings table + anchor lineage stats in audit_log |
| Tool runs | TEST | VERIFY/CONVERGENCE | {command, exit_code, success, output} | tooling_evidence |
| Fresh IDs | REGRESSION | CONVERGENCE | regression list | audit_log only |
| Scores/classification | CONVERGENCE | user + trend | classification, score, 12 gates | convergence + gates tables |
| LIMITATION text | FS | `_validate_limitations_file` | pass/fail + reason | audit_log on FAIL |

## External sources that influence convergence
- **LIMITATIONS.md** — read fresh each CONVERGENCE phase (no caching; gate `limitations_documented`).
- **Findings table at cycles 1..cn-1** — REGRESSION resolves∩current across ALL prior cycles (any severity).
- **convergence table at cn-1** — supplies consecutive_converged_cycles + audits_since_last_finding.
