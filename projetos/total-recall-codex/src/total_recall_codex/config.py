"""
config.py — Configuração global do Total Recall Codex
======================================================

Todos os paths, pesos e parâmetros de busca.
Variáveis de ambiente com prefixo TOTAL_RECALL_CODEX_* sobrescrevem defaults.
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────
DATA_DIR = Path(os.getenv("TOTAL_RECALL_CODEX_DATA", str(Path.home() / ".total-recall-codex")))
DB_PATH = DATA_DIR / "total-recall-codex.db"
EXPORTS_PATH = DATA_DIR / "exports"
SESSIONS_ROOT = Path(os.getenv("TOTAL_RECALL_CODEX_SESSIONS", str(Path.home() / ".codex" / "sessions")))

# ── Embedding ──────────────────────────────────────────────────
EMBED_PROVIDER = os.getenv("TOTAL_RECALL_CODEX_EMBED_PROVIDER", "ollama")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_EMBED_MODEL = os.getenv("TOTAL_RECALL_CODEX_OPENAI_MODEL", "text-embedding-3-small")
OPENAI_BASE_URL = os.getenv("TOTAL_RECALL_CODEX_OPENAI_BASE_URL", "")
OLLAMA_BASE_URL = os.getenv("TOTAL_RECALL_CODEX_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_EMBED_MODEL = os.getenv("TOTAL_RECALL_CODEX_OLLAMA_MODEL", "qwen3-embedding:4b")
EMBEDDING_DIMENSIONS = int(os.getenv("TOTAL_RECALL_CODEX_EMBEDDING_DIMENSIONS", "1024"))

EMBED_QUERY_INSTRUCTION = (
    "Given a search query in Portuguese or English, retrieve relevant "
    "Codex session passages that match the user's intent."
)

# ── Busca híbrida ──────────────────────────────────────────────
VECTOR_WEIGHT = 0.7
TEXT_WEIGHT = 0.3
CONTEXT_BUDGET = 6000
MIN_VECTOR_ONLY_SCORE = float(os.getenv("TOTAL_RECALL_CODEX_MIN_SCORE", "0.42"))
ADAPTIVE_VECTOR_WEIGHT_SPECIFIC = float(os.getenv("TOTAL_RECALL_CODEX_ADAPTIVE_VECTOR_WEIGHT", "0.25"))
ADAPTIVE_TEXT_WEIGHT_SPECIFIC = float(os.getenv("TOTAL_RECALL_CODEX_ADAPTIVE_TEXT_WEIGHT", "0.75"))
FUZZY_THRESHOLD = float(os.getenv("TOTAL_RECALL_CODEX_FUZZY_THRESHOLD", "0.70"))
FUZZY_MAX_EXPANSIONS = int(os.getenv("TOTAL_RECALL_CODEX_FUZZY_MAX_EXPANSIONS", "5"))
FUZZY_MIN_TOKEN_LENGTH = int(os.getenv("TOTAL_RECALL_CODEX_FUZZY_MIN_TOKEN_LENGTH", "4"))

# ── Recall engine ──────────────────────────────────────────────
DECAY_HALF_LIFE_DAYS = 30
MMR_LAMBDA = 0.7

# ── Chunking ───────────────────────────────────────────────────
MAX_CHUNK_CHARS = 1500
CHUNK_OVERLAP_CHARS = 200
