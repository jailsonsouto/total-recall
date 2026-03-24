"""
session_parser.py — Parser de sessões JSONL do Claude Code
==========================================================

Lê um arquivo JSONL, extrai metadados da sessão e produz
chunks indexáveis baseados em exchanges (pergunta + resposta).
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS
from .models import SessionInfo, Chunk


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Converte ISO timestamp para datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _extract_text(content) -> str:
    """
    Extrai texto puro de um campo content (str ou lista de blocos).
    Ignora tool_use, tool_result e thinking — só indexa texto legível.
    """
    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, list):
        return ""

    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text", "").strip()
            if text:
                parts.append(text)

    return "\n\n".join(parts)


def _chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """
    Divide texto longo em chunks com overlap.
    Tenta quebrar em parágrafos; se não for possível, quebra por char.
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars

        # Tenta quebrar no último parágrafo dentro do range
        if end < len(text):
            last_break = text.rfind("\n\n", start, end)
            if last_break > start + max_chars // 3:
                end = last_break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Avança com overlap
        start = end - overlap if end < len(text) else len(text)

    return chunks


class SessionParser:
    """Parseia um único JSONL e produz SessionInfo + lista de Chunks."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._entries: list[dict] = []
        self._line_map: dict[str, int] = {}  # uuid → line number

    def parse(self) -> tuple[SessionInfo, list[Chunk]]:
        """Retorna (metadados da sessão, lista de chunks)."""
        self._load_entries()
        session_info = self._extract_session_info()
        chunks = self._build_chunks()
        return session_info, chunks

    def _load_entries(self):
        """Carrega JSONL, ignora linhas malformadas."""
        self._entries = []
        self._line_map = {}
        with open(self.file_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    uid = entry.get("uuid")
                    if uid:
                        self._line_map[uid] = line_num
                    self._entries.append(entry)
                except json.JSONDecodeError:
                    continue

    def _extract_session_info(self) -> SessionInfo:
        """Extrai metadados da sessão."""
        session_id = ""
        project_path = ""
        title = ""
        started_at = None
        ended_at = None
        user_count = 0
        asst_count = 0

        for e in self._entries:
            etype = e.get("type", "")

            if etype == "system" and not session_id:
                session_id = e.get("sessionId", "")
                started_at = _parse_timestamp(e.get("timestamp", ""))

            if etype == "custom-title" and not title:
                title = e.get("title", "")

            if etype == "user" and not e.get("isSidechain"):
                user_count += 1
            if etype == "assistant" and not e.get("isSidechain"):
                asst_count += 1

            ts = _parse_timestamp(e.get("timestamp", ""))
            if ts:
                ended_at = ts

        # Derive project info from file path
        project_dir = self.file_path.parent.name
        project_label = self._derive_project_label(project_dir)

        # Fallback session_id from filename
        if not session_id:
            session_id = self.file_path.stem

        # Fallback title
        if not title:
            title = f"Sessão {session_id[:8]}"

        return SessionInfo(
            session_id=session_id,
            project_path=project_dir,
            project_label=project_label,
            title=title,
            started_at=started_at,
            ended_at=ended_at,
            user_messages=user_count,
            asst_messages=asst_count,
            file_path=str(self.file_path),
            file_size=self.file_path.stat().st_size,
            is_subagent="subagent" in str(self.file_path),
            parent_session_id=self._detect_parent_session(),
        )

    def _derive_project_label(self, project_dir: str) -> str:
        """
        Converte nome do diretório em label legível.
        '-Users-criacao-Library-CloudStorage-OneDrive-Embelleze-MEUS-PROJETOS-IA-AGENTES-CLAUDE'
        → 'AGENTES/CLAUDE'
        """
        parts = [p for p in project_dir.split("-") if p and p != "Users"]
        if len(parts) >= 2:
            return "/".join(parts[-2:])
        return project_dir[:30] if project_dir else "unknown"

    def _detect_parent_session(self) -> Optional[str]:
        """Para subagents: extrai session_id do diretório pai."""
        parts = self.file_path.parts
        for i, p in enumerate(parts):
            if p == "subagents" and i > 0:
                return parts[i - 1]
        return None

    def _build_chunks(self) -> list[Chunk]:
        """
        Constrói chunks baseados em exchanges (user + assistant).
        Cada exchange é uma unidade semântica.
        """
        # Filtra user/assistant, ordena por timestamp, exclui sidechains
        messages = [
            e for e in self._entries
            if e.get("type") in ("user", "assistant")
            and not e.get("isSidechain", False)
        ]
        messages.sort(key=lambda x: x.get("timestamp", ""))

        # Emparelha user → assistant por parentUuid
        exchanges = self._pair_exchanges(messages)
        chunks = []

        for idx, (user_entry, asst_entry) in enumerate(exchanges):
            user_text = ""
            asst_text = ""
            timestamp = None
            line_start = None
            line_end = None

            if user_entry:
                user_text = _extract_text(user_entry.get("message", {}).get("content", ""))
                timestamp = _parse_timestamp(user_entry.get("timestamp", ""))
                uid = user_entry.get("uuid")
                if uid:
                    line_start = self._line_map.get(uid)

            if asst_entry:
                asst_text = _extract_text(asst_entry.get("message", {}).get("content", []))
                if not timestamp:
                    timestamp = _parse_timestamp(asst_entry.get("timestamp", ""))
                uid = asst_entry.get("uuid")
                if uid:
                    line_end = self._line_map.get(uid)

            # Monta o exchange
            exchange_parts = []
            if user_text:
                exchange_parts.append(f"[Usuário]: {user_text}")
            if asst_text:
                exchange_parts.append(f"[Claude]: {asst_text}")

            full_text = "\n\n".join(exchange_parts)
            if not full_text.strip():
                continue

            # Chunka se necessário
            text_chunks = _chunk_text(full_text, MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS)

            for ci, chunk_text in enumerate(text_chunks):
                role = "exchange" if user_text and asst_text else (
                    "user" if user_text else "assistant"
                )
                chunks.append(Chunk(
                    id=None,
                    session_id="",  # preenchido pelo indexer
                    role=role,
                    content=chunk_text,
                    timestamp=timestamp,
                    chunk_index=len(chunks),
                    line_start=line_start,
                    line_end=line_end,
                    metadata={"exchange_idx": idx, "sub_chunk": ci},
                ))

        return chunks

    def _pair_exchanges(self, messages: list[dict]) -> list[tuple]:
        """
        Emparelha mensagens user → assistant.
        Usa parentUuid quando disponível, senão emparelha sequencialmente.
        """
        # Indexa por uuid para lookup rápido
        by_uuid = {e.get("uuid"): e for e in messages if e.get("uuid")}

        paired = []
        used = set()

        # Tenta emparelhar por parentUuid
        for msg in messages:
            if msg.get("type") != "assistant":
                continue
            parent_uuid = msg.get("parentUuid")
            if parent_uuid and parent_uuid in by_uuid:
                parent = by_uuid[parent_uuid]
                if parent.get("type") == "user" and parent.get("uuid") not in used:
                    paired.append((parent, msg))
                    used.add(parent.get("uuid"))
                    used.add(msg.get("uuid"))

        # Mensagens user sem par
        for msg in messages:
            uid = msg.get("uuid")
            if uid not in used:
                if msg.get("type") == "user":
                    paired.append((msg, None))
                elif msg.get("type") == "assistant":
                    paired.append((None, msg))

        # Ordena por timestamp
        paired.sort(key=lambda x: (
            x[0] or x[1] or {}
        ).get("timestamp", ""))

        return paired
