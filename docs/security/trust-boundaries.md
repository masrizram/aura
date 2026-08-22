# Trust Boundaries & Security Controls — AURA v3.5

> **Verified from:** `src/aura/providers.py`, `src/aura/remediation.py`, `src/aura/llm.py`, `src/aura/cli.py`

## Trust Boundaries Map

```
┌─────────────────────────────────────────────────────────────┐
│ LOCAL MACHINE (High Trust)                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ AURA Process                                           │  │
│  │  ┌─────────┐  ┌──────────┐  ┌────────────────────┐   │  │
│  │  │ Engine  │  │ AutoFixer │  │ EvidenceChain      │   │  │
│  │  └────┬────┘  └─────┬────┘  └────────┬───────────┘   │  │
│  │       │              │               │                │  │
│  │  ┌────▼──────────────▼───────────────▼────────────┐   │  │
│  │  │            SQLite Database (.aura/state/)        │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────┐  ┌────────────────────────────┐  │
│  │   Repository Files    │  │   Git CLI (subprocess)     │  │
│  │   (Read Only)         │  │   (Read Only)              │  │
│  └──────────────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
           │                         │
     ┌─────▼─────┐           ┌──────▼──────────┐
     │ TRUST     │           │ TRUST BOUNDARY   │
     │ BOUNDARY  │           │ (subprocess)     │
     │ (API)     │           │                  │
     └─────┬─────┘           └──────┬───────────┘
           │                        │
 ┌─────────▼────────────────────────▼──────────────────────┐
 │ EXTERNAL (Low Trust / Untrusted)                        │
 │                                                         │
 │  ┌──────────────────────┐  ┌──────────────────────────┐ │
 │  │  LLM API              │  │  Tooling (npm, pytest,   │ │
 │  │  (UNTRUSTED output)   │  │  semgrep, bandit, etc.)  │ │
 │  │                       │  │  (exit code only trusted)│ │
 │  └──────────────────────┘  └──────────────────────────┘ │
 └─────────────────────────────────────────────────────────┘
```

## Security Controls Inventory

### Secrets Management

| Control | Location | Implementation |
|---|---|---|
| LLM API key from env var | `cli.py:522-523`, `llm.py:37` | `os.environ.get("AURA_LLM_KEY", "")` — never hardcoded |
| No hardcoded credentials | All code | Verified: no credentials in source |
| Secret detection in repos | `adversarial.py:297-329`, `domain_auditor.py:576-608` | Regex patterns for: OpenAI keys, GitHub tokens, Slack tokens, Telegram bots, private keys, generic API keys, connection strings |
| Secret redaction in evidence | `adversarial.py:324` | `re.sub()` masks credential values in displayed evidence |

### Input Validation

| Control | Location | Implementation |
|---|---|---|
| Config validation | `config.py:148-227` | Pydantic `model_validate` with custom validators |
| CLI arg parsing | `cli.py:89-111` | Click parameter types + custom validation |
| JSON parse error handling | Multiple locations | `try/except json.JSONDecodeError` with graceful fallback |
| Encoding error handling | `analyzer.py:478` | `read_text(encoding="utf-8", errors="ignore")` |

### Output Encoding / LLM Safety

| Control | Location | Implementation |
|---|---|---|
| UNTRUSTED tag on all LLM output | `llm.py:22`, `providers.py:40` | `untrusted: bool = True` — design contract |
| Structured logging to stderr only | `logging.py:48` | `StreamHandler(sys.stderr)` — stdout reserved for clean data |
| No LLM output treated as authoritative | `convergence.py:316` | `"llm_involvement": "NONE — all gate decisions are deterministic"` |

### Sandbox (AutoFixer)

| Control | Location | Implementation |
|---|---|---|
| Path traversal prevention | `remediation.py:103-110` | `resolved.startswith(repo_resolved)` check |
| Dangerous pattern blocking | `remediation.py:117-127` | Block list: `os.system(`, `subprocess.`, `exec(`, `eval(`, `__import__(`, `compile(`, `rm -rf`, `DROP TABLE`, `DROP DATABASE` |
| Old code verification | `remediation.py:157-177` | Checks that LLM's `old_code` actually matches file content before writing |
| Automatic rollback | `remediation.py:204-220` | All modified files backed up; `rollback()` restores all originals if tooling fails |
| Dry-run mode | `remediation.py:129-134` | `--dry-run` flag previews diffs without writing |

### Circuit Breaker

| Control | Location | Implementation |
|---|---|---|
| Failure threshold | `providers.py:61` | 3 failures in rolling 120s window → OPEN |
| Cooldown period | `providers.py:62` | 30s before HALF_OPEN probe |
| Half-open probe | `providers.py:63` | 1 request allowed before re-tripping |
| Fallback routing | `providers.py:282-287` | Priority-ordered provider list, skips OPEN providers |

### Subprocess Safety

| Control | Location | Implementation |
|---|---|---|
| Timeout on all subprocess calls | `engine.py:833,919` | 30s for git, 300s for tooling |
| Shell=False on Windows | `engine.py:921` | `["cmd", "/c", cmd]` — but cmd.exe is a shell |
| Exit code capture only | `engine.py:924` | `capture_output=True`, exit codes stored, output truncated to 2000 chars |
| Exception handling | `engine.py:927-932` | `TimeoutExpired` + generic `Exception` both caught |

### Data Integrity

| Control | Location | Implementation |
|---|---|---|
| Stable finding IDs (SHA-256) | `engine.py:60-68` | Content-based, not timestamp-based — ensures cross-cycle identity |
| Evidence chain hash verification | `evidence.py:118-124` | SHA-256 chain: each entry hashes itself + previous entry |
| SQLite WAL mode | `db.py:215` | Write-Ahead Logging for crash safety |
| Foreign key enforcement | `db.py:216` | `PRAGMA foreign_keys=ON` |
| Transactional writes | `db.py:240-248` | `BEGIN IMMEDIATE` → `COMMIT` / `ROLLBACK` |
| DB integrity check | `db.py:258-260` | `PRAGMA integrity_check` via `aura health` |
| DB backup | `db.py:262-267` | `sqlite3.backup()` API |

## Security Gaps (MISSING / PARTIAL)

| Gap | Impact | Priority |
|---|---|---|
| No authentication on CLI | Low — local-only tool | Info |
| DB stored unencrypted | Sensitive findings in plaintext SQLite | Medium |
| Subprocess tooling executes arbitrary code from package.json | If package.json has malicious scripts, they run with user privileges | High |
| No repository integrity verification before scanning | Modified files during scan cause inconsistent results | Low |
| Evidence chain hash verification not triggered automatically | Tampering detected only if manually checked | Low |
| Checkpoint file has no integrity protection | Resume from tampered checkpoint | Low |
| `cmd /c` on Windows is a shell — commands with metacharacters | If config specifies `required_pass_commands`, shell injection possible | Medium |