# Checklist operacional - Branch A e full run seguro no Sabiazinho

**Projeto:** Vozes da Comunidade  
**Objetivo:** evitar repeticao do fracasso operacional do run anterior e garantir evidencia utilizavel no corpus total

## 1. Pre-flight obrigatorio

- [ ] Confirmar que o `Router` do branch ja esta alinhado ao schema atual
- [ ] Confirmar que `reply_or_conversation` nao esta entrando no slice ASTE principal
- [ ] Confirmar que o `Gate` salva decisao por comentario
- [ ] Confirmar que existe `MARITACA_API_KEY` carregada de forma correta
- [ ] Confirmar que o modelo configurado e `sabiazinho-4`
- [ ] Confirmar que existe caminho de saida versionado para o run
- [ ] Confirmar que o runner suporta `resume`
- [ ] Confirmar que o runner faz save incremental antes de qualquer sumario final
- [ ] Confirmar que ja existe estimativa de custo antes do run

## 2. Dry-run obrigatorio

Antes do corpus total:

- [ ] rodar `n=20` ou `n=50`
- [ ] verificar JSON salvo
- [ ] verificar parse por comentario
- [ ] verificar tokens e custo
- [ ] verificar retry/backoff
- [ ] verificar se o processo retoma de checkpoint

Se o dry-run falhar, **nao** iniciar corpus total.

## 3. Regras de persistencia

O runner deve salvar:

- [ ] resultado por comentario assim que o comentario termina
- [ ] checkpoint de progresso a cada lote pequeno
- [ ] arquivo de erros separado
- [ ] sumario parcial periodico

Nunca depender apenas de um arquivo final unico.

## 4. Regras de idempotencia

Antes de enviar qualquer comentario para a API:

- [ ] verificar se `comment_id` ja existe no artefato parcial
- [ ] pular comentarios ja processados com sucesso
- [ ] preservar comentarios com erro para retry controlado

O runner nao pode reprocessar cegamente o corpus inteiro apos um crash.

## 5. Regras de seguranca de custo

- [ ] mostrar estimativa antes do start
- [ ] permitir `--limit`
- [ ] permitir `--resume`
- [ ] permitir abortar sem perder o que ja foi salvo
- [ ] registrar custo total ao final

## 6. Execucao do corpus total

So iniciar o full run quando:

- [ ] dry-run passou
- [ ] amostra intermediaria passou
- [ ] checkpoint foi validado
- [ ] saida parcial foi inspecionada manualmente

## 7. Pos-run obrigatorio

- [ ] salvar artefato final por comentario
- [ ] salvar sumario agregado
- [ ] salvar metadados do run: commit, modelo, data, dataset, parametros
- [ ] gerar relatorio curto do resultado
- [ ] verificar se o numero de comentarios processados bate com o esperado

## 8. Sinal de sucesso real

Este run so conta como sucesso se:

- nao houver perda total por falha tardia
- for possivel retomar apos interrupcao
- o corpus total produzir artefato auditavel
- o custo final ficar explicavel

## 9. Sinal de falha

O Branch A falha se acontecer qualquer um destes:

- reprocessamento cego de comentarios ja pagos
- dependencia de um unico save final
- falta de `resume`
- saida agregada sem detalhe por comentario
- novo desperdicio evitavel de chamadas na Maritaca

