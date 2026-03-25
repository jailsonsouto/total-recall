"""
embeddings.py — Abstração de provedores de embedding
=====================================================

Provedor padrão: qwen3-embedding:4b via Ollama (local, 1024 dims).
Alternativa: OpenAI text-embedding-3-small (pago, 1536 dims).

O Qwen é instruction-aware: queries recebem instrução,
documentos são embedados crus. Isso melhora o recall semântico.

Graceful degradation: se Ollama não estiver rodando, retorna None
e o sistema funciona com FTS5-only.
"""

import hashlib
from abc import ABC, abstractmethod
from typing import Optional

from .config import (
    EMBED_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_EMBED_MODEL,
    EMBEDDING_DIMENSIONS,
    EMBED_QUERY_INSTRUCTION,
    OPENAI_EMBED_MODEL,
    OPENAI_API_KEY,
)


class EmbeddingProvider(ABC):
    """Interface para provedores de embedding."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embeda uma query de busca (pode receber instrução)."""

    @abstractmethod
    def embed_document(self, text: str) -> list[float]:
        """Embeda um documento/chunk para indexação (sem instrução)."""

    def embed(self, text: str) -> list[float]:
        """Atalho — default é embed_document."""
        return self.embed_document(text)

    @abstractmethod
    def dimensions(self) -> int:
        pass

    @property
    def model_name(self) -> str:
        return "unknown"

    def text_hash(self, text: str) -> str:
        """Hash que inclui modelo e dimensão para evitar colisão no cache."""
        key = f"{self.model_name}:{self.dimensions()}:{text}"
        return hashlib.sha256(key.encode()).hexdigest()


class OllamaEmbedProvider(EmbeddingProvider):
    """Provedor local via Ollama (qualquer modelo de embedding)."""

    def __init__(self, model: str = OLLAMA_EMBED_MODEL,
                 dims: int = EMBEDDING_DIMENSIONS,
                 base_url: str = OLLAMA_BASE_URL):
        self._model = model
        self._dims = dims
        self._base_url = base_url

    def embed_query(self, text: str) -> list[float]:
        formatted = (
            f"Instruct: {EMBED_QUERY_INSTRUCTION}\n"
            f"Query: {text}"
        )
        return self._call_ollama(formatted)

    def embed_document(self, text: str) -> list[float]:
        return self._call_ollama(text)

    def _call_ollama(self, text: str) -> list[float]:
        import ollama
        response = ollama.embed(
            model=self._model,
            input=text,
        )
        vec = response["embeddings"][0]
        # Trunca/pad para a dimensão configurada se necessário
        if len(vec) > self._dims:
            vec = vec[:self._dims]
        return vec

    def dimensions(self) -> int:
        return self._dims

    @property
    def model_name(self) -> str:
        return self._model


class OpenAIEmbedProvider(EmbeddingProvider):
    """Provedor pago via API da OpenAI."""

    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY não configurada. "
                "Use TOTAL_RECALL_EMBED_PROVIDER=ollama para o provedor local."
            )

    def embed_query(self, text: str) -> list[float]:
        return self._call_openai(text)

    def embed_document(self, text: str) -> list[float]:
        return self._call_openai(text)

    def _call_openai(self, text: str) -> list[float]:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.embeddings.create(
            input=text,
            model=OPENAI_EMBED_MODEL,
        )
        return response.data[0].embedding

    def dimensions(self) -> int:
        return 1536

    @property
    def model_name(self) -> str:
        return OPENAI_EMBED_MODEL


def get_embedding_provider() -> Optional[EmbeddingProvider]:
    """
    Retorna o provedor configurado, ou None se indisponível.

    Retornar None permite graceful degradation: o sistema
    funciona com FTS5-only se embedding não estiver disponível.
    """
    try:
        if EMBED_PROVIDER == "ollama":
            provider = OllamaEmbedProvider()
            provider.embed_document("test")
            return provider
        elif EMBED_PROVIDER == "openai":
            return OpenAIEmbedProvider()
        else:
            return None
    except Exception:
        return None
