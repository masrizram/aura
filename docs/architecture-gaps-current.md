# Architecture Gaps — discovered during blind rebuild 2026-08-22 (RULE 9)

> Each gap: identifier, discovery evidence, reproduction, root cause, severity, status.
> Implementation happens ONLY after reproduction — see RULE 10.

## GAP-DB-PATH-RESOLUTION-01 (CRITICAL)

**Claim:** `DatabaseConfig.path = ".aura/state/aura.db"` is treated as relative to the
process CWD, not to the target `repo_root`.

**Evidence:** `db.py:202` `self._path = Path(config.path)` — no join with any repo_root.
`Engine.__init__` does not adjust either (`engine.py:70-84`).

**Reproduction:** create a tiny target at a temp dir, then `Engine(tempdir).run_audit()`
**while the process CWD is `C:/laraenv/www/aura`** — the SQLite file is created at
`C:/laraenv/www/aura/.aura/state/aura.db`, NOT inside the target.

**Impact:** Running AURA against target X via `aura audit --repo /path/to/X` from a
different working directory misplaces the entire audit DB, checkpoint, memory file, and
any per-repo evidence. Two targets audited from the same CWD share the same DB. The CLI
`--repo` flag, by design, does *not* chdir.

**Root cause:** config uses a relative default; `Database` never anchors it; no code
resolves the path against the Engine's own `repo_root`.

**Severity:** CRITICAL for multi-repo usage; invisible for the common CLI case of
`cd <repo> && aura audit`.

**Status:** ✅ IMPLEMENTED — `db.Database` ctor now takes optional `repo_root`; engine wires it (engine.py:74). Regression tests: tests/test_architecture_gaps.py::TestGAPDBPathResolution01 (3 tests).

## GAP-CLI-VERSION-BANNER-02 (LOW)

**Claim:** CLI `--help`/`--version` banner literal says `v3.5.0` while module
`VERSION = "3.5.3"`.

**Evidence:** `cli.py:42` `VERSION = "3.5.3"`; `cli.py:96` docstring literal ends `...
Engine v3.5.0`.

**Impact:** misleading operator feedback; breaks any downstream parser trusting the
banner as the version source. Cosmetic but part of RULE 13 honest-output requirements.

**Status:** ✅ FIXED — banner now uses `VERSION` module constant via f-string-in-click-
docstring replacement.

## GAP-DOMAIN-WAVE-EXPOSED-03 (MEDIUM)

**Claim:** 29 of 40 registered audit domains have no runtime auditor; the engine's
public claim "40-domain registry" is honest only when paired with "11 concrete auditors
in Wave 1".

**Evidence:** AST extraction of `class \w+Auditor\(BaseDomainAuditor\)` = 11 classes;
`WAVE_REGISTRY = {1: [...11 auditors...]}` with literal comment `# Wave 2-4 to be populated`
(domain_auditor.py:932-936). Live `run_all_legacy()` on temp repo returned exactly 11
non-meta keys + `_framework` + `_synthesis`.

**Impact:** users could assume 40 live checks. Documentation reflects reality;
no implementation needed beyond docs (the register's other 29 are *intended* Wave 2-4 work).

**Status:** documented in `architecture/README.md` §6 and `component/component-diagram.md`.

## GAP-VALIDATORS-OFFLINE-04 (MEDIUM)

**Claim:** `validate_finding_state_integrity`, `validate_gate_evidence_integrity`,
`validate_gate_findings_crosscheck`, plus `EvidenceValidator` trio are library-only —
engine never calls them at runtime.

**Evidence:** grep over `engine.py` reveals zero call sites; they appear only in
`adversarial.py` self-test campaigns and tests.

**Impact:** stated invariants ("no illegal finding transitions", "gate flip needs evidence")
are enforced by convention/engine construction, not by a runtime validator. A direct DB
writer can bypass them.

**Status:** documented in `decision-validation/invariants.md` L-01..L-07. No code change —
wiring them in would duplicate engine's own converged-classification logic.

## GAP-SILENT-FALLBACK-05 (LOW)

**Claim:** domain orchestrator → legacy 12-role fallback is *silent* (no audit_log entry).

**Evidence:** `engine.py:226-232` — `try/except` catches all exceptions from
`self.domain_orch.run_all_legacy()` and calls `self.adversarial.run_all(self.repo_root)`
without recording which path was taken.

**Impact:** post-hoc audits cannot distinguish "orchestrator ran" from "legacy ran"
from audit_log alone; `DomainAudit` info message only discloses domain count.

**Status:** recorded as observability gap (no implementation in this mission).

## GAP-ENGINE-JUDGE-DIVERGENCE-06 (DOCUMENTED / ACCEPTED)

See `decision-validation/convergence.md` (dual 12-gate systems). Probed: same clean
state ⇒ judge converged=True, engine would stay CONDITIONALLY_READY without LIMITATIONS.md.
By construction the judge only runs **after** the engine already declared
PRODUCTION_READY, so the divergent scenario cannot corrupt convergence in the real loop.

**Status:** documented; accepted by design; no fix.

## GAP-UNUSED-ASYNC-STACK-07 (DOCUMENTED)

`aiosqlite`/`pytest-asyncio` extras exist but there is no async code path (no `async def`
outside tests). Declared in `[project.optional-dependencies]`.

**Status:** documented; no implementation.
