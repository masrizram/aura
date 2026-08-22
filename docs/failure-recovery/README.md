# Failure/Recovery — README (index)

## Files
- `retry.md` — HTTP retry policy (only in providers.py) + loop safeguards.
- `circuit-breaker.md` — circuit state machine, defaults, health derivation.
- `provider-failover.md` — registry routing algorithm + health.
- `error-flow.md` — end-to-end path of errors from origin to surface.
- `recovery-matrix.md` — concrete recovery behavior per failure type.

## Quick truth table

| Failure surface | Retry inside AURA? | Fallback path |
|---|---|---|
| LLM HTTP transport | ✅ Yes — only here, classified | next provider via ProviderRegistry |
| LLM fix JSON | ❌ No HTTP retry; ✅ one business retry with file context | dead_letter → next finding |
| Tooling subprocess | ❌ No retry of the subprocess | tooling gate = fail until clean |
| DB transaction | automatic ROLLBACK | caller's retry policy via DatabaseError taxonomy |
| Checkpoint resume | ❌ No auto-recovery | refuse → fresh run |
