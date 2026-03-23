"""
Configuração central do Vozes da Comunidade.

Toda configuração é lida de variáveis de ambiente.
Copie .env.example para .env e ajuste os caminhos.
"""
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Backend de extração ASTE
# ---------------------------------------------------------------------------

ASTE_BACKEND: str = os.getenv("ASTE_BACKEND", "bertimbau")
"""
Motor de extração ASTE:
  bertimbau → BERTimbauExtractor (Plano A — requer fine-tuning)
  slm       → SLMExtractor      (Plano B — funciona imediatamente)

Se ASTE_BACKEND=bertimbau e o modelo não estiver disponível,
o sistema faz fallback automático para o SLM com aviso no log.
"""

# ---------------------------------------------------------------------------
# Plano A — BERTimbau
# ---------------------------------------------------------------------------

BERTIMBAU_MODEL_PATH: str | None = os.getenv("BERTIMBAU_MODEL_PATH")
"""
Caminho para o checkpoint fine-tuned do BERTimbau.
None enquanto o fine-tuning ainda não foi realizado — sistema usa SLM.

Exemplo:
  BERTIMBAU_MODEL_PATH=./models/bertimbau-embelleze-v1
"""

DINAMICA_ABSA_PATH: str = os.getenv(
    "DINAMICA_ABSA_PATH",
    str(Path.home() / "Library/CloudStorage/OneDrive-Embelleze"
        "/MEUS-PROJETOS-IA/COLETA-COMENTARIOS-TIKTOK"
        "/PROCESSAMENTO-COLETA/kimi/dinamica_absa"),
)
"""
Caminho para o diretório raiz do dinamica_absa (TCC).
Adicionado ao sys.path para importação como dependência.
"""

BERTIMBAU_MAX_LENGTH: int = int(os.getenv("BERTIMBAU_MAX_LENGTH", "128"))
BERTIMBAU_BATCH_SIZE: int = int(os.getenv("BERTIMBAU_BATCH_SIZE", "16"))

# ---------------------------------------------------------------------------
# Plano B — SLM local
# ---------------------------------------------------------------------------

SLM_BACKEND: str = os.getenv("SLM_BACKEND", "ollama")
"""
Backend do SLM:
  ollama  → via servidor ollama (mais simples, qualquer modelo)
  mlx     → via MLX-LM nativo Apple Silicon (mais rápido no M1)
"""

SLM_MODEL: str = os.getenv("SLM_MODEL", "qwen2.5:7b")
"""
Identificador do modelo SLM.
  Para ollama:  qwen2.5:7b | phi3.5 | mistral
  Para MLX:     mlx-community/Qwen2.5-7B-Instruct-4bit
"""

OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")

SLM_MAX_TOKENS: int = int(os.getenv("SLM_MAX_TOKENS", "512"))
SLM_MAX_RETRIES: int = int(os.getenv("SLM_MAX_RETRIES", "3"))
"""
Número de tentativas em caso de JSON inválido na saída do SLM.
"""

# ---------------------------------------------------------------------------
# Thresholds de qualidade
# ---------------------------------------------------------------------------

MIN_CONFIDENCE: float = float(os.getenv("MIN_CONFIDENCE", "0.5"))
"""
Triplas com confiança abaixo deste valor são descartadas.
"""

BRIEFING_RELEVANCE_THRESHOLD: float = float(
    os.getenv("BRIEFING_RELEVANCE_THRESHOLD", "0.6")
)
"""
Score mínimo de relevância para incluir um padrão no briefing.
"""
