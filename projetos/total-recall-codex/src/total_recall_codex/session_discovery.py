"""
session_discovery.py — Descobre sessões Codex no filesystem
============================================================

Varre ~/.codex/sessions/**/*.jsonl (hierárquico por data: YYYY/MM/DD/).
Extrai session ID do filename: rollout-{timestamp}-{uuid}.jsonl
Project label vem do conteúdo do JSONL (session_meta.payload.cwd).
"""

import hashlib
import re
from pathlib import Path
from typing import Optional

from .config import SESSIONS_ROOT


def _extract_session_id_from_filename(file_path: str) -> Optional[str]:
    """Extrai session ID do filename do Codex.

    Formato: rollout-{ISO-timestamp}-{uuid}.jsonl
    Retorna o UUID (parte após o último hífen antes da extensão).
    """
    name = Path(file_path).stem
    # rollout-20260403T120000Z-abc123def456... → UUID é a última parte
    parts = name.rsplit("-", 1)
    if len(parts) == 2:
        return parts[1]
    return None


def _compute_file_hash(file_path: str) -> str:
    """SHA-256 do arquivo para detecção de mudanças."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_project_label_from_meta(file_path: str) -> Optional[str]:
    """Lê o session_meta do JSONL para extrair o project label (cwd)."""
    import json
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("type") == "session_meta":
                    cwd = entry.get("payload", {}).get("cwd", "")
                    if cwd:
                        return cwd.split("/")[-1]
                    return None
    except (json.JSONDecodeError, IOError):
        pass
    return None


def discover_sessions(sessions_root: Optional[Path] = None,
                      session_ids: Optional[list[str]] = None) -> list[dict]:
    """
    Descobre sessões Codex no filesystem.

    Args:
        sessions_root: Raiz das sessões (default: ~/.codex/sessions/)
        session_ids: Se fornecido, filtra por session IDs específicos

    Returns:
        Lista de dicts com file_path, session_id, file_hash, project_label
    """
    root = sessions_root or SESSIONS_ROOT
    if not root.exists():
        return []

    jsonl_files = sorted(root.glob("**/*.jsonl"))
    sessions = []

    for file_path in jsonl_files:
        session_id = _extract_session_id_from_filename(str(file_path))
        if not session_id:
            continue

        if session_ids and session_id not in session_ids:
            continue

        file_hash = _compute_file_hash(str(file_path))
        project_label = _get_project_label_from_meta(str(file_path))

        sessions.append({
            "file_path": str(file_path),
            "session_id": session_id,
            "file_hash": file_hash,
            "project_label": project_label or "unknown",
        })

    return sessions
