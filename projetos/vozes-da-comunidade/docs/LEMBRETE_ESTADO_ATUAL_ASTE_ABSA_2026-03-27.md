# Lembrete do Estado Atual — ASTE/ABSA

**Data:** `2026-03-27`

## Estado consolidado

- O projeto saiu da fase de diagnostico solto e agora tem dois caminhos arquiteturais formalizados em spec-driven development.
- O caminho `BERTimbau + LLM professora` foi consolidado como opcao principal de medio prazo para span extraction em PT-BR.
- O caminho `LLM open/local fine-tuned com Unsloth + Hugging Face` foi consolidado como opcao alternativa de baixo custo local e maior flexibilidade.
- A recomendacao metodologica continua sendo:
  - `gold` humano pequeno e blindado
  - `silver` gerado por professora forte
  - modelo de producao barato e versionado

## Artefatos criados nesta conversa

- `docs/SPEC_CICLO_3A_BERTIMBAU_LLM_PROFESSORA.md`
- `docs/SPEC_CICLO_3B_LLM_LOCAL_UNSLOTH_HF.md`

## Interpretacao atual

- **Cenario 3A**: melhor para construir ativo proprietario, reduzir dependencia de API e melhorar spans.
- **Cenario 3B**: melhor para experimentar flexibilidade generativa local e instruction tuning com menos atrito.
- Os dois cenarios nao devem ser implementados no mesmo branch sem separar claramente dataset, benchmark e conclusao.

## Proximo assunto interrompido

Antes de escolher entre `3A` e `3B`, o usuario quer testar outros modelos SLM/professores.

Foco imediato:

- comparar economicamente `sabiazinho-4` e `sabia-4` da Maritaca com `Claude Haiku`
- usar o mesmo perfil de carga do benchmark atual para estimativa
- depois decidir se vale colocar Maritaca na rodada de benchmark como professora ou benchmark local-brasileiro

## Hipotese operacional vigente

- para rotulacao inicial, uma professora forte por API ainda parece a forma mais rapida de ganhar qualidade
- para producao, o alvo continua sendo um modelo local ou fine-tuned com custo baixo

## Observacao importante

Este lembrete existe para retomar a conversa rapidamente sem reabrir toda a trilha de raciocinio.
