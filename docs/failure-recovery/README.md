# Failure & Recovery — README

Failure mode analysis and recovery mechanisms for AURA v3.5.

| Document | Scope |
|---|---|
| [error-flow.md](error-flow.md) | Error taxonomy, propagation, and handling throughout the pipeline |
| [retry.md](retry.md) | Retry strategies, exponential backoff, dead letter queue |
| [circuit-breaker.md](circuit-breaker.md) | Circuit breaker state machine and provider failover |
| [provider-failover.md](provider-failover.md) | (Consolidated in circuit-breaker.md) |
| [recovery-matrix.md](recovery-matrix.md) | Complete failure→recovery mapping for all components |

## Quick Reference: Error Categories

| Category | Retry? | Severity | Example |
|---|---|---|---|
| CONFIGURATION | No | FATAL | Invalid aura.json |
| VALIDATION | No | ERROR | Invalid finding transition |
| AUTHENTICATION | No | ERROR | Missing API key |
| AUTHORIZATION | No | ERROR | N/A (local tool) |
| NETWORK | Retry | ERROR | Connection refused |
| TIMEOUT | Retry + Fallback | ERROR | LLM request timeout |
| RATE_LIMIT | Retry | WARNING | 429 from LLM API |
| PROVIDER | Retry + Fallback | ERROR | LLM API error |
| DEPENDENCY | No | ERROR | Missing git |
| DATABASE | Retry + Fallback | ERROR | SQLite I/O error |
| PARSING | No | ERROR | Invalid LLM JSON |
| INTERNAL | No | ERROR | Unexpected exception |
| NOT_FOUND | No | ERROR | Finding not found |
| STATE_MACHINE | No | ERROR | Illegal transition |