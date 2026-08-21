# Changelog

All notable changes to the AURA Audit Engine.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.5.0] — 2026-08-21

### Added

- **Semantic Code Intelligence** — AST parsing, taint analysis (source→sanitizer→sink), data-flow tracking, and sanitizer capability matrix for 25+ sanitizers × 6 sink types.
- **Expression-Aware Detection** — f-string SQLi, qualified method calls (`hashlib.md5`), string concatenation SQLi, PHP variable interpolation, Go string concat SQLi, and string-concat path traversal.
- **Execution Context Layer** — classifies every file (PRODUCTION_CODE, TEST_CODE, MIGRATION_CODE, DOCUMENTATION, GENERATED_CODE, THIRD_PARTY, INFRASTRUCTURE, etc.) with confidence modifiers per context.
- **Finding Subclass System** — separates CODE_DEFECT, SECURITY_ADVISORY, ENVIRONMENT_BLOCKER, GOVERNANCE_FINDING, TEST_QUALITY, CODE_QUALITY, and INFORMATIONAL for gate-aware scoring.
- **40-Domain Audit Registry** — 11 active domain auditors (DEPENDENCY, CONFIGURATION, SECRET, CRYPTOGRAPHY, INJECTION, PATH_AND_FILE, DESERIALIZATION, AUTHENTICATION, AUTHORIZATION, SESSION, INPUT_VALIDATION) with shared intelligence layer.
- **Shared Intelligence Layer** — pre-built file index, dependency manifest parsers (7 formats), and framework detection shared across all domain auditors.
- **Repository Memory** — learns project sanitizers, framework primitives, and safe patterns across audit cycles for higher precision.
- **Confidence Classification** — TRUE_POSITIVE, LIKELY_TRUE, UNCERTAIN, LIKELY_FALSE_POSITIVE, FALSE_POSITIVE, MITIGATED with per-finding evidence graphs.
- **CWE/OWASP/CVSS Knowledge Base** — 21+ CWE entries mapped to detection rules with severity and exploitability scoring.
- **Framework-Aware Scoring** — Laravel, Django, FastAPI, Flask, Express, Spring, Rails security primitives recognized and weighted.
- **Directional Taint Analysis** — sanitizer capability matrix checks per sink type (HTML≠SQL≠SHELL≠URL≠JS≠PATH).
- **Benchmark v3 Framework** — 500+ case generation, mutation engine (6 operators), metamorphic testing, capability registry, CI regression gate.
- **Benchmark v2 Results** — Recall 100%, F1 96.8%, Precision 93.8% on 25-case, 6-language ground-truth benchmark.
- **Multi-Language Analyzer** — 62 language groups, 650+ rules, 130+ file extension mappings, expression-aware patterns.
- **`.env.example`** with comprehensive template (no real credentials).

### Changed

- **Engine core** — 5 bugs fixed (remediation table schema, adversarial count accuracy, git status None guard, Haskell glob detection, json import optimization).
- **Convergence gates** — P2_zero and critical_security now use finding subclass (advisories don't block).
- **Score computation** — normalized per-severity penalty (P0=15, P1=8, P2=3, P3+=1) with floor score for large projects.
- **Project type detection** — composer.json checked before package.json for PHP projects.
- **Test coverage detection** — project-aware source directories (app/, src/, lib/, includes/, modules/, routes/).
- **Type checking** — `# type: ignore[code]` → P4 (acceptable), bare `# type: ignore` → P2.
- **Context-aware suppression** — findings in docs/tests/migrations automatically suppressed (unless P0).
- **Version** — bumped from 1.0.0 to 3.5.0.

### Fixed

- **Data lineage invariant** — `combined_raw - intra_dupes - cross_overlap = unique` now always holds.
- **Circular convergence dependency** — consecutive_clean gate reads previous cycle convergence, not current.
- **CONDITIONALLY_READY counter** — consecutive_converged_cycles now increments for CONDITIONALLY_READY, not just PRODUCTION_READY.
- **Test coverage double-counting** — test coverage computed once in `_to_finding_dicts`, not duplicated in ancillary.
- **Scanner skip-dir completeness** — `.tools/`, `.terraform/`, `bower_components/`, and 15+ other patterns added.
- **AUTHZ false positives** — SQLAlchemy model definitions (Mapped, ForeignKey) excluded from authorization scan.
- **PATH false positives** — `__DIR__`-based paths and `dirname()` recognized as safe in context.
- **Remediation table** — SQL schema with real newlines (not literal `\n\n`), table now creates correctly on fresh DBs.
- **139/139 tests pass** — zero unexpected failures.

### Verified

- **External convergence proof** — Vidbro (FastAPI) reached PRODUCTION_READY at cycle 4, 12/12 gates, 91/100.
- **Regression resurrection** — injected P0 correctly detected, NOT_READY → fix → re-converged to PRODUCTION_READY.
- **Cross-repository** — Klinik (raw PHP) 42/100, Laravel 88/100, Vidbro 89/100, Benchmark recall 100%.
- **Semantic memory** — learned sanitizers across cycles improved score stability.

---

## [1.0.0] — 2026-08-14

### Added

- Autonomous remediation engine (`aura auto-fix`).
- 12 deterministic convergence gates with zero LLM involvement.
- 7 safeguards (A-G): infinite loop protection, no-progress detection, same-finding attempt cap.
- 12 finding statuses including terminal states.
- Durable checkpointing (`--resume` flag).
- Evidence chain per cycle with cryptographic hash chain.
- `remediation_attempts` table for persistent LLM fix tracking.
- Whitespace-normalized fuzzy matching for robust patch application.
- 10 CLI commands.
- 139 automated tests + 16/16 self-test adversarial campaigns.
- `.env` configuration via python-dotenv.

### Security

- LLM API key loaded from `AURA_LLM_KEY` environment variable.
- `.gitignore` blocks `.env`, `.aura/state/`, and runtime artifacts.

[3.5.0]: https://github.com/aura/aura-audit/releases/tag/v3.5.0
[1.0.0]: https://github.com/aura/aura-audit/releases/tag/v1.0.0