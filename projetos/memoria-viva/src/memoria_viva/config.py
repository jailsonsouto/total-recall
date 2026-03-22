"""
config.py — Configuração centralizada da Memória Viva
=====================================================

Este arquivo é o "painel de controle" do sistema. Todas as decisões
de configuração passam por aqui — caminhos de arquivos, qual modelo
de embedding usar, dimensões dos vetores, etc.

QUANDO MEXER AQUI:
    - Trocar de embedding local (nomic) para pago (OpenAI)
    - Mudar onde o banco de dados é armazenado
    - Ajustar parâmetros de busca

QUANDO NÃO MEXER:
    - Nunca altere EMBEDDING_DIMENSIONS sem re-embedar todo o banco.
      Vetores de dimensões diferentes são incomparáveis.
      (ver ADR sobre lock-in de embedding model)

VARIÁVEIS DE AMBIENTE:
    As configurações podem ser definidas no arquivo .env ou
    exportadas no terminal. O arquivo .env.example mostra todas.
"""

import os
from pathlib import Path


# ══════════════════════════════════════════════════════════════
# CAMINHOS
# ══════════════════════════════════════════════════════════════

# Raiz do projeto (projetos/memoria-viva/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Onde fica o arquivo .db — o "cérebro" do sistema.
# Um ÚNICO arquivo SQLite que guarda Hot Store + Warm Store.
# (ver ADR-001: tudo no mesmo arquivo = transações atômicas)
DB_PATH = Path(os.getenv(
    "MEMORIA_VIVA_DB",
    str(BASE_DIR / "data" / "novex-memory.db")
))

# Onde ficam os arquivos Markdown (Cold Store).
# São legíveis por humanos — Jay pode abrir e editar diretamente.
# (ver ADR-003: Markdown porque é LLM-friendly e git-friendly)
COLD_STORE_PATH = Path(os.getenv(
    "MEMORIA_VIVA_COLD_STORE",
    str(BASE_DIR / "cold_store")
))


# ══════════════════════════════════════════════════════════════
# EMBEDDING — o "dicionário" que traduz texto → números
# ══════════════════════════════════════════════════════════════
#
# Este é o ponto de LOCK-IN REAL do sistema.
# Trocar o modelo de embedding exige re-embedar TODO o banco.
# A abstração em embeddings.py garante que a troca é cirúrgica:
# muda UMA variável aqui, roda UM script de migração.

# Qual provedor usar:
#   "nomic"  = local e gratuito, roda via Ollama na sua máquina
#   "openai" = pago, dados vão para servidores da OpenAI
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "nomic")

# Dimensões do vetor — depende do modelo escolhido.
# nomic-embed-text      = 768 dimensões
# text-embedding-3-small = 1536 dimensões
#
# ATENÇÃO: trocar este valor sem re-embedar o banco
# corrompe TODA a busca vetorial. Os números antigos
# vivem em 768 dimensões; os novos em 1536. Incomparáveis.
EMBEDDING_DIMENSIONS = 768 if EMBED_PROVIDER == "nomic" else 1536

# Modelo específico de cada provedor
NOMIC_MODEL = "nomic-embed-text"
OPENAI_EMBED_MODEL = "text-embedding-3-small"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ══════════════════════════════════════════════════════════════
# BUSCA — pesos para busca híbrida
# ══════════════════════════════════════════════════════════════
#
# A busca híbrida combina duas estratégias:
#   - Vetorial: encontra textos com SIGNIFICADO similar
#     ("creme para cabelos danificados" ↔ "reconstrução capilar")
#   - Keyword: encontra textos com as PALAVRAS exatas
#     ("quinoa" → textos que mencionam quinoa literalmente)
#
# Os pesos abaixo controlam quanto cada estratégia influencia.

VECTOR_WEIGHT = 0.7   # 70% significado
TEXT_WEIGHT = 0.3      # 30% palavra exata

# Budget máximo de tokens no contexto injetado pré-execução.
# Limita o tamanho do "pacote de conhecimento" para não
# sobrecarregar os agentes com contexto excessivo.
CONTEXT_BUDGET = 4000


# ══════════════════════════════════════════════════════════════
# AGING — envelhecimento de insights
# ══════════════════════════════════════════════════════════════
#
# Insights antigos perdem relevância com o tempo.
# Soft-trim: reduz o peso na busca (insight ainda existe).
# Hard-clear: remove completamente (insight é apagado).

SOFT_TRIM_DAYS = 90    # > 90 dias → perde peso
HARD_CLEAR_DAYS = 365  # > 1 ano → removido
