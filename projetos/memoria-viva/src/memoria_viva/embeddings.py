"""
embeddings.py — Abstração de modelos de embedding
==================================================

CONCEITO CENTRAL:
    Um "embedding" é a tradução de texto humano para números que um
    computador pode comparar por similaridade. A frase "sérum de quinoa"
    vira uma lista de 768 números — e frases com significado parecido
    ficam com números parecidos.

    "sérum de transição" → [0.12, -0.45, 0.78, ..., 0.33]  (768 números)
    "creme para cabelos" → [0.11, -0.42, 0.80, ..., 0.31]  (768 números — parecidos!)
    "política fiscal"    → [0.89, 0.15, -0.67, ..., -0.44] (768 números — BEM diferentes)

POR QUE ESTE ARQUIVO É IMPORTANTE:
    O modelo de embedding é onde está o LOCK-IN REAL do sistema.
    Trocar de modelo exige re-embedar todo o banco (pode levar horas).
    Esta abstração garante que a troca é cirúrgica:
        - muda UMA variável no .env (EMBED_PROVIDER=openai)
        - roda UM script de migração
        - os 7+1 agentes NUNCA sabem qual modelo está em uso

COMO ADICIONAR UM NOVO PROVEDOR:
    1. Crie uma nova classe que herda de EmbeddingProvider
    2. Implemente embed() e dimensions()
    3. Adicione a opção em get_embedding_provider()
"""

import hashlib
from abc import ABC, abstractmethod

from .config import (
    EMBED_PROVIDER,
    NOMIC_MODEL,
    OPENAI_EMBED_MODEL,
    OPENAI_API_KEY,
)


class EmbeddingProvider(ABC):
    """
    Interface que todo provedor de embedding deve implementar.

    É como um contrato: qualquer provedor (local ou pago) precisa
    saber fazer duas coisas:
        1. embed(texto) → lista de números
        2. dimensions() → quantos números são gerados

    Os agentes só conhecem ESTA interface — nunca a implementação.
    Isso é o que permite trocar de provedor sem alterar nenhum agente.
    """

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Converte texto em vetor numérico (embedding)."""
        pass

    @abstractmethod
    def dimensions(self) -> int:
        """Quantas dimensões tem o vetor gerado."""
        pass

    @property
    def model_name(self) -> str:
        """Nome do modelo (registrado no banco para saber quem gerou cada vetor)."""
        return "unknown"

    def text_hash(self, text: str) -> str:
        """
        Gera um identificador único (hash) para um texto.

        Usado pelo cache de embeddings: se o mesmo texto já foi
        embedado antes, usa o resultado guardado em vez de
        recalcular (economiza tempo e chamadas de API).
        """
        return hashlib.sha256(text.encode()).hexdigest()


class NomicEmbedProvider(EmbeddingProvider):
    """
    Provedor LOCAL e GRATUITO via Ollama.

    Usa o modelo nomic-embed-text rodando na sua máquina.
    Nenhum dado sai do computador. Zero custo.

    Pré-requisitos:
        1. Ollama instalado (https://ollama.com)
        2. Modelo baixado: ollama pull nomic-embed-text
        3. Ollama rodando: ollama serve

    Gera vetores de 768 dimensões (~3 KB por vetor).
    """

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
    """
    Provedor PAGO via API da OpenAI.

    Usa text-embedding-3-small (1.536 dimensões).
    Requer chave de API (OPENAI_API_KEY no .env).

    ATENÇÃO:
        - Dados são enviados para os servidores da OpenAI
        - Vetores gerados são INCOMPATÍVEIS com nomic-embed-text
        - Trocar de provedor exige re-embedar todo o banco

    Custo aproximado (Março 2026):
        ~$0.02 por 1 milhão de tokens
        ~4.500 vetores/ano ≈ $0.05/ano (praticamente grátis)
    """

    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY não configurada. "
                "Defina no arquivo .env ou como variável de ambiente.\n"
                "Se quiser usar o provedor local gratuito, "
                "mude EMBED_PROVIDER=nomic no .env"
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


def get_embedding_provider() -> EmbeddingProvider:
    """
    Fábrica que retorna o provedor configurado.

    A decisão de qual provedor usar vem da variável EMBED_PROVIDER
    (definida no .env ou config.py):
        "nomic"  (padrão) → NomicEmbedProvider (local, gratuito)
        "openai"          → OpenAIEmbedProvider (pago, API)

    Este é o ÚNICO ponto onde a decisão é tomada.
    Todo o resto do código chama get_embedding_provider()
    e recebe o provedor certo, sem saber qual é.

    Para trocar de provedor:
        1. Mude EMBED_PROVIDER no .env
        2. Rode o script de re-embedding (se já houver vetores no banco)
    """
    if EMBED_PROVIDER == "nomic":
        return NomicEmbedProvider()
    elif EMBED_PROVIDER == "openai":
        return OpenAIEmbedProvider()
    else:
        raise ValueError(
            f"EMBED_PROVIDER='{EMBED_PROVIDER}' não reconhecido. "
            f"Use 'nomic' (local, gratuito) ou 'openai' (pago)."
        )
