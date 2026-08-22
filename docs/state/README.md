# State — README

State machine documentation for AURA.

| Document | Scope |
|---|---|
| [finding-state.md](finding-state.md) | Finding lifecycle (11 statuses, valid/invalid transitions) |
| [provider-state.md](provider-state.md) | Classification state (4 states), Circuit Breaker state (3 states), Provider Health state (4 states), Convergence Gate invariants |
| [audit-state.md](audit-state.md) | Cycle state progression |

## State Machine Overview

```mermaid
graph TD
    subgraph "Finding State (11 statuses)"
        O["OPEN"] --> IP["IN_PROGRESS"]
        IP --> FX["FIXED"]
        FX --> VY["VERIFYING"]
        VY --> VD["VERIFIED"]
        VD --> O
    end
    
    subgraph "Classification (4 states)"
        NR["NOT_READY"] --> CR["CONDITIONALLY_READY"]
        CR --> PR["PRODUCTION_READY"]
        PR --> NR
        HB["HUMAN_BLOCKED"] --> NR
        HB --> CR
        NR --> HB
        CR --> HB
        PR --> HB
    end
    
    subgraph "Circuit Breaker (3 states)"
        CL["CLOSED"] --> OP["OPEN"]
        OP --> HO["HALF_OPEN"]
        HO --> CL
        HO --> OP
    end
```