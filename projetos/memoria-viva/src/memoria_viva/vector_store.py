"""
vector_store.py — Busca vetorial e textual via sqlite-vec + FTS5
================================================================

CONCEITO:
    O vector store é o "buscador de significado". Quando Jay submete
    "sérum de transição com quinoa", este módulo busca padrões
    similares no banco — não por palavra-chave, mas por significado.

COMO FUNCIONA (simplificado):
    1. O texto de busca é convertido em vetor (768 números)
    2. O sqlite-vec compara esse vetor com todos os vetores no banco
    3. Retorna os mais próximos (menor distância = mais similar)

    É como procurar num mapa: você está na cidade "sérum de quinoa"
    e quer saber quais cidades estão mais perto. O mapa tem 768
    dimensões (impossível de visualizar, mas a matemática funciona).

TRÊS TIPOS DE BUSCA:
    1. Semântica (vetorial): encontra significado similar
       "creme para cabelos danificados" → "reconstrução capilar"
    2. Keyword (FTS5): encontra palavras exatas
       "quinoa" → textos que mencionam "quinoa"
    3. Híbrida: combina as duas (RECOMENDADA)

POR QUE SQLITE-VEC E NÃO CHROMADB/LANCEDB (ADR-001):
    - Mesmo arquivo do Hot Store → transações atômicas
    - Volume do projeto (4.500 vetores/ano) não precisa de índices sofisticados
    - Zero dependências de servidor
"""

import json
import struct
from abc import ABC, abstractmethod
from typing import Optional

from .database import Database, serialize_vector
from .embeddings import EmbeddingProvider
from .models import SearchResult


class VectorStore(ABC):
    """
    Interface para qualquer store de vetores.

    Hoje: SQLiteVectorStore (sqlite-vec, arquivo local).
    Futuro: LanceDBVectorStore (se busca ultrapassar 200ms).

    Os agentes chamam: store.search("texto da busca")
    e recebem resultados. NUNCA sabem qual implementação está em uso.

    Para criar um novo store (ex: LanceDB), basta:
        1. Criar classe que herda de VectorStore
        2. Implementar add(), search(), keyword_search()
        3. Trocar a instância em memory_manager.py
    """

    @abstractmethod
    def add(self, content: str, collection: str,
            metadata: Optional[dict] = None, _conn=None) -> int:
        """Adiciona um texto ao store (embeda e armazena)."""
        pass

    @abstractmethod
    def search(self, query: str, collection: Optional[str] = None,
               n_results: int = 5) -> list[SearchResult]:
        """Busca semântica por proximidade vetorial."""
        pass

    @abstractmethod
    def keyword_search(self, query: str, collection: Optional[str] = None,
                       n_results: int = 5) -> list[SearchResult]:
        """Busca por palavra-chave (FTS5)."""
        pass

    def hybrid_search(self, query: str, collection: Optional[str] = None,
                      n_results: int = 5,
                      vector_weight: float = 0.7,
                      text_weight: float = 0.3) -> list[SearchResult]:
        """
        Busca híbrida: combina vetorial + keyword.

        Por que híbrido?
            - Vetorial encontra "creme para cabelos danificados" quando
              você busca "reconstrução capilar" (significado similar)
            - Keyword encontra "quinoa" exatamente quando você busca "quinoa"
              (o vetorial pode trazer "aveia" que é semanticamente próximo)
            - Combinados: o melhor dos dois mundos

        Parâmetros:
            query: texto a buscar
            collection: filtrar por coleção (None = todas)
            n_results: quantos resultados retornar
            vector_weight: peso da busca vetorial (padrão 70%)
            text_weight: peso da busca keyword (padrão 30%)
        """
        # Busca mais resultados do que precisa de cada tipo,
        # para ter margem ao combinar e filtrar
        vector_results = self.search(query, collection, n_results * 2)
        keyword_results = self.keyword_search(query, collection, n_results * 2)

        # Combina os resultados com pesos
        # Cada resultado recebe um score combinado
        scored: dict[str, dict] = {}

        for r in vector_results:
            key = r.content
            scored[key] = {
                "result": r,
                "score": vector_weight * (1.0 / (1.0 + r.distance)),
            }

        for r in keyword_results:
            key = r.content
            if key in scored:
                # Texto apareceu nas duas buscas → soma os scores
                scored[key]["score"] += text_weight * (1.0 / (1.0 + r.distance))
            else:
                scored[key] = {
                    "result": r,
                    "score": text_weight * (1.0 / (1.0 + r.distance)),
                }

        # Ordena por score combinado (maior = mais relevante)
        ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
        return [item["result"] for item in ranked[:n_results]]


class SQLiteVectorStore(VectorStore):
    """
    Implementação usando sqlite-vec + FTS5.

    Tudo vive no MESMO arquivo SQLite do Hot Store:
        - chunks:     metadados (texto, coleção, modelo de embedding)
        - chunks_vec: vetores (busca por similaridade)
        - chunks_fts: texto indexado (busca por keyword)

    As 3 tabelas são ligadas por rowid (ID da linha):
        chunks.id = chunks_vec.rowid = chunks_fts.rowid

    Quando adicionamos "sérum de transição com quinoa":
        1. chunks     → guarda o texto + metadata    → rowid = 42
        2. chunks_vec → guarda [0.12, -0.45, ...]    → rowid = 42
        3. chunks_fts → indexa as palavras            → rowid = 42
    """

    def __init__(self, db: Database, embed_provider: EmbeddingProvider):
        self.db = db
        self.embed = embed_provider

    def _get_cached_embedding(self, conn, text: str) -> Optional[list[float]]:
        """
        Busca no cache para evitar re-embedar textos já processados.

        Se "sérum de transição com quinoa" já foi embedado antes,
        retorna o vetor guardado em vez de chamar o Ollama de novo.
        Economiza tempo e (se usando OpenAI) dinheiro.
        """
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
        """Salva embedding no cache para uso futuro."""
        text_hash = self.embed.text_hash(text)
        conn.execute(
            "INSERT OR REPLACE INTO embedding_cache "
            "(text_hash, embedding, model) VALUES (?, ?, ?)",
            [text_hash, serialize_vector(vector), self.embed.model_name],
        )

    def _embed_with_cache(self, conn, text: str) -> list[float]:
        """Embeda com cache: reutiliza se já existe, senão gera e guarda."""
        cached = self._get_cached_embedding(conn, text)
        if cached:
            return cached
        vector = self.embed.embed(text)
        self._cache_embedding(conn, text, vector)
        return vector

    def add(self, content: str, collection: str,
            metadata: Optional[dict] = None, _conn=None) -> int:
        """
        Adiciona um texto ao Warm Store.

        Passos:
            1. Texto → vetor (via EmbeddingProvider)
            2. Insere metadados na tabela chunks
            3. Insere vetor na tabela chunks_vec (sqlite-vec)
            4. Insere texto na tabela chunks_fts (FTS5)

        O parâmetro _conn permite reusar uma conexão existente —
        importante para transações atômicas no Committee Flush.
        Se _conn é fornecido, NÃO abre nova transação (o caller já abriu).
        Se _conn é None, abre uma transação própria.

        Retorna o rowid do novo registro.
        """

        def _do_add(conn) -> int:
            # Passo 1: gera o vetor (ou usa cache)
            vector = self._embed_with_cache(conn, content)

            # Passo 2: insere metadados (tabela normal)
            cursor = conn.execute(
                "INSERT INTO chunks (collection, content, embed_model, metadata) "
                "VALUES (?, ?, ?, ?)",
                [collection, content, self.embed.model_name,
                 json.dumps(metadata or {}, ensure_ascii=False)],
            )
            rowid = cursor.lastrowid

            # Passo 3: insere vetor (tabela virtual sqlite-vec)
            # O rowid DEVE ser o mesmo da tabela chunks
            conn.execute(
                "INSERT INTO chunks_vec (rowid, embedding) VALUES (?, ?)",
                [rowid, serialize_vector(vector)],
            )

            # Passo 4: insere no índice de texto (FTS5)
            conn.execute(
                "INSERT INTO chunks_fts (rowid, content, collection) VALUES (?, ?, ?)",
                [rowid, content, collection],
            )

            return rowid

        # Se recebeu uma conexão existente, usa ela (transação do caller)
        if _conn:
            return _do_add(_conn)

        # Senão, abre uma transação própria
        with self.db.transaction() as conn:
            return _do_add(conn)

    def search(self, query: str, collection: Optional[str] = None,
               n_results: int = 5) -> list[SearchResult]:
        """
        Busca semântica: encontra textos com significado similar.

        "sérum de transição" → encontra padrões sobre transição capilar,
        mesmo que usem palavras completamente diferentes.

        Funciona em dois passos:
            1. sqlite-vec encontra os vetores mais próximos (rowids)
            2. Buscamos os metadados na tabela chunks (texto, coleção, etc.)
        """
        query_vector = self.embed.embed(query)

        with self.db.connection() as conn:
            # Passo 1: busca vetorial — retorna rowids ordenados por distância
            # Busca mais do que precisa para compensar o filtro por coleção
            fetch_limit = n_results * 3 if collection else n_results
            vec_rows = conn.execute(
                "SELECT rowid, distance FROM chunks_vec "
                "WHERE embedding MATCH ? "
                "ORDER BY distance LIMIT ?",
                [serialize_vector(query_vector), fetch_limit],
            ).fetchall()

            if not vec_rows:
                return []

            # Passo 2: busca metadados para cada rowid
            results = []
            for row in vec_rows:
                rowid = row[0]
                distance = row[1]

                meta = conn.execute(
                    "SELECT content, collection, metadata FROM chunks WHERE id = ?",
                    [rowid],
                ).fetchone()

                if not meta:
                    continue

                # Filtra por coleção se especificado
                if collection and meta[1] != collection:
                    continue

                results.append(SearchResult(
                    content=meta[0],
                    collection=meta[1],
                    distance=distance,
                    metadata=json.loads(meta[2]) if meta[2] else {},
                ))

                if len(results) >= n_results:
                    break

        return results

    def keyword_search(self, query: str, collection: Optional[str] = None,
                       n_results: int = 5) -> list[SearchResult]:
        """
        Busca por palavra-chave (FTS5): encontra textos com as palavras exatas.

        "quinoa" → encontra textos que mencionam "quinoa" literalmente.

        FTS5 é o mecanismo de busca textual built-in do SQLite.
        Suporta operadores como:
            "quinoa AND transição" → ambas as palavras
            "quinoa OR aveia"     → qualquer uma das palavras
        """
        with self.db.connection() as conn:
            # FTS5 MATCH retorna resultados rankeados por relevância
            # rank é negativo (mais negativo = mais relevante)
            fts_rows = conn.execute(
                "SELECT rowid, rank FROM chunks_fts "
                "WHERE chunks_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                [query, n_results * 3 if collection else n_results],
            ).fetchall()

            if not fts_rows:
                return []

            results = []
            for row in fts_rows:
                rowid = row[0]
                rank = abs(row[1])  # converte para positivo para consistência

                meta = conn.execute(
                    "SELECT content, collection, metadata FROM chunks WHERE id = ?",
                    [rowid],
                ).fetchone()

                if not meta:
                    continue

                if collection and meta[1] != collection:
                    continue

                results.append(SearchResult(
                    content=meta[0],
                    collection=meta[1],
                    distance=rank,
                    metadata=json.loads(meta[2]) if meta[2] else {},
                ))

                if len(results) >= n_results:
                    break

        return results
