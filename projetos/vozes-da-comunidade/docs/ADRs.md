# Architecture Decision Records — Vozes da Comunidade

**Projeto:** Vozes da Comunidade
**Data:** Março/2026

---

## ADR-001: Reaproveitar `dinamica_absa` (TCC) como motor do Agente 4

**Status:** Aceito

**Contexto:**
Ao planejar o Agente 4, haviam duas opções: (A) construir um novo motor de extração ASTE do zero, otimizado para o contexto de briefing; (B) reaproveitar o framework `dinamica_absa` desenvolvido no TCC do MBA, adaptando-o.

**Decisão:**
Reaproveitar `dinamica_absa` como motor principal do Agente 4, sem duplicar código.

**Motivos:**

1. **O motor já existe e está correto.** O `dinamica_absa` implementa BERTimbau + 4 camadas (encoding, extraction, classification, adaptation) — exatamente a arquitetura correta para ASTE em PT-BR informal.

2. **O corpus e o codebook já existem.** 4.802 comentários coletados, Codebook V3 com 10+ categorias de aspecto, regras de ironia documentadas. Recomeçar do zero seria perder meses de trabalho.

3. **Evita divergência.** Se o Agente 4 tiver motor próprio e o TCC tiver outro, qualquer melhoria precisará ser aplicada nos dois lugares. Com um motor único, a evolução do TCC melhora automaticamente o Agente 4.

4. **O TCC é a Fase 1.** O dataset anotado que o TCC produz é o único caminho para fazer o fine-tuning do BERTimbau funcionar. Sem ele, não há Agente 4.

**Trade-offs:**
- O `dinamica_absa` usa PostgreSQL internamente (arquitetura bronze/prata/ouro). O sistema usa SQLite. Solução: o Agente 4 processa internamente em qualquer formato, mas exporta resultados no schema do Agente 8 (SQLite). A fronteira está clara.
- O TCC tem objetivos acadêmicos (publicação, métricas F1, ablações). O Agente 4 tem objetivos operacionais (velocidade, integração, output acionável). Esses objetivos não conflitam — o TCC entrega o modelo, o Agente 4 usa o modelo.

---

## ADR-002: BERTimbau fine-tuned vs Claude Haiku para extração ASTE

**Status:** Aceito

**Contexto:**
Para extrair triplas ASTE dos comentários, havia a opção de usar um modelo de linguagem grande (Claude Haiku via prompt) ou um modelo fine-tuned menor (BERTimbau).

**Decisão:**
BERTimbau fine-tuned para extração ASTE em batch (fase offline). Claude Haiku para síntese e formatação do output para o briefing (fase online).

**Motivos:**

1. **Volume.** O batch offline processa 4.802+ comentários por vez. Claude Haiku custaria ~$0.25/1M tokens × 4.802 comentários × ~200 tokens = ~$0.24 por batch — aceitável, mas evitável. BERTimbau rodando local no M1 custa zero.

2. **Latência em batch.** BERTimbau no M1 via MPS processa ~50-100 comentários/segundo. Uma API LLM com rate limit seria 10-50x mais lenta para o mesmo volume.

3. **Span extraction.** ASTE exige identificar spans exatos no texto (início/fim do aspecto e da opinião). Isso é uma tarefa de sequence labeling — o domínio natural de modelos BERT. LLMs fazem isso bem em prompts, mas sem a precisão de offsets que o Codebook V3 exige.

4. **Síntese é diferente de extração.** Claude Haiku é usado onde seu ponto forte brilha: tomar os padrões extraídos pelo BERTimbau e sintetizá-los em linguagem clara, contextual, para o PM. A tarefa de síntese não exige precisão de span — exige fluência e julgamento.

**Trade-offs:**
- BERTimbau fine-tuned requer dataset anotado (500 exemplos, TCC). Sem ele, o modelo não funciona. Claude Haiku zero-shot funcionaria imediatamente, mas com qualidade inferior em português informal e sem spans precisos.
- Durante a Fase 1 (antes do fine-tuning), usa-se Claude Haiku como fallback para extração. Quando o modelo estiver treinado, o Haiku volta a ser apenas síntese.

---

## ADR-003: Coleta TikTok via Chrome extension + scraper manual

**Status:** Aceito (com ressalva)

**Contexto:**
Para alimentar o corpus do Agente 4, precisamos de comentários de TikTok sobre cosméticos capilares. As opções eram: (A) API oficial do TikTok; (B) Chrome extension de coleta manual; (C) scraping automatizado.

**Decisão:**
Chrome extension + scraper manual (já implementado no TCC). Não construir pipeline automatizado de coleta por enquanto.

**Motivos:**

1. **Já existe e funciona.** O TCC já tem a infraestrutura de coleta e 4.802 comentários. Construir nova infraestrutura seria duplicar trabalho.

2. **TikTok API é instável.** A API oficial do TikTok para Research Access tem restrições significativas, mudanças frequentes de política, e não está disponível para uso comercial. Dependência de API é risco.

3. **Volume suficiente para MVP.** 4.802 comentários de múltiplos vídeos de diferentes marcas são suficientes para a Fase 2. A questão não é volume — é qualidade do fine-tuning.

4. **Privacidade por design.** O schema V1 já remove PII: `author_identity_strategy: "hash_only"`, sem persistência de `uniqueId`, `username` ou URLs pessoais. A coleta manual mantém esse controle.

**Ressalva:**
A coleta manual é um gargalo de escalabilidade. Para o Estágio 3 (cobertura de mais categorias e marcas), será necessário automatizar. Mas isso é trabalho futuro — não bloqueia o MVP.

**Regra de coleta:**
Apenas comentários de conteúdo orgânico público (`source_type: "organic_public_content"`). Não coletar de contas privadas ou conteúdo patrocinado sem divulgação.

---

## ADR-004: Segmentação HNR por campo `netnography` vs modelo dedicado

**Status:** Aceito

**Contexto:**
Para segmentar comentários por tipo de consumidora (cacheadas, enroladas, henêgatas), havia duas opções: (A) treinar um classificador dedicado de segmento; (B) usar os campos já preenchidos no schema V1 durante a coleta/triagem (`netnography.native_terms`, `cultural_markers`).

**Decisão:**
Usar os campos do schema V1 como fonte primária de segmentação HNR. Classificador dedicado é roadmap futuro.

**Motivos:**

1. **O schema V1 já captura isso.** O Codebook V3 instrui o anotador a preencher `native_terms` (ex: "método curly", "gel ativador") e `cultural_markers` (ex: "cacheada", "3c") durante a triagem. Esses sinais são mais confiáveis que inferência posterior.

2. **Vocabulário nativo é mais preciso que embeddings.** "Uso gel ativador no pós-banho" indica cacheada com mais precisão do que qualquer modelo de similaridade semântica. A comunidade tem um vocabulário altamente específico.

3. **Custo de treino de classificador.** Um classificador de segmento HNR precisa de exemplos anotados por segmento — que ainda não existem em quantidade. Usar o schema V1 permite começar a segmentar sem dados extras.

**Trade-offs:**
- Comentários onde `native_terms` está vazio (coletados antes do Codebook V3) não têm segmento definido. Esses comentários entram em "segmento indefinido" e são tratados com peso menor na análise.
- O modelo definitivo de segmentação será um classificador treinado no futuro, mas sem urgência para o MVP.

---

## ADR-005: Indicadores PN/AP em vez de score único de sentimento

**Status:** Aceito

**Contexto:**
Poderia-se entregar ao briefing apenas um score de sentimento agregado por categoria (ex: "sentimento 78% positivo"). A alternativa é decompor em múltiplos indicadores: PN, AP, Controvérsia, Crescimento.

**Decisão:**
Indicadores decompostos (PN, AP, Controvérsia, Crescimento) — alinhados com o framework do TCC.

**Motivos:**

1. **Score único é desinformativo.** "78% positivo" não diz ao PM o que fazer. "Aspecto X tem AP 0.84 — destaque no copy" e "Aspecto Y tem PN 0.91 — evitar na formulação" são acionáveis.

2. **Controvérsia é um sinal crítico.** Um produto com 50% positivo / 50% negativo em um aspecto tem score médio neutro. Mas é um risco enorme de backlash se aquele aspecto for usado como claim. Controvérsia expõe isso — score médio esconde.

3. **Crescimento informa timing.** Saber que um ingrediente está crescendo +30% no corpus dos últimos 3 meses é informação que o PM precisa para decidir se inclui no briefing agora ou espera.

4. **Alinhamento com o TCC.** Os indicadores PN/AP foram desenvolvidos e validados no contexto do TCC. Usar os mesmos indicadores nos dois projetos garante consistência metodológica e evita re-trabalho.

**Implementação:**
Os quatro indicadores são calculados na fase offline sobre o corpus completo, agregados por (categoria, segmento HNR, período trimestral), e persistidos no Warm Store da Memória Viva. A fase online apenas recupera e formata.
