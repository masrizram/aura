# Recovery Matrix — AURA v3.5

> **Verified from:** all `src/aura/*.py` modules

## Complete Failure → Recovery Matrix

| Component | Failure Mode | Detection | Recovery | Automatic? | Evidence |
|---|---|---|---|---|---|
| **Config** | Invalid aura.json | `json.JSONDecodeError` / `ValidationError` | Exit (FATAL) | N/A | `config.py:179-212` |
| **Config** | Missing config file | `Path.exists() == False` | Use defaults (`AuraConfig()`) | Yes | `config.py:174-175` |
| **DB** | Not initialized | `_conn is None` | `RuntimeError` | No — must call `initialize()` | `db.py:206-208` |
| **DB** | Schema migration needed | `_get_schema_version() < SCHEMA_VERSION` | Apply `SCHEMA_SQL` | Yes (on `initialize()`) | `db.py:220-228` |
| **DB** | Transaction failure | Exception in `with transaction()` | `ROLLBACK` | Yes | `db.py:240-248` |
| **DB** | Integrity corrupted | `PRAGMA integrity_check` | `vacuum()` | Manual (`aura health`) | `db.py:258-260` |
| **DB** | I/O error | `sqlite3.Error` | `DatabaseError` with `RETRY_WITH_FALLBACK` | Yes | `errors.py:108-123` |
| **Git** | git not installed | `subprocess.CalledProcessError` | `ctx["git"]["GitError"] = True` | Yes — audit continues without git context | `engine.py:826-849` |
| **Git** | Git command timeout | `Exception` (30s timeout) | `ctx["GitError"] = True` | Yes | `engine.py:837` |
| **Git** | Git command returns non-zero | `returncode != 0` | `ctx["GitError"] = True` | Yes | `engine.py:835` |
| **Analyzer** | File read error | `Exception` from `read_text()` | Skip file, continue | Yes | `analyzer.py:479-480` |
| **Analyzer** | No matching language | `_lang_for() == "unknown"` | Skip file | Yes | `analyzer.py:473-474` |
| **Domain Auditor** | Auditor throws exception | `except Exception` | Empty findings for that domain | Yes | `domain_auditor.py:962-964` |
| **Domain Auditor** | Shared intelligence build fails | Exception in `build()` | Would propagate to orchestrator | PARTIAL — not explicitly handled | `domain_auditor.py:948` |
| **Semantic** | `enrich_findings()` fails | Exception | `ctx["semantic_enriched"] = []` | Yes | `engine.py:423-425` |
| **Semantic** | AST parse error | `SyntaxError` | Empty node list | Yes | `semantic.py:349-350` |
| **Semantic** | File read for taint analysis | `Exception` | Return `None` | Yes | `semantic.py:802-803` |
| **LLM Client** | HTTP !=200 | `resp.status_code != 200` | `LLMResponse with LLM_ERROR` | Yes | `llm.py:74-75` |
| **LLM Client** | Connection error | `Exception` | `LLMResponse with LLM_ERROR` | Yes | `llm.py:76-77` |
| **LLM Client** | JSON parse failure | `json.JSONDecodeError` | `{"findings": [], "summary": "LLM parse error"}` | Yes | `llm.py:201-202` |
| **Provider** | Circuit OPEN | `allow_request() == False` | Skip provider, use fallback | Yes | `providers.py:156-162` |
| **Provider** | Rate limit (429) | `resp.status_code == 429` | Retry with backoff (3x) | Yes | `providers.py:234-243` |
| **Provider** | All providers down | `get_healthy_provider() == None` | `ProviderResponse(error)` | Yes | `providers.py:298-305` |
| **Tooling** | Command timeout | `subprocess.TimeoutExpired` | Record `exit_code=-1, success=False` | Yes | `engine.py:927-929` |
| **Tooling** | Command exception | `Exception` | Record `exit_code=-1, success=False` | Yes | `engine.py:930-932` |
| **Tooling** | Tool not found | `shutil.which() == None` | Command not added to list | Yes | `engine.py:939` |
| **AutoFixer** | Path traversal attempt | `resolved not in repo_root` | `FixResult(error="SANDBOX REJECTED")` | Yes | `remediation.py:103-110` |
| **AutoFixer** | Dangerous pattern in fix | Pattern match in block list | `FixResult(error="SANDBOX REJECTED")` | Yes | `remediation.py:117-127` |
| **AutoFixer** | File not found | `full_path.exists() == False` | `FixResult(error="File not found")` | Yes | `remediation.py:136-140` |
| **AutoFixer** | old_code mismatch | `norm_old not in norm_actual` | Retry with actual file content | Yes (1 retry) | `remediation.py:435-498` |
| **AutoFixer** | File write fails | `Exception` | `FixResult(error=str(e))` | Yes | `remediation.py:198-202` |
| **AutoFixer** | Tooling fails after fixes | `returncode != 0` | `rollback()` — restore all backups | Yes | `remediation.py:538-541` |
| **AutoFixer** | Rollback fails | `Exception` in write_text | Count in `failed_rollback` | Yes — partial rollback | `remediation.py:208-213` |
| **Loop Safeguard** | Max iterations reached | `iteration > MAX_ITERATIONS` | Stop loop | Yes | `convergence.py:191-192` |
| **Loop Safeguard** | Same finding 3+ attempts | `finding_attempts[fid] > MAX` | Stop retrying that finding | Yes | `convergence.py:195-199` |
| **Loop Safeguard** | No progress 3 cycles | Score unchanged for 3 cycles | Stop loop | Yes | `convergence.py:202-205` |
| **Loop Safeguard** | Score regression >10 | `delta < REGRESSION_THRESHOLD` | Stop loop | Yes | `convergence.py:208-211` |
| **State Machine** | Illegal finding transition | `is_valid_finding_transition() == False` | Violation logged, refused | Yes | `state_machine.py:154-160` |
| **State Machine** | Gate flip without evidence | `validate_gate_evidence_integrity()` | Violation logged | Yes | `state_machine.py:183-274` |
| **State Machine** | Score regression | `new_score < old_score` | Violation logged | Yes | `state_machine.py:247-250` |
| **State Machine** | Score spike >15 | `new_score > old_score + 15` | Violation logged | Yes | `state_machine.py:252-256` |
| **Checkpoint** | JSON parse error | `json.JSONDecodeError` | Return `None` (no checkpoint) | Yes | `durable.py:53-54` |
| **Checkpoint** | File not found | `checkpoint_path.exists() == False` | Return `None` | Yes | `durable.py:49-50` |
| **Logging** | Log write failure | stderr closed/full | Silent — structlog handles internally | Yes | `logging.py` |
| **CLI** | `--config` points to missing file | `ConfigError` | `console.print → sys.exit(1)` | No — user must fix | `cli.py:109-111` |
| **CLI** | `--repo` points to non-repo | Engine runs with empty/partial results | Lagit context will show errors | Yes — continues gracefully | `engine.py:824-849` |

## Failure Recovery Patterns

### Pattern 1: Silent Degradation
```
Component fails → log warning → continue with reduced functionality
Examples: Git unavailable, Semantic enrichment fails, Domain auditor exception
```

### Pattern 2: Retry with Backoff
```
Transient failure → retry N times with exponential backoff → fail permanently
Examples: LLM API 429, network errors, provider failures
```

### Pattern 3: Rollback on Failure
```
Apply changes → verify with tooling → if tooling fails → restore originals
Example: AutoFixer applies fixes, runs tests, rolls back on failure
```

### Pattern 4: Fail-Closed (Safe Default)
```
Invalid operation detected → block → record violation → continue without change
Examples: Sandbox rejects dangerous fix, state machine blocks illegal transition
```

### Pattern 5: Checkpoint & Resume
```
Long operation → save checkpoint at each boundary → if interrupted → resume from last checkpoint
Example: DurableAutonomousLoop saves checkpoint after each cycle
```

## MISSING Recovery Mechanisms

| Gap | Impact | Priority |
|---|---|---|
| No partial cycle recovery | If engine crashes mid-cycle (phase 7 of 13), restart starts fresh cycle | Medium |
| No DB crash recovery beyond WAL | WAL protects against process crash but not disk corruption | Low |
| No evidence chain auto-repair | Tampered evidence detected but not automatically restored | Low |
| No filesystem snapshot/backup before AutoFixer | If rollback itself fails, original files lost | Medium |
| No circuit breaker for subprocess tooling | If `npm test` hangs forever, only timeout saves it (300s) | Low |
| No graceful shutdown handler | SIGINT during mid-cycle leaves DB in intermediate state (but WAL protects) | Low |