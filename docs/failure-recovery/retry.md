# Failure/Recovery — Retry

> **Scope honesty:** Runtime HTTP LLM calls use `httpx` with hand-rolled retry loops.
> `tenacity>=9.0` is declared in `pyproject.toml` dependencies but **is never imported**
> under `src/aura/`. The only place the literal string `tenacity` appears in source is
> `adversarial.py:481` — a regex inside the RELIABILITY auditor that searches *audited
> repositories* for resilience libraries (it does not mean AURA's own retry uses tenacity).
> This document describes the retry that actually runs.

## Where retries actually live

### 1. `OpenAICompatibleProvider.chat` — the ONLY HTTP retry layer

`src/aura/providers.py:216-291` (wrapped by `_wrap_call` → circuit accounting).

**Classification** (`_NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}`, L188):

| Condition | Class | Action |
|---|---|---|
| HTTP 200 | success | return content (always `untrusted=True`) |
| HTTP 400/401/403/404/422 | **non-retryable** | fail fast, return error response (no retries burned) |
| HTTP 429, 5xx, anything else | retryable | sleep & retry up to `max_retries=3` (default) |
| network exception / timeout | retryable | sleep & retry up to `max_retries` |

**Backoff** (`_backoff_sleep`, L210-214): **full jitter** —
`sleep = random.uniform(0, min(cap, base * 2**attempt))` with `base=1.0s, cap=30.0s`.
Full jitter prevents thundering-herd against a recovering provider (documented inline).

**Retry-After honor** (L277-279): on retryable status with a numeric `Retry-After`
header, sleep `min(float(retry_after), backoff_cap)` instead of the jitter value.

**Final exhaustion** (L284-289): after `max_retries`, return a single error
`ProviderResponse(error="Failed after N attempts: ...")` — never raises.

### 2. `ProviderRegistry.chat_with_fallback` — routing, NOT retry

`providers.py:316-360`. Routes across up to `max_providers=3` non-OPEN providers in
`_priority_order`. It adds **no additional retries** on top of each provider's own
policy (deliberate, to avoid retry amplification — R2-04). Each provider error still
feeds *its own* circuit breaker via `_wrap_call`.

### 3. LLM fix-retry (business-level, one shot)

`remediation.py:443-492`: on first apply_fix failure where `old_code` mismatches,
re-prompt the LLM once with the actual file context and try again (`+2` attempts in
`cycle_finding_attempts` so it cannot loop indefinitely). Capped by
`LoopSafeguard.MAX_SAME_FINDING_ATTEMPTS=3`.

### 4. Loop-level convergence retry (business)

`convergence.LoopSafeguard` caps: `MAX_ITERATIONS=10`, `MAX_SAME_FINDING_ATTEMPTS=3`,
`NO_PROGRESS_CYCLES=3`, `REGRESSION_THRESHOLD=-10` (`convergence.py:175-178`). `can_continue`
returns `(False, reason)` on any breach — the loop stops cleanly instead of cycling forever.

## Failure taxonomy (which retry class each error maps to)

From `errors.py`:

| Exception | RetryDecision | Meaning |
|---|---|---|
| `NetworkError` | RETRY | transient, exponential backoff sensible |
| `TimeoutError` | RETRY_WITH_FALLBACK | retry, then pick another provider |
| `RateLimitError` | RETRY (honors Retry-After) | transient |
| `ProviderError` | RETRY_WITH_FALLBACK | fail to next provider after local retries exhausted |
| `ConfigError`, `ValidationError`, `StateMachineError`, `NotFoundError` | NO_RETRY | permanent, deterministic |
| `DatabaseError` | RETRY_WITH_FALLBACK (default) | SQLite contention should be rare |

## Operational mechanics (verified)

- `httpx.post(..., timeout=self.timeout)` with default `timeout=120.0` (`llm.py:39`,`providers.py:196`).
- Per-request temperature fixed at `0.1`, `stream=False`, `max_tokens=4000` default
  (`providers.py:220-228`).
- Provider timeouts are **network-side**; engine subprocess-side timeouts are separate
  (`_run_tooling` `timeout=300`, `engine.py:985`).