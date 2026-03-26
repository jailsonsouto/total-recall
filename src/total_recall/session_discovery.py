"""
session_discovery.py — Descobre e rastreia sessões JSONL
========================================================

Escaneia ~/.claude/projects/ recursivamente, detecta arquivos
novos ou alterados via SHA-256 hash.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import SESSIONS_ROOT
from .database import Database


@dataclass
class DiscoveredFile:
    """Um arquivo JSONL descoberto."""
    path: Path
    file_hash: str
    file_size: int
    is_subagent: bool
    parent_session_id: Optional[str]
    status: str  # 'new', 'changed', 'changed_nonmonotonic', 'unchanged'
    project_dir: str


class SessionDiscovery:
    """Descobre sessões JSONL e detecta mudanças via hash."""

    def __init__(self, sessions_root: Optional[Path] = None,
                 db: Optional[Database] = None,
                 include_subagents: bool = False):
        self.sessions_root = sessions_root or SESSIONS_ROOT
        self.db = db
        self.include_subagents = include_subagents

    def discover(self) -> list[DiscoveredFile]:
        """Escaneia todos os projetos e retorna lista de arquivos."""
        if not self.sessions_root.exists():
            return []

        files = []
        for jsonl_path in sorted(self.sessions_root.rglob("*.jsonl")):
            is_subagent = "subagent" in str(jsonl_path)

            if is_subagent and not self.include_subagents:
                continue

            parent_sid = self._detect_parent_session(jsonl_path)
            file_hash = self._compute_file_hash(jsonl_path)
            file_size = jsonl_path.stat().st_size
            project_dir = self._get_project_dir(jsonl_path)
            status = self._check_status(str(jsonl_path), file_hash, file_size)

            files.append(DiscoveredFile(
                path=jsonl_path,
                file_hash=file_hash,
                file_size=file_size,
                is_subagent=is_subagent,
                parent_session_id=parent_sid,
                status=status,
                project_dir=project_dir,
            ))

        return files

    def get_changed_files(self) -> list[DiscoveredFile]:
        """Retorna apenas arquivos novos ou alterados."""
        return [f for f in self.discover()
                if f.status in ("new", "changed", "changed_nonmonotonic")]

    def _compute_file_hash(self, path: Path) -> str:
        """SHA-256 do conteúdo do arquivo."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                h.update(block)
        return h.hexdigest()

    def _get_project_dir(self, path: Path) -> str:
        """Extrai o diretório de projeto relativo à raiz."""
        try:
            rel = path.relative_to(self.sessions_root)
            return str(rel.parts[0]) if rel.parts else ""
        except ValueError:
            return ""

    def _detect_parent_session(self, path: Path) -> Optional[str]:
        """Para subagents: extrai session_id do diretório pai."""
        parts = path.parts
        for i, p in enumerate(parts):
            if p == "subagents" and i > 0:
                return parts[i - 1]
        return None

    def _check_status(self, file_path: str, file_hash: str, file_size: int) -> str:
        """Verifica se o arquivo é novo, alterado ou inalterado.

        Distingue 'changed' (cresceu — elegível para append-only) de
        'changed_nonmonotonic' (encolheu ou mesmo tamanho com hash diferente —
        exige reindexação completa da sessão).
        """
        if not self.db:
            return "new"

        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT file_hash, file_size FROM sessions WHERE file_path = ?",
                [file_path],
            ).fetchone()

            if not row:
                return "new"
            if row[0] == file_hash:
                return "unchanged"
            # Hash mudou: verificar se crescimento é monotônico
            stored_size = row[1] or 0
            if file_size > stored_size:
                return "changed"
            return "changed_nonmonotonic"
