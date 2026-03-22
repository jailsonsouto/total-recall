# Glossário — Memória Viva & Sistema Multi-Agente Novex/Embelleze

## Termos do Domínio de Produto

| Termo | Definição |
|---|---|
| **HNR** | Hidratação → Nutrição → Reconstrução — ciclo de necessidades capilares da linha Novex |
| **IAM** | Índice de Alinhamento de Marca — score 0-100 calculado pelo Agente 1 |
| **BVS** | Branding Value Score — métrica Ana Couto adaptada do NPS |
| **BVS Preditivo** | BVS estimado pelo Agente 2 antes do lançamento |
| **BVS Real** | BVS medido após lançamento (preenchido ~6 meses depois) |
| **ICB** | Índice de Coerência de Briefing — score 0-100 calculado pelo Agente 7 |
| **RICE** | Reach × Impact × Confidence ÷ Effort — framework de priorização |
| **ABSA** | Aspect-Based Sentiment Analysis — análise de sentimento por aspecto (Agente 4) |
| **Código Genético** | Núcleo identitário da organização (metodologia Ana Couto) |
| **DE_PARA** | Plano estratégico de mudança em 3 eixos |
| **Valometry** | Ferramenta de gestão contínua de branding da Ana Couto |
| **Ondas de Valor** | 3 ondas progressivas: Produto → Pessoas → Propósito |
| **Decodificador de Valor** | Impulsionadores / Detratores / Aceleradores |
| **É, FAZ e FALA** | Framework central da metodologia Ana Couto |

## Termos Técnicos da Memória Viva

| Termo | Definição |
|---|---|
| **Hot Store** | Camada SQLite da Memória Viva — estado ativo de briefings em execução |
| **Warm Store** | Camada ChromaDB — memória semântica buscável por embeddings |
| **Cold Store** | Camada Filesystem/Markdown — histórico legível por humanos, versionado em Git |
| **Post-briefing Flush** | Escrita de memória pós-execução; análogo ao pre-compaction flush do OpenClaw |
| **Committee Memory Flush** | Escrita de memória após decisão do Comitê — nunca pode falhar; usa WAL mode |
| **MIP** | Memory Integration Protocol — interface que novos agentes implementam para se conectar ao Agente 8 sem refatoração |
| **WAL** | Write-Ahead Logging — modo SQLite que garante durabilidade em crash |
| **Memory Aging** | Soft-trim de insights > 90 dias; hard-clear > 1 ano |
| **Calibração Bayesiana** | Atualização automática do BVS Preditivo após 5+ decisões do Comitê com dados reais |
| **TD Learning** | Temporal Difference Learning — método de RL leve usado no Estágio 4 para calibração com dados de venda |
| **Context Budget** | Limite de 4.000 tokens para contexto injetado pré-execução; garante latência < 2s |
| **Staleness Flag** | Sinalização de que um insight tem > 90 dias e deve ser reanalisado |

## Referências de Projetos de Memória

| Projeto | Relevância |
|---|---|
| **OpenClaw** | Referência principal — padrões de workspace files, pre-compaction flush, session pruning |
| **Nano-claw** | Referência de design minimalista (stateless por escolha) — o oposto do que queremos |
| **LangGraph SqliteSaver** | Implementação de checkpoints de estado por nó no LangGraph |
| **ChromaDB** | Banco de vetores local usado no Warm Store |
| **Pinecone** | Destino de migração do ChromaDB em produção (ADR-001) |
