"""
embeddings.py — Abstração de provedores de embedding
=====================================================

Provedor padrão: nomic-embed-text via Ollama (local, gratuito, 768 dims).
Alternativa: OpenAI text-embedding-3-small (pago, 1536 dims).

Graceful degradation: se Ollama não estiver rodando, retorna None
e o sistema funciona com FTS5-only.
"""

import hashlib
from abc import ABC, abstractmethod
from typing import Optional

from .config import (
    EMBED_PROVIDER,
    NOMIC_MODEL,
    OPENAI_EMBED_MODEL,
    OPENAI_API_KEY,
)


class EmbeddingProvider(ABC):
    """Interface para provedores de embedding."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        pass

    @abstractmethod
    def dimensions(self) -> int:
        pass

    @property
    def model_name(self) -> str:
        return "unknown"

    def text_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()


class NomicEmbedProvider(EmbeddingProvider):
    """Provedor local via Ollama (nomic-embed-text, 768 dims)."""

    def embed(self, text: str) -> list[float]:
        import ollama
        response = ollama.embeddings(model=NOMIC_MODEL, prompt=text)
        return response["embedding"]

    def dimensions(self) -> int:
        return 768

    @property
    def model_name(self) -> str:
        return NOMIC_MODEL


class OpenAIEmbedProvider(EmbeddingProvider):
    """Provedor pago via API da OpenAI (1536 dims)."""

    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY não configurada. "
                "Use TOTAL_RECALL_EMBED_PROVIDER=nomic para o provedor local."
            )

    def embed(self, text: str) -> list[float]:
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
        if EMBED_PROVIDER == "nomic":
            provider = NomicEmbedProvider()
            # Teste rápido: verifica se Ollama está rodando
            provider.embed("test")
            return provider
        elif EMBED_PROVIDER == "openai":
            return OpenAIEmbedProvider()
        else:
            return None
    except Exception:
        return None
