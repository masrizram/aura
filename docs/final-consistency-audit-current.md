# Final Consistency Audit — Blind Documentation Rebuild (2026-08-22)

> RULE 7 + RULE 13 record. Every documented claim was re-checked against source/tests/
> runtime probes after the rebuild. Adversarial falsification attempted on the riskiest claims.

## Method

1. Baseline recorded pre-deletion (BASELINE.md).
2. 46 current-state docs deleted; 8 historical artifacts preserved untouched in `docs/history/`.
3. All 23 src modules read directly; 3 parallel subagents dispatched for semantic.py,
   domain_auditor.py, adversarial.py+cli.py; 6 live runtime probes executed.
4. 35 docs rewritten from scratch across the 11 mandated categories.
5. Architecture gap audit discovered 7 gaps; 2 reproduced and implemented (RULE 10).
6. Every claim in the new docs re-verified via an automated 22-check probe matrix.
7. Adversarial falsification ran against the riskiest claims (convergence behavior,
   sandbox containment, DB path, banner version, silent fallback).

## Adversarial falsification results (attempted disproof)

| Falsification target | Attack | Outcome | Verdict |
|---|---|---|---|
| "1×P3 → PRODUCTION_READY" (C-17) | tiny repo + real P3 finding + valid LIMITATIONS.md + 2 consecutive cycles | Cycle 4 → PRODUCTION_READY, gates 12/12, score 100 | claim HOLDS |
| "DB path anchored to repo_root" (C-38, post-fix) | audit two distinct temp repos from foreign CWD | each repo got its own `.aura/state/aura.db`; cycle counts independent | claim HOLDS |
| "CLI banner == VERSION" (C-39, post-fix) | read callback docstring + invoke `--help` | banner shows `v3.5.3`, stale `v3.5.0` absent | claim HOLDS |
| "Sandbox containment rejects traversal" (C-31) | `apply_fix("../outside.py")` and `apply_fix("src/../../etc/evil.py")` | both rejected with `SANDBOX REJECTED: path traversal` | claim HOLDS |
| "Dangerous pattern advisory rejects `os.system`" (C-31) | `apply_fix` with `new_code="import os; os.system('id')"` | rejected with `SANDBOX REJECTED: dangerous patterns` | claim HOLDS |
| "old_code mismatch safety" (C-31) | apply_fix with fabricated old_code | rejected: `old_code not found near line ...` | claim HOLDS |
| "rollback restores originals" (C-31) | apply then rollback | file content reverted to original | claim HOLDS |
| "Silent fallback to legacy 12 roles" (GAP-05) | grep audit_log for fallback marker after successful run | no marker (orchestrator succeeded; fallback not triggered) — fallback path verified by code inspection, runtime branch untestable without injected failure | claim HOLDS (as documented) |
| "Domain wave isolation per auditor" (C-06) | source inspection of try/except inside wave loop | `except Exception: all_findings[domain_id]=[]` per auditor | claim HOLDS |
| "Dual gate divergence" (C-18) | ConvergenceJudge on clean state without LIMITATIONS signal | judge converged=True; engine would say CONDITIONALLY_READY | claim HOLDS |

No falsification succeeded. Where behavior was originally misdocumented (P2→NOT_READY vs
CONDITIONALLY_READY; banner string) the docs/code were corrected before this audit ran.

## Consistency matrix

See `docs/component/consistency-matrix.md` — 40 claims C-01..C-40, all classified
ACCURATE. Zero INCORRECT, zero UNVERIFIED, zero OUTDATED at close.

## Residual honest statements

- `mypy src/aura` reports **116 errors** (13/23 files), unchanged from baseline — these
  are pre-existing strict-mode typing issues (e.g. `Unused "type: ignore" comment`,
  `Incompatible types in assignment`), not regressions.
- `ruff check src tests` reports **892 errors** (top: E501 line-too-long ×425, F401 ×71),
  unchanged from baseline.
- The REMEDIATE phase of `aura audit` does not itself apply fixes; remediation is
  exclusive to `aura auto-fix` (verified: `_phase_remediate` only inserts DB rows).
- 29 of 40 registered domains are Wave 2-4 (registry-only metadata). Documentation,
  README, and gap ledger all carry this number.
- `validate_*` state-machine validators remain opt-in library functions; engine enforces
  the rules by construction, not by calling those validators.

## Sign-off

Documentation rebuilt blind; every diagram traces to code; every number to a probe or
source line; every gap either implemented (with regression tests) or documented with
reproduction. Baseline gates all green or unchanged.
