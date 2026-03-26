---
name: recall
description: |
  Search across all past Claude Code sessions for any topic, decision, or conversation.
  Use when the user wants to recall something from a previous session, recover lost context,
  or find a past discussion. Triggers: "lembra quando", "recall", "em qual sessão",
  "o que decidimos sobre", "busca nas sessões", "recupera o contexto".
argument-hint: <query about past sessions>
allowed-tools:
  - Bash(total-recall *)
---

You are searching the user's past Claude Code sessions for relevant information.

## Supported flags (parsed from $ARGUMENTS before searching)

| Flag | Effect |
|------|--------|
| `--clip` | Save results to a dated Markdown file in `~/.total-recall/clips/` |
| `--limit N` | Return N results (default: 8) |
| `--session <id>` | Filter by session ID prefix |

Strip recognized flags from `$ARGUMENTS` before using it as the search query.

## Instructions

1. Parse flags from `$ARGUMENTS`:
   - If `--clip` is present → add `--output -auto-` to the search command and strip `--clip` from the query
   - If `--limit N` is present → use that value instead of 8 and strip from query
   - If `--session <id>` is present → add `--session <id>` to the command and strip from query

2. Run the search:

```
total-recall search "<cleaned query>" --format context --limit 8 [--output -auto-] [--session <id>]
```

3. If results are found, analyze them and present:
   - A direct answer to the question (when possible)
   - Session ID and date for each piece of evidence
   - Relevant quotes from the transcripts — preserve **`bold code`** highlighting on matched terms
   - If the topic spans multiple sessions, synthesize across them
   - Show the source engine (VECTOR, FTS5) and any fuzzy/abbreviation expansions
   - Use the score and age to prioritize which results to quote first

4. Format your response for clarity:
   - Use **`bold code`** to highlight key matched terms in quotes so the user spots them instantly
   - Group results by topic when they overlap
   - Mention the session ID (`abc12345`) and date so the user can drill deeper
   - If `--clip` was used, report the saved file path at the end

5. If no results, suggest:
   - Alternative search terms the user could try
   - Check if indexing is up to date: `total-recall status`
   - Run `total-recall index` if needed

6. To drill deeper into a specific session:

```
total-recall search "<query>" --session <session-id> --limit 15
```
