"""
Plano B — SLMExtractor

Extração ASTE via SLM local (Qwen2.5 ou similar) usando prompt estruturado.
Suporta dois backends:
  - ollama  → servidor local, qualquer modelo suportado
  - mlx     → MLX-LM nativo Apple Silicon (mais rápido no M1, sem servidor)

is_ready() sempre retorna True — funciona zero-shot sem fine-tuning.
LoRA fine-tuning opcional via mlx_lm.lora (ver docs/PLANO_B_SLM.md).

Referências:
  Qwen2.5:  https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
  ollama:   https://github.com/ollama/ollama
  MLX-LM:   https://github.com/ml-explore/mlx-lm
  LoRA:     https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel

from vozes_da_comunidade.types import ASTETriplet, ExtractionContext
from vozes_da_comunidade import config as cfg
from .base import ASTEExtractor


# ---------------------------------------------------------------------------
# Schema Pydantic para saída estruturada do ollama
# Passado como format=_ASTESchema.model_json_schema() — constrained decoding
# garante JSON válido E tipos corretos, sem depender apenas do prompt.
# ---------------------------------------------------------------------------

class _TripletSchema(BaseModel):
    aspecto: str
    opiniao: str
    polaridade: Literal["POS", "NEG", "NEU", "MIX"]
    confianca: float
    categoria_aspecto: str


class _ASTESchema(BaseModel):
    triplas: list[_TripletSchema]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
Você é um especialista em análise de sentimentos (ABSA/ASTE) para cosméticos capilares.
Seu foco é PT-BR informal: gírias, emojis, ironia, linguagem de TikTok.

Categorias de aspecto válidas (Codebook V3):
PRODUTO | RESULTADO_EFICACIA | TEXTURA_CABELO | TEXTURA_PRODUTO |
EMBALAGEM | APLICACAO | CUSTO | CRONOGRAMA_CAPILAR | PRESCRITOR |
CABELO_TIPO | ATIVO_INGREDIENTE | CLAIM_EFICACIA |
CUSTO_PERCEBIDO | ROTINA_CRONOGRAMA

Regras obrigatórias:
1. Aspecto = expressão exata do texto (ingrediente, resultado, textura, marca, embalagem, preço, rotina)
2. Opinião = expressão exata do texto que expressa o julgamento
3. Polaridade: POS | NEG | NEU | MIX
4. Se há ironia (🤡, "claro que...", kkk após reclamação): polaridade inversa ao aparente
5. Gírias: interprete o significado real ("n salvou" = não salvou = NEG)
6. Um comentário pode ter ZERO ou VÁRIAS triplas
7. Responda SOMENTE JSON — nenhum texto antes ou depois
"""

_USER_PROMPT = """\
Contexto do vídeo: {macro_theme}
Segmento inferido: {segmento_hnr}
Marca primária: {marca_primaria}
Ironia sinalizada: {has_irony}
Negação presente: {has_negation}

Comentário:
"{text}"

Responda com o JSON abaixo (sem markdown, sem texto extra):
{{
  "triplas": [
    {{
      "aspecto": "<expressão exata do texto>",
      "opiniao": "<expressão exata do texto>",
      "polaridade": "POS|NEG|NEU|MIX",
      "confianca": 0.0,
      "categoria_aspecto": "<categoria do Codebook V3>"
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# SLMExtractor
# ---------------------------------------------------------------------------


class SLMExtractor(ASTEExtractor):
    """
    Extrator ASTE via SLM local (Plano B).

    Funciona imediatamente sem fine-tuning.
    Para acumular conhecimento da Embelleze progressivamente,
    use LoRA fine-tuning via mlx_lm.lora (ver docs/PLANO_B_SLM.md).

    Backends:
      ollama (padrão): requer `ollama serve` + `ollama pull <modelo>`
      mlx: requer `pip install mlx-lm` + Apple Silicon
    """

    def __init__(
        self,
        model: str | None = None,
        backend: str | None = None,
    ) -> None:
        self._model = model or cfg.SLM_MODEL
        self._backend = backend or cfg.SLM_BACKEND
        self._mlx_model = None
        self._mlx_tokenizer = None

        if self._backend == "mlx":
            self._load_mlx()
        logger.info(
            "SLMExtractor: backend=%s model=%s", self._backend, self._model
        )

    def _load_mlx(self) -> None:
        """Carrega o modelo MLX em memória (M1 — executa na GPU unificada)."""
        try:
            from mlx_lm import load  # type: ignore

            self._mlx_model, self._mlx_tokenizer = load(self._model)
            logger.info("SLMExtractor[MLX]: modelo '%s' carregado.", self._model)
        except ImportError:
            logger.warning(
                "mlx-lm não instalado. Instale com: pip install mlx-lm. "
                "Fallback para ollama."
            )
            self._backend = "ollama"

    # ------------------------------------------------------------------
    # Interface ASTEExtractor
    # ------------------------------------------------------------------

    def is_ready(self) -> bool:
        return True  # SLM não requer fine-tuning para funcionar

    def extract(self, text: str, context: ExtractionContext) -> list[ASTETriplet]:
        prompt = _USER_PROMPT.format(
            macro_theme=context.macro_theme,
            segmento_hnr=context.segmento_hnr,
            marca_primaria=context.marca_primaria,
            has_irony=context.linguistic_signals.get("has_irony_signal", False),
            has_negation=context.linguistic_signals.get("has_negation", False),
            text=text,
        )

        raw_json = self._call_with_retry(prompt)
        return self._parse(raw_json, context)

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def _call_with_retry(self, prompt: str) -> dict[str, Any]:
        """
        Chama o backend com retry em caso de falha de parsing.

        Para ollama: constrained decoding via schema Pydantic garante JSON válido
        na quase totalidade dos casos — retry é segurança extra para edge cases.
        Para MLX: parsing manual do texto gerado, mais suscetível a falhas.
        """
        for attempt in range(1, cfg.SLM_MAX_RETRIES + 1):
            try:
                raw = self._call_backend(prompt)
                if isinstance(raw, dict):
                    return raw  # ollama já retorna dict parseado via Pydantic
                return json.loads(raw)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(
                    "SLMExtractor: falha no parsing (tentativa %d/%d): %s",
                    attempt,
                    cfg.SLM_MAX_RETRIES,
                    exc,
                )
                if attempt == cfg.SLM_MAX_RETRIES:
                    logger.error("SLMExtractor: todas as tentativas falharam.")
                    return {"triplas": []}
        return {"triplas": []}

    def _call_backend(self, prompt: str) -> str:
        """Despacha para ollama ou MLX."""
        if self._backend == "mlx":
            return self._call_mlx(prompt)
        return self._call_ollama(prompt)

    def _call_ollama(self, prompt: str) -> dict[str, Any]:
        """
        Chama o modelo via ollama com constrained decoding por schema Pydantic.

        format=_ASTESchema.model_json_schema() é mais robusto que format='json':
        - Garante não só JSON válido, mas tipos corretos e campos obrigatórios
        - Polaridade é Literal["POS","NEG","NEU","MIX"] — sem valores inválidos
        - Sem necessidade de post-processing manual de enums

        Referência: https://github.com/ollama/ollama/blob/main/docs/api.md
        """
        try:
            import ollama  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "ollama não instalado. Instale com: pip install ollama"
            ) from exc

        response = ollama.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            format=_ASTESchema.model_json_schema(),  # constrained decoding por schema
            options={"temperature": 0},              # temperatura 0 = determinístico
        )
        # Valida e retorna como dict — Pydantic garante tipos corretos
        validated = _ASTESchema.model_validate_json(response["message"]["content"])
        return validated.model_dump()

    def _call_mlx(self, prompt: str) -> str:
        """
        Chama o modelo via MLX-LM (nativo Apple Silicon).

        Referência: https://github.com/ml-explore/mlx-lm
        Modelo recomendado: mlx-community/Qwen2.5-7B-Instruct-4bit (4.28 GB)
        """
        from mlx_lm import generate  # type: ignore

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        formatted = self._mlx_tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        raw = generate(
            self._mlx_model,
            self._mlx_tokenizer,
            prompt=formatted,
            max_tokens=cfg.SLM_MAX_TOKENS,
            verbose=False,
        )
        # Extrai o JSON da resposta (MLX pode retornar texto com prefixo)
        return self._extract_json_block(raw)

    # ------------------------------------------------------------------
    # Parsing e validação
    # ------------------------------------------------------------------

    def _parse(
        self, data: dict[str, Any], context: ExtractionContext
    ) -> list[ASTETriplet]:
        """Converte o JSON retornado pelo SLM em lista de ASTETriplet."""
        triplas_raw = data.get("triplas", [])
        triplets = []

        for t in triplas_raw:
            if not isinstance(t, dict):
                continue
            aspecto = t.get("aspecto", "").strip()
            opiniao = t.get("opiniao", "").strip()
            if not aspecto or not opiniao:
                continue

            polaridade = t.get("polaridade", "NEU").upper()
            if polaridade not in {"POS", "NEG", "NEU", "MIX"}:
                polaridade = "NEU"

            confianca = float(t.get("confianca", 0.5))
            if confianca < cfg.MIN_CONFIDENCE:
                continue

            triplets.append(
                ASTETriplet(
                    aspecto=aspecto,
                    opiniao=opiniao,
                    polaridade=polaridade,
                    confianca=confianca,
                    categoria_aspecto=t.get("categoria_aspecto", "PRODUTO"),
                    # SLM não produz spans — apenas string
                    span_aspecto=None,
                    span_opiniao=None,
                )
            )
        return triplets

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """Extrai o bloco JSON de uma resposta que pode conter texto extra."""
        # Tenta encontrar {...} mais externo
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)
        return text
