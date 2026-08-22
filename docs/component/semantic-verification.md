# Semantic Layer — Verification (appended to architecture)

> Located in `semantic.py`. Dataclass shapes + measured entry points.

## AST parsing — parse_file dispatch (semantic.py:529-538)

| Extensions | Handler | Type |
|---|---|---|
| `.py, .pyi, .pyx` | `ASTParser.parse_python` | real `ast` module |
| `.php, .phtml` | `ASTParser.parse_php` | tokenizer-based structural |
| `.js, .jsx, .ts, .tsx, .mjs, .cjs` | `ASTParser.parse_javascript` | regex-based structural |
| **any other** | `[]` | not parsed |

## Confidence / status enums (semantic.py:25-46, verified by direct import)

```python
ConfidenceLevel: TRUE_POSITIVE, LIKELY_TRUE, UNCERTAIN, LIKELY_FALSE_POSITIVE,
                 FALSE_POSITIVE, MITIGATED
FindingStatus:   RAW, LOCATED, ANALYZED, CLASSIFIED, ACTIONABLE, FIXED,
                 VERIFIED, MITIGATED, WAIVED
```

## SemanticAuditor entry points (verified by introspection)

`SemanticAuditor(repo_root: Path)` public methods are exactly:
`enrich_findings`, `classification_summary`, `compute_enriched_score`, `store_cycle_memory`.
There is **no `audit_file` method** — earlier drafts assumed one; corrected here.

## Evidence graph & taint model

- `_SECURITY_SINKS` per language (php, python, typescript, java).
- Taint tracking uses a ±20-line context window with sanitizer capability matrix
  (LIMITATIONS.md §1); there is no real inter-procedural dataflow.
- `TaintAnalyzer.__init__` takes a `Path`-like repo_root — passing a raw string
  raises `TypeError` on `/` operator (probe 2026-08-22).
- `RepositoryMemory` persists `.aura/memory.json` JSON only.

## Real runtime behavior (probes)

- Domain wave executes via try/except isolation per auditor (domain_auditor.py:954-964).
- On exception, `all_findings[domain_id] = []` — the cycle CONTINUES for other domains.
- On orchestrator exception (outside the per-auditor scope), engine falls back silently
  to legacy 12-role scan (engine.py:226-232).
