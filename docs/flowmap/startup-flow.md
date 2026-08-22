# Startup Flow — AURA v3.5

> **Verified from:** `src/aura/cli.py:89-111`, `src/aura/engine.py:70-100`

See [audit-flow.md](audit-flow.md) for the combined startup + audit flow documentation.

## CLI Dispatch

```mermaid
flowchart TD
    ENTRY(["python -m aura\nor aura command"]) --> MAIN[cli.main() → cli(obj={})]
    MAIN --> CLICK["click.group: cli()"]
    CLICK --> DOTENV[load_dotenv() — loads .env file]
    DOTENV --> CONFIG["AuraConfig.from_env_or_file(repo_root)"]
    CONFIG --> VALIDATE{Config valid?}
    VALIDATE -->|Yes| DISPATCH[Route to subcommand]
    VALIDATE -->|No| EXIT["Console: red error\nsys.exit(1)"]
    
    DISPATCH --> INIT["init"]
    DISPATCH --> AUDIT["audit"]
    DISPATCH --> STATUS["status"]
    DISPATCH --> HEALTH["health"]
    DISPATCH --> DOCTOR["doctor"]
    DISPATCH --> VERIFY["verify"]
    DISPATCH --> LOG["log"]
    DISPATCH --> REPORT["report"]
    DISPATCH --> TREND["trend"]
    DISPATCH --> AUTOFIX["auto-fix"]
```

### Config Discovery Priority
1. `--config` CLI flag (if provided)
2. `$AURA_CONFIG_PATH` environment variable
3. `{repo_root}/config/aura.json`
4. `{repo_root}/aura.json`
5. Defaults (`AuraConfig()` with Pydantic defaults)