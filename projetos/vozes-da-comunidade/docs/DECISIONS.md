# DECISIONS — Vozes da Comunidade

**Atualizado em:** 2026-03-27

## D-001

**Decisão:** usar `docs/` como memória operacional mínima em vez de criar `.specs/`.

**Motivo:** o projeto já tem documentação abundante em `docs/`; criar uma segunda raiz documental aumentaria dispersão.

## D-002

**Decisão:** separar uma camada curta de retomada dos documentos longos de análise, benchmark e post-mortem.

**Motivo:** os arquivos longos continuam úteis como evidência, mas são pesados demais para servir como porta de entrada da próxima sessão.

## D-003

**Decisão:** quando houver conflito entre documentação histórica e código atual, tratar o código atual como fonte primária e a documentação antiga como histórico.

**Motivo:** a árvore atual já contém `gate.py` e `scripts/run_corpus.py`, então nem todo bloqueio descrito no crash continua válido.

## D-004

**Decisão:** nenhum run com custo de API antes de um `--dry-run` ponta a ponta no ambiente Python escolhido.

**Motivo:** o crash de 2026-03-27 mostrou que smoke tests parciais não bastam; o fluxo inteiro precisa ser validado antes de gastar.

## D-005

**Decisão:** manter `3A` e `3B` como trilhas separadas até nova adjudicação explícita.

**Motivo:** benchmark, dataset e conclusão ficam mais auditáveis quando cada hipótese evolui sem mistura.

## D-006

**Decisão:** estes arquivos curtos devem guardar apenas fatos, riscos, decisões e próximo passo.

**Motivo:** memória mínima só funciona se não virar depósito de transcript, raciocínio bruto ou segredos.
