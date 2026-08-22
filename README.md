# AURA v3.5 — Autonomous Software Reliability Engine

[![Tests](https://img.shields.io/badge/tests-139%2F139-brightgreen?style=flat-square)](https://github.com/aura/aura)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Languages](https://img.shields.io/badge/languages-51%20groups%20(17%20with%20rules)-orange?style=flat-square)](https://github.com/aura/aura)
[![Rules](https://img.shields.io/badge/rules-127-yellow?style=flat-square)](https://github.com/aura/aura-audit)
[![Benchmark](https://img.shields.io/badge/benchmark%20F1-96.8%25-brightgreen?style=flat-square)](https://github.com/aura/aura)

AURA autonomously discovers, analyzes, remediates, independently verifies, regression-tests, and repeatedly re-audits a repository until deterministic evidence satisfies its convergence policy.

[Website](https://github.com/aura/aura) · [Docs](https://github.com/aura/aura#readme) · [Benchmark](https://github.com/aura/aura#benchmark) · [Changelog](CHANGELOG.md)

## Install

Requires Python 3.11+.

```bash
# Clone
git clone https://github.com/aura/aura.git
cd aura-audit

# Install with dev dependencies
uv pip install -e ".[dev]"
```

Or install the published package:

```bash
pip install aura
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

## Security

All LLM output is treated as **UNTRUSTED CLAIM** until validated by independent tool execution evidence. No convergence gate decision involves LLM input. Every finding requires:

1. Real tool execution (pytest, lint, build) captured by the orchestrator
2. Exit codes captured from the actual tool, not the LLM
3. Independent verifier confirmation (not self-verified)
4. Regression audit that proves no re-introduced defects

API keys are loaded from environment variables only — never hardcoded. `.env` is gitignored. See `.env.example` for the configuration template.

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