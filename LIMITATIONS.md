# AURA v3.5 — Known Limitations

This file is validated by AURA's convergence gate `limitations_documented`.
It must contain structured sections with specific limitation descriptions.
Empty or placeholder content will cause the gate to FAIL.

---

## 1. Detection Engine

- **Regex-based primary scanning:** The primary detection layer uses 127 regex patterns
  across ~15 languages. This is NOT equivalent to true static analysis — there is no type
  resolution, no variable scoping, and no inter-procedural analysis in the regex phase.
  False negatives are possible for vulnerabilities that require deep semantic understanding
  (e.g., indirect taint through multiple function calls).

- **Limited AST support:** Real AST parsing is available for Python only (via the stdlib
  `ast` module). PHP parsing uses a regex-based tokenizer. JavaScript/TypeScript use
  regex-based structural recognition. Other languages have regex-only detection with
  no structural parsing at all.

- **Language capability varies:** The 51-language-group LANG_EXTS table maps extensions to
  language names. Actual detection patterns exist for only ~17 languages. Many listed
  languages have empty pattern lists and are effectively "discovered only."

- **±20-line taint window:** The directional taint analysis (with sanitizer capability
  matrix) operates within a ±20-line context window using substring matching. There is
  no SSA form, no variable propagation graph, and no real inter-procedural dataflow
  tracking. This is explicitly documented in the README.

## 2. Remediation & LLM

- **LLM output is UNTRUSTED:** All LLM-generated fixes are tagged `untrusted=True`
  and require independent verification via tool exit codes. However, the LLM may
  generate semantically incorrect fixes that pass surface-level tests while introducing
  new bugs. AURA's re-audit mechanism catches some but not all of these.

- **No sandboxing for LLM-generated code:** When the autonomous remediation loop applies
  LLM-generated patches, the code is written directly to the repository's filesystem
  and tooling commands are executed in the same process context as AURA. This is a
  known security gap. The `auto-fix` command mitigates this with `--dry-run` mode
  and automatic rollback on tooling failure.

- **Single provider model:** The LLM client (`llm.py`) supports one OpenAI-compatible
  endpoint at a time. Provider fallback and multi-model routing were added in v3.5.1
  (`providers.py`) but are not yet threaded through all code paths.

## 3. Convergence & Gates

- **Dual gate systems:** AURA has two separate 12-gate systems: user-facing gates in
  `state_machine.py` (`P0_zero`, `P1_zero`, etc.) and internal judge gates in
  `convergence.py` (`G01`–`G12`). These are documented as "separate but correlated."
  In theory, they could produce different convergence decisions for the same state.
  Cross-validation between the two systems is not enforced at runtime.

- **Limitations gate hardening (v3.5.1):** The `limitations_documented` gate now validates
  structured content (existence, minimum length, no placeholders, bullet-point descriptions
  under section headers). Previously it only checked file existence.

- **False convergence risk:** AURA can theoretically reach `PRODUCTION_READY` on projects
  with zero tests if all regex-detected findings are resolved. There is no minimum test
  coverage ratio enforced at the gate level.

## 4. Performance & Scalability

- **Single-threaded scanning:** File analysis runs sequentially with no concurrency.
  Large repositories (>5000 files) will be slow. The ScaleConfig in `config.py` warns
  at 500 files and requires chunked audit above 2000.

- **No incremental analysis:** Every audit cycle performs a full repository scan.
  There is no file hash cache, no changed-file detection, and no dependency-based
  invalidation. This is acceptable for small-to-medium projects but becomes
  prohibitive for large codebases with frequent re-audits.

- **SQLite single-writer:** The database layer uses SQLite with WAL mode. This is
  appropriate for single-machine, single-user architecture but limits concurrent
  access and horizontal scaling.

## 5. Cross-File Analysis

- **No call graph:** Cross-file correlation fields exist in the domain auditor
  (`domain_auditor.py`) but are not yet implemented. There is no module graph,
  import graph, or call graph construction.

- **No inter-procedural analysis:** Each finding is evaluated in isolation at its
  file:line location. Function call chains, import chains, and cross-module
  dependencies are not analyzed.

## 6. Validation & Benchmarking

- **Small benchmark:** The existing benchmark (`benchmark.py`) uses only 25 cases
  across 6 languages. The v3 benchmark framework (`benchmark_v3.py`) supports
  500+ case generation but cases are not yet fully populated.

- **Self-reported external validation:** Scores for external repositories
  (Laravel 88, Vidbro 89, Klinik 42) are self-reported in the CHANGELOG.
  Independent third-party validation has not been performed.

- **No CI/CD integration tested:** GitHub Actions template exists (`.github/workflows/aura-gate.yml`)
  but has not been validated in a live CI environment.

## 7. Security of AURA Itself

- **No self-audit:** AURA auditing its own repository produces findings but has not
  undergone independent security review. The tool treats audited repositories as
  potentially hostile but does not run in a sandbox or container.

- **Subprocess execution:** Tooling commands (pytest, semgrep, etc.) are executed
  via `subprocess.run()` in the same user context. A malicious repository could
  theoretically exploit this through crafted configuration files.

---

*This file was generated as part of the AURA v3.5.1 limitations gate hardening.
Last reviewed: 2025-08-22*