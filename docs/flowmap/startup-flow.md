# Flowmap — Startup Flow (aura <cmd>)

```mermaid
flowchart TD
    U([user]) --> CLI[cli.py group callback]
    CLI --> CFG{config path?<br/>--config / AURA_CONFIG_PATH /<br/>config/aura.json / aura.json}
    CFG --> LOAD[AuraConfig.from_file<br/>pydantic validation]
    LOAD -->|ValidationError| EXIT1[console.print red + sys.exit 1]
    LOAD --> LOG[configure_logging<br/>level from --verbose<br/>stderr only]
    LOG --> ENGINE[Engine(repo_root, config)]
    ENGINE --> INIT[initialize: DB schema + cycle 1]
    INIT --> CMD[specific subcommand]
    CMD --> AUDIT[run_audit 13 phases]
    CMD --> AUTO[auto-fix→ AutonomousRemediationLoop]
    CMD --> READ[status/health/doctor/log/verify/report/trend read-only]
```
