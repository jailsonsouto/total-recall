"""
models.py — Estruturas de dados do Total Recall
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


def _strip_accents(text: str) -> str:
    """Remove acentos/diacríticos — mesma normalização que o tokenizer
    padrão do FTS5 (unicode61) já faz por padrão. Sem isso, um termo que
    o FTS5 encontrou (índice já sem acento) pode não bater numa
    comparação de string crua em Python, mesmo sendo o mesmo match —
    achado real: "próximo" no conteúdo não batia com "proximo" (variante
    fuzzy sem acento), fazendo a barra de cobertura mostrar ausente onde
    era, na verdade, um match fuzzy real."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


# ══════════════════════════════════════════════════════════════
# Highlighting — marcador de texto para termos encontrados
# ══════════════════════════════════════════════════════════════

# ANSI: cores de fundo para terminal
_ANSI_YELLOW = "\033[43m\033[30m"   # query terms
_ANSI_GREEN = "\033[42m\033[30m"    # fuzzy matches
_ANSI_CYAN = "\033[46m\033[30m"     # abbreviation matches
_ANSI_RESET = "\033[0m"


# ══════════════════════════════════════════════════════════════
# Origem — busca cruzada (total-recall / total-recall-codex)
# ══════════════════════════════════════════════════════════════

_ORIGIN_LABELS = {
    "claude-code": "CLAUDE-CODE",
    "codex": "CODEX",
}


def origin_plain(origin: str) -> str:
    """Rótulo de origem sem colchetes — pra colunas de tabela, onde o
    cabeçalho já dá o contexto e os colchetes só adicionam ruído visual."""
    return _ORIGIN_LABELS.get(origin, origin.upper())


def origin_label(origin: str) -> str:
    """Selo de origem para exibição — sempre visível, nunca omitido pra
    'origem padrão': numa busca cruzada, marcar só o banco estrangeiro
    obriga o leitor a inferir o local pela ausência de marca."""
    return f"[{origin_plain(origin)}]"


_EXPANSION_TYPE_LABELS = {
    "fuzzy": "fuzzy",
    "abbreviation": "abrev",
    "split": "composta",
    "fuzzy+split": "fuzzy+composta",
}


def expansion_label(exp_type: str) -> str:
    """Rótulo de exibição pro tipo de expansão de query — fallback pro
    próprio valor se for um tipo novo ainda não mapeado, em vez de cair
    silenciosamente em "abrev" por engano (bug real: um `else` genérico
    rotularia "split" como abreviação)."""
    return _EXPANSION_TYPE_LABELS.get(exp_type, exp_type)


# ══════════════════════════════════════════════════════════════
# Barra de cobertura por termo — --format table
# ══════════════════════════════════════════════════════════════
#
# Substitui o score decimal bruto (opaco, não comparável entre buscas —
# ver APRENDIZADOS.md) por um selo verificável: pra cada termo da query,
# mostra se ele bateu literal, só via fuzzy/abreviação, ou não apareceu.
# Cada símbolo corresponde a um fato checável no próprio trecho, não a
# uma conta interna. Desenhado com base em achado real (Haiku, 3 rodadas):
# um modelo fraco lendo só o score bruto concluiu "isso é ruído" quando
# o match era genuíno — a barra de cobertura resolve isso sem precisar
# de julgamento sobre pesos/fórmulas internas.

_COVERAGE_CHARS = {
    "literal": "█",
    "fuzzy": "▒",
    "ausente": "░",
}

COVERAGE_LEGEND = "█ literal · ▒ fuzzy/abrev · ░ ausente"

# Numeração circular pros termos na legenda (①②③...) — cai pra "(N)" além
# do 20º termo, caso extremo que não deveria acontecer na prática.
_CIRCLED_DIGITS = [chr(0x2460 + i) for i in range(20)]  # ① a ⑳


def circled_number(n: int) -> str:
    """①②③... pro n-ésimo termo (1-indexed); fallback "(N)" além de 20."""
    if 1 <= n <= len(_CIRCLED_DIGITS):
        return _CIRCLED_DIGITS[n - 1]
    return f"({n})"


def term_coverage(content: str, query_terms: list[str],
                  expansions: list[dict]) -> list[str]:
    """Pra cada termo em `query_terms` (na ordem digitada), retorna o
    nível de match encontrado em `content`: "literal" (o termo em si
    aparece), "fuzzy" (só uma expansão fuzzy/abreviação dele aparece,
    via `expansions` — o mesmo `query_info["expansions"]` que já existe),
    ou "ausente" (nenhum dos dois). Comparação sem acento (mesma
    normalização do tokenizer FTS5) — ver `_strip_accents`."""
    content_folded = _strip_accents(content.lower())
    exp_map = {e["original"]: e.get("expanded", []) for e in expansions}

    levels = []
    for term in query_terms:
        if _strip_accents(term) in content_folded:
            levels.append("literal")
            continue
        variants = exp_map.get(term, [])
        if any(_strip_accents(v.lower()) in content_folded for v in variants if v):
            levels.append("fuzzy")
        else:
            levels.append("ausente")
    return levels


def render_coverage_bar(levels: list[str], total_width: int = 10) -> str:
    """Desenha a barra segmentada: um segmento por termo, `total_width`
    caracteres divididos entre os segmentos (mesma largura total pra
    todas as linhas de uma mesma busca, pra alinhar em coluna)."""
    if not levels:
        return "[]"
    seg_width = max(1, total_width // len(levels))
    segments = [_COVERAGE_CHARS.get(level, "░") * seg_width for level in levels]
    return "[" + "|".join(segments) + "]"


def relative_percent(score: float, top_score: float) -> int:
    """Score relativo ao melhor resultado desta busca (top=100%) — não
    comparável entre buscas diferentes, só dentro da mesma lista, onde
    a comparação já é válida (é a mesma ordenação que gerou o ranking)."""
    if top_score <= 0:
        return 0
    return round(min(1.0, score / top_score) * 100)


def highlight_text(text: str, terms: list[str],
                   mode: str = "ansi") -> str:
    """Aplica marcador de texto nos termos encontrados.

    mode: "ansi" = cores no terminal, "markdown" = **bold**
    """
    if not terms or not text:
        return text

    escaped = [re.escape(t) for t in terms if t]
    if not escaped:
        return text

    pattern = re.compile(f"({'|'.join(escaped)})", re.IGNORECASE)

    if mode == "ansi":
        return pattern.sub(
            lambda m: f"{_ANSI_YELLOW}{m.group()}{_ANSI_RESET}", text
        )
    elif mode == "markdown":
        return pattern.sub(lambda m: f"**`{m.group()}`**", text)
    return text


# ══════════════════════════════════════════════════════════════
# Preview truncado — janela centralizada no match, não no início
# ══════════════════════════════════════════════════════════════
#
# Chunks podem ter até MAX_CHUNK_CHARS (1500 chars, config.py). Formatos
# truncados (rich: 300 chars, pointers "rest": 120 chars) mostravam sempre
# os primeiros N caracteres do chunk — se o termo buscado caísse depois
# dessa janela (comum em chunks longos), o resultado parecia ruído mesmo
# sendo um match genuíno e corretamente rankeado. Achado em produção:
# `total-recall search "duckdb analista" --source both --format rich`
# retornou 5 chunks corretos, mas nenhum preview mostrava "duckdb" ou
# "analista" — os termos estavam lá, só fora da janela fixa de 300 chars.

def extract_query_terms(query: str) -> list[str]:
    """Termos literais digitados pelo usuário, sem expansões fuzzy/abreviação.
    Usado para decidir onde centralizar o preview: uma expansão fuzzy ruidosa
    (ex.: "wren" → "when", palavra comum) pode casar numa posição do texto
    sem relação nenhuma com a busca real — a query literal é sinal mais
    confiável de onde está o match relevante."""
    terms = []
    for word in query.lower().split():
        clean = word.strip(".,!?;:")
        if clean and len(clean) >= 2:
            terms.append(clean)
    return terms


def _find_first_term_pos(content: str, terms: list[str]) -> Optional[int]:
    """Posição do primeiro termo de `terms` que aparece em `content`
    (case-insensitive), ou None se nenhum aparecer."""
    escaped = [re.escape(t) for t in terms if t]
    if not escaped:
        return None
    pattern = re.compile(f"({'|'.join(escaped)})", re.IGNORECASE)
    match = pattern.search(content)
    return match.start() if match else None


def _find_term_positions(content: str, terms: list[str]) -> list[int]:
    """Posição da primeira ocorrência de CADA termo distinto de `terms`
    que aparece em `content` (uma por termo, não todas as ocorrências —
    o suficiente pra saber o alcance da cobertura)."""
    positions = []
    for term in terms:
        if not term:
            continue
        pos = _find_first_term_pos(content, [term])
        if pos is not None:
            positions.append(pos)
    return positions


def preview_window(content: str, priority_terms: list[str],
                    fallback_terms: list[str], width: int = 300,
                    max_width: Optional[int] = None) -> str:
    """Janela de preview centralizada no(s) termo(s) encontrado(s) — não
    sempre `content[:width]`.

    Busca primeiro em `priority_terms` (a query literal). Se NENHUM termo
    literal aparecer, cai para `fallback_terms` (expansões fuzzy/abreviação,
    que sozinhas podem ser ruidosas — daí só decidirem a janela quando não
    há nenhuma âncora literal). Se nada aparecer, faz fallback para o
    comportamento antigo (começa do caractere 0) — melhor mostrar algo do
    chunk do que nada.

    Quando pelo menos um termo literal já ancora a janela, `fallback_terms`
    também entra — não pra decidir sozinho onde centralizar, mas pra
    ESTENDER uma janela já legítima. Achado real: query "buscla vetorial"
    (typo fuzzy-corrigido para "buscar" + termo literal "vetorial") só
    mostrava "vetorial" no trecho — "buscar" existia no mesmo chunk mas
    ficava de fora porque antes o fallback era ignorado assim que qualquer
    termo literal aparecia, mesmo que só 1 de 2 termos da query.

    Quando mais de uma posição (literal e/ou fuzzy) aparece no conteúdo,
    tenta expandir a janela (até `max_width`, padrão 2×`width`) pra cobrir
    do primeiro ao último — um chunk com "duckdb" e "analista" a 400 chars
    de distância ainda é um match completo, mas uma janela fixa de largura
    `width` centralizada só no primeiro termo esconderia o segundo, fazendo
    o resultado parecer parcial mesmo sendo genuíno. Se os termos estiverem
    longe demais pra caber em `max_width`, cai de volta pra centralizar só
    no primeiro — melhor mostrar um termo com clareza do que dois raspando
    nas bordas.
    """
    if max_width is None:
        max_width = width * 2

    if len(content) <= width:
        return content.replace("\n", " ")

    priority_positions = _find_term_positions(content, priority_terms)

    if priority_positions:
        # Já tem âncora literal — fallback pode ESTENDER a janela, mas se a
        # extensão não couber em max_width, volta a centralizar só na(s)
        # posição(ões) literal(is) — fallback nunca decide o centro sozinho.
        merged = priority_positions + _find_term_positions(content, fallback_terms)
        first_pos, last_pos = min(merged), max(merged)
        span = last_pos - first_pos
        if span > 0 and span <= (max_width - width):
            center = (first_pos + last_pos) // 2
            target_width = min(max_width, span + width)
        else:
            center = min(priority_positions)
            target_width = width
    else:
        positions = _find_term_positions(content, fallback_terms)
        if not positions:
            window = content[:width].replace("\n", " ")
            return window + "..."
        first_pos, last_pos = min(positions), max(positions)
        span = last_pos - first_pos
        if span > 0 and span <= (max_width - width):
            center = (first_pos + last_pos) // 2
            target_width = min(max_width, span + width)
        else:
            center = first_pos
            target_width = width

    half = target_width // 2
    start = max(0, center - half)
    end = min(len(content), start + target_width)
    start = max(0, end - target_width)  # reajusta se a janela bateu no fim

    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content) else ""
    window = content[start:end].replace("\n", " ")
    return f"{prefix}{window}{suffix}"


@dataclass
class SessionInfo:
    """Metadados de uma sessão Claude Code."""
    session_id: str
    project_path: str
    project_label: str
    title: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    user_messages: int
    asst_messages: int
    file_path: str
    file_size: int = 0
    is_subagent: bool = False
    parent_session_id: Optional[str] = None


@dataclass
class Chunk:
    """Unidade semântica indexável extraída de uma sessão."""
    id: Optional[int]       # None antes de inserir no DB
    session_id: str
    role: str               # 'user', 'assistant', 'exchange'
    content: str
    timestamp: Optional[datetime]
    chunk_index: int
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    has_embedding: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """Resultado de uma busca híbrida."""
    content: str
    session_id: str
    role: str
    timestamp: Optional[datetime]
    distance: float
    score: float = 0.0          # score combinado (hybrid + decay + MMR)
    metadata: dict = field(default_factory=dict)
    session_title: str = ""
    project_label: str = ""
    sources: list[str] = field(default_factory=list)  # ["vector", "fts5"]
    chunk_id: Optional[int] = None  # rowid em chunks / chunks_vec
    origin: str = "claude-code"  # "claude-code" | "codex" — qual banco respondeu (busca cruzada)


@dataclass
class RecallContext:
    """Pacote retornado pelo /recall para injeção no contexto do Claude."""
    query: str
    results: list[SearchResult]
    sessions_searched: int
    total_chunks: int
    query_info: dict = field(default_factory=dict)

    def format_for_context(self) -> str:
        if not self.results:
            return (
                f"Nenhum resultado encontrado para: \"{self.query}\"\n"
                f"({self.sessions_searched} sessões indexadas, "
                f"{self.total_chunks} chunks no banco)"
            )

        lines = [
            f"## Resultados para: \"{self.query}\"",
            f"*{len(self.results)} resultados de "
            f"{self.sessions_searched} sessões indexadas*\n",
        ]

        # Expansion summary
        expansions = self.query_info.get("expansions", [])
        if expansions:
            exp_parts = []
            for exp in expansions:
                label = expansion_label(exp["type"])
                targets = ", ".join(exp["expanded"][:3])
                exp_parts.append(f"{label}: {exp['original']} → {targets}")
            lines.append(f"*Expansões: {'; '.join(exp_parts)}*\n")

        # Collect highlight terms
        highlight_terms = self._collect_highlight_terms()

        for i, r in enumerate(self.results, 1):
            ts = r.timestamp.strftime("%d/%m/%Y %H:%M") if r.timestamp else "?"
            sources_str = " + ".join(s.upper() for s in r.sources) if r.sources else "?"
            header = f"### {i}. {origin_label(r.origin)} {r.project_label} — {r.session_title}"
            meta = f"*Sessão `{r.session_id[:8]}` | {ts} | score: {r.score:.3f} | {sources_str}*"
            content = highlight_text(r.content, highlight_terms, mode="markdown")
            lines.append(header)
            lines.append(meta)
            lines.append(f"\n{content}\n")
            lines.append("---\n")

        return "\n".join(lines)

    def format_pointers(self, max_full_sessions: int = 4) -> str:
        """Formato ponteiro guiado por sessão (estudo empírico 2026-07-05):
        cita na íntegra o melhor hit (primeiro no ranking) de cada sessão
        distinta, até `max_full_sessions` sessões; hits repetidos de sessões
        já citadas — e sessões além do teto — viram ponteiros de 1 linha.
        Racional: o rank sozinho não prediz utilidade (evidência nova aparece
        nos ranks 4-8); sessão ainda não representada, sim."""
        if not self.results:
            return self.format_for_context()

        quoted_sessions: set = set()
        full: list = []
        rest: list = []
        for idx, r in enumerate(self.results, 1):
            if (r.session_id not in quoted_sessions
                    and len(quoted_sessions) < max_full_sessions):
                quoted_sessions.add(r.session_id)
                full.append((idx, r))
            else:
                rest.append((idx, r))

        lines = [
            f"## Resultados para: \"{self.query}\"",
            f"*{len(self.results)} resultados de "
            f"{self.sessions_searched} sessões indexadas — melhor hit de "
            f"{len(full)} sessão(ões) citado na íntegra, restante como ponteiros*\n",
        ]

        expansions = self.query_info.get("expansions", [])
        if expansions:
            exp_parts = []
            for exp in expansions:
                label = expansion_label(exp["type"])
                targets = ", ".join(exp["expanded"][:3])
                exp_parts.append(f"{label}: {exp['original']} → {targets}")
            lines.append(f"*Expansões: {'; '.join(exp_parts)}*\n")

        highlight_terms = self._collect_highlight_terms()
        query_terms = extract_query_terms(self.query)

        for i, r in full:
            ts = r.timestamp.strftime("%d/%m/%Y %H:%M") if r.timestamp else "?"
            sources_str = " + ".join(s.upper() for s in r.sources) if r.sources else "?"
            lines.append(f"### [{i}] {origin_label(r.origin)} {r.project_label} — {r.session_title}")
            lines.append(
                f"*Sessão `{r.session_id[:8]}` | {ts} | "
                f"score: {r.score:.3f} | {sources_str}*"
            )
            lines.append(f"\n{highlight_text(r.content, highlight_terms, mode='markdown')}\n")
            lines.append("---\n")

        if rest:
            lines.append("### Ponteiros (drill-down sob demanda)")
            for i, r in rest:
                ts = r.timestamp.strftime("%d/%m/%Y") if r.timestamp else "?"
                # Trecho centralizado no match — mesma correção do formato
                # rich: um preview sempre do caractere 0 podia esconder o
                # termo buscado em chunks longos e parecer ruído sem ser.
                preview = preview_window(r.content, query_terms, highlight_terms, width=120)
                repeat = " (sessão já citada)" if r.session_id in quoted_sessions else ""
                lines.append(
                    f"- [{i}] {origin_label(r.origin)} `{r.session_id[:8]}`{repeat} | {ts} | {r.score:.2f} | "
                    f"{r.project_label} — {preview}"
                )
            lines.append(
                f"\n*Para expandir um ponteiro: "
                f"`total-recall search \"{self.query}\" --session <id> --source <origem> --format context`*"
                f" — troque `<origem>` por `claude-code` ou `codex` conforme o rótulo mostrado"
                f" entre colchetes ao lado do ponteiro (o padrão do `--source` é `claude-code`,"
                f" então um ponteiro `[CODEX]` some se você não passar `--source codex`)."
            )

        return "\n".join(lines)

    def _collect_highlight_terms(self) -> list[str]:
        """Coleta termos para highlighting a partir da query e expansões."""
        terms = set()
        for word in self.query.lower().split():
            clean = word.strip(".,!?;:")
            if clean and len(clean) >= 2:
                terms.add(clean)
        for exp in self.query_info.get("expansions", []):
            for expanded in exp["expanded"]:
                terms.add(expanded.lower())
        return sorted(terms, key=len, reverse=True)
