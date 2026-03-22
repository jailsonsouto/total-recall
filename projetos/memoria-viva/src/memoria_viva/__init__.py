"""
Memória Viva — Agente 8 (Memory Manager)
=========================================

Sistema de memória persistente para o framework multi-agente Novex/Embelleze.
Transforma o sistema de "ferramenta que responde" em "sistema que aprende".

O QUE ESTE PACOTE FAZ:
    Antes de cada briefing, injeta contexto histórico nos agentes.
    Depois de cada briefing, salva o que vale lembrar.
    Quando o Comitê decide GO/NO-GO, extrai padrões para o futuro.

COMO USAR:
    from memoria_viva import MemoryManager

    mm = MemoryManager()
    contexto = mm.memory_read("sérum de transição com quinoa")
    # → retorna padrões históricos, alertas de rejeição, calibrações

PARA MAIS INFORMAÇÕES:
    Ver docs/ARQUITETURA.md para a arquitetura completa.
    Ver docs/ADRs.md para as decisões de design.
    Ver INSTALL.md para instruções de instalação.
"""

__version__ = "0.1.0"

from .memory_manager import MemoryManager
from .models import MemoryContext, SearchResult, BriefingThread

__all__ = ["MemoryManager", "MemoryContext", "SearchResult", "BriefingThread"]
