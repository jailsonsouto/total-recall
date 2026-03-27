"""
run_corpus.py — Extração ASTE no corpus completo via Maritaca API.

Uso:
    python3 scripts/run_corpus.py --dry-run          # valida pipeline, não consome API
    python3 scripts/run_corpus.py                    # roda sabiazinho-4 no corpus completo
    python3 scripts/run_corpus.py --model sabia-4    # modelo diferente
    python3 scripts/run_corpus.py --resume           # retoma de partials existentes

Safeguards contra o crash de 2026-03-27:
    - save incremental a cada 100 comentários (data/corpus_partial_N.json)
    - retry com backoff exponencial para erros 429/529 (3 tentativas: 5s/15s/45s)
    - --resume: pula comentários já processados em partials anteriores
    - --dry-run: valida toda a pipeline em 10 comentários antes de consumir API
    - atributo correto: d.classification (não d.gate_class — bug do crash anterior)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Garante que o pacote vozes_da_comunidade seja importável a partir da raiz do projeto
PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT / ".env")

from vozes_da_comunidade.batch.router import Router
from vozes_da_comunidade.batch.gate import SemanticGate, GateClass

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

MARITACA_API_KEY = os.getenv("MARITACA_API_KEY", "")
MARITACA_BASE_URL = "https://chat.maritaca.ai/api"
SAVE_EVERY = 100       # salvar partial a cada N comentários extraídos
DRY_RUN_LIMIT = 10     # número de comentários no dry-run
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 45]  # segundos de espera entre tentativas

SYSTEM_PROMPT = """\
Você é um especialista em análise de sentimentos (ABSA/ASTE) para cosméticos capilares.
Seu foco é PT-BR informal: gírias, emojis, ironia, linguagem de TikTok.

Categorias de aspecto válidas (Codebook V3):
PRODUTO | RESULTADO_EFICACIA | TEXTURA_CABELO | TEXTURA_PRODUTO |
EMBALAGEM | APLICACAO | CUSTO | CRONOGRAMA_CAPILAR | PRESCRITOR |
CABELO_TIPO | ATIVO_INGREDIENTE | CLAIM_EFICACIA | CUSTO_PERCEBIDO | ROTINA_CRONOGRAMA

Regras obrigatórias:
1. Aspecto = expressão exata do texto
2. Opinião = expressão exata do texto que expressa o julgamento
3. Polaridade: POS | NEG | NEU | MIX
4. Se há ironia: polaridade inversa ao aparente
5. Gírias: interprete o significado real
6. Aspecto != Opinião (nunca repetir o mesmo termo em ambos)
7. Zero triplas é resposta válida
8. Responda SOMENTE JSON sem markdown
"""

USER_PROMPT_TEMPLATE = """\
Comentário: "{text}"

Responda com JSON (sem markdown, sem texto extra):
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
# Helpers
# ---------------------------------------------------------------------------

def load_corpus(input_dir: Path) -> list[dict]:
    """Carrega todos os JSONs do corpus_v1, descartando normalization_summary."""
    comments = []
    for json_file in sorted(input_dir.glob("**/*.json")):
        if "normalization_summary" in json_file.name:
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            batch = data if isinstance(data, list) else data.get("comments", [])
            comments.extend(batch)
        except Exception as exc:
            print(f"[AVISO] Falha ao ler {json_file.name}: {exc}")
    return comments


def load_resume_ids(data_dir: Path) -> set[str]:
    """Carrega IDs de comentários já processados em partials anteriores."""
    processed_ids: set[str] = set()
    for partial in sorted(data_dir.glob("corpus_partial_*.json")):
        try:
            records = json.loads(partial.read_text(encoding="utf-8"))
            for r in records:
                cid = r.get("comment_id") or r.get("comment", {}).get("comment_id")
                if cid:
                    processed_ids.add(str(cid))
        except Exception:
            pass
    return processed_ids


def load_partial_results(data_dir: Path) -> list[dict]:
    """Carrega e mescla todos os partials existentes."""
    results = []
    for partial in sorted(data_dir.glob("corpus_partial_*.json")):
        try:
            records = json.loads(partial.read_text(encoding="utf-8"))
            results.extend(records)
        except Exception:
            pass
    return results


def save_partial(results: list[dict], data_dir: Path, n: int) -> None:
    """Salva checkpoint parcial."""
    path = data_dir / f"corpus_partial_{n}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [partial] {len(results)} resultados salvos em {path.name}")


def extract_json(text: str) -> dict:
    """Extrai JSON de uma resposta que pode ou não ter markdown."""
    import re
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"triplas": []}


def call_maritaca(client, model: str, text: str) -> dict:
    """
    Chama a API Maritaca com retry e backoff exponencial.

    Retorna dict com chave 'triplas'. Em caso de falha persistente,
    retorna {'triplas': [], 'error': '<mensagem>'}.
    """
    prompt = USER_PROMPT_TEMPLATE.format(text=text.replace('"', "'"))
    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=512,
            )
            raw = response.choices[0].message.content
            return extract_json(raw)
        except Exception as exc:
            last_error = str(exc)
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if code in (429, 529) and attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAYS[attempt]
                print(f"  [retry {attempt+1}/{MAX_RETRIES}] API {code} — aguardando {wait}s...")
                time.sleep(wait)
            elif attempt < MAX_RETRIES - 1:
                # Erro genérico: tenta uma vez mais
                time.sleep(2)
            else:
                break
    return {"triplas": [], "error": last_error}


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run(
    input_dir: Path,
    output_path: Path,
    model: str,
    dry_run: bool,
    resume: bool,
) -> None:
    data_dir = output_path.parent

    print(f"\n{'='*60}")
    print(f"run_corpus.py — modelo={model}")
    print(f"  input:  {input_dir}")
    print(f"  output: {output_path}")
    if dry_run:
        print(f"  modo:   DRY-RUN (primeiros {DRY_RUN_LIMIT} comentários, sem salvar)")
    elif resume:
        print(f"  modo:   RESUME (retoma de partials existentes)")
    print(f"{'='*60}\n")

    # 1. Carregar corpus
    print("[1/4] Carregando corpus...")
    all_comments = load_corpus(input_dir)
    print(f"      {len(all_comments)} comentários carregados")

    # 2. Router
    print("[2/4] Aplicando Router...")
    router = Router()
    router_result = router.route(all_comments)
    print(f"      {router_result.summary()}")

    # 3. Gate semântico
    print("[3/4] Aplicando Gate semântico...")
    gate = SemanticGate()
    gate_result = gate.classify_all(router_result.accepted)
    print(f"      {gate_result.summary()}")

    # Mapa comment_id → GateDecision (para lookup correto no loop)
    # Usar id() do objeto como chave — mesmo objeto retornado pelo classify_all
    decision_by_obj_id: dict[int, "GateDecision"] = {
        id(comment): decision
        for comment, decision in zip(router_result.accepted, gate_result.decisions)
    }

    # Elegíveis para extração
    eligible = gate_result.aste_ready
    print(f"\n      Elegíveis para extração ASTE: {len(eligible)}")

    if dry_run:
        eligible = eligible[:DRY_RUN_LIMIT]
        print(f"      [DRY-RUN] Limitado a {len(eligible)} comentários\n")

    # 4. Extração com Maritaca
    print("[4/4] Extraindo triplas via Maritaca API...")

    # Resume: pular IDs já processados
    skip_ids: set[str] = set()
    results: list[dict] = []
    if resume and not dry_run:
        skip_ids = load_resume_ids(data_dir)
        results = load_partial_results(data_dir)
        print(f"      [resume] {len(skip_ids)} comentários já processados — pulando")

    if not dry_run and not MARITACA_API_KEY:
        print("\n[ERRO] MARITACA_API_KEY não encontrada no .env")
        sys.exit(1)

    client = None
    if not dry_run:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=MARITACA_API_KEY, base_url=MARITACA_BASE_URL)
        except ImportError:
            print("[ERRO] openai não instalado. Execute: pip install openai")
            sys.exit(1)

    start = time.perf_counter()
    extracted = 0
    errors = 0

    for i, comment in enumerate(eligible):
        cid = str(comment.get("comment_id", f"idx_{i}"))

        if cid in skip_ids:
            continue

        text = comment.get("text_for_model") or comment.get("text", "")
        if not text.strip():
            continue

        if dry_run:
            # Simula chamada — valida apenas a pipeline
            triplas = [{"aspecto": "[DRY-RUN]", "opiniao": text[:30], "polaridade": "NEU", "confianca": 1.0, "categoria_aspecto": "PRODUTO"}]
            data = {"triplas": triplas}
        else:
            data = call_maritaca(client, model, text)

        dec = decision_by_obj_id.get(id(comment))
        record = {
            "comment_id": cid,
            "text": text,
            "model": model,
            "triplas": data.get("triplas", []),
            "gate_class": dec.classification.value if dec else "aste_ready",
            "gate_reason": dec.reason if dec else "",
        }
        if "error" in data:
            record["api_error"] = data["error"]
            errors += 1

        results.append(record)
        extracted += 1

        # Progresso
        if extracted % 10 == 0 or dry_run:
            elapsed = time.perf_counter() - start
            rate = extracted / elapsed if elapsed > 0 else 0
            print(f"  {extracted}/{len(eligible)} | {rate:.1f} req/s | erros={errors}")

        # Save incremental a cada SAVE_EVERY comentários
        if not dry_run and extracted % SAVE_EVERY == 0:
            save_partial(results, data_dir, extracted)

    elapsed_total = time.perf_counter() - start

    # Dry-run: mostrar amostra e sair
    if dry_run:
        print(f"\n{'='*60}")
        print("DRY-RUN concluído")
        print(f"  {extracted} comentários validados em {elapsed_total:.1f}s")
        print(f"\nAmostra de triplas extraídas:")
        shown = 0
        for r in results:
            for t in r.get("triplas", []):
                if shown >= 3:
                    break
                print(f"  [{r['gate_class']}] {t.get('aspecto')} | {t.get('opiniao')} | {t.get('polaridade')}")
                shown += 1
        print(f"\nDry-run OK — {len(eligible)} comentários elegíveis para extração real")
        print(f"Rode sem --dry-run para processar o corpus completo")
        print(f"{'='*60}\n")
        return

    # Salvar resultado final
    print(f"\nSalvando resultado final em {output_path}...")
    output = {
        "model": model,
        "total_comments_corpus": len(all_comments),
        "router_accepted": len(router_result.accepted),
        "gate_aste_ready": len(gate_result.aste_ready),
        "extracted": extracted,
        "errors": errors,
        "elapsed_seconds": round(elapsed_total, 1),
        "results": results,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"Extração concluída")
    print(f"  Comentários no corpus:   {len(all_comments)}")
    print(f"  Aceitos pelo Router:     {len(router_result.accepted)}")
    print(f"  Elegíveis (aste_ready):  {len(gate_result.aste_ready)}")
    print(f"  Extraídos com sucesso:   {extracted - errors}")
    print(f"  Erros de API:            {errors}")
    print(f"  Tempo total:             {elapsed_total:.1f}s ({elapsed_total/60:.1f}min)")
    print(f"  Resultado salvo em:      {output_path}")
    print(f"{'='*60}\n")

    # Limpar partials se tudo correu bem
    if errors == 0:
        for partial in data_dir.glob("corpus_partial_*.json"):
            partial.unlink()
            print(f"  [cleanup] {partial.name} removido")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extração ASTE no corpus completo via Maritaca API"
    )
    parser.add_argument(
        "--input",
        default="data/corpus_v1",
        help="Diretório com arquivos JSON do corpus (default: data/corpus_v1)",
    )
    parser.add_argument(
        "--output",
        default="data/corpus_completo_sabiazinho4.json",
        help="Arquivo de saída (default: data/corpus_completo_sabiazinho4.json)",
    )
    parser.add_argument(
        "--model",
        default="sabiazinho-4",
        help="Modelo Maritaca (default: sabiazinho-4)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Processa apenas 10 comentários para validar a pipeline",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Retoma de partials existentes (pula comentários já processados)",
    )
    args = parser.parse_args()

    input_dir = PROJECT / args.input
    output_path = PROJECT / args.output

    if not input_dir.exists():
        print(f"[ERRO] Diretório de input não encontrado: {input_dir}")
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    run(
        input_dir=input_dir,
        output_path=output_path,
        model=args.model,
        dry_run=args.dry_run,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()
