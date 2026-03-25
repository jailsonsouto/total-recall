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

## Instructions

1. Run the search:

```
total-recall search "$ARGUMENTS" --format context --limit 8
```

2. If results are found, analyze them and present:
   - A direct answer to the question (when possible)
   - Session ID and date for each piece of evidence
   - Relevant quotes from the transcripts — preserve **bold** highlighting on matched terms
   - If the topic spans multiple sessions, synthesize across them
   - Show the source engine (VECTOR, FTS5) and any fuzzy/abbreviation expansions
   - Use the score and age to prioritize which results to quote first

3. Format your response for clarity:
   - Use **bold** to highlight the key matched terms in quotes so the user can spot them instantly
   - Group results by topic when they overlap
   - Mention the session ID (`abc12345`) and date so the user can drill deeper

4. If no results, suggest:
   - Alternative search terms the user could try
   - Check if indexing is up to date: `total-recall status`
   - Run `total-recall index` if needed

5. To drill deeper into a specific session:

```
total-recall search "$ARGUMENTS" --session <session-id> --limit 15
```
