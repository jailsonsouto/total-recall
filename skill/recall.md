---
name: recall
description: |
  Search across all past Claude Code sessions for any topic, decision, or conversation.
  Use when the user wants to recall something from a previous session, recover lost context,
  or find a past discussion. Triggers: "lembra quando", "recall", "em qual sessão",
  "o que decidimos sobre", "busca nas sessões", "recupera o contexto".
argument-hint: <query about past sessions>
allowed-tools:
  - Agent
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

2. Delegate the search and synthesis to a cheap sub-agent — don't run `total-recall` or read raw results yourself. This is grunt work (running a CLI, reading transcript dumps) that shouldn't burn the orchestrator's own context/tokens.

   Call the `Agent` tool with `subagent_type: "general-purpose"` and `model: "sonnet"`. The sub-agent starts with zero context, so its prompt must be fully self-contained. Use this template:

   ```
   Run this exact command:

   total-recall search "<cleaned query>" --format context --limit 8 [--output -auto-] [--session <id>]

   Then, based on the output:

   - If results are found, analyze them and produce a synthesized answer (not a raw dump):
     - A direct answer to the question (when possible)
     - Session ID and date for each piece of evidence
     - Relevant quotes from the transcripts — preserve **`bold code`** highlighting on matched terms
     - If the topic spans multiple sessions, synthesize across them
     - Show the source engine (VECTOR, FTS5) and any fuzzy/abbreviation expansions
     - Use the score and age to prioritize which results to quote first
     - Use **`bold code`** to highlight key matched terms so they stand out
     - Group results by topic when they overlap
     - Mention the session ID (`abc12345`) and date for each piece of evidence so the user can drill deeper
     - If `--output -auto-` was used, report the saved clip file path at the end

   - If no results are found, say so clearly and suggest:
     - Alternative search terms to try
     - Checking `total-recall status` (index might be stale)
     - Running `total-recall index` if needed

   Return ONLY the final synthesized answer in your last message — no tool call logs, no raw search output. That message is relayed verbatim to the user.
   ```

3. Relay the sub-agent's final message to the user as your answer. Don't re-run the search yourself, don't re-fetch the raw results, and don't second-guess the sub-agent's reading of the transcripts unless something in its answer looks clearly wrong or contradicts something you already know.

4. To drill deeper into a specific session, repeat step 2 with `--session <session-id> --limit 15` added to the command inside the sub-agent prompt.
