# AURA v3.5 — Autonomous Software Reliability Engine

[![Tests](https://img.shields.io/badge/tests-139%2F139-brightgreen?style=flat-square)](https://github.com/aura/aura-audit)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Languages](https://img.shields.io/badge/languages-51%20groups%20(17%20with%20rules)-orange?style=flat-square)](https://github.com/aura/aura-audit)
[![Rules](https://img.shields.io/badge/rules-127-yellow?style=flat-square)](https://github.com/aura/aura-audit)
[![Benchmark](https://img.shields.io/badge/benchmark%20F1-96.8%25-brightgreen?style=flat-square)](https://github.com/aura/aura-audit)

AURA is an autonomous audit-remediate-verify-converge engine. It scans repositories across 51 language groups (17 with active rules, 127 patterns total), applies semantic code intelligence (AST parsing for Python; regex-based structural recognition for PHP/JS; heuristic taint detection via ±20-line context windows), generates LLM-candidate patches, verifies fixes with real tool output, re-audits, and converges only when all 12 deterministic gates pass — zero LLM involvement in gate decisions.

[Website](https://github.com/aura/aura-audit) · [Docs](https://github.com/aura/aura-audit#readme) · [Benchmark](https://github.com/aura/aura-audit#benchmark) · [Changelog](CHANGELOG.md)

## Install

Requires Python 3.11+.

```bash
# Clone
git clone https://github.com/aura/aura-audit.git
cd aura-audit

# Install with dev dependencies
uv pip install -e ".[dev]"
```

Or install the published package:

```bash
pip install aura-audit
```

## Quick start

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env: set AURA_LLM_KEY to your API key (required for autonomous remediation)

# 2. Initialize and audit
python -m aura init
python -m aura audit

# 3. View results
python -m aura verify        # All findings grouped by severity
python -m aura trend         # Score trajectory across cycles
python -m aura report        # Markdown audit report

# 4. Autonomous remediation
python -m aura auto-fix --max-cycles 5
```

Static audit (`aura audit`) works without LLM credentials. Autonomous remediation (`aura auto-fix`) requires `AURA_LLM_KEY` set in `.env`.

## How it fits together

- The **[Analyzer](src/aura/analyzer.py)** scans 51 language groups with 127 expression-aware patterns. 17 languages have active rules; 34 are file-extension recognition only (zero rules, recognized for language stats).
- **[Domain Auditors](src/aura/domain_auditor.py)** attack the codebase from 40 specialized perspectives (11 active).
- **[Semantic Intelligence](src/aura/semantic.py)** layers AST parsing (Python: stdlib `ast`; PHP/JS: regex-based structural recognition), heuristic taint analysis (±20-line context windows with directional sanitizer capability matrix), and CWE/OWASP/CVSS mapping.
- **[Execution Context](src/aura/execution_context.py)** classifies every file (production/test/migration/docs/generated/third-party) for false-positive suppression.
- **[Finding Subclass](src/aura/finding_subclass.py)** separates CODE_DEFECT from SECURITY_ADVISORY, ENVIRONMENT_BLOCKER, and GOVERNANCE_FINDING.
- **[Convergence Engine](src/aura/engine.py)** runs a 13-phase lifecycle with 12 deterministic gates and 7 safeguards.
- **[LLM Remediation](src/aura/llm.py)** generates candidate patches (UNTRUSTED CLAIM). The engine independently verifies with real tool output.

```text
Repository → Discover + Model → Multi-Lang Scan → Domain Auditors
→ Correlate + Context + Subclass → Semantic Intelligence
→ Remediate → Verify → Re-Audit → 12 Gates → PRODUCTION_READY
```

## Security

All LLM output is treated as **UNTRUSTED CLAIM** until validated by independent tool execution evidence. No convergence gate decision involves LLM input. Every finding requires:

1. Real tool execution (pytest, lint, build) captured by the orchestrator
2. Exit codes captured from the actual tool, not the LLM
3. Independent verifier confirmation (not self-verified)
4. Regression audit that proves no re-introduced defects

API keys are loaded from environment variables only — never hardcoded. `.env` is gitignored. See `.env.example` for the configuration template.

## Architecture Notes\n\n### AST Depth by Language\n\n| Language | AST Parser | Implementation |\n|---|---|---|\n| Python | ✅ Real AST | Python stdlib `ast` module — full parse tree with node types, children, line/col |\n| PHP | ⚠️ Structural | Regex per-line tokenizer wrapped as ASTNode objects — recognizes superglobals, function calls, SQL patterns, include/require |\n| JavaScript/TypeScript | ⚠️ Structural | Regex per-line pattern matching — recognizes DOM manipulation, eval/Function, fetch/XHR |\n| SQL | ❌ None | Detected via regex in _PATTERNS only |\n| All other languages | ❌ None | Regex pattern matching only via _PATTERNS |\n\n### Taint Analysis Implementation\n\nAURA's taint analysis uses **heuristic ±20-line context window substring matching**, not AST-level dataflow tracing:\n\n1. **Source detection**: Regex for `$_GET`, `$_POST`, `request.args`, etc. in the context window\n2. **Sanitizer detection**: Regex for `htmlspecialchars()`, `filter_var()`, ORM abstractions (`Model::find`, `.filter(`), etc.\n3. **Sink detection**: Regex on the finding line for `eval`, `exec`, `innerHTML`, etc.\n4. **Sanitizer capability** is directional (e.g., `htmlspecialchars()` → HTML:0.85, SQL:0.0, SHELL:0.0)\n\nThis is NOT real dataflow tracing — there is no variable propagation graph, no SSA form, and no inter-procedural analysis. The ±20-line window heuristic produces reasonable results for linear code but cannot track sanitization across function boundaries.\n\n### Dual Gate Systems\n\nAURA has two separate 12-gate evaluation systems:\n\n| System | Gates | Location | Role |\n|---|---|---|---|\n| **User-facing gates** | P0_zero…module_dependency_integrity | `state_machine.py` | Displayed in CLI output; evaluates actionable findings |\n| **Internal judge gates** | G01…G12 | `convergence.py:ConvergenceJudge` | Used by autonomous remediation loop; evaluates convergence proof integrity |\n\nThese are documented as \"separate but correlated\" in the code. The engine uses the user-facing gates for CLI display; the autonomous loop uses the internal judge for convergence decision.\n\n### Finding ID Stability\n\nFinding IDs are now **content-hash based** (SHA-256 of `file:line:rule`), not timestamp-based. This ensures IDs are stable across cycles, enabling the `regression` gate to actually detect reappearing findings via set intersection of `prev_ids & current_ids`.\n\n## Documentation

| Goal | Start here |
|---|---|
| Understand the engine | [Engine core](src/aura/engine.py) · [State machine](src/aura/state_machine.py) · [Convergence](src/aura/convergence.py) |
| Configure AURA | [Configuration](src/aura/config.py) · [`.env.example`](.env.example) |
| Run audits | CLI: `aura init` · `aura audit` · `aura verify` · `aura trend` · `aura report` |
| Autonomous remediation | CLI: `aura auto-fix --max-cycles 5` · `--dry-run` · `--resume` |
| Understand findings | [Finding subclass](src/aura/finding_subclass.py) · [Execution context](src/aura/execution_context.py) |
| Extend domain auditors | [Domain auditor registry](src/aura/domain_auditor.py) (40 domains, 11 active) |
| Validate detection | [Benchmark v3](src/aura/benchmark_v3.py) · 61 cases · 10 languages · Frozen targets |

## Benchmark

| Metric | Score | Cases | Languages |
|---|---|---|---|
| Recall | **100%** | 25 ground-truth | 6 languages |
| Precision | **93.8%** | 1 FP (parameter name) | |
| F1 | **96.8%** | 0 critical misses | |
| Framework | Benchmark v3 | 61 cases, 10 languages | Frozen targets: F1≥95%, Recall≥95% |

Frozen targets for v3.6: Recall ≥95%, Precision ≥95%, F1 ≥95%, critical FN = 0 on ≥500 cases across ≥12 languages.

## External Validation

| Repository | Type | Score | P0 | P1 | Classification |
|---|---|---|---|---|---|
| Klinik | Raw PHP | 42/100 | 1* | 4* | NOT_READY |
| Laravel 13.x | PHP Framework | 88/100 | 0 | 0 | CONDITIONALLY_READY |
| Vidbro | FastAPI | 89/100 | 0 | 0 | PRODUCTION_READY (cycle 4) |

\* False positive — raw PHP patterns without framework context

## Regression Resurrection Proof

```text
Cycle 5: PRODUCTION_READY — 12/12 ✅ Converged
Cycle 6: NOT_READY        — 10/12 ❌ P0 eval() injected + detected
Cycle 7: PRODUCTION_READY — 12/12 ✅ Re-converged after fix
Cycle 8: PRODUCTION_READY — 12/12 ✅ Durable (consecutive)
Cycle 9: PRODUCTION_READY — 12/12 ✅ Durable
```

PRODUCTION_READY is falsifiable and reversible — AURA detects regression, invalidates status, and re-converges.

## Development

```bash
git clone https://github.com/aura/aura-audit.git
cd aura-audit
uv pip install -e ".[dev]"
python -m pytest tests/ -q
```

See [CHANGELOG.md](CHANGELOG.md) for version history and [ENGINE.md](src/aura/engine.py) for the 13-phase lifecycle architecture.

## License

[MIT](LICENSE) © AURA Engineering. See [CHANGELOG.md](CHANGELOG.md) for release history and contributors.