"""
session_parser.py — Parser para JSONL do Codex
===============================================

Formato de entrada (Codex JSONL):
- Top-level `type`: session_meta, response_item, event_msg, turn_context, compacted
- response_item.payload.type: message, function_call, function_call_output, reasoning,
  custom_tool_call, custom_tool_call_output, web_search_call
- event_msg.payload.type: task_started, task_complete, token_count, agent_message,
  user_message, context_compacted, turn_aborted, item_completed, thread_rolled_back

Unidade de chunking: turn-based (cada task_started → task_complete = um turno)
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Chunk, SessionInfo

# Marcadores seletivos para blocos internos (decisões, diagnósticos, planejamento)
_SELECTIVE_MARKERS = {
    # PT-BR — decisões
    "decidimos", "decisão", "decisao", "escolhemos", "optamos", "vamos usar",
    "vamos fazer", "a melhor abordagem", "a abordagem correta",
    # PT-BR — diagnósticos
    "o problema é", "o problema era", "root cause", "a causa",
    "não funciona", "nao funciona", "não funcionou", "nao funcionou",
    "falha", "erro", "bug", "issue",
    # PT-BR — planejamento
    "plano", "precisamos", "temos que", "vou criar", "vou adicionar",
    "próximo passo", "proximo passo", "next step",
    # EN — decisions
    "we decided", "we chose", "we'll use", "we will use", "going to use",
    "the best approach", "the right approach",
    # EN — diagnostics
    "the issue is", "the problem is", "root cause", "doesn't work",
    "did not work", "didn't work", "fails", "error",
    # EN — planning
    "we need to", "let's create", "let's add", "next step",
    # Rejeições (memória diagnóstica)
    "descartamos", "descartado", "não vamos usar", "nao vamos usar",
    "não faz sentido", "nao faz sentido", "rejected", "discard",
    "instead of", "ao invés de", "ao inves de",
}


def _parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    """Normaliza timestamp ISO para datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _has_selective_marker(text: str) -> bool:
    """Verifica se o texto contém marcadores de decisão/diagnóstico."""
    lower = text.lower()
    return any(marker in lower for marker in _SELECTIVE_MARKERS)


def _extract_entities(text: str) -> list[str]:
    """Extrai entidades candidatas do texto para Graph Lite."""
    entities = set()
    # Backtick terms: `sqlite-vec`, `ChromaDB`
    entities.update(re.findall(r'`([^`]+)`', text))
    # ADR references: ADR-001, ADR 002
    entities.update(re.findall(r'(ADR[-\s]?\d+)', text))
    # ALL-CAPS technical terms (3+ chars): SQLite, ChromaDB, PostgreSQL
    # Filtra path components comuns
    _PATH_NOISE = {"OneDrive", "CloudStorage", "MEUS", "PROJETOS", "AGENTES",
                   "IA", "CLAUDE", "src", "bin", "lib", "Users", "Library",
                   "COMPLETO", "EM", "PARA", "COM", "DE", "NA", "NO", "DA", "DO"}
    caps = re.findall(r'\b([A-Z][a-zA-Z]{2,}[A-Z][a-zA-Z]*)\b', text)
    entities.update(c for c in caps if c not in _PATH_NOISE)
    # Short ALL-CAPS acronyms: API, GPU, SQL, PLN
    _ACOYM_NOISE = {"OK", "NEU", "PT", "BR", "REPLY", "PARENT", "THE", "AND",
                    "FOR", "NOT", "GET", "SET", "NEW", "USE", "HAS", "WAS",
                    "ALL", "OFF", "TOP", "OUT", "PUT", "RUN", "LOG", "END",
                    "ERR", "STD", "ENV", "VAR", "KEY", "VAL", "RAW"}
    acronyms = re.findall(r'\b([A-Z]{2,4})\b', text)
    entities.update(a for a in acronyms if a not in _ACOYM_NOISE)
    return sorted(entities)


def _chunk_content_for_turn(turn_messages: list[dict], turn_start_ts: Optional[str]) -> tuple[str, str, Optional[str], list[str]]:
    """
    Monta o conteúdo de um turno a partir das mensagens coletadas.

    Returns (content, role, timestamp, entities)
    """
    if not turn_messages:
        return "", "", turn_start_ts, []

    parts = []
    role = "exchange"
    user_parts = []
    assistant_parts = []
    agent_parts = []
    all_entities = []

    for msg in turn_messages:
        msg_type = msg.get("msg_type", "")
        content = msg.get("content", "")
        ts = msg.get("timestamp", turn_start_ts)

        if msg_type == "user":
            user_parts.append(f"[Usuário]: {content}")
        elif msg_type == "assistant":
            assistant_parts.append(f"[Codex]: {content}")
        elif msg_type == "agent":
            agent_parts.append(f"[Agente]: {content}")

        all_entities.extend(msg.get("entities", []))

    if user_parts and assistant_parts:
        parts = user_parts + [""] + assistant_parts
        role = "exchange"
    elif user_parts:
        parts = user_parts
        role = "user"
    elif assistant_parts:
        parts = assistant_parts
        role = "assistant"
    elif agent_parts:
        parts = agent_parts
        role = "agent"

    content = "\n\n".join(parts)
    entities = sorted(set(all_entities))

    return content, role, turn_start_ts, entities


def _merge_short_turns(turns: list[dict], min_chars: int = 200) -> list[dict]:
    """Merge turn dicts curtos do mesmo role consecutivo.

    Codex turn-based chunking pode gerar chunks de 1-2 linhas.
    Merge chunks consecutivos do mesmo role até atingir min_chars.
    """
    if not turns:
        return []

    merged = []
    current = turns[0].copy()

    for turn in turns[1:]:
        if turn["role"] == current["role"] and len(current["content"]) < min_chars:
            current["content"] += "\n\n" + turn["content"]
            current["entities"] = sorted(set(current["entities"] + turn["entities"]))
            # Mantém o timestamp mais recente
            if turn["timestamp"]:
                current["timestamp"] = turn["timestamp"]
        else:
            merged.append(current)
            current = turn.copy()

    merged.append(current)
    return merged


def _split_chunk_if_too_large(content: str, role: str, timestamp: Optional[str],
                               entities: list[str], max_chars: int = 1500,
                               overlap: int = 200) -> list[tuple[str, str, Optional[str], list[str]]]:
    """Divide chunks muito grandes preservando contexto."""
    if len(content) <= max_chars:
        return [(content, role, timestamp, entities)]

    chunks = []
    start = 0
    while start < len(content):
        end = start + max_chars
        chunk_text = content[start:end]

        # Tenta quebrar em limite de parágrafo
        if end < len(content):
            last_newline = chunk_text.rfind("\n\n")
            if last_newline > max_chars * 0.5:
                end = start + last_newline
                chunk_text = content[start:end]

        chunks.append((chunk_text, role, timestamp, entities))
        start = end - overlap if end < len(content) else end

    return chunks


def parse_codex_session(file_path: str,
                        max_chunk_chars: int = 1500,
                        chunk_overlap: int = 200) -> tuple[SessionInfo, list[Chunk]]:
    """
    Parser principal para sessões Codex.

    Formato: JSONL com entries do tipo:
      { "type": "session_meta" | "response_item" | "event_msg" | "turn_context" | "compacted",
        "payload": { ... } }

    Returns (SessionInfo, list[Chunk])
    """
    entries = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not entries:
        raise ValueError(f"Arquivo vazio ou inválido: {file_path}")

    # ── Extrair session meta ──────────────────────────────────
    session_meta = None
    for entry in entries:
        if entry.get("type") == "session_meta":
            session_meta = entry.get("payload", {})
            break

    if not session_meta:
        raise ValueError(f"Nenhum session_meta encontrado em: {file_path}")

    session_id = session_meta.get("id", "")
    cwd = session_meta.get("cwd", "")
    project_label = cwd.split("/")[-1] if cwd else "unknown"
    originator = session_meta.get("originator", "Codex")
    model = session_meta.get("model", "")
    cli_version = session_meta.get("cli_version", "")

    # Timestamps
    started_at = session_meta.get("timestamp")
    ended_at = None
    for entry in reversed(entries):
        ts = entry.get("payload", {}).get("timestamp")
        if ts:
            ended_at = ts
            break

    # ── Parse turn-based chunks ───────────────────────────────
    turns = []
    current_turn_messages = []
    current_turn_start_ts = None
    in_turn = False

    for entry in entries:
        entry_type = entry.get("type", "")
        payload = entry.get("payload", {})
        payload_type = payload.get("type", "")

        if entry_type == "event_msg" and payload_type == "task_started":
            in_turn = True
            current_turn_start_ts = payload.get("timestamp")
            current_turn_messages = []

        elif entry_type == "event_msg" and payload_type == "task_complete":
            if in_turn and current_turn_messages:
                content, role, ts, entities = _chunk_content_for_turn(
                    current_turn_messages, current_turn_start_ts
                )
                if content:
                    sub_chunks = _split_chunk_if_too_large(
                        content, role, ts, entities, max_chunk_chars, chunk_overlap
                    )
                    for sc, sr, st, se in sub_chunks:
                        turns.append({
                            "content": sc,
                            "role": sr,
                            "timestamp": st,
                            "entities": se,
                        })
            in_turn = False
            current_turn_messages = []

        elif in_turn:
            msg = None
            msg_type = None

            if entry_type == "response_item" and payload_type == "message":
                message = payload.get("message", {})
                role = message.get("role", "")
                content_parts = message.get("content", [])

                if isinstance(content_parts, list):
                    text_parts = []
                    for part in content_parts:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                    text = "\n".join(text_parts).strip()
                elif isinstance(content_parts, str):
                    text = content_parts
                else:
                    text = ""

                if text:
                    if role == "user":
                        msg_type = "user"
                    elif role == "assistant":
                        msg_type = "assistant"
                    else:
                        msg_type = "assistant"

                    msg = {
                        "msg_type": msg_type,
                        "content": text,
                        "timestamp": payload.get("timestamp"),
                        "entities": _extract_entities(text),
                    }

            elif entry_type == "event_msg" and payload_type == "agent_message":
                text = payload.get("message", "") or payload.get("content", "")
                if text and _has_selective_marker(text):
                    msg = {
                        "msg_type": "agent",
                        "content": text,
                        "timestamp": payload.get("timestamp"),
                        "entities": _extract_entities(text),
                    }

            elif entry_type == "event_msg" and payload_type == "user_message":
                text = payload.get("message", "") or payload.get("content", "")
                if text:
                    msg = {
                        "msg_type": "user",
                        "content": text,
                        "timestamp": payload.get("timestamp"),
                        "entities": _extract_entities(text),
                    }

            if msg:
                current_turn_messages.append(msg)

    # ── Merge chunks muito curtos do mesmo role ────────────────
    turns = _merge_short_turns(turns, min_chars=200)

    # ── Contar mensagens ──────────────────────────────────────
    user_messages = sum(1 for t in turns if t["role"] in ("user", "exchange"))
    asst_messages = sum(1 for t in turns if t["role"] in ("assistant", "agent", "exchange"))

    # Hash do arquivo
    file_hash = hashlib.sha256(open(file_path, "rb").read()).hexdigest()
    file_size = Path(file_path).stat().st_size

    session_info = SessionInfo(
        session_id=session_id,
        project_path=cwd,
        project_label=project_label,
        title=f"Codex — {project_label}",
        started_at=_parse_timestamp(started_at),
        ended_at=_parse_timestamp(ended_at),
        user_messages=user_messages,
        asst_messages=asst_messages,
        file_path=file_path,
        file_size=file_size,
        is_subagent=False,
        parent_session_id=None,
    )

    chunks = []
    # Fallback: usa o timestamp da sessão para chunks sem timestamp próprio
    session_ts = _parse_timestamp(started_at)
    for i, turn in enumerate(turns):
        ts = _parse_timestamp(turn["timestamp"]) or session_ts
        chunks.append(Chunk(
            id=None,
            session_id=session_id,
            role=turn["role"],
            content=turn["content"],
            timestamp=ts,
            chunk_index=i,
            line_start=None,
            line_end=None,
            has_embedding=True,
            metadata={"entities": turn["entities"]} if turn["entities"] else {},
        ))

    return session_info, chunks
