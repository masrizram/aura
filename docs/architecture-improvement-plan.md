# AURA Architecture Improvement Plan — v3.5.0

> Every finding traces to source-code evidence. Priorities: **P0** critical, **P1** high, **P2** medium, **P3** low.
> Scope rule: fixes must not create a second competing architecture; correct behavior is preserved.

---

## IMP-01 — Two parallel LLM client architectures
- **Category:** Duplicated logic / provider architecture
- **Severity:** P1
- **Current:** `llm.py:LLMClient` (plain httpx, no resilience) and `providers.py:OpenAICompatibleProvider` (retry + circuit breaker) coexist. `cli.py:auto_fix` bridges them with an inline `_RegistryLLMWrapper` class defined inside a command function. `Engine.__init__` accepts `LLMClient`.
- **Problem:** Two competing implementations of the same concern. The wrapper class is defined per-invocation (leaky, untestable). Engine depends on the weaker client.
- **Root cause:** `providers.py` was added later without migrating `llm.py` consumers.
- **Impact:** Reliability features (circuit breaker, health) are absent from any path that uses `LLMClient` directly; provider code is harder to test; type safety is eroded (`type: ignore` comments at cli.py:586-590).
- **Recommended:** Single provider architecture: `providers.py` is canonical. `llm.py` keeps `LLMResponse` + `AutonomousLoop` but its `LLMClient` becomes a thin adapter over `BaseProvider` (backward compatible constructor). Wrapper moves to a named, testable module-level class.
- **Implementation plan:** (1) Add `ProviderBackedLLMClient` in llm.py wrapping a `ProviderRegistry`. (2) cli.py uses it, deleting the inline class. (3) Engine type hints accept the protocol.
- **Migration risk:** Low — public constructor signatures preserved.
- **Testing:** unit test adapter (success, error, circuit-open paths).
- **Documentation impact:** provider-architecture docs updated to show one canonical stack.
- **Priority:** P1

## IMP-02 — ConvergenceJudge gate G07 hardcoded `True`; `module_dependency_integrity` hardcoded `True`
- **Category:** False convergence / validation weakness
- **Severity:** P0
- **Current:** `convergence.py:84` — `g07 = True  # If tooling passed, this passes`. `engine.py:677` — `module_integrity_pass=True`.
- **Problem:** Two gates claim to verify something they never check. Judge's G07 does not even inherit the tooling result — it is unconditionally true even when tooling failed (G06 may be false while G07 is true, a contradictory pair).
- **Root cause:** Stub never replaced with real check.
- **Impact:** `PRODUCTION_READY` can be reached with a broken typecheck and with missing engine modules — the exact false-convergence class AURA exists to prevent.
- **Recommended:** G07 mirrors G06 (tooling pass) until a real typecheck signal exists — and is documented as such. `module_dependency_integrity` performs a real import check of required `aura.*` modules, result cached at engine init.
- **Implementation plan:** (1) convergence.py: `g07 = g06`. (2) engine.py: `_check_module_integrity()` imports required modules in try/except; pass result into `evaluate_all_gates`.
- **Migration risk:** Low — gates may newly FAIL on broken environments (intended, fail-closed).
- **Testing:** regression tests: judge with failing tooling → G07 false; engine with simulated missing module → gate false.
- **Documentation impact:** state/failure-recovery docs updated; false-convergence test list extended.
- **Priority:** P0

## IMP-03 — Score monotonicity invariant contradicts remediation reality
- **Category:** Incorrect invariant / validation weakness
- **Severity:** P1
- **Current:** `state_machine.py:247-256` — any score decrease is a "SCORE REGRESSION" violation; any increase >15 is a "SCORE SPIKE" violation.
- **Problem:** A remediation cycle that *discovers new real findings* legitimately lowers the score. Flagging that as a violation penalizes honest detection. Additionally the validator is **dead code at runtime** — the engine never calls it — so the invariant exists only on paper yet misleads readers.
- **Root cause:** Invariant designed for gate-gaming prevention without distinguishing "score drop due to new findings" from "score drop due to gate manipulation."
- **Impact:** If ever wired in, it would block legitimate cycles; today it is documentation debt.
- **Recommended:** Remove score-regression/spike violations from the validator; keep the counter-jump invariants (those are genuine). Document the removal rationale.
- **Implementation plan:** delete the two blocks; adjust `test_state_machine.py` expectations; keep `COUNTER` invariants.
- **Migration risk:** None at runtime (validator was never called); test updates required.
- **Testing:** update existing validator tests; add test proving new-finding-driven score drop is NOT a violation.
- **Documentation impact:** invariants.md corrected — invariant removed, rationale recorded.
- **Priority:** P1

## IMP-04 — `evidence_chain` SQL table diverges from JSON-file EvidenceChain
- **Category:** Data integrity / duplicated state
- **Severity:** P1
- **Current:** `db.py` defines `evidence_chain` table (signature, signer, chain_index, previous_hash). `evidence.py:EvidenceChain` persists to JSON files. Zero code reads/writes the SQL table.
- **Problem:** Two parallel storage designs, one dead. JSON chain has `previous_hash` only implicitly (no field), so hash-linkage is not actually chained — each entry hash is self-contained, meaning deleted entries go undetected.
- **Root cause:** DB schema written ahead of implementation; JSON path shipped instead.
- **Impact:** Evidence tampering detection is weaker than documented; schema misleads operators.
- **Recommended:** Make the chain real: add `chain_index` + `previous_hash` linkage in `EvidenceChain` (JSON), persist the same entries into the SQL table when a `Database` is attached. Verify chain by walking both stores.
- **Implementation plan:** (1) `Evidence` gains `chain_index`, `previous_hash`. (2) `EvidenceChain.append` links hashes. (3) Optional `Database.attach_evidence_chain()` sync. (4) `verify_chain` checks linkage.
- **Migration risk:** Low — new fields default safely; old JSON files fail verification loudly (acceptable, they were unverifiable anyway).
- **Testing:** tamper tests (modify entry, delete entry, reorder) → verification fails; round-trip test JSON↔SQL.
- **Documentation impact:** data-model + security docs updated to describe ONE evidence store with two persistence backends.
- **Priority:** P1

## IMP-05 — Retry amplification & missing jitter in provider stack
- **Category:** Reliability / retry storm
- **Severity:** P1
- **Current:** `OpenAICompatibleProvider.chat` retries up to 3× with `time.sleep(min(2**attempt, …))` — no jitter, no idempotency/error classification (retries HTTP 4xx auth errors the same as timeouts), and sleeps cap differs between branches (30s vs 10s). Callers may add their own retries on top.
- **Problem:** (a) deterministic backoff → thundering herd against a recovering provider; (b) retrying non-retryable errors wastes budget and delays failure; (c) nested retry layers multiply attempts.
- **Root cause:** Retry policy embedded ad-hoc in the provider rather than expressed via the existing `RetryDecision` taxonomy in `errors.py`.
- **Recommended:** Single retry policy in the provider: full jitter (`random.uniform(0, min(cap, base*2**attempt))`), classify errors (429/5xx/timeouts/network → RETRY; 4xx auth/validation → NO_RETRY), and document that callers MUST NOT retry above the provider. Keep max 3 attempts.
- **Implementation plan:** rewrite `_do_call` loop; map status codes to `RetryDecision`; add jitter; unify caps.
- **Migration risk:** Low — latency distribution changes, semantics do not.
- **Testing:** mock httpx: 401 → 1 attempt; 429 → 3 attempts with increasing sleeps; timeout → retried; assert sleep bounds include jitter range.
- **Documentation impact:** failure-recovery/retry.md rewritten to match implementation.
- **Priority:** P1

## IMP-06 — AutoFixer sandbox: substring blocklist + symlink escape in path check
- **Category:** Security
- **Severity:** P1
- **Current:** `remediation.py:106` — `str(resolved).startswith(str(repo_resolved))` prefix check; `remediation.py:118-120` — dangerous-pattern substring blocklist (`"exec("`, `"subprocess."`, …) applied to the *whole new_code blob* with case-insensitive matching.
- **Problem:** (a) Prefix check without path separator: repo `/a/repo` accepts `/a/repo-evil/x`. `Path.is_relative_to` is the correct primitive. (b) Substring blocklist produces false positives (a fix touching `subprocess.run([...], shell=False)` legitimately) and false negatives (`getattr(os,'sys'+'tem')`, `os . system (` with spaces). Blocklists cannot win; the actual safety net is dry-run + rollback + tooling verification.
- **Root cause:** String-level sandbox reasoning instead of path/object-level.
- **Impact:** Possible path escape on crafted repo layouts; legitimate fixes blocked; obfuscated dangerous fixes pass.
- **Recommended:** (1) Use `resolved.is_relative_to(repo_resolved)` (Py3.9+; project requires 3.11). (2) Keep the pattern list but reframe it as *advisory* (log + require `dry_run=False` explicit acknowledgement) rather than pretending it is a boundary; document that the real controls are rollback + verification. (3) Add checkpoint integrity hash (see IMP-07).
- **Implementation plan:** patch `apply_fix`; add test for sibling-prefix escape; adjust blocklist messaging.
- **Migration risk:** Behavior change only for previously-exploitable paths — intended.
- **Testing:** path traversal regression tests (sibling dir, `..`, symlink); blocklist unit tests.
- **Documentation impact:** security-controls.md updated with accurate boundary description.
- **Priority:** P1

## IMP-07 — Checkpoint files lack integrity protection
- **Category:** Reliability / data integrity
- **Severity:** P2
- **Current:** `durable.py:CheckpointManager` writes `.aura/checkpoint.json` with no hash; `load()` silently returns parsed JSON.
- **Problem:** Corrupted or hand-edited checkpoints resume into inconsistent loop state undetected.
- **Recommended:** Store `state_hash` (SHA-256 over canonical JSON of `state`); verify on load; on mismatch refuse resume with a clear error.
- **Implementation plan:** add `_compute_hash`; `save` embeds; `load` verifies and returns None + logs on mismatch.
- **Migration risk:** Old checkpoints without hash → treated as invalid, fresh start (acceptable, documented).
- **Testing:** tamper test; truncation test; legacy-file test.
- **Documentation impact:** failure-recovery docs.
- **Priority:** P2

## IMP-08 — Dead/unwired code and dependency drift
- **Category:** Maintainability / dead code
- **Severity:** P2
- **Current:** `benchmark.py` superseded by `benchmark_v3.py` (which itself has 8 ruff invalid-syntax errors — **it does not even parse**); `pytest-asyncio`, `aiosqlite`, `cryptography` extras declared but unused; `registry.json` plugin array empty with no loader; `validate_*` state-machine validators uncalled by engine; docs claim 62 langs/650+ rules (actual 51/127).
- **Problem:** Dead code misleads contributors; unparsable module breaks `ruff`/packaging; dependency extras promise unimplemented features.
- **Recommended:** (1) Fix syntax errors in benchmark_v3.py (it is referenced by docs/benchmarks) or exclude it from packaging explicitly. (2) Mark `benchmark.py` deprecated in docstring. (3) Remove unused extras or wire them (choose remove — YAGNI until implemented). (4) Correct all numeric claims to 51/17/127.
- **Implementation plan:** minimal edits; re-run ruff to confirm parse; update pyproject extras comments; grep-fix numbers.
- **Migration risk:** None for removals of unused extras.
- **Testing:** `python -c "import aura.benchmark_v3"` parse check; ruff clean for that file.
- **Documentation impact:** README + docs metrics unified.
- **Priority:** P2

## IMP-09 — Observability: no execution/audit/provider request IDs, no phase timing
- **Category:** Observability
- **Severity:** P2
- **Current:** structlog present; engine logs phase names; but no `audit_id`/`execution_id` propagated, provider requests carry no ID, phase durations are not measured, finding provenance (which source produced it) is only implicit in `correlation_stats`.
- **Recommended:** (1) Generate `cycle_id` (uuid) per `run_audit`, bind to logger, include in audit_log metadata. (2) Time each phase, store in cycle metadata + log. (3) Provider requests get `request_id` echoed into ProviderResponse and logs.
- **Implementation plan:** engine: uuid + `time.perf_counter` around handlers; providers: uuid per call.
- **Migration risk:** None — additive.
- **Testing:** assert audit_log metadata contains cycle_id + phase durations; provider error path includes request_id.
- **Documentation impact:** observability section in architecture docs.
- **Priority:** P2

## IMP-10 — Non-Python "AST" overclaim in docs
- **Category:** Documentation integrity
- **Severity:** P2
- **Current:** Docs/README imply "AST (Python real, PHP/JS structural)"; semantic.py uses regex tokenizers for PHP/JS.
- **Recommended:** State precisely: Python = real AST (stdlib `ast`); PHP/JS = heuristic structural regex; all other languages = pattern matching only. This is already partially in LIMITATIONS.md — propagate to architecture docs and README.
- **Priority:** P2

---

### Out of scope (documented, not implemented now)
- Real cryptographic signing of evidence (needs key management design) — table fields remain until then.
- 29 unimplemented Wave 2-4 domain auditors — roadmap item, not a defect.
- Notification system — config exists, delivery unimplemented; documented as NOT IMPLEMENTED in README.
- Plugin system — registry.json placeholder; documented as NOT IMPLEMENTED.
