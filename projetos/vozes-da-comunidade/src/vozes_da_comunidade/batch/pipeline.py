"""
BatchPipeline — orquestrador da fase offline.

Fluxo:
  JSONs do corpus
    → Router (filtra por interaction_type)
    → TikTokTextProcessor (normalização PT-BR)
    → ASTEExtractor (extrai triplas)
    → [Calculador de indicadores — passo 2]
    → [post_batch_flush → Warm Store — passo 3]

Uso:
    pipeline = BatchPipeline()
    result = pipeline.run(input_dir="./data/corpus/")
    print(result.summary())
"""
from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from vozes_da_comunidade import config as cfg
from vozes_da_comunidade.extractors import build_extractor
from vozes_da_comunidade.types import ASTETriplet, ctx_from_comment
from .router import Router, RouterResult

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Resultado de uma execução do pipeline batch."""

    input_dir: str = ""
    files_processed: int = 0
    files_failed: int = 0

    # Router
    comments_total: int = 0
    comments_accepted: int = 0
    comments_rejected: int = 0

    # Extração
    comments_extracted: int = 0
    comments_failed_extraction: int = 0
    triplets_total: int = 0

    # Timing
    elapsed_seconds: float = 0.0

    # Triplas extraídas — input para o Calculador (passo 2)
    triplets_by_comment: list[tuple[dict, list[ASTETriplet]]] = field(
        default_factory=list
    )

    @property
    def acceptance_rate(self) -> float:
        if self.comments_total == 0:
            return 0.0
        return self.comments_accepted / self.comments_total

    @property
    def extraction_rate(self) -> float:
        if self.comments_accepted == 0:
            return 0.0
        return self.comments_extracted / self.comments_accepted

    @property
    def triplets_per_comment(self) -> float:
        if self.comments_extracted == 0:
            return 0.0
        return self.triplets_total / self.comments_extracted

    def summary(self) -> str:
        lines = [
            "=" * 60,
            f"BatchPipeline — {self.input_dir}",
            "=" * 60,
            f"Arquivos:      {self.files_processed} processados, {self.files_failed} falhas",
            f"Comentários:   {self.comments_total} total",
            f"  ✓ aceitos:   {self.comments_accepted} ({self.acceptance_rate:.1%})",
            f"  ✗ rejeitados:{self.comments_rejected}",
            f"Extração:",
            f"  ✓ extraídos: {self.comments_extracted} ({self.extraction_rate:.1%} dos aceitos)",
            f"  ✗ falhas:    {self.comments_failed_extraction}",
            f"Triplas:       {self.triplets_total} ({self.triplets_per_comment:.1f}/comentário)",
            f"Tempo:         {self.elapsed_seconds:.1f}s",
            "=" * 60,
        ]
        return "\n".join(lines)


class BatchPipeline:
    """
    Pipeline offline do Vozes da Comunidade.

    Processa todos os JSONs de um diretório e retorna as triplas
    extraídas prontas para o Calculador de indicadores.

    O TikTokTextProcessor é importado do DINAMICA-ABSA via sys.path.
    Se não estiver disponível, o pipeline usa o texto bruto
    (text_for_model do schema V1 já vem pré-processado na coleta).
    """

    def __init__(self) -> None:
        self._router = Router()
        self._extractor = build_extractor()
        self._processor = self._load_processor()

        logger.info(
            "BatchPipeline iniciado: extrator=%s, processor=%s",
            self._extractor.name,
            "TikTokTextProcessor" if self._processor else "passthrough",
        )

    def _load_processor(self):
        """Tenta importar TikTokTextProcessor do DINAMICA-ABSA."""
        absa_path = cfg.DINAMICA_ABSA_PATH
        if absa_path and absa_path not in sys.path:
            sys.path.insert(0, absa_path)
        try:
            from dinamica_absa.src.data.tiktok_schema_normalizer import (  # type: ignore
                TikTokSchemaNormalizer,
            )
            return TikTokSchemaNormalizer()
        except ImportError:
            logger.warning(
                "TikTokTextProcessor não disponível — usando text_for_model do schema V1 diretamente."
            )
            return None

    def run(self, input_dir: str | Path) -> BatchResult:
        """
        Processa todos os JSONs em input_dir.

        Args:
            input_dir: Diretório com arquivos .json no schema V1.

        Returns:
            BatchResult com triplas extraídas e estatísticas.
        """
        input_path = Path(input_dir)
        if not input_path.exists():
            raise FileNotFoundError(f"Diretório não encontrado: {input_dir}")

        result = BatchResult(input_dir=str(input_dir))
        json_files = list(input_path.glob("**/*.json"))

        if not json_files:
            logger.warning("Nenhum arquivo .json encontrado em %s", input_dir)
            return result

        logger.info("Iniciando batch: %d arquivos em %s", len(json_files), input_dir)
        start = time.perf_counter()

        for json_file in json_files:
            self._process_file(json_file, result)

        result.elapsed_seconds = time.perf_counter() - start
        logger.info("\n%s", result.summary())
        return result

    def run_sample(self, input_dir: str | Path, n: int = 20) -> BatchResult:
        """
        Processa apenas os primeiros N comentários — útil para validação rápida.

        Args:
            input_dir: Diretório com arquivos .json.
            n: Número máximo de comentários a processar.
        """
        input_path = Path(input_dir)
        result = BatchResult(input_dir=f"{input_dir} [amostra n={n}]")
        collected: list[dict] = []

        for json_file in input_path.glob("**/*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                comments = data if isinstance(data, list) else data.get("comments", [])
                collected.extend(comments)
                if len(collected) >= n:
                    break
            except Exception:
                pass

        comments_sample = collected[:n]
        start = time.perf_counter()
        self._process_comments(comments_sample, result)
        result.elapsed_seconds = time.perf_counter() - start
        result.files_processed = 1  # aproximação para sample
        logger.info("\n%s", result.summary())
        return result

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _process_file(self, json_file: Path, result: BatchResult) -> None:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Falha ao ler %s: %s", json_file, exc)
            result.files_failed += 1
            return

        result.files_processed += 1

        # Router
        router_result: RouterResult = self._router.route_file(data)
        result.comments_total += router_result.total
        result.comments_accepted += len(router_result.accepted)
        result.comments_rejected += len(router_result.rejected)

        logger.debug("%s → %s", json_file.name, router_result.summary())

        self._process_comments(router_result.accepted, result)

    def _process_comments(self, comments: list[dict], result: BatchResult) -> None:
        for comment in comments:
            text = self._get_text(comment)
            if not text:
                result.comments_failed_extraction += 1
                continue

            ctx = ctx_from_comment(comment)
            try:
                triplets = self._extractor.extract(text, ctx)
                result.comments_extracted += 1
                result.triplets_total += len(triplets)
                result.triplets_by_comment.append((comment, triplets))
            except Exception as exc:
                logger.warning(
                    "Falha na extração do comentário %s: %s",
                    comment.get("comment_id", "?"),
                    exc,
                )
                result.comments_failed_extraction += 1

    def _get_text(self, comment: dict) -> str:
        """Retorna o texto processado do comentário."""
        # Schema V1 já tem text_for_model pré-processado
        text = comment.get("text_for_model", "").strip()
        if text:
            return text
        # Fallback: texto bruto
        return comment.get("text", "").strip()
