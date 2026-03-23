# Status — Vozes da Comunidade — 23/03/2026

## O que foi feito hoje

### Contexto geral
Sessão longa (duas partes, contexto comprimido no meio). Objetivo: implementar o **Estágio 1 MVP** do pipeline batch + indicadores + CLI, seguindo o plano aprovado.

---

## Arquivos entregues

### Batch (fase offline)
| Arquivo | O que faz |
|---|---|
| `src/batch/router.py` | Filtra o corpus: aceita `product_opinion`, `comparison`, `technical_question` — descarta interações sociais, respostas de criador, comentários curtos/emoji |
| `src/batch/pipeline.py` | Orquestra a fase offline: lê JSONs da pasta → Router → Extractor ASTE → retorna `BatchResult` com contagens e triplas |
| `src/batch/__init__.py` | Export do módulo |

### Indicadores
| Arquivo | O que faz |
|---|---|
| `src/indicators/calculator.py` | Calcula PN (Prioridade Negativa), AP (Alavancagem Positiva), Controvérsia e Crescimento por (categoria × segmento). Retorna `ConsumerIntelligenceOutput` por segmento |
| `src/indicators/__init__.py` | Export do módulo |

### Persistência no Warm Store (Agente 8)
| Arquivo | O que faz |
|---|---|
| `src/memory/flush.py` | Persiste `ConsumerIntelligenceOutput` no Warm Store da Memória Viva (`collection="vozes_comunidade"`). Fallback automático: se Memória Viva não estiver disponível, salva JSON local em `data/vozes_cache/` |
| `src/memory/__init__.py` | Export do módulo |

### Síntese (fase online)
| Arquivo | O que faz |
|---|---|
| `src/synthesis/formatter.py` | Busca padrões no Warm Store (ou usa outputs diretos) → envia para Claude Haiku → retorna seção `## INTELIGÊNCIA DE CONSUMIDOR` formatada em markdown |
| `src/synthesis/__init__.py` | Export do módulo |

### CLI
| Arquivo | O que faz |
|---|---|
| `src/cli.py` | Typer CLI com 3 comandos: `vozes batch`, `vozes query`, `vozes status` |

### Configuração
| Arquivo | O que mudou |
|---|---|
| `src/config.py` | Adicionados: `MEMORIA_VIVA_PATH`, `ANTHROPIC_API_KEY`, `SYNTHESIS_MODEL` |
| `.env.example` | Atualizado com as novas variáveis |
| `pyproject.toml` | Criado — instala o pacote + entry point `vozes` no terminal |

---

## Como usar agora

```bash
# 1. Instalar o pacote (uma vez)
cd projetos/vozes-da-comunidade
pip install -e .

# 2. Copiar e preencher o .env
cp .env.example .env
# editar: ANTHROPIC_API_KEY e SLM_MODEL/OLLAMA_HOST

# 3. Rodar batch em amostra do corpus
vozes batch --input /caminho/para/corpus/ --sample 50 --verbose

# 4. Consultar (gera seção de briefing)
vozes query "máscara de reconstrução cacheadas"

# 5. Ver cobertura do Warm Store
vozes status
```

---

## Estado do pipeline (ponta a ponta)

```
Corpus JSON  →  Router  →  ASTEExtractor  →  IndicatorCalculator
                                                      ↓
                                              ConsumerIntelligenceOutput
                                                      ↓
                                            post_batch_flush (Warm Store)
                                                      ↓
                              vozes query → synthesize() → Claude Haiku
                                                      ↓
                                        ## INTELIGÊNCIA DE CONSUMIDOR
```

**Tudo implementado. Nada testado ainda com corpus real.**

---

## Próximos passos

### Imediato — teste real
1. Garantir que `ollama` está rodando com `qwen2.5:7b` (`ollama pull qwen2.5:7b`)
2. Rodar `vozes batch --input .../kimi/package/user_input_files/ --sample 50 --verbose`
3. Validar se as triplas extraídas fazem sentido (aspecto, opinião, polaridade)
4. Validar se os indicadores PN/AP são coerentes com o que você conhece do mercado

### Estágio 2 (quando o TCC avançar)
- Plug-in do BERTimbau fine-tuned: só configurar `ASTE_BACKEND=bertimbau` e `BERTIMBAU_MODEL_PATH`
- O restante do pipeline não muda

### Integração com briefings (Agente 6)
- A função `synthesize(query)` já está pronta
- O Agente 6 chama `synthesize()` passando o texto do briefing como query
- Recebe a seção formatada e injeta no documento

---

## Aprendizados registrados nesta sessão

Ver `APRENDIZADOS.md` — itens 8, 9, 10:
- Mapeamento do pacote `src/` → `vozes_da_comunidade` no pyproject.toml
- Erro de design `_raw_chunk_text` no dataclass (e solução: `list[str]` direto)
- Flush usa `vector_store.add()`, não `MemoryManager.post_briefing_flush()`

---

## Git

Commit: `3a7d833` — "Implementar Estágio 1 MVP: pipeline batch + indicadores + flush + CLI"
Branch: `main` — pushed para `origin`
