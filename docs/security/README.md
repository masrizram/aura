# Security — README

Security analysis for AURA v3.5.

| Document | Scope |
|---|---|
| [threat-model.md](threat-model.md) | STRIDE analysis of all 6 threat categories |
| [trust-boundaries.md](trust-boundaries.md) | Trust boundary diagram + complete security controls inventory |
| [attack-surface.md](attack-surface.md) | Attack surface enumeration + dependency supply chain |
| [security-controls.md](security-controls.md) | Implemented/Partial/Missing controls summary |

## TL;DR: Security Posture

AURA is a local-only audit tool with **no network-facing surface** (except LLM API calls in `auto-fix` mode). The primary security concerns are:

1. **LLM output injection** into source code — mitigated by AutoFixer sandbox
2. **Subprocess execution** of tooling commands — mitigated by hardcoded command lists
3. **Secrets exposure** — mitigated by env-var-only API keys and secret redaction

The most significant residual risk is the `auto-fix` command's reliance on a block list for dangerous LLM-generated code patterns. A sophisticated adversarial LLM could produce novel code that evades the block list while still being dangerous. The `--dry-run` flag and automatic rollback provide defense-in-depth.