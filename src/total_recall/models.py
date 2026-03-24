"""
models.py — Estruturas de dados do Total Recall
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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


@dataclass
class RecallContext:
    """Pacote retornado pelo /recall para injeção no contexto do Claude."""
    query: str
    results: list[SearchResult]
    sessions_searched: int
    total_chunks: int

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

        for i, r in enumerate(self.results, 1):
            ts = r.timestamp.strftime("%d/%m/%Y %H:%M") if r.timestamp else "?"
            header = f"### {i}. {r.project_label} — {r.session_title}"
            meta = f"*Sessão `{r.session_id[:8]}` | {ts} | score: {r.score:.3f}*"
            lines.append(header)
            lines.append(meta)
            lines.append(f"\n{r.content}\n")
            lines.append("---\n")

        return "\n".join(lines)
