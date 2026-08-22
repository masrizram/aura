# CURRENT_BASELINE — AURA Documentation Rebuild Mission
Recorded: 2026-08-22 (pre-deletion baseline, RULE 1)

## Repository
- Path: C:\laraenv\www\aura
- Branch: main (tracking origin/main, clean sync)
- Commit: 60dee62aa0b80e74f277a11eea2e469e7edbad3d "fix: v3.5.3 — RUN #3 adversarial final audit (R3-01, R3-02)"
- Preceding: 83a1f33 (v3.5.2), 00d8b2a (v3.5.1), c6ebd93 (docs v3.5)
- Working tree: NO source modifications. Working tree contains ONLY deletions of previous current-state docs (52 files under docs/ + LIMITATIONS.md + q.md + repository.md), all recoverable from HEAD. No untracked files.
- Stash: (checked, see git log; none relevant)

## Toolchain (Windows host, git-bash shell)
- python: 3.11.15 (hermes venv)
- git: 2.54.0.windows.1
- uv: installed (build backend setuptools>=75)
- ruff: 0.16.3
- mypy: per .mypy_cache 3.11

## Quality Gate Results (baseline)
| Gate | Command | Result | Evidence |
|---|---|---|---|
| Unit+Integration Tests | `python -m pytest tests/ -q` | **206 passed, 0 failed** in 16.77s | collected 206; 10 test files all green |
| Build | `uv build` | **PASS** — `dist\aura_audit-3.5.3.tar.gz` + `dist\aura_audit-3.5.3-py3-none-any.whl` | exit 0 |
| Typecheck | `mypy src/aura` (strict=true) | **116 errors** in 13/23 files | baseline state; NOT introduced by this mission |
| Lint | `ruff check src tests` | **892 errors** (132 fixable) | top: E501=425, F401=71, PLC0415=61, E701=33, PLW1510=28, S607=27 |
| aura doctor | `python -m aura doctor` | **PASS** — git ✓, Python ✓, Database ✓, Config ✓ "All systems OK" | exit 0 |
| Packaging version | pyproject.toml | 3.5.3 | `[project] version="3.5.3"`, name="aura-audit" |
| CLI | `python -m aura --help` | OK — 11 commands: audit, auto-fix, doctor, health, init, log, report, status, trend, verify | banner "v3.5.0" (note: banner string ≠ package version 3.5.3) |

## Lint breakdown (ruff --statistics, top 30)
425 E501 (line-too-long), 71 F401, 61 PLC0415, 33 E701, 28 PLW1510, 27 S607, 26 F541, 25 S110, 21 I001, 20 RUF001, 20 W292, 14 F841, 10 N806, 9 E702, 9 UP045, 8 SIM102, 7 UP042, 6 C420, 5 E741, 5 PLW0108, 5 S108, 5 S608, 4 C408, 4 RUF005, 4 RUF059, 4 S603, 3 B007, 3 RUF002, 3 RUF012, 3 RUF013

## Notes
- pytest exit captured via verification_evidence: status=passed, canonical_command=pytest.
- ruff/mypy print errors but were piped; their nonzero counts are the raw baseline. No gate regression is acceptable per RULE 14 (same or better counts required; tests/build/doctor must stay green).
- pyproject description claims "51 language groups (127 rules)" and "12-gate deterministic convergence" and "40-domain audit registry" — these are CLAIMS to be verified against source in RULE 4 (memory notes say 62lang/650+rules/40-domain/12-gate: discrepancy must be resolved from code, not docs).
