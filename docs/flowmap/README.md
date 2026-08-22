# Flowmap — README

End-to-end execution flow documentation.

| Document | Scope |
|---|---|
| [audit-flow.md](audit-flow.md) | Full 13-phase audit pipeline, startup flow, exceptional paths |
| [startup-flow.md](startup-flow.md) | (Consolidated in audit-flow.md — CLI dispatch shown there) |

## Quick Reference: 13 Phases

| # | Phase | Source | Key Actions |
|---|---|---|---|
| 1 | DISCOVER | `engine.py:157` | git context, language detection |
| 2 | MODEL | `engine.py:165` | project type detection |
| 3 | AUDIT | `engine.py` | regex scan 127 rules |
| 4 | ADVERSARIAL_AUDIT | `engine.py:187` | domain orchestration (fallback: 12 roles) |
| 5 | CORRELATE | `engine.py:203` | deduplication, context filtering, semantic enrichment |
| 6 | PRIORITIZE | `engine.py:427` | sort by severity |
| 7 | REMEDIATE | `engine.py:437` | DB insertion of findings |
| 8 | TEST | `engine.py:464` | SAST + language tooling execution |
| 9 | VERIFY | `engine.py:471` | verification evidence tracking |
| 10 | REGRESSION | `engine.py:493` | reappeared finding detection |
| 11 | UPDATE_STATE | `engine.py:513` | compute cycle statistics |
| 12 | CONVERGENCE | `engine.py:636` | 12-gate evaluation, scoring, classification |
| 13 | PUSH_APPROVAL | `engine.py:751` | semantic memory storage, log |