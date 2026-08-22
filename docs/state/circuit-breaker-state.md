# State Documentation — Circuit Breaker

> Full state machine documented in `failure-recovery/circuit-breaker.md`.
> This file is a short pointer so the `docs/state/` index is complete on its own terms.

- 3 states: CLOSED → OPEN → HALF_OPEN → CLOSED (or back to OPEN).
- Defaults: threshold=3, cooldown=30 s, half_open_max=1, rolling_window=120 s.
- Health derivation: CLOSED=HEALTHY, HALF_OPEN=DEGRADED, OPEN=UNHEALTHY.
