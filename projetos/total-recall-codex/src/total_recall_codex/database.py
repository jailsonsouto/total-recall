"""
database.py — Conexão e schema SQLite do Total Recall
======================================================

Arquivo único SQLite (WAL mode) com:
  - sessions: metadados de cada sessão indexada
  - chunks + chunks_vec + chunks_fts: conteúdo indexado
  - embedding_cache: evita recomputar embeddings
  - indexing_runs: log de execuções do indexador
"""

import sqlite3
import struct
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import sqlite_vec

from .config import DB_PATH, EMBEDDING_DIMENSIONS


def serialize_vector(vector: list[float]) -> bytes:
    """Converte lista de floats em bytes (4 bytes por float32)."""
    return struct.pack(f"{len(vector)}f", *vector)


def deserialize_vector(blob: bytes) -> list[float]:
    """Converte bytes de volta para lista de floats."""
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


class Database:
    """
    Gerenciador do banco SQLite com sqlite-vec + FTS5.

    Uso:
        db = Database()
        with db.connection() as conn:
            conn.execute("SELECT ...")
        with db.transaction() as conn:
            conn.execute("INSERT ...")  # atômico
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self):
        conn = self._get_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self.transaction() as conn:

            # ── SESSIONS ────────────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id        TEXT PRIMARY KEY,
                    project_path      TEXT NOT NULL,
                    project_label     TEXT,
                    title             TEXT,
                    started_at        TIMESTAMP,
                    ended_at          TIMESTAMP,
                    user_messages     INTEGER DEFAULT 0,
                    asst_messages     INTEGER DEFAULT 0,
                    file_path         TEXT NOT NULL UNIQUE,
                    file_hash         TEXT NOT NULL,
                    file_size         INTEGER DEFAULT 0,
                    is_subagent       BOOLEAN DEFAULT FALSE,
                    parent_session_id TEXT,
                    indexed_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_started
                ON sessions(started_at)
            """)

            # ── CHUNKS ──────────────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id    TEXT NOT NULL REFERENCES sessions(session_id),
                    role          TEXT NOT NULL,
                    content       TEXT NOT NULL,
                    timestamp     TIMESTAMP,
                    chunk_index   INTEGER NOT NULL,
                    line_start    INTEGER,
                    line_end      INTEGER,
                    has_embedding BOOLEAN DEFAULT TRUE,
                    embed_model   TEXT,
                    metadata      TEXT,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_session
                ON chunks(session_id)
            """)

            # ── CHUNKS_VEC (sqlite-vec) ─────────────────────────
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec
                USING vec0(embedding float[{EMBEDDING_DIMENSIONS}])
            """)

            # ── CHUNKS_FTS (FTS5) ───────────────────────────────
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(content, session_id, role)
            """)

            # ── EMBEDDING CACHE ─────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    text_hash   TEXT PRIMARY KEY,
                    embedding   BLOB NOT NULL,
                    model       TEXT NOT NULL,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # ── INDEXING RUNS ───────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS indexing_runs (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at        TIMESTAMP,
                    files_scanned   INTEGER DEFAULT 0,
                    files_indexed   INTEGER DEFAULT 0,
                    chunks_created  INTEGER DEFAULT 0,
                    errors          TEXT
                )
            """)

            # ── GRAPH LITE: entidades e co-ocorrência ──────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL UNIQUE,
                    type        TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunk_entities (
                    chunk_id    INTEGER REFERENCES chunks(id),
                    entity_id   INTEGER REFERENCES entities(id),
                    PRIMARY KEY (chunk_id, entity_id)
                )
            """)

    def recreate_vec_table(self):
        """Recria chunks_vec com a dimensão atual (para migração de modelo)."""
        with self.transaction() as conn:
            conn.execute("DROP TABLE IF EXISTS chunks_vec")
            conn.execute(f"""
                CREATE VIRTUAL TABLE chunks_vec
                USING vec0(embedding float[{EMBEDDING_DIMENSIONS}])
            """)
