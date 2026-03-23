# Agentes IA — Novex/Embelleze

Este repositório contém os agentes de IA desenvolvidos para o processo de briefing de produto da **Novex/Embelleze**, uma das maiores empresas de cosméticos capilares do Brasil.

O objetivo não é automatizar o trabalho de gestores de marca — é amplificar o que eles já fazem bem. Cada agente foi desenhado para absorver uma parte do esforço analítico que hoje consome horas antes de qualquer decisão criativa acontecer.

---

## O sistema

O coração do repositório é um **sistema multi-agente de briefing de produto**: 8 agentes especializados que operam em paralelo ou em sequência para transformar uma ideia de produto em um briefing completo, rastreável e calibrado pela metodologia de branding da consultoria Ana Couto.

Um PM submete uma ideia — *"sérum de transição capilar com ativo de quinoa"* — e o sistema entrega em ~90 segundos um briefing com análise de alinhamento de marca, BVS preditivo, RICE score, análise de sentimento de consumidor por segmento, e índice de coerência. O que levaria um dia de trabalho analítico.

### Os 8 agentes

| # | Agente | O que faz |
|---|---|---|
| 1 | Alinhamento de Marca | Avalia a ideia contra o Código Genético da marca (IAM) |
| 2 | BVS Preditivo | Prevê o Branding Value Score antes do lançamento |
| 3 | Análise Competitiva | Posicionamento em relação ao mercado |
| **4** | **Inteligência de Consumidor** | **ABSA/ASTE em comentários TikTok reais + netnografia HNR. Ver abaixo.** |
| 5 | Priorização | RICE score por Onda de Valor |
| 6 | Briefing Writer | Gera o documento final |
| 7 | Coerência | Audita consistência interna do briefing (ICB) |
| **8** | **Memória Viva** | **Faz o sistema aprender. Ver abaixo.** |

---

## Projetos neste repositório

### [`projetos/agente-4/`](projetos/agente-4/)

O Agente 4. A camada de escuta — extrai inteligência da voz real da consumidora antes de qualquer briefing ser escrito.

Motor analítico baseado em BERTimbau fine-tuned para PT-BR informal, com extração de triplas ASTE `(aspecto, opinião, polaridade)` de 4.802+ comentários reais do TikTok. Segmenta por comunidade HNR (cacheadas, enroladas, henêgatas) e entrega indicadores acionáveis: PN (Prioridade Negativa), AP (Alavancagem Positiva), Controvérsia e Crescimento.

O motor analítico é desenvolvido no contexto do TCC MBA DSA USP/ESALQ — *"Da Netnografia ao ABSA/ASTE: escuta 360° da consumidora no TikTok em marcas de cosméticos"*. O TCC é a Fase 1 do Agente 4.

**Planejamento completo. Fase 1 (motor ASTE/TCC) em andamento.**

### [`projetos/memoria-viva/`](projetos/memoria-viva/)

O Agente 8. A camada de inteligência que transforma um sistema sofisticado-mas-amnésico em um sistema que efetivamente aprende com cada briefing processado, cada rejeição do Comitê, cada dado de venda que retorna meses depois.

**MVP implementado. Pronto para integração com os demais agentes.**

---

## Estrutura

```
agentes/
├── projetos/
│   ├── agente-4/        ← Agente 4 (Consumer Intelligence) — planejamento completo
│   └── memoria-viva/    ← Agente 8 (Memory Manager) — MVP pronto
├── notas/               ← Sessões de planejamento e decisões de arquitetura
└── templates/           ← Templates reutilizáveis (roadmap)
```

---

*Desenvolvido com Claude Code. MacBook M1 (casa) + Windows 11 (trabalho), sincronizado via OneDrive.*
