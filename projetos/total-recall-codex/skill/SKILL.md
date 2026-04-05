---
name: total-recall-codex
description: Search across all past Codex sessions for decisions, context, code discussions, and past conversations. Use when the user wants to recall something from a previous Codex session, recover lost context, or find a past discussion. Triggers: "lembra quando", "recall", "em qual sessão", "o que decidimos sobre", "busca nas sessões", "recupera o contexto".
---

# Total Recall Codex

You are searching the user's past Codex sessions for relevant information.

## Supported flags (parsed from $ARGUMENTS before searching)

| Flag | Effect |
|------|--------|
| `--clip` | Save results to a dated Markdown file in `~/.total-recall-codex/clips/` |
| `--limit N` | Return N results (default: 8) |
| `--session <id>` | Filter by session ID prefix |

Strip recognized flags from `$ARGUMENTS` before using it as the search query.

## Instructions

1. Parse flags from `$ARGUMENTS`
2. Run: `total-recall-codex search "<cleaned query>" --format context --limit 8`
3. Analyze results and present direct answers with session IDs, dates, and sources
4. Use **`bold code`** for key matched terms
5. If no results, suggest alternatives and check indexing status with `total-recall-codex status`

## Output format

Present findings as a synthesized answer, not as raw chunks. Include:
- Session ID (first 8 chars)
- Date of the session
- Project label
- Direct quote or paraphrase with attribution

Example:
```
Na sessão `c3b0e47e` (22/03/2026, projeto memoria-viva), discutimos que:
"SQLite unificado ao invés de pgvector. Volume ~4500 vetores/ano..."

O raciocínio foi que pgvector adiciona uma dependência externa desnecessária
quando sqlite-vec já resolve dentro do mesmo arquivo SQLite.
```

## When no results

If the search returns nothing:
1. Check if indexing is up to date: `total-recall-codex status`
2. Suggest alternative queries (broader terms, synonyms)
3. Note that the topic may not have been discussed in Codex sessions yet
