"""
vector_store.py — Busca vetorial + FTS5 (híbrida)
==================================================

Adaptado do padrão do Memória Viva. Três tabelas ligadas por rowid:
  chunks (metadados) ↔ chunks_vec (vetores) ↔ chunks_fts (texto)

Pipeline de busca keyword (V02):
  query → _normalize_technical() → _expand_abbreviations() → _expand_fuzzy() → FTS5
"""

import json
import re
import struct
import time
from typing import Optional

from .config import (
    VECTOR_WEIGHT, TEXT_WEIGHT, EMBEDDING_DIMENSIONS,
    FUZZY_THRESHOLD, FUZZY_MAX_EXPANSIONS, FUZZY_MIN_TOKEN_LENGTH,
    MIN_VECTOR_ONLY_SCORE,
    ADAPTIVE_VECTOR_WEIGHT_SPECIFIC, ADAPTIVE_TEXT_WEIGHT_SPECIFIC,
)
from .database import Database, serialize_vector
from .embeddings import EmbeddingProvider
from .models import SearchResult


# ══════════════════════════════════════════════════════════════
# V02 — Tabela de abreviações PT-BR para expansão de query
# ══════════════════════════════════════════════════════════════

_PT_ABBREVIATIONS: dict[str, list[str]] = {
    # Pronomes
    "vc":     ["você"],
    "vcs":    ["vocês"],
    "cê":     ["você"],
    "cmg":    ["comigo"],
    # Negação
    "nao":    ["não"],
    "ñ":      ["não"],
    # Conectivos
    "pq":     ["porque", "por que"],
    "qdo":    ["quando"],
    "qnd":    ["quando"],
    "qto":    ["quanto"],
    "tbm":    ["também"],
    "tb":     ["também"],
    "tmb":    ["também"],
    "msm":    ["mesmo"],
    # Intensidade
    "mt":     ["muito"],
    "mto":    ["muito"],
    "muinto": ["muito"],
    # Tempo
    "hj":     ["hoje"],
    "dps":    ["depois"],
    "agr":    ["agora"],
    "amanha": ["amanhã"],
    # Cortesia
    "obg":    ["obrigado", "obrigada"],
    "pfv":    ["por favor"],
    "pfvr":   ["por favor"],
    "vlw":    ["valeu"],
    "flw":    ["falou"],
    # Confirmação
    "blz":    ["beleza"],
    "ctz":    ["certeza"],
    "clr":    ["claro"],
    # Localização / quantidade
    "kd":     ["cadê", "onde"],
    "td":     ["tudo"],
    "nda":    ["nada"],
    # Técnico (comum em sessões Claude Code)
    "repo":   ["repositório", "repository"],
    "deps":   ["dependências", "dependencies"],
    "env":    ["ambiente", "environment"],
    "db":     ["banco de dados", "database"],
    "msg":    ["mensagem", "message"],
    "msgs":   ["mensagens", "messages"],
}


def _normalize_technical(text: str) -> str:
    """Normaliza separadores técnicos: sqlite-vec → sqlite vec, session_id → session id."""
    return re.sub(r'[-_]', ' ', text).strip()


# ══════════════════════════════════════════════════════════════
# V03 — Palavras que indicam query semântica/descritiva
#
# Presença de qualquer uma dessas palavras sinaliza que a query
# tem contexto natural e o modo híbrido padrão é o correto.
# Sem elas, tokens raros/acrônimos indicam modo FTS5-dominante.
# ══════════════════════════════════════════════════════════════

_SEMANTIC_STOP_WORDS = frozenset({
    # PT-BR — conectivos e palavras de pergunta
    "como", "por", "que", "porque", "quando", "onde", "qual", "quais",
    "quem", "se", "mas", "nem", "pois", "logo", "então",
    # PT-BR — artigos e preposições
    "de", "da", "do", "em", "para", "com", "sem", "sobre", "entre",
    "no", "na", "nos", "nas", "ao", "aos", "às", "pelo", "pela",
    "um", "uma", "uns", "umas", "o", "a", "os", "as",
    # PT-BR — verbos comuns em queries de memória
    "foi", "usar", "usamos", "decidimos", "escolhemos", "queremos",
    "temos", "fazer", "faz", "está", "estamos", "não", "nao",
    # EN — equivalentes
    "how", "why", "when", "what", "where", "who", "which",
    "the", "is", "are", "was", "we", "did", "not",
    "with", "for", "about", "from", "to", "in", "on", "at",
})

# Detecta nomes técnicos com prefixo maiúsculo: BERTimbau, GPT4, SQLite, XGBoost
_CAPS_PREFIX = re.compile(r"^[A-Z]{2,}")


class SQLiteVectorStore:
    """Implementação com sqlite-vec + FTS5 + embedding cache."""

    def __init__(self, db: Database, embed_provider: Optional[EmbeddingProvider]):
        self.db = db
        self.embed = embed_provider
        self._vocab_cache: Optional[tuple[float, dict[str, int]]] = None

    def _get_cached_embedding(self, conn, text: str) -> Optional[list[float]]:
        if not self.embed:
            return None
        text_hash = self.embed.text_hash(text)
        row = conn.execute(
            "SELECT embedding FROM embedding_cache WHERE text_hash = ?",
            [text_hash],
        ).fetchone()
        if row:
            n = len(row[0]) // 4
            return list(struct.unpack(f"{n}f", row[0]))
        return None

    def _cache_embedding(self, conn, text: str, vector: list[float]):
        if not self.embed:
            return
        text_hash = self.embed.text_hash(text)
        conn.execute(
            "INSERT OR REPLACE INTO embedding_cache "
            "(text_hash, embedding, model) VALUES (?, ?, ?)",
            [text_hash, serialize_vector(vector), self.embed.model_name],
        )

    def _embed_with_cache(self, conn, text: str,
                          kind: str = "document") -> Optional[list[float]]:
        """Embeda com cache. kind='query' usa instrução, 'document' não."""
        if not self.embed:
            return None
        cached = self._get_cached_embedding(conn, text)
        if cached:
            return cached
        try:
            if kind == "query":
                vector = self.embed.embed_query(text)
            else:
                vector = self.embed.embed_document(text)
            self._cache_embedding(conn, text, vector)
            return vector
        except Exception:
            return None

    def add(self, session_id: str, role: str, content: str,
            timestamp: Optional[str], chunk_index: int,
            line_start: Optional[int], line_end: Optional[int],
            has_embedding: bool, embed_model: str,
            metadata: Optional[dict], _conn=None) -> int:
        """Adiciona um chunk às 3 tabelas (chunks + vec + fts)."""

        def _do_add(conn) -> int:
            vector = None
            actual_has_embedding = False

            if has_embedding and self.embed:
                vector = self._embed_with_cache(conn, content)
                actual_has_embedding = vector is not None

            # chunks (metadados)
            cursor = conn.execute(
                "INSERT INTO chunks "
                "(session_id, role, content, timestamp, chunk_index, "
                " line_start, line_end, has_embedding, embed_model, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [session_id, role, content, timestamp, chunk_index,
                 line_start, line_end, actual_has_embedding,
                 embed_model or "", json.dumps(metadata or {}, ensure_ascii=False)],
            )
            rowid = cursor.lastrowid

            # chunks_vec (vetor)
            if vector:
                conn.execute(
                    "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                    [rowid, serialize_vector(vector)],
                )

            # chunks_fts (texto indexado)
            conn.execute(
                "INSERT INTO chunks_fts (rowid, content, session_id, role) "
                "VALUES (?, ?, ?, ?)",
                [rowid, content, session_id, role],
            )

            return rowid

        if _conn:
            return _do_add(_conn)
        with self.db.transaction() as conn:
            return _do_add(conn)

    def search(self, query: str, n_results: int = 5,
               session_id: Optional[str] = None) -> list[SearchResult]:
        """Busca semântica por proximidade vetorial."""
        if not self.embed:
            return []

        try:
            query_vector = self.embed.embed_query(query)
        except Exception:
            return []

        with self.db.connection() as conn:
            fetch_limit = n_results * 3
            vec_rows = conn.execute(
                "SELECT rowid, distance FROM chunks_vec "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                [serialize_vector(query_vector), fetch_limit],
            ).fetchall()

            if not vec_rows:
                return []

            results = []
            for row in vec_rows:
                rowid, distance = row[0], row[1]
                meta = conn.execute(
                    "SELECT c.content, c.session_id, c.role, c.timestamp, c.metadata, "
                    "       s.title, s.project_label "
                    "FROM chunks c JOIN sessions s ON c.session_id = s.session_id "
                    "WHERE c.id = ?",
                    [rowid],
                ).fetchone()

                if not meta:
                    continue
                if session_id and meta["session_id"] != session_id:
                    continue

                from .session_parser import _parse_timestamp
                results.append(SearchResult(
                    content=meta["content"],
                    session_id=meta["session_id"],
                    role=meta["role"],
                    timestamp=_parse_timestamp(meta["timestamp"]) if meta["timestamp"] else None,
                    distance=distance,
                    score=1.0 / (1.0 + distance),
                    metadata=json.loads(meta["metadata"]) if meta["metadata"] else {},
                    session_title=meta["title"] or "",
                    project_label=meta["project_label"] or "",
                ))

                if len(results) >= n_results:
                    break

            return results

    # ══════════════════════════════════════════════════════════
    # V02 — Pré-processamento de query (normalização + abreviações + fuzzy)
    # ══════════════════════════════════════════════════════════

    def _get_fts_vocabulary(self, conn) -> dict[str, int]:
        """Extrai tokens do FTS5 com doc count via fts5vocab (cache 60s).

        Retorna {term: doc_count} — permite distinguir termos comuns
        de termos raros (prováveis typos ou menções pontuais).
        """
        now = time.time()
        if (self._vocab_cache is not None
                and now - self._vocab_cache[0] < 60):
            return self._vocab_cache[1]

        try:
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts_vocab "
                "USING fts5vocab('chunks_fts', 'row')"
            )
            rows = conn.execute(
                "SELECT term, doc FROM chunks_fts_vocab "
                "WHERE LENGTH(term) >= ?",
                [FUZZY_MIN_TOKEN_LENGTH],
            ).fetchall()
            vocab = {r[0]: r[1] for r in rows}
        except Exception:
            vocab = {}

        self._vocab_cache = (now, vocab)
        return vocab

    def _classify_query_weights(self, query: str, conn) -> tuple[float, float, str]:
        """Classifica a query e retorna pesos adaptativos para hybrid_search.

        Lógica em duas etapas:

        1. Contexto semântico detectado (artigos, preposições, verbos de pergunta)
           → modo híbrido padrão (70/30). Queries descritivas se beneficiam do vetor.

        2. Sem contexto semântico:
           a. Queries curtas (≤ 2 tokens significativos) → FTS5-dominante (25/75).
              Lookups diretos — "netnografia", "ABSA ASTE", "BERTimbau" — são buscas
              por termo específico, não por conceito. FTS5 é o sinal primário.
           b. Queries longas → verifica se TODOS os tokens são acrônimos (ALL CAPS)
              ou raros no corpus (doc_count ≤ 10). Se sim → FTS5-dominante.
              Caso contrário → híbrido.

        Returns (vector_weight, text_weight, mode_label)
          mode_label: "hybrid" | "fts5_dominant"
        """
        raw_tokens = [w.strip(".,!?;:") for w in query.split()]

        # Etapa 1: presença de stop word semântica → query descritiva → híbrido
        if any(t.lower() in _SEMANTIC_STOP_WORDS for t in raw_tokens):
            return VECTOR_WEIGHT, TEXT_WEIGHT, "hybrid"

        # Tokens significativos (comprimento mínimo, sem stop words).
        # V03.1: acrônimos ALL-CAPS de 2-3 chars (PLN, NER, SQL, API) também contam
        # mesmo abaixo de FUZZY_MIN_TOKEN_LENGTH — são termos técnicos, não stop words.
        def _is_meaningful(t: str) -> bool:
            tl = t.lower()
            if tl in _SEMANTIC_STOP_WORDS:
                return False
            if len(t) >= FUZZY_MIN_TOKEN_LENGTH:
                return True
            # Acrônimo curto ALL-CAPS de 2-3 letras
            return t == t.upper() and t.isalpha() and len(t) >= 2

        meaningful = [t for t in raw_tokens if _is_meaningful(t)]

        if not meaningful:
            return VECTOR_WEIGHT, TEXT_WEIGHT, "hybrid"

        # Etapa 2a: query curta sem contexto → lookup específico → FTS5-dominante
        if len(meaningful) <= 2:
            return ADAPTIVE_VECTOR_WEIGHT_SPECIFIC, ADAPTIVE_TEXT_WEIGHT_SPECIFIC, "fts5_dominant"

        # Etapa 2b: query longa → verifica se todos os tokens são técnicos
        vocab = self._get_fts_vocabulary(conn)
        specific = sum(
            1 for t in meaningful
            if (t == t.upper() and not t.isdigit() and len(t) >= 2)  # ALL CAPS: PLN, NER
            or _CAPS_PREFIX.match(t)                                   # CamelCase técnico: BERTimbau, GPT4
            or vocab.get(t.lower(), 0) <= 10                          # raro no corpus
        )
        if specific == len(meaningful):
            return ADAPTIVE_VECTOR_WEIGHT_SPECIFIC, ADAPTIVE_TEXT_WEIGHT_SPECIFIC, "fts5_dominant"

        return VECTOR_WEIGHT, TEXT_WEIGHT, "hybrid"

    def _fuzzy_find_variants(self, token: str, conn) -> list[str]:
        """Busca variantes fuzzy de um token no vocabulário FTS5.

        Usa doc count como desempate: termos comuns (absa=52 docs)
        são preferidos sobre raros (abel=1 doc) em caso de mesma
        similaridade. Isso resolve typos para o termo correto.
        """
        try:
            from rapidfuzz import process, fuzz
        except ImportError:
            return []

        vocab = self._get_fts_vocabulary(conn)
        if not vocab:
            return []

        # Busca mais candidatos para ter margem de seleção
        matches = process.extract(
            token, list(vocab.keys()),
            scorer=fuzz.ratio,
            limit=FUZZY_MAX_EXPANSIONS * 3,
            score_cutoff=FUZZY_THRESHOLD * 100,
        )

        # Filtra self-match e ordena por score desc, doc_count desc
        candidates = [
            (m[0], m[1], vocab.get(m[0], 0))
            for m in matches if m[0] != token
        ]
        candidates.sort(key=lambda x: (-x[1], -x[2]))

        return [c[0] for c in candidates[:FUZZY_MAX_EXPANSIONS]]

    def _build_fts_query(self, query: str, conn) -> tuple[str, list[dict]]:
        """Constrói query FTS5 com abreviações + fuzzy em uma única passada.

        Para cada token:
          1. Se é abreviação PT-BR → expande com OR-group
          2. Se tem ≥ FUZZY_MIN_TOKEN_LENGTH chars → tenta fuzzy
          3. Senão → usa literal entre aspas

        Retorna (query_fts5, expansions) onde expansions é lista de
        dicts com {original, expanded, type}.
        """
        words = query.lower().split()
        parts = []
        any_expansion = False
        expansions: list[dict] = []

        for word in words:
            clean = word.strip(".,!?;:")
            if not clean or len(clean) < 2:
                continue

            # Prioridade 1: abreviações PT-BR
            if clean in _PT_ABBREVIATIONS:
                variants = [clean] + _PT_ABBREVIATIONS[clean]
                group = " OR ".join(f'"{v}"' for v in variants)
                parts.append(f"({group})")
                any_expansion = True
                expansions.append({
                    "original": clean,
                    "expanded": _PT_ABBREVIATIONS[clean],
                    "type": "abbreviation",
                })
                continue

            # Prioridade 2: fuzzy — para typos e termos raros
            # Termos comuns (>10 docs) são usados literalmente.
            # Termos raros (≤10 docs) ou ausentes podem ser typos → expandir.
            if len(clean) >= FUZZY_MIN_TOKEN_LENGTH:
                vocab = self._get_fts_vocabulary(conn)
                doc_count = vocab.get(clean, 0)
                if doc_count <= 10:  # ausente ou raro → provável typo
                    fuzzy_variants = self._fuzzy_find_variants(clean, conn)
                    if fuzzy_variants:
                        all_forms = [clean] + fuzzy_variants
                        group = " OR ".join(f'"{v}"' for v in all_forms)
                        parts.append(f"({group})")
                        any_expansion = True
                        expansions.append({
                            "original": clean,
                            "expanded": fuzzy_variants,
                            "type": "fuzzy",
                        })
                        continue

            parts.append(f'"{clean}"')

        if any_expansion or len(parts) > 1:
            return " OR ".join(parts), expansions
        if parts:
            return parts[0], expansions
        return self._sanitize_fts_query(query), expansions

    # ══════════════════════════════════════════════════════════

    def keyword_search(self, query: str, n_results: int = 5,
                       session_id: Optional[str] = None
                       ) -> tuple[list['SearchResult'], dict]:
        """Busca por palavra-chave via FTS5.

        Pipeline V02:
          query → normalize → (abbreviations + fuzzy) em passada única → FTS5

        Retorna (results, query_info) com metadados de expansão.
        """
        # V02 Passo 1: normalizar separadores técnicos
        query = _normalize_technical(query)

        with self.db.connection() as conn:
            # V02 Passos 2+3: abreviações + fuzzy em uma passada
            safe_query, expansions = self._build_fts_query(query, conn)

            query_info = {
                "normalized_query": query,
                "fts_query": safe_query,
                "expansions": expansions,
            }

            try:
                fts_rows = conn.execute(
                    "SELECT rowid, rank FROM chunks_fts "
                    "WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                    [safe_query, n_results * 3],
                ).fetchall()
            except Exception:
                # Se FTS query falha, tenta busca simples com LIKE
                return self._fallback_like_search(conn, query, n_results, session_id), query_info

            if not fts_rows:
                return [], query_info

            results = []
            for row in fts_rows:
                rowid, rank = row[0], abs(row[1])
                meta = conn.execute(
                    "SELECT c.content, c.session_id, c.role, c.timestamp, c.metadata, "
                    "       s.title, s.project_label "
                    "FROM chunks c JOIN sessions s ON c.session_id = s.session_id "
                    "WHERE c.id = ?",
                    [rowid],
                ).fetchone()

                if not meta:
                    continue
                if session_id and meta["session_id"] != session_id:
                    continue

                from .session_parser import _parse_timestamp
                results.append(SearchResult(
                    content=meta["content"],
                    session_id=meta["session_id"],
                    role=meta["role"],
                    timestamp=_parse_timestamp(meta["timestamp"]) if meta["timestamp"] else None,
                    distance=rank,
                    score=1.0 / (1.0 + rank),
                    metadata=json.loads(meta["metadata"]) if meta["metadata"] else {},
                    session_title=meta["title"] or "",
                    project_label=meta["project_label"] or "",
                ))

                if len(results) >= n_results:
                    break

            return results, query_info

    def hybrid_search(self, query: str, n_results: int = 5,
                      session_id: Optional[str] = None,
                      vector_weight: float = VECTOR_WEIGHT,
                      text_weight: float = TEXT_WEIGHT
                      ) -> tuple[list['SearchResult'], dict]:
        """Combina busca vetorial + keyword com pesos adaptativos (V03).

        Classifica a query antes de buscar:
          - Queries semânticas/descritivas → pesos padrão (70% vetor / 30% FTS5)
          - Queries técnicas/específicas (acrônimos, termos raros) → FTS5-dominante (25%/75%)

        Os parâmetros vector_weight/text_weight são sobrescritos pela classificação.
        Para forçar pesos fixos, passe-os explicitamente com adaptive=False — ou use
        keyword_search() / search() diretamente.

        Retorna (results, query_info) com atribuição de fonte e modo de busca.
        """
        with self.db.connection() as _conn_classify:
            vector_weight, text_weight, search_mode = self._classify_query_weights(
                query, _conn_classify
            )

        vector_results = self.search(query, n_results * 2, session_id)
        keyword_results, query_info = self.keyword_search(query, n_results * 2, session_id)
        query_info["search_mode"] = search_mode

        scored: dict[str, dict] = {}

        for r in vector_results:
            key = f"{r.session_id}:{r.content[:100]}"
            scored[key] = {
                "result": r,
                "score": vector_weight * r.score,
                "sources": ["vector"],
            }

        for r in keyword_results:
            key = f"{r.session_id}:{r.content[:100]}"
            if key in scored:
                scored[key]["score"] += text_weight * r.score
                scored[key]["sources"].append("fts5")
            else:
                scored[key] = {
                    "result": r,
                    "score": text_weight * r.score,
                    "sources": ["fts5"],
                }

        ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)

        # Filtra resultados vector-only abaixo do piso de confiança.
        # Resultados com FTS5 (match literal no corpus) passam incondicionalmente.
        ranked = [
            item for item in ranked
            if not (item["sources"] == ["vector"] and item["score"] < MIN_VECTOR_ONLY_SCORE)
        ]

        results = []
        for item in ranked[:n_results]:
            r = item["result"]
            r.score = item["score"]
            r.sources = list(dict.fromkeys(item["sources"]))  # deduplicate
            results.append(r)

        return results, query_info

    def _sanitize_fts_query(self, query: str) -> str:
        """Sanitiza query para FTS5 — wrap em aspas se tem caracteres especiais."""
        special = set('(){}[]^*:!"\'')
        if any(c in special for c in query):
            escaped = query.replace('"', '""')
            return f'"{escaped}"'
        # Se parece query natural, usa OR entre palavras
        words = query.split()
        if len(words) > 1:
            return " OR ".join(f'"{w}"' for w in words if len(w) > 2)
        return query

    def _fallback_like_search(self, conn, query: str, n_results: int,
                              session_id: Optional[str]) -> list[SearchResult]:
        """Fallback com LIKE quando FTS5 falha."""
        sql = (
            "SELECT c.id, c.content, c.session_id, c.role, c.timestamp, c.metadata, "
            "       s.title, s.project_label "
            "FROM chunks c JOIN sessions s ON c.session_id = s.session_id "
            "WHERE c.content LIKE ? "
        )
        params = [f"%{query}%"]
        if session_id:
            sql += "AND c.session_id = ? "
            params.append(session_id)
        sql += "LIMIT ?"
        params.append(n_results)

        rows = conn.execute(sql, params).fetchall()
        results = []
        from .session_parser import _parse_timestamp
        for row in rows:
            results.append(SearchResult(
                content=row["content"],
                session_id=row["session_id"],
                role=row["role"],
                timestamp=_parse_timestamp(row["timestamp"]) if row["timestamp"] else None,
                distance=1.0,
                score=0.5,
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                session_title=row["title"] or "",
                project_label=row["project_label"] or "",
            ))
        return results
