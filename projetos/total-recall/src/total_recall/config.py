"""
config.py — Configuração centralizada do Total Recall
=====================================================

Todas as constantes e caminhos em um só lugar.
Configurável via variáveis de ambiente ou .env.
"""

import os
from pathlib import Path

# ══════════════════════════════════════════════════════════════
# CAMINHOS
# ══════════════════════════════════════════════════════════════

# Diretório de dados em runtime (~/.total-recall/)
DATA_DIR = Path(os.getenv(
    "TOTAL_RECALL_DATA",
    str(Path.home() / ".total-recall")
))

# Banco SQLite (WAL mode, sqlite-vec + FTS5)
DB_PATH = DATA_DIR / "total-recall.db"

# Exportações Markdown das sessões
EXPORTS_PATH = DATA_DIR / "exports"

# Raiz dos projetos Claude Code (onde ficam os JSONLs)
SESSIONS_ROOT = Path(os.getenv(
    "TOTAL_RECALL_SESSIONS",
    str(Path.home() / ".claude" / "projects")
))

# ══════════════════════════════════════════════════════════════
# EMBEDDING
# ══════════════════════════════════════════════════════════════

EMBED_PROVIDER = os.getenv("TOTAL_RECALL_EMBED_PROVIDER", "ollama")

# Ollama (default)
OLLAMA_BASE_URL = os.getenv("TOTAL_RECALL_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_EMBED_MODEL = os.getenv("TOTAL_RECALL_OLLAMA_MODEL", "qwen3-embedding:4b")

# Dimensão dos vetores (1024 = bom equilíbrio para busca híbrida)
EMBEDDING_DIMENSIONS = int(os.getenv("TOTAL_RECALL_EMBEDDING_DIMENSIONS", "1024"))

# Instrução para queries (Qwen é instruction-aware)
EMBED_QUERY_INSTRUCTION = os.getenv(
    "TOTAL_RECALL_EMBED_QUERY_INSTRUCTION",
    "Given a search query in Portuguese or English, "
    "retrieve relevant Claude Code conversation passages that answer the query."
)

# OpenAI (alternativa paga)
OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ══════════════════════════════════════════════════════════════
# BUSCA
# ══════════════════════════════════════════════════════════════

VECTOR_WEIGHT = 0.7
TEXT_WEIGHT = 0.3

# Budget de tokens no output do /recall
CONTEXT_BUDGET = 6000

# ══════════════════════════════════════════════════════════════
# FUZZY MATCHING (V02)
# ══════════════════════════════════════════════════════════════

# Similaridade mínima para expansão fuzzy (0.0–1.0)
FUZZY_THRESHOLD = float(os.getenv("TOTAL_RECALL_FUZZY_THRESHOLD", "0.70"))

# Máximo de variantes por token
FUZZY_MAX_EXPANSIONS = int(os.getenv("TOTAL_RECALL_FUZZY_MAX_EXPANSIONS", "5"))

# Tokens menores que isso não passam por fuzzy (evita falsos positivos)
FUZZY_MIN_TOKEN_LENGTH = int(os.getenv("TOTAL_RECALL_FUZZY_MIN_TOKEN_LENGTH", "4"))

# ══════════════════════════════════════════════════════════════
# TEMPORAL DECAY
# ══════════════════════════════════════════════════════════════

# Meia-vida em dias: após 30 dias, score cai pela metade
DECAY_HALF_LIFE_DAYS = 30

# Lambda para MMR (Maximal Marginal Relevance)
# 1.0 = só relevância, 0.0 = só diversidade
MMR_LAMBDA = 0.7

# ══════════════════════════════════════════════════════════════
# CHUNKING
# ══════════════════════════════════════════════════════════════

MAX_CHUNK_CHARS = 1500       # ~375 tokens por chunk
CHUNK_OVERLAP_CHARS = 200    # overlap entre chunks consecutivos

# Indexar subagents por padrão? (geralmente ruidosos)
INDEX_SUBAGENTS = os.getenv(
    "TOTAL_RECALL_INDEX_SUBAGENTS", "false"
).lower() == "true"
