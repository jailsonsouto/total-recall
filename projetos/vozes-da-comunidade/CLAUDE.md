# Vozes da Comunidade — Contexto do Projeto

## O que é
Vozes da Comunidade do sistema multi-agente de briefing de produto Novex/Embelleze.
Extrai inteligência da voz real da consumidora (TikTok) usando ABSA/ASTE e netnografia.

## Ativos cedidos pelo TCC
O TCC MBA DSA USP/ESALQ (Jailson de Castro de Souto) é um projeto independente que cedeu ativos para este projeto. São atividades distintas.

Ativos recebidos — localização:
`/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/COLETA-COMENTARIOS-TIKTOK/PROCESSAMENTO-COLETA/kimi/`

Ao trabalhar neste projeto, **não duplicar** lógica do `dinamica_absa` — importar como dependência.

## Motor analítico (dinamica_absa)
- Encoder: BERTimbau (neuralmind/bert-base-portuguese-cased)
- Pipeline: 4 camadas (encoding → extraction → classification → adaptation)
- Schema de entrada: MODELO_JSON_EXPLORATORIO_TCC_V1.json
- Codebook: Codebook V3 (10 categorias de aspecto + extensões para briefing)

## Corpus de dados
- 4.802 comentários TikTok coletados (JSON, schema V1)
- Marcas: Novex, Elseve, Embelleze, Amend, Haskell
- Categorias: máscaras de reconstrução, reposição de massa, cronograma capilar
- Localização: `.../kimi/package/user_input_files/`

## Indicadores que o agente produz
- PN (Prioridade Negativa): dores mais citadas por segmento
- AP (Alavancagem Positiva): atributos que convertem
- Controvérsia: aspectos divisórios (alerta para Comitê)
- Crescimento: tendências emergentes no corpus

## Segmentação HNR
Cacheadas, Enroladas, Henêgatas — via campos `netnography.native_terms` e `cultural_markers` do schema V1.

## Integração com o sistema
- Agente 8 (Memória Viva): persiste padrões por (categoria, segmento) no Warm Store
- Agente 6 (Briefing Writer): recebe seção "INTELIGÊNCIA DE CONSUMIDOR"
- LangGraph: nó do grafo que roda entre Agente 3 e Agente 5 (pendente)

## Documentos deste projeto
- `docs/PRD.md` — Problema, objetivos, métricas
- `docs/ARQUITETURA.md` — Pipeline completo, schemas, integração
- `docs/ADRs.md` — 5 decisões de arquitetura
- `ROADMAP.md` — 4 estágios alinhados com o TCC

## Gargalo atual
As 500 anotações ASTE com o Codebook V3 são o pré-requisito para o fine-tuning do BERTimbau.
Sem elas, usa-se Claude Haiku como fallback de extração (zero-shot, qualidade inferior).
