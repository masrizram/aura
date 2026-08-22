# Component Dependency Graph — AURA v3.5

> **Verified from:** import analysis of all `src/aura/*.py` files

## Import Graph

```mermaid
graph TD
    subgraph "Entry Points"
        MAIN["__main__.py"] --> CLI["cli.py"]
    end
    
    subgraph "Core"
        ENGINE["engine.py"] --> CONFIG["config.py"]
        ENGINE --> DB["db.py"]
        ENGINE --> ANALYZER["analyzer.py"]
        ENGINE --> ADVERSARIAL["adversarial.py"]
        ENGINE --> DOMAIN["domain_auditor.py"]
        ENGINE --> SEMANTIC["semantic.py"]
        ENGINE --> EXEC_CTX["execution_context.py"]
        ENGINE --> STATE_MACHINE["state_machine.py"]
        ENGINE --> FINDING_SUB["finding_subclass.py"]
        ENGINE --> EVIDENCE["evidence.py"]
        ENGINE --> CONVERGENCE["convergence.py"]
        ENGINE --> LLM["llm.py"]
        ENGINE --> LOGGING["logging.py"]
    end
    
    subgraph "Analysis"
        ANALYZER
        ADVERSARIAL
        DOMAIN --> ADVERSARIAL
        DOMAIN --> DOMAIN
        SEMANTIC
        EXEC_CTX
    end
    
    subgraph "Decision"
        STATE_MACHINE
        CONVERGENCE
        FINDING_SUB
    end
    
    subgraph "Providers / LLM"
        PROVIDERS["providers.py"] --> ERRORS["errors.py"]
        LLM
    end
    
    subgraph "Remediation"
        REMEDIATION["remediation.py"] --> CONVERGENCE
        REMEDIATION --> DB
        DURABLE["durable.py"] --> REMEDIATION
    end
    
    subgraph "Persistence"
        DB --> CONFIG
        EVIDENCE
    end
    
    subgraph "Infrastructure"
        CONFIG --> ERRORS
        ERRORS
        LOGGING
    end
    
    CLI --> ENGINE
    CLI --> CONFIG
    CLI --> LLM
    CLI --> REMEDIATION
    CLI --> DURABLE
    CLI --> PROVIDERS
    CLI --> LOGGING
```

## Dependency Counts (fan-in / fan-out)

| Module | Imported by (fan-in) | Imports (fan-out) |
|---|---|---|
| `config.py` | cli, engine, db | errors |
| `errors.py` | config, providers | (stdlib only) |
| `db.py` | cli, engine, remediation | config |
| `engine.py` | cli, remediation | config, db, analyzer, adversarial, domain_auditor, semantic, execution_context, state_machine, finding_subclass, evidence, convergence, llm, logging |
| `analyzer.py` | engine | (stdlib only — stdlib `re`, `dataclasses`, `pathlib`) |
| `adversarial.py` | engine, domain_auditor | (stdlib only) |
| `domain_auditor.py` | engine | adversarial |
| `semantic.py` | engine | (stdlib only — `ast`, `re`, `json`) |
| `execution_context.py` | engine | (stdlib only) |
| `state_machine.py` | engine, convergence | (stdlib only) |
| `finding_subclass.py` | engine | (stdlib only) |
| `evidence.py` | engine | (stdlib only) |
| `convergence.py` | engine, remediation | (stdlib only) |
| `llm.py` | cli, engine | (httpx only) |
| `providers.py` | cli | errors |
| `remediation.py` | cli | convergence, db |
| `durable.py` | cli | (stdlib only) |
| `logging.py` | cli, engine | structlog |
| `cli.py` | __main__ | config, engine, llm, remediation, durable, providers, logging |

## Key Observations

1. **`engine.py` is the highest fan-out module** — imports from 13 other aura modules. This is expected for an orchestrator but creates a broad dependency surface.

2. **Most analysis modules are self-contained** — `analyzer.py`, `semantic.py`, `state_machine.py`, `finding_subclass.py`, `evidence.py`, `execution_context.py`, `adversarial.py` import only stdlib.

3. **No circular imports** — The dependency graph is strictly acyclic (DAG).

4. **`providers.py` is underutilized** — Only imported by `cli.py` for the `auto-fix` command. `engine.py` uses the simpler `LLMClient` directly, not the `ProviderRegistry` with circuit breaker.

5. **`benchmark.py` and `benchmark_v3.py` have zero in-project imports** — standalone test utilities not imported by any production module.