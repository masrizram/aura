# Security Controls — AURA v3.5.1

> **Verified from:** `src/aura/*.py` (post IMP-01..IMP-09, 2026-08-22)

See the comprehensive analysis in:
- [threat-model.md](threat-model.md) — STRIDE threat model
- [trust-boundaries.md](trust-boundaries.md) — Trust boundaries map + security controls inventory
- [attack-surface.md](attack-surface.md) — Attack surface analysis + supply chain risk

## Key Security Properties

### ✅ IMPLEMENTED

| Control | Location |
|---|---|
| UNTRUSTED tag on all LLM output | `llm.py`, `providers.py` |
| AutoFixer path containment via `Path.is_relative_to()` (rejects sibling-prefix + symlink escapes) | `remediation.py` (IMP-06, v3.5.1) |
| AutoFixer rollback on tooling failure | `remediation.py` |
| Circuit breaker for LLM providers (CLOSED→OPEN→HALF_OPEN) | `providers.py` |
| Provider fallback routing + health status | `providers.py` |
| Classified retry (4xx auth = NO_RETRY; 429/5xx/network = RETRY, full jitter, Retry-After honored) | `providers.py` (IMP-05, v3.5.1) |
| Secrets via environment variables only | `cli.py` (`AURA_LLM_KEY`) |
| Secret detection + redaction in audit | `adversarial.py` |
| Stable finding IDs (SHA-256, not timestamps) | `engine.py` |
| Evidence hash chain with linkage verification (tamper/deletion/reorder detection) | `evidence.py` (IMP-04, v3.5.1) |
| Checkpoint integrity hash (tampered checkpoints refused on resume) | `durable.py` (IMP-07, v3.5.1) |
| SQLite WAL mode + foreign keys | `db.py` |
| Immutable audit log | `db.py` |
| Transactional writes | `db.py` |
| Module-integrity gate (fail-closed import check) | `engine.py` (IMP-02, v3.5.1) |

### ⚠️ PARTIAL

| Control | Gap |
|---|---|
| Dangerous-pattern blocklist (AutoFixer) | **Advisory signal, not a security boundary.** Substring matching is bypassable via obfuscation and over-blocks legitimate code (e.g. `subprocess.run` with list args). The real controls are: `--dry-run` preview, `old_code` match verification, automatic rollback on tooling failure, and post-fix re-audit (IMP-06). |
| LLM API identity verification | No TLS certificate pinning or API key validation beyond Bearer auth |
| DB integrity | Only checked via `aura health` CLI command |
| LIMITATIONS.md validation | Validates content structure, not source authenticity |
| Subprocess safety | `cmd /c` on Windows is a shell; tooling commands execute whatever the repo's package.json/Makefile declares — AURA audits repositories it trusts enough to execute their test/build scripts |

### ❌ MISSING (honest inventory)

| Control | What's needed |
|---|---|
| Repository snapshot | Lock files during scan to prevent TOCTOU |
| DB encryption | SQLite encryption-at-rest for findings with sensitive data |
| Evidence cryptographic signing | Fields exist in schema (`signature`, `signer`, `public_key_fingerprint`); no key-management infrastructure yet — hash chain provides tamper evidence, not non-repudiation |
| Rate limiting for SAST tools | Could overload system resources on large repos |