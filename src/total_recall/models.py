"""
models.py — Estruturas de dados do Total Recall
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ══════════════════════════════════════════════════════════════
# Highlighting — marcador de texto para termos encontrados
# ══════════════════════════════════════════════════════════════

# ANSI: cores de fundo para terminal
_ANSI_YELLOW = "\033[43m\033[30m"   # query terms
_ANSI_GREEN = "\033[42m\033[30m"    # fuzzy matches
_ANSI_CYAN = "\033[46m\033[30m"     # abbreviation matches
_ANSI_RESET = "\033[0m"


def highlight_text(text: str, terms: list[str],
                   mode: str = "ansi") -> str:
    """Aplica marcador de texto nos termos encontrados.

    mode: "ansi" = cores no terminal, "markdown" = **bold**
    """
    if not terms or not text:
        return text

    escaped = [re.escape(t) for t in terms if t]
    if not escaped:
        return text

    pattern = re.compile(f"({'|'.join(escaped)})", re.IGNORECASE)

    if mode == "ansi":
        return pattern.sub(
            lambda m: f"{_ANSI_YELLOW}{m.group()}{_ANSI_RESET}", text
        )
    elif mode == "markdown":
        return pattern.sub(lambda m: f"**{m.group()}**", text)
    return text


@dataclass
class SessionInfo:
    """Metadados de uma sessão Claude Code."""
    session_id: str
    project_path: str
    project_label: str
    title: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    user_messages: int
    asst_messages: int
    file_path: str
    file_size: int = 0
    is_subagent: bool = False
    parent_session_id: Optional[str] = None


@dataclass
class Chunk:
    """Unidade semântica indexável extraída de uma sessão."""
    id: Optional[int]       # None antes de inserir no DB
    session_id: str
    role: str               # 'user', 'assistant', 'exchange'
    content: str
    timestamp: Optional[datetime]
    chunk_index: int
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    has_embedding: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """Resultado de uma busca híbrida."""
    content: str
    session_id: str
    role: str
    timestamp: Optional[datetime]
    distance: float
    score: float = 0.0          # score combinado (hybrid + decay + MMR)
    metadata: dict = field(default_factory=dict)
    session_title: str = ""
    project_label: str = ""
    sources: list[str] = field(default_factory=list)  # ["vector", "fts5"]


@dataclass
class RecallContext:
    """Pacote retornado pelo /recall para injeção no contexto do Claude."""
    query: str
    results: list[SearchResult]
    sessions_searched: int
    total_chunks: int
    query_info: dict = field(default_factory=dict)

    def format_for_context(self) -> str:
        if not self.results:
            return (
                f"Nenhum resultado encontrado para: \"{self.query}\"\n"
                f"({self.sessions_searched} sessões indexadas, "
                f"{self.total_chunks} chunks no banco)"
            )

        lines = [
            f"## Resultados para: \"{self.query}\"",
            f"*{len(self.results)} resultados de "
            f"{self.sessions_searched} sessões indexadas*\n",
        ]

        # Expansion summary
        expansions = self.query_info.get("expansions", [])
        if expansions:
            exp_parts = []
            for exp in expansions:
                label = "fuzzy" if exp["type"] == "fuzzy" else "abrev"
                targets = ", ".join(exp["expanded"][:3])
                exp_parts.append(f"{label}: {exp['original']} → {targets}")
            lines.append(f"*Expansões: {'; '.join(exp_parts)}*\n")

        # Collect highlight terms
        highlight_terms = self._collect_highlight_terms()

        for i, r in enumerate(self.results, 1):
            ts = r.timestamp.strftime("%d/%m/%Y %H:%M") if r.timestamp else "?"
            sources_str = " + ".join(s.upper() for s in r.sources) if r.sources else "?"
            header = f"### {i}. {r.project_label} — {r.session_title}"
            meta = f"*Sessão `{r.session_id[:8]}` | {ts} | score: {r.score:.3f} | {sources_str}*"
            content = highlight_text(r.content, highlight_terms, mode="markdown")
            lines.append(header)
            lines.append(meta)
            lines.append(f"\n{content}\n")
            lines.append("---\n")

        return "\n".join(lines)

    def _collect_highlight_terms(self) -> list[str]:
        """Coleta termos para highlighting a partir da query e expansões."""
        terms = set()
        for word in self.query.lower().split():
            clean = word.strip(".,!?;:")
            if clean and len(clean) >= 2:
                terms.add(clean)
        for exp in self.query_info.get("expansions", []):
            for expanded in exp["expanded"]:
                terms.add(expanded.lower())
        return sorted(terms, key=len, reverse=True)
