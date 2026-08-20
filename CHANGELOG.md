# Changelog

All notable changes to the AURA Audit Engine are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] — 2026-08-20

### Added

- **Package manager support**: AURA can now be installed via npm, pip, Homebrew, Composer, or a universal shell installer.
  - `package.json` — npm package with `aura`, `aura-ps`, and `aura-audit` bin entries, plus a `postinstall` hook that bootstraps `.aura/` and `.githooks/` into the install target.
  - `setup.py` — pip package with `click`, `pyyaml`, and `rich` dependencies for a future Python orchestrator; exposes `aura` as a console entry point.
  - `.github/homebrew/aura-audit.rb` — Homebrew formula with a dependency on `powershell`, installing bin scripts and shareable bootstrap data into the cellar.
  - `composer.json` — PHP project definition registering `bin/aura.sh` and `run-audit.sh`.
  - `install.sh` — universal bash installer that detects the OS, checks for PowerShell and git, downloads or copies the engine files, bootstraps `.aura/` and `.githooks/`, and installs bin scripts with optional symlinks.
  - `CHANGELOG.md` — this file.

- **Installation section** added to `README.md` with commands for all five installation methods.

### Changed

- README.md reorganized: Installation section inserted before Quick Start.

---

## [2.0.0] — 2026-08-19

### Added

- Complete engine rewrite: modular architecture with strict state machine enforcement.
- 12 convergence gates replacing the previous simpler readiness check.
- Multi-agent mode with independent auditor, adversarial auditor, remediator, verifier, regression auditor, and convergence judge roles.
- Self-test capability: adversarial campaign (12 attacks), false convergence campaign (9 attacks), false evidence campaign (10 attacks), git safety campaign (10 scenarios), mutation testing, failure recovery (7 scenarios).
- Evidence-based trust model: agent output treated as untrusted claims; tool exit codes, filesystem state, and independent verification required.
- State machine enforcement for all finding transitions with illegal transition rejection.
- Classification transition guards (NOT_READY → PRODUCTION_READY forbidden directly).
- Score monotonicity guard: overall_score cannot decrease or jump more than 15 points per cycle.
- Comprehensive `.gitignore` for runtime artifacts, campaign results, temp files, and secrets.

### Changed

- Engine layout restructured: `src/engine/`, `src/modules/`, `src/agents/` with `.aura/` reserved for state and reports.
- Bootstrap proxy at `.aura/run-audit.ps1` delegates to `src/engine/run-audit.ps1`.
- Cross-platform `run-audit.sh` wrapper with argument parsing and PowerShell auto-detection.

---

## [1.0.0] — 2026-08-18

### Added

- Initial release: single-agent audit-remediate-verify loop.
- Basic findings model: OPEN, IN_PROGRESS, FIXED, VERIFIED, REJECTED, DEFERRED, BLOCKED.
- Orchestrator-driven cycle prompt generation.
- State persistence in `.aura/state/`.
- Push command with interactive approval.

---

[2.1.0]: https://github.com/aura/aura-audit/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/aura/aura-audit/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/aura/aura-audit/releases/tag/v1.0.0