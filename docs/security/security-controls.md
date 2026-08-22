# Security Controls — AURA v3.5

> **Verified from:** `src/aura/*.py`

See the comprehensive analysis in:
- [threat-model.md](threat-model.md) — STRIDE threat model
- [trust-boundaries.md](trust-boundaries.md) — Trust boundaries map + security controls inventory
- [attack-surface.md](attack-surface.md) — Attack surface analysis + supply chain risk

## Key Security Properties

### ✅ IMPLEMENTED

| Control | Location |
|---|---|
| UNTRUSTED tag on all LLM output | `llm.py:22`, `providers.py:40` |
| AutoFixer sandbox (path traversal + dangerous patterns) | `remediation.py:101-127` |
| AutoFixer rollback on tooling failure | `remediation.py:204-220` |
| Circuit breaker for LLM providers | `providers.py:56-118` |
| Provider fallback routing | `providers.py:282-287` |
| Secrets via environment variables only | `cli.py:522-523` |
| Secret detection + redaction in audit | `adversarial.py:297-329` |
| Stable finding IDs (SHA-256, not timestamps) | `engine.py:60-68` |
| Evidence hash chain with verification | `evidence.py:81-128` |
| SQLite WAL mode + foreign keys | `db.py:215-216` |
| Immutable audit log | `db.py:440-468` |
| Transactional writes | `db.py:240-248` |

### ⚠️ PARTIAL

| Control | Gap |
|---|---|
| LLM API identity verification | No TLS certificate pinning or API key validation beyond Bearer auth |
| DB integrity | Only checked via `aura health` CLI command |
| LIMITATIONS.md validation | Validates content structure, not source authenticity |
| Dynamic command blocking | Block list is pattern-based, not behavioral |
| Subprocess safety | `cmd /c` on Windows is a shell; tooling commands could be dangerous |

### ❌ MISSING

| Control | What's needed |
|---|---|
| Checkpoint file integrity | Hash or sign `.aura/checkpoint.json` |
| Repository snapshot | Lock files during scan to prevent TOCTOU |
| DB encryption | SQLite encryption-at-rest for findings with sensitive data |
| AutoFixer allowlist | Instead of block list, allow only known-safe code patterns |
| Rate limiting for SAST tools | Could overload system resources on large repos |