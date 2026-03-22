# Memória Viva — Agente 8

> *"Um sistema de IA que esquece tudo depois de cada sessão não é inteligente. É uma calculadora cara."*

O sistema multi-agente de briefing da Novex/Embelleze executava análises sofisticadas — IAM, BVS preditivo, RICE, ABSA — mas era completamente amnésico. Cada briefing começava do zero. O Comitê rejeitava uma ideia por um motivo específico e, três semanas depois, uma variação da mesma ideia passava pelos mesmos 7 agentes, produzia o mesmo resultado fraco, e chegava ao mesmo Comitê pelo mesmo caminho.

A Memória Viva é a resposta para isso. É o **Agente 8** — a camada de memória persistente que faz o sistema acumular inteligência ao longo do tempo.

---

## O que muda na prática

**Sem a Memória Viva:**
- Briefing 1 sobre sérum de transição → rejeitado (ativo acima do teto de custo Onda 2)
- Briefing 2 sobre sérum de transição → os mesmos 7 agentes analisam do zero → mesmo briefing fraco → mesma rejeição
- BVS preditivo: 8.2. BVS real (6 meses depois): 7.1. O sistema nunca soube.

**Com a Memória Viva:**
- Briefing 2 chega. Antes de qualquer agente rodar, o sistema já injetou no contexto: *"ALERTA: briefings de sérum de transição foram rejeitados por custo de ativo acima do teto Onda 2 (2 ocorrências)."*
- O Agente 2 recebe a calibração: *"BVS preditivo tende a ser +0.4 acima do real neste segmento — ajuste aplicado."*
- O Agente 4 não reanálisa os 600 comentários capilares que já foram processados. Usa o insight consolidado.

Ao longo de 12 meses, o sistema acumula padrões de aprovação e rejeição, calibra os scores com dados reais de venda, e desenvolve o que nenhum agente individual consegue sozinho: **memória institucional**.

---

## Arquitetura

A memória é organizada em 3 camadas, cada uma com uma função distinta:

```
┌─────────────────────────────────────────────────────┐
│  HOT STORE — "O que está acontecendo agora"         │
│  SQLite + LangGraph State                           │
│  Estado completo do briefing, scores, checkpoints   │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  WARM STORE — "O que é relevante buscar"            │
│  sqlite-vec (vetorial) + FTS5 (keyword)             │
│  Padrões embedados, insights de segmento,           │
│  calibrações, decisões do Comitê                    │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│  COLD STORE — "O que aconteceu antes"               │
│  Filesystem Markdown + Git                          │
│  BRAND_MEMORY.md, logs diários, insights legíveis   │
│  por humanos — o PM pode editar diretamente         │
└─────────────────────────────────────────────────────┘
```

**Hot e Warm Store vivem no mesmo arquivo SQLite.** Isso não é um detalhe técnico — é uma decisão de arquitetura deliberada. Significa que a decisão do Comitê (GO ou NO-GO) e o padrão extraído dela são escritos em uma única transação atômica. Ou tudo é salvo, ou nada é salvo. O banco nunca fica em estado inconsistente.

### Os 4 momentos de operação

**Momento 1 — Memory Read** (pré-execução)
Antes de qualquer agente rodar, o Agente 8 monta um pacote de contexto: padrões históricos similares, alertas de rejeição ativos, calibrações de score, insights do segmento. Injetado nos outros agentes como memória. Budget fixo de 4.000 tokens.

**Momento 2 — Post-briefing Flush** (pós-execução)
Quando o briefing termina, o resumo é embedado e salvo no Warm Store para buscas futuras. O log diário é atualizado no Cold Store. Transação atômica.

**Momento 3 — Committee Flush** (pós-decisão do Comitê)
O flush mais crítico. Disparado por polling da API do Basecamp a cada 15 minutos. Registra GO/NO-GO, extrai o padrão da decisão, atualiza os pesos na busca futura (GO vale o dobro), verifica se há dados suficientes para recalibrar o BVS preditivo. A cada 5 decisões com BVS real disponível, calibração Bayesiana automática.

**Momento 4 — Manutenção** (cron semanal)
Aging de insights antigos, compactação de logs, remoção de duplicatas semânticas, backup Git do Cold Store. *(Roadmap — não implementado no MVP)*

---

## Por que SQLite e não um banco de vetores dedicado

A pergunta óbvia é: por que não ChromaDB, Pinecone, ou LanceDB?

**Volume:** 200-300 briefings/ano × 4 gestores de marca × ~15 vetores/briefing ≈ 4.500 vetores/ano. A busca O(n) do sqlite-vec completa em menos de 5ms até ~200.000 vetores. Esse limiar está a décadas de distância neste uso.

**Atomicidade:** Com Hot e Warm Store no mesmo arquivo, o Committee Flush — a operação mais crítica do sistema — é uma única transação ACID. Com dois bancos separados, seria necessário lógica de compensação manual para garantir consistência em caso de falha.

**Dependências:** ChromaDB e LanceDB são projetos jovens. O SQLite tem 25 anos, está em bilhões de dispositivos, e nunca vai ser descontinuado.

**Portabilidade real:** O lock-in não está no banco de vetores — está no modelo de embedding. Vetores são arrays de floats portáteis. Trocar de SQLite para LanceDB é um script de 30 linhas. Trocar o modelo de embedding exige re-embedar tudo. Por isso a abstração `EmbeddingProvider` existe: a troca é uma linha no `.env`.

---

## Stack

| Componente | Tecnologia | Motivo |
|---|---|---|
| Banco unificado | SQLite (WAL mode) | Zero servidor, transações atômicas, 25 anos de robustez |
| Busca vetorial | sqlite-vec | Mesmo arquivo, sem sincronização |
| Busca textual | FTS5 (built-in SQLite) | Zero dependências extras |
| Embedding padrão | nomic-embed-text via Ollama | Local, gratuito, dados não saem da máquina |
| Embedding alternativo | OpenAI text-embedding-3-small | Configurável no `.env` sem tocar código |
| Trigger do Comitê | Basecamp polling 15 min | Sem URL pública, sem servidor exposto |
| BVS Real | CLI manual + normalização | Proxy sell-through Onda 1 até metodologia BVS amadurecer |

---

## Instalação

```bash
# Pré-requisito: Ollama
ollama pull nomic-embed-text

# Ambiente
cd projetos/memoria-viva
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Configuração e inicialização
cp .env.example .env
memoria-viva init
```

Ver **[INSTALL.md](INSTALL.md)** para o guia completo com troubleshooting.

---

## Comandos

```bash
memoria-viva status                             # Estado atual da memória
memoria-viva memory-read "sérum de transição"  # Simula o Memory Read
memoria-viva search "transição capilar"         # Busca semântica + keyword
memoria-viva briefings                          # Lista briefings registrados
memoria-viva flush <id> GO -r "ativo validado"  # Committee Flush manual
memoria-viva bvs-real <id> 85.0                # Insere sell-through Onda 1
```

---

## Documentação técnica

| Documento | Conteúdo |
|---|---|
| [docs/PRD.md](docs/PRD.md) | Problema, objetivos e métricas de sucesso |
| [docs/ARQUITETURA.md](docs/ARQUITETURA.md) | Os 4 momentos, schema SQL, MIP |
| [docs/ADRs.md](docs/ADRs.md) | 7 decisões de arquitetura com motivos e trade-offs |
| [docs/GLOSSARIO.md](docs/GLOSSARIO.md) | IAM, BVS, RICE, ICB, HNR, MIP e outros termos |
| [ROADMAP.md](ROADMAP.md) | 4 estágios: Amnésica → Episódica → Semântica → Estratégica |

---

## Estágio atual

```
Estágio 1 — Amnésica     [concluído — era o estado anterior]
Estágio 2 — Episódica    [MVP IMPLEMENTADO]
  ✓ Schema Hot + Warm Store unificado
  ✓ Memory Read com budget de tokens
  ✓ Post-briefing Flush (atômico)
  ✓ Committee Flush com calibração Bayesiana
  ✓ CLI completo
  ✗ Integração com LangGraph (próximo passo)
  ✗ Preenchimento do BRAND_MEMORY.md com dados reais

Estágio 3 — Semântica    [roadmap: ~3 meses]
Estágio 4 — Estratégica  [roadmap: 6+ meses]
```

---

*Parte do sistema multi-agente de briefing de produto Novex/Embelleze.*
*Planejado e implementado em Março/2026 com Claude Code.*
