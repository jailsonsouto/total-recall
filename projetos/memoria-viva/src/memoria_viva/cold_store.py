"""
cold_store.py — Operações no filesystem (Markdown)
===================================================

CONCEITO:
    O Cold Store é a memória LEGÍVEL POR HUMANOS. Enquanto o Hot Store
    (SQLite) e o Warm Store (vetores) são para máquinas, o Cold Store
    é para pessoas — Jay pode abrir e ler qualquer arquivo.

ESTRUTURA DE PASTAS:
    cold_store/
    ├── BRAND_MEMORY.md     → Código Genético da marca (sempre injetado)
    ├── PM_CONTEXT.md       → Contexto do PM (preferências, histórico)
    ├── MEMORY.md           → Insights consolidados (atualizado pelos flushes)
    ├── briefings/
    │   └── 2026-03-22.md   → Log do que foi processado nesse dia
    ├── segments/
    │   └── transicao-capilar.md → Tudo sobre transição capilar
    └── archive/
        └── (backups de threads completas em JSONL)

POR QUE MARKDOWN (ADR-003):
    - Legível por humanos (PM pode editar BRAND_MEMORY.md diretamente)
    - LLM-friendly (Claude lê Markdown como contexto nativo)
    - Git = auditoria grátis (quem editou, quando, o quê)
    - Zero custo operacional
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import COLD_STORE_PATH


class ColdStore:
    """
    Gerenciador de arquivos Markdown do Cold Store.

    Responsável por:
        - Ler o Código Genético (BRAND_MEMORY.md)
        - Ler e atualizar insights consolidados (MEMORY.md)
        - Registrar logs diários de briefings processados
        - Manter insights por segmento (transição, reconstrução, etc.)
    """

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or COLD_STORE_PATH
        self._ensure_structure()

    def _ensure_structure(self):
        """Cria a estrutura de pastas se não existir."""
        (self.base_path / "briefings").mkdir(parents=True, exist_ok=True)
        (self.base_path / "segments").mkdir(parents=True, exist_ok=True)
        (self.base_path / "archive").mkdir(parents=True, exist_ok=True)

    # ══════════════════════════════════════════════════════════
    # LEITURA
    # ══════════════════════════════════════════════════════════

    def read_brand_memory(self) -> str:
        """
        Lê o Código Genético da marca (BRAND_MEMORY.md).

        Este arquivo é SEMPRE injetado como contexto em toda execução.
        É o "DNA" da Novex/Embelleze — define o que a marca É, FAZ e FALA
        (metodologia Ana Couto).

        Se o arquivo não existir, retorna string vazia.
        (O template é criado na instalação — ver INSTALL.md)
        """
        path = self.base_path / "BRAND_MEMORY.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def read_memory(self) -> str:
        """
        Lê os insights consolidados (MEMORY.md).

        Este arquivo é atualizado automaticamente pelo Committee Flush
        com padrões de aprovação/rejeição aprendidos ao longo do tempo.
        Jay também pode editá-lo manualmente.
        """
        path = self.base_path / "MEMORY.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def read_segment(self, segment: str) -> str:
        """
        Lê o arquivo de insights de um segmento específico.

        Exemplo: read_segment("transicao-capilar")
        → lê cold_store/segments/transicao-capilar.md
        """
        path = self.base_path / "segments" / f"{segment}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def read_pm_context(self) -> str:
        """
        Lê o contexto do PM (PM_CONTEXT.md).

        Contém preferências pessoais, histórico de trabalho,
        e notas sobre como o PM prefere receber os briefings.
        """
        path = self.base_path / "PM_CONTEXT.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    # ══════════════════════════════════════════════════════════
    # ESCRITA
    # ══════════════════════════════════════════════════════════

    def append_to_briefing_log(self, content: str,
                                date: Optional[datetime] = None):
        """
        Adiciona entrada ao log diário de briefings.

        Cada dia tem seu próprio arquivo:
            briefings/2026-03-22.md

        Permite rastrear o que o sistema processou em cada dia.
        Jay pode abrir o arquivo e ver todos os briefings do dia.

        Parâmetros:
            content: texto da entrada (Markdown)
            date: data do registro (padrão: agora)
        """
        date = date or datetime.now()
        filename = date.strftime("%Y-%m-%d") + ".md"
        path = self.base_path / "briefings" / filename

        # Cria cabeçalho se o arquivo é novo
        if not path.exists():
            header = f"# Briefings — {date.strftime('%d/%m/%Y')}\n\n"
            path.write_text(header, encoding="utf-8")

        # Adiciona a entrada com timestamp
        timestamp = date.strftime("%H:%M")
        entry = f"\n---\n\n### {timestamp}\n\n{content}\n"

        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)

    def update_memory(self, section: str, content: str):
        """
        Atualiza uma seção específica do MEMORY.md.

        O MEMORY.md é organizado por seções:
            ## Padrões de Aprovação
            ## Padrões de Rejeição a Evitar
            ## Calibrações de Score

        Esta função encontra a seção e ADICIONA conteúdo a ela.
        Se a seção não existir, cria no final do arquivo.

        IDEMPOTÊNCIA: o Committee Flush verifica memory_flush_done
        antes de chamar esta função, então ela não roda duas vezes
        para o mesmo briefing.

        Parâmetros:
            section: nome da seção (sem ##) — ex: "Padrões de Aprovação"
            content: texto a adicionar na seção
        """
        path = self.base_path / "MEMORY.md"

        if not path.exists():
            path.write_text(
                "# Memória Viva — Insights Consolidados\n\n"
                "_Atualizado automaticamente pelo Agente 8._\n\n",
                encoding="utf-8",
            )

        current = path.read_text(encoding="utf-8")
        section_header = f"## {section}"

        if section_header in current:
            # Seção já existe → adiciona conteúdo ao final dela
            # Encontra o final da seção (próximo ## ou fim do arquivo)
            lines = current.split("\n")
            new_lines = []
            in_section = False
            content_added = False

            for line in lines:
                if line.strip() == section_header:
                    in_section = True
                    new_lines.append(line)
                    continue
                elif in_section and line.startswith("## "):
                    # Chegou na próxima seção → insere conteúdo antes
                    if not content_added:
                        new_lines.append(content)
                        content_added = True
                    in_section = False

                new_lines.append(line)

            # Se a seção era a última do arquivo
            if in_section and not content_added:
                new_lines.append(content)

            path.write_text("\n".join(new_lines), encoding="utf-8")
        else:
            # Seção não existe → cria no final
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n{section_header}\n\n{content}\n")

    def update_segment(self, segment: str, content: str):
        """
        Adiciona insight ao arquivo de um segmento.

        Exemplo: update_segment("transicao-capilar", "BVS médio: 7.2")
        → adiciona ao arquivo segments/transicao-capilar.md

        Cada segmento acumula conhecimento ao longo do tempo:
        tendências, padrões de aprovação/rejeição, baselines de score.

        Parâmetros:
            segment: identificador do segmento (ex: "transicao-capilar")
            content: texto do insight (Markdown)
        """
        path = self.base_path / "segments" / f"{segment}.md"

        if not path.exists():
            # Nome bonito: "transicao-capilar" → "Transicao Capilar"
            title = segment.replace("-", " ").title()
            header = f"# Insights — {title}\n\n"
            path.write_text(header, encoding="utf-8")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n### Atualização {timestamp}\n\n{content}\n"

        with open(path, "a", encoding="utf-8") as f:
            f.write(entry)
