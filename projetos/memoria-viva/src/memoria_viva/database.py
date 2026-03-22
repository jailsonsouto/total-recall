"""
database.py — Conexão e schema do banco de dados SQLite
=======================================================

Este é o "cérebro" do sistema — um ÚNICO arquivo SQLite que guarda:
    - Hot Store: estado dos briefings, scores, decisões do Comitê
    - Warm Store: vetores para busca semântica + keywords para busca textual

DECISÃO DE DESIGN (ADR-001):
    Tudo no mesmo arquivo elimina a necessidade de dois bancos separados
    e garante transações atômicas (tudo ou nada) — crítico para o
    Committee Flush, que NUNCA pode deixar o banco inconsistente.

O ARQUIVO .DB:
    Fica em: data/novex-memory.db (configurável no .env)
    É um único arquivo que você pode copiar, fazer backup, versionar.

O QUE É WAL MODE?
    WAL = Write-Ahead Logging. É um modo do SQLite que:
    1. Permite leituras enquanto uma escrita está acontecendo
    2. Garante que, se o computador desligar no meio de uma escrita,
       o banco não fica corrompido (a escrita é revertida)
    Isso é CRÍTICO para o Committee Flush — se cair no meio,
    o banco volta ao estado anterior, não fica meio-escrito.
"""

import sqlite3
import struct
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import sqlite_vec

from .config import DB_PATH, EMBEDDING_DIMENSIONS


# ══════════════════════════════════════════════════════════════
# FUNÇÕES DE SERIALIZAÇÃO DE VETORES
# ══════════════════════════════════════════════════════════════
#
# O sqlite-vec guarda vetores como bytes (sequências de 0s e 1s),
# não como texto. Isso é muito mais eficiente para armazenamento
# e busca. Estas funções convertem entre os dois formatos.


def serialize_vector(vector: list[float]) -> bytes:
    """
    Converte uma lista de números decimais em bytes.

    Exemplo: [0.1, 0.2, 0.3] → b'\\xcd\\xcc\\xcc=...' (12 bytes)

    Cada número ocupa 4 bytes (float32), então:
        768 dimensões × 4 bytes = 3.072 bytes por vetor (~3 KB)

    Isso é importante porque:
        4.500 vetores/ano × 3 KB = ~13 MB/ano
        Em 10 anos: ~130 MB — cabe no bolso.
    """
    return struct.pack(f"{len(vector)}f", *vector)


def deserialize_vector(blob: bytes) -> list[float]:
    """Converte bytes de volta para lista de números decimais."""
    n = len(blob) // 4  # cada float32 = 4 bytes
    return list(struct.unpack(f"{n}f", blob))


# ══════════════════════════════════════════════════════════════
# CLASSE PRINCIPAL
# ══════════════════════════════════════════════════════════════


class Database:
    """
    Gerenciador do banco de dados SQLite.

    Responsável por:
        1. Criar o arquivo .db se não existir
        2. Configurar WAL mode (segurança contra crash)
        3. Carregar a extensão sqlite-vec (busca vetorial)
        4. Criar todas as tabelas na primeira execução
        5. Fornecer conexões para os outros módulos

    Uso:
        db = Database()
        with db.connection() as conn:
            conn.execute("SELECT * FROM briefing_threads")

        with db.transaction() as conn:
            conn.execute("INSERT INTO ...")  # tudo ou nada
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        # Cria a pasta 'data/' se não existir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Cria as tabelas na primeira execução
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Cria uma nova conexão SQLite com as extensões carregadas.

        Cada conexão é independente — isso é importante porque
        SQLite permite leituras concorrentes com WAL mode, mas
        cada leitura precisa da sua própria conexão.
        """
        conn = sqlite3.connect(str(self.db_path))

        # Row factory: permite acessar colunas por nome
        # Em vez de row[0], row[1], pode usar row["thread_id"]
        conn.row_factory = sqlite3.Row

        # Carrega a extensão sqlite-vec (busca vetorial)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        # WAL mode: segurança contra crash + leituras concorrentes
        conn.execute("PRAGMA journal_mode = WAL")
        # Integridade referencial: garante que referências entre tabelas são válidas
        conn.execute("PRAGMA foreign_keys = ON")

        return conn

    @contextmanager
    def connection(self):
        """
        Fornece uma conexão que se fecha automaticamente.

        Uso:
            with db.connection() as conn:
                rows = conn.execute("SELECT ...").fetchall()
            # conexão é fechada automaticamente aqui
        """
        conn = self._get_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """
        Fornece uma conexão dentro de uma transação atômica.

        ATÔMICO significa: ou TUDO dentro do bloco é salvo,
        ou NADA é salvo. Não existe estado "meio-escrito".

        Isso é CRÍTICO para o Committee Flush:
            - Escrita 1 (Hot Store: decisão do Comitê)
            - Escrita 2 (Warm Store: padrão embedado)
        Se qualquer uma falhar, as duas são revertidas.

        Uso:
            with db.transaction() as conn:
                conn.execute("UPDATE ...")  # escrita 1
                conn.execute("INSERT ...")  # escrita 2
                # Se chegar aqui sem erro → COMMIT (salva tudo)
                # Se der erro em qualquer linha → ROLLBACK (desfaz tudo)
        """
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
        """
        Cria todas as tabelas na primeira execução.

        Se as tabelas já existem, não faz nada (IF NOT EXISTS).
        Isso torna seguro rodar múltiplas vezes — não perde dados.

        As tabelas são organizadas em duas camadas:
            HOT STORE: dados estruturados (briefings, scores, padrões)
            WARM STORE: vetores e texto indexado (busca semântica + keyword)
        """
        with self.transaction() as conn:

            # ─── HOT STORE ────────────────────────────────────────
            # Dados estruturados: briefings, scores, decisões.
            # São acessados por queries SQL tradicionais.

            # Tabela principal: cada linha é um briefing completo
            conn.execute("""
                CREATE TABLE IF NOT EXISTS briefing_threads (
                    thread_id           TEXT PRIMARY KEY,
                    product_idea        TEXT NOT NULL,
                    pm_id               TEXT NOT NULL DEFAULT 'jay',
                    segment             TEXT,
                    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    current_status      TEXT NOT NULL DEFAULT 'running',
                    iam_score           REAL,
                    bvs_preditivo       REAL,
                    bvs_real            REAL,
                    rice_score          REAL,
                    icb_score           REAL,
                    committee_decision  TEXT,
                    committee_date      TIMESTAMP,
                    committee_reasons   TEXT,
                    committee_notes     TEXT,
                    memory_flush_done   BOOLEAN DEFAULT FALSE,
                    memory_flush_at     TIMESTAMP,
                    last_memory_read_at TIMESTAMP,
                    langgraph_thread_id TEXT UNIQUE
                )
            """)

            # Calibrações de score (atualizada a cada 5 decisões)
            # Registra o viés sistemático do Agente 2 para corrigir previsões futuras
            conn.execute("""
                CREATE TABLE IF NOT EXISTS score_calibrations (
                    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                    calibration_date         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    n_data_points            INTEGER NOT NULL,
                    bvs_onda1_adjustment     REAL DEFAULT 0.0,
                    bvs_onda2_adjustment     REAL DEFAULT 0.0,
                    bvs_onda3_adjustment     REAL DEFAULT 0.0,
                    bvs_total_adjustment     REAL DEFAULT 0.0,
                    rice_confidence_baseline REAL DEFAULT 6.0,
                    confidence_level         TEXT DEFAULT 'baixa'
                )
            """)

            # Padrões de memória (aprendidos de aprovações/rejeições)
            # Cada padrão é uma "lição" extraída de decisões passadas
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_patterns (
                    id               TEXT PRIMARY KEY,
                    pattern_type     TEXT NOT NULL,
                    segment          TEXT,
                    description      TEXT NOT NULL,
                    occurrences      INTEGER DEFAULT 1,
                    confidence       TEXT DEFAULT 'baixa',
                    first_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active        BOOLEAN DEFAULT TRUE,
                    rejection_alert  BOOLEAN DEFAULT FALSE,
                    source_thread_ids TEXT
                )
            """)

            # ─── WARM STORE ───────────────────────────────────────
            # Vetores e texto indexado: busca por significado e por palavra.
            # Três tabelas trabalhando juntas, ligadas por rowid:
            #
            #   chunks (metadados) ←→ chunks_vec (vetores) ←→ chunks_fts (texto)
            #
            # Quando adicionamos um texto:
            #   1. Insere em chunks → recebe um ID (rowid)
            #   2. Insere o vetor em chunks_vec com o MESMO rowid
            #   3. Insere o texto em chunks_fts com o MESMO rowid
            # Assim conseguimos buscar por vetor e voltar ao texto original.

            # Tabela de metadados dos chunks (tabela normal)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection  TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    embed_model TEXT NOT NULL,
                    metadata    TEXT,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Índice para busca rápida por coleção
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_collection
                ON chunks(collection)
            """)

            # Tabela virtual sqlite-vec: guarda APENAS os vetores
            # float[768] → cada vetor tem 768 números decimais (nomic-embed-text)
            # Se trocar para OpenAI, precisa recriar com float[1536]
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec
                USING vec0(embedding float[{EMBEDDING_DIMENSIONS}])
            """)

            # Tabela virtual FTS5: busca por palavra-chave
            # Permite buscar "quinoa" por texto exato, não por significado
            # FTS5 é built-in no SQLite — zero dependências extras
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(content, collection)
            """)

            # Cache de embeddings: evita recalcular vetores para textos iguais
            # Se o mesmo texto for embedado duas vezes, usa o cache
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embedding_cache (
                    text_hash   TEXT PRIMARY KEY,
                    embedding   BLOB NOT NULL,
                    model       TEXT NOT NULL,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
