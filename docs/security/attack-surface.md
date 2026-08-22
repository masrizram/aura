# Attack Surface

> Concrete external inputs with enforcing code.

## Input surface

| Input | Where it enters | Validation | Failure mode |
|---|---|---|---|
| `--repo <path>` | cli.py | `Path.resolve()`; must exist for engine init | Engine __init__ raises on missing path (implicit) |
| `--config <path>` | cli.py | `AuraConfig.from_file`; pydantic | ConfigError FATAL → exit(1) |
| `AURA_CONFIG_PATH` env | config.py | explicit override | ConfigError FATAL |
| `config/aura.json` | config.py | pydantic validation, severity defaults injected | ConfigError FATAL |
| `aura.json` (repo root) | config.py | pydantic | same |
| `.env` | dotenv → os.environ | none (env vars trusted) | — |
| `AURA_LLM_URL`, `AURA_LLM_KEY`, `AURA_LLM_MODEL` | llm.py | presence check only (can be empty) | LLM calls fail as network errors |
| Target source files | analyzer/adversarial/domain | utf-8 errors=ignore; per-line regex | skipped on I/O error |
| LIMITATIONS.md | engine CONVERGENCE | 4 structural checks | gate=False |
| `.aura/checkpoint.json` | durable.py | JSON parse + sha256 state hash | tamper → refuse resume |
| `.aura/memory.json` | semantic.py | JSON parse | corrupt → [] |
| `.aura/evidence/convergence_proof.json` | write only | — | — |
| LLM HTTP body | llm.py / providers.py | JSON parse; markdown/ brace fallback | _untrusted:{findings:[]} |
| TTY stdout | rich Console | — | — |

## Command surface (only entry is CLI)

10 commands. Each maps to a fixed code path; no RPC, no eval, no shell metacharacter
interpretation of operator args beyond Click's own handling.

```
init, audit, status, health, doctor, log, verify [finding_id] [--fix],
report [-o], trend, auto-fix [--dry-run] [--max-cycles N]
```

## Spawn surface (commands the engine can issue)

From `_detect_commands` (engine.py:1001-1026) — all strings are templates AURA owns:

- `semgrep scan --config=auto --quiet`
- `bandit -r src/ -ll`
- `gitleaks detect --no-git`
- `npx tsc --noEmit`
- `python -m pytest --tb=short`
- `npm run {test|lint|build}` (scripts names from package.json — repo-controlled)

  *Note:* `npm run <name>` names come from the repo's `package.json` `scripts` keys —
  AURA chooses which *kind* (`test`, `lint`, `build`) but the chosen value is the key name.
  The runner is `npm` with `shell=False`; the risk is repo-controlled scripts, which is
  accepted (operator asked to audit the repo).
- `make test`
- `go test ./...`
- `cargo test`

Plus `git` invocations in `_get_git_context` (`branch --show-current`, `status --short`, `ls-files`, `log -1`).

## Network surface

Single outbound URL: `{AURA_LLM_URL}/chat/completions` (HTTPS recommended by usage).
No inbound HTTP/RPC.
