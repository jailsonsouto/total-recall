---
name: recall
description: |
  Search across all past Claude Code sessions for any topic, decision, or conversation.
  Use when the user wants to recall something from a previous session, recover lost context,
  or find a past discussion. Triggers: "lembra quando", "recall", "em qual sessão",
  "o que decidimos sobre", "busca nas sessões", "recupera o contexto".
  Prefira fontes diretas (contexto atual da conversa, git, arquivos do repo) quando a
  informação já está disponível nelas — sessões passadas são para o que não está à mão.
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

Also recognize these trigger phrases anywhere in the free text (not literal flags, but expand the search source beyond this project's own database):

| Phrase | Effect |
|--------|--------|
| "cruzada", "cross", "nos dois", "nas duas ferramentas" | add `--source both` (fuse this database with the sibling total-recall-codex database) |
| "só codex", "somente codex", "buscar-no-codex" | add `--source codex` (search only the sibling total-recall-codex database, skip this project's own) |

If none of these phrases is present, don't add `--source` at all — the CLI's default is `claude-code`, this project's own database (fast, no second database to open). Cross-project search is opt-in: the user has to ask for "cruzada"/"cross" or explicitly say Codex when they want the sibling total-recall-codex database checked too.

Strip recognized flags/phrases from `$ARGUMENTS` before using it as the search query.

## Instructions

1. Parse flags from `$ARGUMENTS`:
   - If `--clip` is present → add `--output -auto-` to the search command and strip `--clip` from the query
   - If `--limit N` is present → use that value instead of 8 and strip from query
   - If `--session <id>` is present → add `--session <id>` to the command and strip from query
   - If a source-restriction phrase is present (see table above) → add the matching `--source` flag and strip the phrase from the query

2. Delegate the search and synthesis to a cheap sub-agent — don't run `total-recall` or read raw results yourself. This is grunt work (running a CLI, reading transcript dumps) that shouldn't burn the orchestrator's own context/tokens.

   Call the `Agent` tool with `subagent_type: "general-purpose"` and `model: "sonnet"`. The sub-agent starts with zero context, so its prompt must be fully self-contained. Use this template:

   ```
   Run this exact command:

   total-recall search "<cleaned query>" --format context --limit 8 [--output -auto-] [--session <id>] [--source both|codex]

   Then, based on the output:

   - If results are found, analyze them and produce a synthesized answer (not a raw dump):
     - A direct answer to the question (when possible)
     - Session ID and date for each piece of evidence
     - Which harness each piece of evidence came from — every result is labeled `[CLAUDE-CODE]` or `[CODEX]`; carry that label into your synthesis so the user knows whether a decision/conversation happened in the Claude Code CLI or in Codex, especially when the answer mixes results from both
     - Relevant quotes from the transcripts — preserve **`bold code`** highlighting on matched terms
     - If the topic spans multiple sessions (or multiple harnesses), synthesize across them and call out when the same topic was discussed in both tools
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
     - If `--source` was NOT already `both` or `codex`, mention that the answer might be in the sibling Codex sessions and offer to re-run with `--source both`

   Return ONLY the final synthesized answer in your last message — no tool call logs, no raw search output. That message is relayed verbatim to the user.
   ```

3. Relay the sub-agent's final message to the user as your answer. Don't re-run the search yourself, don't re-fetch the raw results, and don't second-guess the sub-agent's reading of the transcripts unless something in its answer looks clearly wrong or contradicts something you already know.

4. To drill deeper into a specific session, repeat step 2 with `--session <session-id> --limit 15` added to the command inside the sub-agent prompt. Check which harness that session came from (the `[CLAUDE-CODE]`/`[CODEX]` label on the result you're drilling into): if it's `[CODEX]`, also add `--source codex` (or `--source both`) — the default `--source claude-code` won't find a session that lives in the sibling database.
