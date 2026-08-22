# Finding Validation

> How a finding moves from detection to verified — and which parts are gated vs advisory.

## Identity rule (fundamental)

A finding's identity is **content-derived**:

```
finding_id = f"F-{sha256(f'{file}:{line}:{rule}')[:12]}"   (engine.py:60-68)
```

Same (file, line, rule) ⇒ same ID across cycles. This is what makes regression detection
and `no_material_new_findings` possible.

## Subclass classification (finding_subclass.py)

`classify_finding(rule)` → one of 8 subclasses:

- CODE_DEFECT (default if unrecognized or in CODE_DEFECT family)
- SECURITY_ADVISORY (DEP-*)
- TOOLING_FAILURE
- ENVIRONMENT_BLOCKER (GIT-ERROR, GIT-DIRTY)
- GOVERNANCE_FINDING (LICENSE-*, SECURITY-POLICY-*)
- TEST_QUALITY (TEST-COV, PY-ASSERT)
- CODE_QUALITY (PY-TYPE-IGNORE*, PY-PRINT, PY-STAR-IMPORT, PY-GLOBAL)
- INFORMATIONAL (LANG-INFO)

Mapping first tries exact match, then prefix match (e.g. `INJ-` prefix in map).
Unknown rules default to CODE_DEFECT — conservative (over-blocks rather than under-blocks).

## Gate-blocking rules (`is_blocking_for_gate`)

Only CODE_DEFECT blocks: `P_zero` (any) and `critical_security`/`critical_correctness`.
Advisories NEVER block any gate — they live in the report, not the gate.

## Filtering applied before persistence (engine._phase_correlate)

| Filter | Rule | Effect |
|---|---|---|
| Test-file exclusion | `MultiLangAnalyzer` skips `test_*.py`, `*_test.py`, `.test.`, `.spec.`, `conftest.py` | never reach CORRELATE |
| Lockfile exclusion | skips `uv.lock`, `poetry.lock`, `package-lock.json` | no noise |
| Skip dirs | `node_modules, vendor, .venv, __pycache__, dist, build, …` | third-party not audited |
| Comment suppression | pattern match ignored if line starts w/ `#`, `//`, `/*`, `*`, `--` | reduces false positives |
| Context suppression | `ExecutionContextClassifier.should_suppress_finding` per finding (P0 always passes) | TEST/DOC/GENERATED/THIRD_PARTY suppressed; migration rule-aware |
| Semantic mitigation | drop findings whose enriched confidence_level is MITIGATED or FALSE_POSITIVE | excluded from CONVERGENCE gate eval only (still persisted) |

## Transition rules (state_machine)

12 statuses; whitelist + forbidden list (see `docs/state/finding-state.md`).
The validators that enforce these are **opt-in library functions** — the engine's own
write path calls `db.update_finding_status` directly and never passes through the
validators (verified by grep). A finding's status is therefore always one of the 12
(validated at DB CHECK constraint), but an *illegal transition* is not prevented by the
engine — it is prevented by the remediation loop's own sequencing
(OPEN→FIXED→VERIFIED after clean re-audit) and by the DB-level CHECK constraint on values.

## Verification gate input (engine._phase_verify)

The VERIFY phase does not auto-verify findings. It only counts:
- `remediation_verified_count` — how many findings carry independent evidence (set elsewhere).
- The verification gate passes iff no finding is in FIXED.

## Who can mark VERIFIED

AutonomousRemediationLoop only: after applying a fix, the next audit cycle is run and
the regression detector confirms the finding did not re-appear. Then status → VERIFIED.
