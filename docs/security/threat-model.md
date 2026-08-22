# Threat Model

> **Philosophy:** AURA treats two kinds of untrusted input: (a) the *target repository*
> (hostile code AURA reads and sometimes writes to), and (b) *LLM service responses*
> (untrusted JSON AURA parses and optionally converts into source edits). AURA itself
> runs with the user's own privileges — anything AURA writes/executes happens with those
> privileges.

## Actors

| Actor | Trust level | Powers |
|---|---|---|
| AURA CLI user | fully trusted (operator) | can invoke commands, edit repo, read DB |
| Target repository | untrusted data | can contain any text; AURA reads it and may write to it (auto-fix) |
| LLM endpoint | untrusted data producer | returns JSON that is parsed as fixes |
| Tooling binaries (pytest/tsc/semgrep/…) | semi-trusted | auto-detected on PATH, subprocess.exec'd with repo cwd |
| Config file / `.env` | trusted operator input | feeds pydantic + env vars |

## Abuse cases considered

| # | Abuse | Primary defense | Notes |
|---|---|---|---|
| A1 | Repo contains `..\..\evil` path in a finding payload | containment check in `AutoFixer.apply_fix` using `Path.is_relative_to(repo)` | prefix-check bypass fixed (IMP-06) |
| A2 | LLM returns a patch containing `os.system(...)` etc. | patch advisory blocklist + `old_code` match verification + rollback on tool failure + post-fix re-audit | blocklist is documented as an advisory (IMP-06) |
| A3 | LLM returns non-JSON garbage | markdown/brace-extractor fallback → treated as `{_untrusted:True}` with empty findings | `llm.audit_with_llm` never raises |
| A4 | LLM endpoint down / poisoned | circuit-breaker + fallback to next provider; engine still converges deterministically w/o LLM | LLM is optional |
| A5 | Tooling commands execute attacker-controlled repo scripts (e.g. crafted `package.json` scripts, Makefile) | `subprocess.run(sh -c ..., shell=False)` with `sh -c` string — the command string comes from AURA's own detection table, NOT from the repo; spawn is for fixed templates only | repo files never chosen as the command |
| A6 | `.aura/checkpoint.json` tampered between runs | SHA-256 `state_hash` verified on load; tampered → refuse to resume | tamper-evidence |
| A7 | `.aura/evidence/*` entries reordered/deleted | hash chain links `previous_hash`; `verify_chain()` reports violations | tamper-evidence |
| A8 | Secrets in target `.env` | read via `load_dotenv()` at CLI import into environ only; never echoed; logged at DEBUG only (not INFO) | AURA_LLM_KEY not in logs |
| A9 | Huge repo DoS | per-lang `FILE_SIZE_THRESHOLDS` + SKIP_DIRS set + `ScaleConfig` warnings; sequential scan is slow but bounded |
| A10 | Provider returns infinite token stream | `max_tokens=4000` set at request; `httpx timeout=120 s` |
| A11 | SSRF via crafted `_run_tooling` string | command templates are hardcoded in `engine._detect_commands`; only file-existence probes decide which are added | no user-controlled URL/command |
| A12 | Prompt injection against the next fix | context constrained to finding data; `max_tokens=2000`; sandbox guard + rollback | LLM cannot directly execute |

## Specifically NOT defended (and documented)

- AURA writes to the target repo with operator privileges (auto-fix) — a hostile repo
  CoULD craft source content that, when partially rewritten by AURA, triggers a build
  step *outside* AURA. Mitigation is `--dry-run` preview + operator gating the push.
- Engine runs every audit as the invoking user — AURA is not a sandbox.
- Secrets read from `.env` live in the process memory only for the duration of the run.
