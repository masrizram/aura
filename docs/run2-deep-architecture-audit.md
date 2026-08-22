# RUN #2 — Deep Architecture Audit (baseline `00d8b2a` / v3.5.1)

> **Discipline:** every finding below was REPRODUCED against the committed baseline before any fix. No speculative refactors. IMP-01..IMP-09 not reopened.
> **Method:** read previously-unread zones (engine `_to_finding_dicts`/`generate_report`/`get_status`, semantic scorer, remediation VERIFY tail, durable resume), grep-verified usage, live reproduction scripts.

## Reproduction log (evidence)

| ID | Reproduced | Evidence |
|---|---|---|
| R2-01 | ✅ live | `evaluate_all_gates` with a brand-new `finding_id="F-NEW"` P0 returned `no_material_new_findings=True` |
| R2-02 | ✅ live | reappeared finding at severity P3 → `regression=True` |
| R2-03 | ✅ design+string | every auto-detected tooling command ends with `|| true` → exit code forced 0 |
| R2-04 | ✅ live | `chat_with_fallback` with failing primary returned primary's error, never consulted healthy fallback |
| R2-05 | ✅ live | `compute_convergence_score` identical (85) for default vs wildly-different severity weights |
| R2-06 | ✅ code read | `DurableAutonomousLoop._resume` only adjusts `max_cycles`; `LoopSafeguard.finding_attempts`/`scores` not restored |

---

## R2-01 — Gate `no_material_new_findings` is blind (key mismatch)
- **Category:** Validation/convergence — false convergence
- **Severity:** P0
- **Root cause:** DB rows and `_to_finding_dicts` use key `finding_id`; `state_machine.evaluate_all_gates` (and `validate_gate_findings_crosscheck`, `validate_finding_state_integrity`) read `f.get("id")`, which is always `None` → `prev_ids` empty, `has_new_material` never True.
- **Impact:** The gate that must detect "a new P0-P3 appeared after convergence" never fires. A repo can gain a brand-new P0 and still pass `no_material_new_findings`. This is precisely the false-convergence class the engine exists to prevent.
- **Fix:** normalize identity with a single accessor `_fid(f) = f.get("id") or f.get("finding_id")` used in all three functions.
- **Regression test:** new P0 in `finding_id` form must set `no_material_new_findings=False`; also assert `id` form still works (backward compat).

## R2-02 — Regression detection blind to severity drift / re-opened non-P0-P2
- **Category:** Validation/convergence
- **Severity:** P1
- **Root cause:** `_phase_regression` builds `current_ids` filtered to severity P0–P2 only, and `prev_ids` filtered to status VERIFIED/FIXED. A finding that was VERIFIED then reappears as OPEN at severity P3 (e.g. after re-classification) is invisible to the intersection → `regression_pass=True`.
- **Impact:** Regressions in P3+ findings, or regressions accompanied by severity downgrade, never block the `regression` gate.
- **Fix:** widen `current_ids` to all current finding ids regardless of severity; keep `prev_ids` as VERIFIED/FIXED. Intersection = reappeared previously-resolved findings (any severity).
- **Regression test:** VERIFIED-then-reopened P3 with same `finding_id` → `regressions` non-empty → gate False.

## R2-03 — TEST phase auto-passes: `|| true` forces exit code 0 (fail-open)
- **Category:** Reliability / false convergence
- **Severity:** P0
- **Root cause:** `_detect_commands()` appends `2>&1 || true` to every auto-detected command (semgrep, bandit, gitleaks, tsc, pytest, npm, make, go, cargo). `_run_tooling` computes `success = (returncode == 0)`. The shell `|| true` forces 0 → `success=True` even when the tool fails.
- **Impact:** The TEST phase can report "tooling passed" while pytest/tsc/lint are actually failing. Because `verification` gate is only forced False when `tooling_passed` is False, a failing build can still converge. This is a direct fail-open path to false PRODUCTION_READY.
- **Fix:** remove `|| true`; capture the real exit code. Add config `engine.tooling.fail_open` (default `False`) to opt into informational-only tooling. Commands that may be absent are already guarded by `shutil.which` / file-existence checks, so `|| true` was never needed for robustness.
- **Regression test:** a tooling command that exits non-zero must record `success=False` and force `verification` gate False.

## R2-04 — ProviderRegistry never falls back
- **Category:** Provider reliability
- **Severity:** P1
- **Root cause:** `chat_with_fallback` picks the first non-OPEN provider and returns its response verbatim — if that provider returns an error (without its circuit being OPEN yet), the healthy fallback is never consulted. "Fallback" only engages after the primary's circuit has already opened (3+ failures), i.e. after the call already failed.
- **Impact:** Transient primary failure (single 500, timeout, DNS) produces a failed call despite a healthy fallback being registered. The documented "fallback routing" does not provide per-call resilience.
- **Fix:** on error response, try the next non-OPEN provider in priority order, up to N providers; return the first success or the last error. Do not retry the same provider (retry lives inside the provider — IMP-05 layering preserved).
- **Regression test:** failing primary + healthy fallback → response from fallback; all-failing → aggregated error.

## R2-05 — `severity_weights` is a dead parameter (config silently ignored)
- **Category:** Correctness / config drift
- **Severity:** P2
- **Root cause:** `compute_convergence_score(findings, severity_weights, gates)` accepts `severity_weights` but never reads it — penalties are hardcoded (P0×15, P1×8, P2×3, P3+×1). Engine builds the dict from config (`severity_weights = {k: v.weight …}`) and passes it, so users reasonably believe config weights shape the score. They do not.
- **Impact:** Config severity weights have zero effect on the convergence score — silent no-op, misleading configuration surface.
- **Fix:** make the weight→penalty mapping explicit and derived from config weights (normalized), OR remove the parameter and document that scoring penalties are fixed. Chosen: derive penalty per severity from config weights (scaled), preserving the 0–40 finding-score band.
- **Regression test:** different severity weight configs must produce different scores for the same finding set; default config reproduces current 85 for the reference case.

## R2-06 — Durable resume resets loop safeguards
- **Category:** Reliability / safeguard bypass
- **Severity:** P1
- **Root cause:** `DurableAutonomousLoop._resume` constructs no state bridge: it only sets `loop.max_cycles` and calls `run()`. `LoopSafeguard.iteration`, `scores`, `finding_counts`, and `finding_attempts` start at 0/empty on the resumed process.
- **Impact:** `MAX_SAME_FINDING_ATTEMPTS` and `NO_PROGRESS_CYCLES` can be defeated by interrupting and resuming — the safeguard counters reset, allowing unbounded retries of the same finding across resumes.
- **Fix:** persist safeguard state (`iteration`, `scores`, `finding_attempts`) into the checkpoint; restore it on resume.
- **Regression test:** save checkpoint with N attempts on finding F; resume; F's attempt counter is N (not 0).

---

## Additional defects confirmed (lower severity, fixed in same cycle)

## R2-07 — Version drift (3.5.0 in code vs 3.5.1 in CHANGELOG/docs)
- **Severity:** P3 (docs/packaging integrity)
- `src/aura/__init__.py:__version__`, `src/aura/cli.py:VERSION`, `pyproject.toml:version` all read `3.5.0` while CHANGELOG/docs declare `3.5.1`. **Fix:** bump all three to `3.5.2` (this cycle's release) so code, docs, and packaging agree.

## R2-08 — `Engine.evidence_chain` never receives entries (wiring gap)
- **Severity:** P2
- `Engine.__init__` constructs `EvidenceChain()` (in-memory, no path) but no phase ever calls `append()`. The tamper-evident chain from IMP-04 is never populated during a real audit. **Fix:** in `_phase_convergence`, append a `CONVERGED`/`ASSERTED`-level evidence entry per cycle (cycle id, gate summary, score) into the chain and mirror to the `evidence_chain` table via `db.insert_evidence_entry`.

## R2-09 — `_run_tooling` uses `cmd /c` on Windows for every command (shell injection surface)
- **Severity:** P2 (documented; behavior-preserving fix only)
- All tooling commands are auto-detected by AURA itself (not arbitrary user input), so risk is bounded; but `cmd /c` + `shell=False` is contradictory and documented as a partial control. No change this cycle beyond documenting; a full fix requires structured command specs (deferred — needs design).

---

### Not findings (checked, cleared)
- No circular imports (DAG re-verified).
- IMP-01..IMP-09 fixes intact (186/186 still passing pre-change).
- `compute_enriched_score` arithmetic bounded `[0,100]` — no defect.
- `db.insert_finding` ON CONFLICT preserves terminal statuses — correct by design.
