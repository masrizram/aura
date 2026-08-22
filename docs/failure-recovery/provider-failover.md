# Failure/Recovery — Provider Failover

> Source: `providers.py:294-372`.

## Algorithm

```
for name in _priority_order (up to max_providers=3):
    provider = _providers.get(name)
    if provider is None or provider.circuit == OPEN: continue
    resp = provider.chat(...)        # provider's internal retries run here
    if not resp.error: return resp
    last_error = resp                # try next
return ProviderResponse(error="All N provider(s) failed; last error: …")
         or ProviderResponse(error="All providers unhealthy — no fallback available")
```

## Design constraints (in code)

- Registry never retries a provider call — it only routes (R2-04).
- Provider call itself owns the retry classification, backoff, and jitter.
- Circuit OPEN removes the provider from rotation without operator intervention.
- `_priority_order` is derived from registration order (`register` appends; first-call
  priority wins).

## Health aggregation

`ProviderRegistry.get_all_statuses()` returns a snapshot of `ProviderStatus` per provider
(name, health, circuit_state, failure_count, success_count, last_success, last_failure,
last_failure_reason). Useful for `aura doctor`-style diagnostics in future — currently
not surfaced by CLI (UNVERIFIED claim about CLI visibility; CLI doctor does not call this).

## When failover engages

| Condition | Engages? |
|---|---|
| Primary returns any HTTP error (incl. non-retryable) | ✅ yes — router sees `resp.error != None` and tries next |
| Primary exhausts internal retries | ✅ yes (same path) |
| Primary circuit OPEN | ✅ yes — skipped before any request |
| Primary raises exception inside `provider.chat` | ⚠️ no — exception propagates (providers.chat returns ProviderResponse, doesn't raise; but a registry-level raise is unhandled) |
| Registry has 1 provider total | loop tries it once; on error returns "All 1 provider(s) failed" |

## Behavior after failover

The caller sees a single `ProviderResponse` — either success from some provider or an
aggregate error string. No signal about *which* provider served the success unless
`provider_name` is inspected (it is preserved on success).
