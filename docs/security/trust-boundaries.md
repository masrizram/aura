# Trust Boundaries

> What crosses each boundary, in which direction, and with what validation.

## Boundary 1 — operator ⇄ CLI
- Direction: bidirectional (args in; stdout/stderr out).
- Validation: Click parser (types, flags); pydantic on config; exit codes.
- Data: repo path, config path, verbosity, JSON flag.
- Threat: minimal — operator is trusted.

## Boundary 2 — target repository ⇄ engine
- Reads: `pathlib.read_text(encoding="utf-8", errors="ignore")` everywhere.
- Writes: only `AutoFixer.apply_fix` (guarded by `is_relative_to(repo)` + advisory pattern check).
- Validation on write: `old_code` must match (whitespace-tolerant); otherwise retry-once or dead-letter.
- Threat: A1, A2 in threat-model. Containment + advisory + rollback are the boundary.

## Boundary 3 — engine ⇄ SQLite
- Parametric SQL everywhere (`?` placeholders); **no string interpolation for values**.
- Exceptions: internal-only `set_clause` JOIN in `update_finding_status`/`update_cycle` — the *keys* come from hardcoded call sites, not user input.
- WAL + `BEGIN IMMEDIATE` transactions.
- Threat: SQL injection realistic only if a caller interpolated — audited: no such call sites in repo.

## Boundary 4 — engine ⇄ LLM endpoint
- Transport: HTTPS via `httpx`, `Authorization: Bearer $AURA_LLM_KEY`, Content-Type JSON.
- Payload: model, messages, max_tokens, temperature=0.1, stream=false.
- Response: parsed as JSON; content treated as UNTRUSTED text.
- Validation: JSON structural parse only; no schema enforcement on returned fixes beyond dataclass fields.
- Threat: A3, A4, A12 in threat-model. `untrusted=True` is the boundary.

## Boundary 5 — engine ⇄ tooling subprocesses
- Spawn: `subprocess.run(["cmd","/c", cmd] on Windows else ["sh","-c", cmd], shell=False, timeout=300, capture_output=True, cwd=repo_root)`.
- Command string: hardcoded templates from `_detect_commands()` — repo never edits it.
- `fail_open` default False → real exit codes feed `verification` gate.
- Threat: A5, A11 in threat-model.

## Boundary 6 — engine ⇄ `.aura/` filesystem state
- `.aura/state/aura.db` SQLite with WAL.
- `.aura/checkpoint.json` sha256-protected resume state.
- `.aura/memory.json` repository memory.
- `.aura/evidence/*` hash-chained proof artifacts.
- Threat: A6, A7 (tamper). Defenses are detection, not prevention.

## Boundary 7 — engine ⇄ process environment
- `load_dotenv()` at CLI import reads `.env` (into os.environ).
- LLM creds read from env vars, possibly ctor-injected.
- Threat: A8 — secrets never logged, only used in Authorization header.

## Data classification

| Data | Level | Notes |
|---|---|---|
| Target source code | public within operator scope | not a secret to AURA |
| AURA findings DB | internal evidence | contains file paths & snippets (120-char excerpts) — treat as internal |
| LLM API key | secret | only in Authorization header |
| `.env` target contents | internal | parsed for config only |
| Checkpoint / evidence | tamper-evident | integrity-critical |
