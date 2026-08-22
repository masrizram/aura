# Context — README

The context diagram shows all external entities that interact with AURA.

See [context-diagram.md](context-diagram.md).

## External Entities Summary

| Entity | Type | Interaction |
|---|---|---|
| Human User | Actor | CLI commands via terminal |
| Target Repository | Data Source | Source code, config, manifests |
| LLM API | External Service | HTTP POST to `/chat/completions` |
| Local Ollama | External Service | HTTP GET for auto-discovery, optional fallback |
| git CLI | System Tool | Subprocess: `git ls-files`, `git log`, `git status` |
| SAST Tools | System Tool | Subprocess: semgrep, bandit, gitleaks |
| Language Tooling | System Tool | Subprocess: pytest, tsc, npm, go test, cargo test |
| Filesystem | Storage | `.aura/` directory for DB, evidence, checkpoints |
| SQLite Database | Storage | `.aura/state/aura.db` (embedded, in-process) |