# RUN #3 — Adversarial Final Audit (baseline `83a1f33` / v3.5.2)

> **Mandate:** assume the previous remediation may still be wrong. Attempt to falsify every important architectural and correctness claim. Optimize for proving correctness, not for finding more issues. Every issue reproduced independently before modification.

## Attack surface exercised

| # | Attack vector | Method | Result |
|---|---|---|---|
| R3-A | Provider fallback amplifies retries / loses provenance / ignores OPEN circuits | `CountingProvider` instrumentation | **SURVIVED** — each provider tried at most once per call; response provenance correct; OPEN circuits skipped (0 attempts) |
| R3-B | Subclass loophole lets a real defect dodge P0 gates | `classify_finding` over known + unknown rules | **SURVIVED** — unknown rules default to CODE_DEFECT (fail-closed); only genuinely advisory subclasses (DEP-CVE, TEST-COV, LICENSE, LANG-INFO, code-quality) are non-blocking |
| R3-C | Reach PRODUCTION_READY without real fixes (DEFERRED abuse, empty-repo) | gate evaluation over adversarial finding sets | **SURVIVED by design** — DEFERRED is a documented human decision; empty-repo convergence requires 2 consecutive clean cycles + limitations doc; both documented, not defects |
| R3-D | Evidence chain forgery: empty chain, reload, stable-ID collision, forged genesis link | direct `EvidenceChain` manipulation | **SURVIVED** — empty chain valid; reload re-verifies; stable IDs deterministic; forged genesis `previous_hash` detected |
| R3-E | Sandbox escape: sibling prefix, absolute path, Windows case, dry-run write leak, dangerous pattern | `AutoFixer` on crafted layouts | **SURVIVED** — all escapes blocked; dry-run writes nothing; dangerous patterns still rejected |
| R3-F | End-to-end false convergence on a live malicious repo | real `Engine.run_audit()` on repo containing `eval()` + `os.system()` | **SURVIVED** — classification `NOT_READY`, `P0_zero=False`, `critical_security=False`, 7/12 gates |

## New defects found & fixed this run

### R3-01 — Quality score zeroed on tiny repos (P3, scoring proportionality)
- **Reproduced:** `_compute_quality` for a 4-line repo with 1 P0 + 1 P1 returned **0**; the same findings in a 4000-line repo returned **95**. Root cause: `kloc = max(total_lines/1000, 0.1)` — the 0.1 floor amplified the penalty 10× (23 / 0.1 = 230 → clamped to 0).
- **Impact:** disproportionate punishment for small repos; `code_quality` no longer reflected defect density. Classification remained correct (P0_zero blocks regardless), so this is scoring proportionality, not a correctness/convergence defect — hence P3.
- **Fix:** kloc floor raised to `1.0` (a sub-1000-line file is scored as one unit) and penalty contribution capped at 100. Bounded [0,100], monotonic in repo size.
- **Regression tests:** `TestQualityScoreProportionality` (tiny repo not zeroed; bounded + monotonic; clean repo = 100).

### R3-02 — Tautological security test (P3, test integrity)
- **Reproduced:** `tests/test_security.py::test_tooling_commands_not_shell_interpreted` was `assert True  # Verified via code inspection` — asserted nothing at runtime.
- **Impact:** false confidence; the "subprocess not shell-interpreted" property was untested.
- **Fix:** test now introspects `Engine._run_tooling` source and asserts the real controls (`subprocess.run`, `shell=False`, no `os.system`/`shell=True`, `timeout=300`).
- **Regression test:** `TestNoTautologicalTests` — scans all `test_*.py` for bare `assert True` placeholder bodies, fails if any reappear.

## Claims that survived falsification (no change needed)

- Provider fallback has no retry amplification; provenance intact; OPEN circuits honored.
- Subclass system is fail-closed for unknown rules.
- Convergence cannot be reached with an open P0 on a real audit (live-verified).
- Evidence chain detects tamper, deletion, reorder, and forged genesis; survives reload.
- Sandbox blocks sibling-prefix, absolute-path escapes; dry-run is side-effect free.

## Verification (post-fix)

| Check | Result |
|---|---|
| `pytest tests/ -q` | **206 passed** (202 + 4 new: 3 quality + 1 tautology guard) |
| `mypy src/aura/analyzer.py` | clean |
| `aura doctor` | All systems OK |
| version | 3.5.2 (unchanged — fixes are patch-level) |

## Verdict

The v3.5.2 baseline **survived adversarial validation** on all primary attack vectors
(provider, convergence, evidence, sandbox, state machine). Two P3 defects (scoring
proportionality, one tautological test) were found, reproduced, fixed, and covered by
regression tests. No P0/P1 false-convergence or security bypass was reproducible.

**FINAL CONVERGENCE criteria for the audit campaign: met** — no material new
false-convergence, security, or reliability defects remain reproducible against the
hardened baseline. Residual known limitations are documented (LIMITATIONS.md,
README "What AURA does NOT yet do") and are honesty disclosures, not defects.
