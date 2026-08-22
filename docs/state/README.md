# State Documentation — Index

## Files
- `audit-state.md` — cycle-level state (INIT → 13 phases → COMPLETE; classification transitions; counter logic).
- `finding-state.md` — finding-level state machine (12 statuses, whitelist, forbidden jumps, truth-table measured live).
- `circuit-breaker-state.md` — (see `failure-recovery/circuit-breaker.md` for full state machine) — health ↔ circuit mapping.
- `provider-state.md` — provider health derivation + registry routing behavior.
