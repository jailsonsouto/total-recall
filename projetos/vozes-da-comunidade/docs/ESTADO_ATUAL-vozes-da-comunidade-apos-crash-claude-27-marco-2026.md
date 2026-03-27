# ESTADO_ATUAL — vozes-da-comunidade
> Leia este arquivo ANTES de qualquer ação no projeto.
> Gerado em: 2026-03-27 após crash de sessão por overload da API Anthropic (529).

---

## Contexto da crise

A sessão anterior tentou rodar o corpus completo **sabiazinho-4 (891 comentários)** via `run_in_background`. O job extraiu todos os 891 itens, mas falhou na hora de salvar — porque o objeto `GateDecision` foi instanciado com um atributo incorreto (`d.gate_class` em vez do atributo correto). Todo o trabalho de extração foi perdido porque não havia save incremental. A sessão então travou por overload da API Anthropic (HTTP 529) e precisou ser abandonada.

---

## Problemas em aberto — NÃO resolvidos

### PROBLEMA 1 — `gate.py` não existe como fonte
- **O que aconteceu:** Existe apenas o arquivo compilado `.pyc`. O fonte `.py` foi perdido ou nunca foi salvo no projeto.
- **Risco:** Uma nova sessão vai olhar o diretório, não vai encontrar o `.py`, e pode tentar reescrever do zero — possivelmente errado.
- **O que fazer:** Descompilar o `.pyc` para recriar o `gate.py`. Usar `uncompyle6` ou `decompile3` para isso.
  ```bash
  pip install uncompyle6
  uncompyle6 vozes_da_comunidade/batch/gate.cpython-*.pyc > vozes_da_comunidade/batch/gate.py
  ```
  Inspecionar o resultado e corrigir manualmente se necessário.

---

### PROBLEMA 2 — Script de corpus em `/tmp/`
- **O que aconteceu:** O script de execução do corpus foi salvo em `/tmp/` durante a sessão.
- **Risco:** `/tmp/` é limpo a cada reboot. O script já pode ter sumido.
- **O que fazer:** Recriar o script e salvá-lo dentro do projeto:
  ```
  vozes_da_comunidade/scripts/run_corpus_sabiazinho4.py
  ```

---

### PROBLEMA 3 — Bug `d.gate_class` não corrigido
- **O que aconteceu:** O script de corpus usava `d.gate_class` para acessar o resultado de `GateDecision`, mas esse atributo não existe. O atributo correto é `classification` (ou similar — confirmar inspecionando `gate.py` após recriar).
- **Onde está o erro:** Na seção de agregação/salvamento do script de corpus, não na extração. Por isso o smoke test (n=50) não pegou — ele só exercitou a extração.
- **O que fazer:** Após recriar `gate.py`, verificar a assinatura exata de `GateDecision`:
  ```python
  # Inspecionar o .pyc antes de descompilar:
  python3 -c "
  from vozes_da_comunidade.batch.gate import GateDecision
  import inspect
  print(inspect.signature(GateDecision.__init__))
  "
  ```
  Corrigir o script para usar o atributo correto.

---

### PROBLEMA 4 — Sem save incremental
- **O que aconteceu:** O job rodou 891 extrações sem salvar nenhum resultado parcial. Quando o salvamento final falhou, tudo foi perdido.
- **Padrão correto a implementar:**
  ```python
  if (i + 1) % 100 == 0:
      Path("data/partial_sabiazinho4.json").write_text(
          json.dumps(results, ensure_ascii=False, indent=2)
      )
  ```
- **Regra:** Salvar a cada 100 iterações. O save final pode ter bugs de agregação — isso não deve apagar o trabalho de extração já feito.

---

## Sequência de execução recomendada

Execute nesta ordem. Não pule etapas.

**FASE 1 — Restaurar o código**
1. [ ] Abrir sessão Claude Code na pasta do projeto
2. [ ] Descompilar `gate.pyc` → `gate.py`
3. [ ] Inspecionar e validar a assinatura de `GateDecision`
4. [ ] Recriar o script de corpus em `vozes_da_comunidade/scripts/run_corpus_sabiazinho4.py`
5. [ ] Corrigir o bug `d.gate_class` no script

**FASE 2 — Adicionar save incremental**
6. [ ] Adicionar save parcial a cada 100 iterações no script
7. [ ] Validar com smoke test `n=10` antes de qualquer run real

**FASE 3 — Rodar o corpus**
8. [ ] Rodar com `n=50` (smoke test completo, incluindo agregação e save)
9. [ ] Confirmar que o arquivo de saída foi gerado corretamente
10. [ ] Rodar corpus completo (891 comentários)

---

## Aprendizados documentados na sessão anterior (APRENDIZADOS.md)

Entradas 18–21 já registradas:
- **18:** Nunca aprovar job caro sem validar todos os caminhos, inclusive agregação e save
- **19:** `.pyc` sem `.py` funciona mas é armadilha — recriar o fonte antes de confiar
- **20:** Falha tardia sem save incremental = perda total — salvar a cada N iterações
- **21:** `run_in_background` + `sleep` + `tail` é frágil para jobs longos

---

## Localização do projeto

```
/Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/vozes-da-comunidade
```

## Para iniciar nova sessão

```bash
cd /Users/criacao/Library/CloudStorage/OneDrive-Embelleze/MEUS-PROJETOS-IA/AGENTES/CLAUDE/projetos/vozes-da-comunidade
claude
```

Primeira instrução para a nova sessão:
> "Leia o ESTADO_ATUAL.md e execute a FASE 1 da sequência. Não faça nada antes de ler."
