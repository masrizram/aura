# Context Diagram — AURA v3.5

> **Verified from:** `src/aura/cli.py`, `src/aura/engine.py`, `src/aura/llm.py`, `src/aura/providers.py`, `src/aura/db.py`

## External Actors and Systems

```mermaid
graph TD
    subgraph "External"
        USER["👤 Human User (CLI)"]
        REPO["📁 Target Repository\n(source code, config, tests)"]
        LLM_API["🤖 LLM API\n(OpenAI-compatible endpoint)"]
        OLLAMA["🦙 Local Ollama\n(optional fallback)"]
        SAST["🔍 SAST Tools\n(semgrep, bandit, gitleaks)"]
        LANG_TOOLS["🛠️ Language Tooling\n(pytest, tsc, npm, go test, cargo)"]
        GIT["📦 git CLI"]
        FS["💾 Filesystem\n(.aura/ directory)"]
    end

    subgraph "AURA System"
        CLI_PROCESS["aura CLI\n(click commands)"]
        ENGINE["Engine\n(13-phase pipeline)"]
        DB["SQLite Database\n(.aura/state/aura.db)"]
    end

    USER -->|"commands: init, audit, status, health,\ndoctor, verify, log, report, trend, auto-fix"| CLI_PROCESS
    CLI_PROCESS --> ENGINE
    ENGINE -->|"reads source files"| REPO
    ENGINE -->|"git ls-files, git log, git status"| GIT
    ENGINE -->|"executes tests, lint, SAST"| SAST
    ENGINE -->|"executes tests, builds"| LANG_TOOLS
    ENGINE -->|"reads/writes"| DB
    ENGINE -->|"writes .aura/evidence,\n.aura/checkpoint.json"| FS
    ENGINE -->|"POST /chat/completions\n(untreated output)"| LLM_API
    ENGINE -->|"GET /api/tags (auto-discover)"| OLLAMA

    style AURA fill:#1a1a2e,stroke:#16213e,color:#eee
```

## Data Exchange Directions

| From | To | Data | Direction |
|---|---|---|---|
| User | AURA CLI | CLI args: `--repo`, `--config`, `--verbose`, `--json` | → Inbound |
| AURA CLI | User | stdout: audit results (JSON or rich formatted), reports | ← Outbound |
| AURA CLI | User | stderr: structured logs (structlog) | ← Outbound |
| Engine | Repository | Reads source files, config manifests, .env | → Read |
| Engine | git CLI | `git ls-files`, `git log --oneline -5`, `git status --short`, `git branch` | → Subprocess stdout |
| Engine | SAST/Lang Tools | `subprocess.run([cmd])` — exit codes + stdout/stderr captured | ← Subprocess result |
| Engine | SQLite DB | INSERT/UPDATE/SELECT on 12 tables | ↔ Read/Write |
| Engine | Filesystem | Writes `.aura/state/aura.db`, `.aura/checkpoint.json`, `.aura/evidence/cycle-NNN/` | → Write |
| LLMClient | LLM API | POST with JSON body (system prompt + user message) | → Request |
| LLM API | LLMClient | JSON response with `choices[0].message.content` | ← Response (UNTRUSTED) |
| ProviderRegistry | Ollama | GET /api/tags (auto-discover local models) | → Request |
| AutoFixer | Filesystem | Writes modified source files, `.patch` files | → Write (with rollback) |

## Key Principles

1. **All LLM output is UNTRUSTED** — marked `untrusted=True` at the protocol level (`llm.py:22`, `providers.py:40`)
2. **Tool output is OBSERVABLE EVIDENCE** — exit codes, stdout, stderr captured and stored
3. **No external auth needed** for core operation — only LLM API key for auto-fix
4. **Repository access is local-only** — all source scanning happens via filesystem reads, not API calls
5. **Database is embedded** — SQLite in-process, no external DB server