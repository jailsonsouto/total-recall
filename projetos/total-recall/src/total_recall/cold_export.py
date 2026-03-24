"""
cold_export.py — Exporta sessões indexadas para Markdown
========================================================
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import EXPORTS_PATH
from .database import Database


class ColdExporter:
    """Exporta sessões do banco para Markdown legível."""

    def __init__(self, db: Database, exports_path: Optional[Path] = None):
        self.db = db
        self.exports_path = exports_path or EXPORTS_PATH

    def export_session(self, session_id: str) -> Optional[Path]:
        """Exporta uma sessão. Aceita ID parcial (primeiros 8 chars)."""
        self.exports_path.mkdir(parents=True, exist_ok=True)

        with self.db.connection() as conn:
            # Busca sessão (aceita ID parcial)
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id LIKE ?",
                [f"{session_id}%"],
            ).fetchone()

            if not row:
                return None

            full_id = row["session_id"]
            title = row["title"] or f"Sessão {full_id[:8]}"
            started = row["started_at"] or "?"
            project = row["project_label"] or "?"

            # Busca chunks ordenados
            chunks = conn.execute(
                "SELECT * FROM chunks WHERE session_id = ? ORDER BY chunk_index",
                [full_id],
            ).fetchall()

        # Monta Markdown
        lines = [
            f"# {title}",
            f"",
            f"**Projeto:** {project}  ",
            f"**Início:** {started}  ",
            f"**Session ID:** `{full_id}`  ",
            f"**Mensagens:** {row['user_messages']} user + {row['asst_messages']} assistant  ",
            f"",
            f"---",
            f"",
        ]

        for chunk in chunks:
            role = chunk["role"]
            ts = chunk["timestamp"] or ""
            content = chunk["content"]

            if role == "exchange":
                lines.append(f"*{ts}*\n")
                lines.append(content)
            elif role == "user":
                lines.append(f"### Usuário *{ts}*\n")
                lines.append(content)
            elif role == "assistant":
                lines.append(f"### Claude *{ts}*\n")
                lines.append(content)

            lines.append("\n---\n")

        out_path = self.exports_path / f"{full_id[:8]}.md"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return out_path

    def export_all(self) -> list[Path]:
        """Exporta todas as sessões."""
        paths = []
        with self.db.connection() as conn:
            rows = conn.execute("SELECT session_id FROM sessions").fetchall()
            for row in rows:
                path = self.export_session(row["session_id"])
                if path:
                    paths.append(path)
        return paths
