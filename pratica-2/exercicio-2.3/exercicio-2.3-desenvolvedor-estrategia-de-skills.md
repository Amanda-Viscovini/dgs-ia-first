# Exercício 2.3 — DESENVOLVEDOR
# Estratégia de Skills do Projeto NovaTech Assistant

> **Papel:** Desenvolvedor (Sênior)
> **Ferramentas usadas:** Claude (chat) para desenho da estratégia e redação do SKILL.md; GitHub Copilot para teste/refino do SKILL.md no repositório.
> **Referência de estrutura:** Anexo C — as skills vivem em `/skills/foundation/`, `/skills/domain/` e `/skills/artifact/`, um arquivo `.md` por skill, nome do arquivo = slug da skill.

---

## 1. Árvore de skills do projeto

A hierarquia segue **Foundation → Domain → Artifact**, exatamente como já reservado na árvore do repositório (Anexo C). A leitura é em cascata: uma skill de **Artifact** lê as **Domain** das quais depende, e toda **Domain** assume as **Foundation** como base. Nenhuma skill repete o que outra acima já define.

```
skills/
├── foundation/                         # Convenções globais — valem para TODO artefato gerado
│   ├── typescript-conventions.md       # ★ base de todas as outras (TS strict, naming, imports, async, Zod)
│   ├── error-handling.md               # custom errors, logging com pino, retry/backoff
│   └── project-structure.md            # onde cada arquivo mora, módulos, exports, paths do Anexo C
│
├── domain/                             # Padrões por camada — herdam todas as Foundation
│   ├── azure-functions-endpoint.md     # padrão de HTTP trigger (Azure Functions v4)
│   ├── azure-ai-search-integration.md  # query/index no Azure AI Search, top-5 chunks, vigência
│   ├── react-components.md             # padrões de componente do painel web
│   └── testing-patterns.md             # Vitest, msw, fixtures, arrange/act/assert
│
└── artifact/                           # Receitas de geração ponta-a-ponta — herdam Foundation + Domain
    ├── create-rag-endpoint.md          # gera endpoint RAG completo (handler+validator+response-builder)
    ├── create-integration-test.md      # gera teste de integração de endpoint
    └── create-react-card.md            # gera card de resposta/feedback do painel web
```

### Por que esta árvore é coerente com o projeto
- Cada skill mapeia diretamente a um artefato que o time **produz repetidamente** (endpoints RAG, testes de integração, componentes React, docs técnicas).
- Não há skill órfã: toda Domain alimenta ao menos uma Artifact, e toda Artifact tem consumidor real (Copilot gerando código de produção).
- A árvore espelha 1:1 a estrutura já criada no Anexo C, então o agente encontra cada skill no caminho esperado sem ambiguidade.

### Candidatas futuras (não criadas agora — registradas para não virarem skills órfãs)
Estes artefatos também são recorrentes, mas hoje são cobertos por skills existentes ou por template/ADR fora de `/skills/`. Ficam como backlog explícito:
- `artifact/create-adr.md` — hoje coberto pelo `docs/adr/template.md`.
- `artifact/create-spec.md` — hoje coberto pelo fluxo SDD (`requirements/plan/tasks`) governado pelo PS/TL.
- `domain/prompt-engineering.md` — se a manutenção do `prompts/system-prompt.md` virar recorrente.

---

## 2. Mapeamento de criação e consumo

Legenda de frequência: **Alta** = uso em quase toda task de código; **Média** = por módulo/feature; **Baixa** = pontual/setup.

### Foundation

| Skill | Frase-ativação (o agente reconhece) | Cria | Consome (papéis) | Consome (agentes) | Frequência |
|---|---|---|---|---|---|
| `typescript-conventions` | "escrever/gerar qualquer arquivo `.ts`, definir tipos, validar input com Zod, nomear símbolos" | Dev Sênior + Tech Lead | Todos os devs | Copilot, Claude Code | **Alta** |
| `error-handling` | "tratar erro, lançar exceção, logar, fazer retry de chamada externa (Azure)" | Dev Sênior | Devs, QA (assertions de erro) | Copilot, Claude Code | **Alta** |
| `project-structure` | "criar arquivo novo, decidir em qual pasta mora, organizar imports/exports de módulo" | Tech Lead | Todos os devs | Copilot, Claude Code | **Média** |

### Domain

| Skill | Frase-ativação | Cria | Consome (papéis) | Consome (agentes) | Frequência |
|---|---|---|---|---|---|
| `azure-functions-endpoint` | "criar/alterar um endpoint Azure Functions v4 (HTTP trigger)" | Tech Lead | Devs | Copilot, Claude Code | **Média** |
| `azure-ai-search-integration` | "buscar chunks, consultar índice, recuperar top-5, lidar com vigência de documento" | Dev Sênior | Devs | Copilot | **Média** |
| `react-components` | "criar componente React do painel web (card, formulário, página)" | Dev (front) + Product Specialist (UX) | Devs front | Copilot, Claude Design | **Média** |
| `testing-patterns` | "escrever teste com Vitest, mockar HTTP, montar fixture" | QA | Devs, QA | Copilot | **Alta** |

### Artifact

| Skill | Frase-ativação | Cria | Consome (papéis) | Consome (agentes) | Frequência |
|---|---|---|---|---|---|
| `create-rag-endpoint` | "gerar um endpoint RAG novo seguindo o padrão do projeto" | Dev Sênior | Devs | Copilot, Claude Code | **Média** |
| `create-integration-test` | "gerar o teste de integração de um endpoint" | QA + Dev | Devs, QA | Copilot | **Média** |
| `create-react-card` | "gerar um card de resposta/feedback no painel" | Dev (front) | Devs front | Copilot, Claude Design | **Baixa/Média** |

### Visão de time (não é só para devs)
- **Tech Lead** é dono das skills que fixam decisão arquitetural (`project-structure`, `azure-functions-endpoint`) e co-autor das convenções base.
- **QA** é dono de `testing-patterns` e co-autor de `create-integration-test` — garante que código gerado por IA já nasça testável.
- **Product Specialist** participa de `react-components` e `create-react-card` (consistência de UX com o mockup do Teams) e, via Claude Design, consome essas skills.
- **Dev Sênior** é o curador da camada Foundation/Artifact técnica e o revisor final antes de uma skill ser marcada como madura.

### Manutenção (skills são artefatos vivos)
- Toda skill tem dono (coluna "Cria") responsável por atualizá-la quando uma ADR muda.
- Mudança em skill segue o mesmo fluxo de PR local do projeto (`docs/pull-requests/PR-NNNN.md`) e passa pelo Gate 3 (code review do Tech Lead).
- Skill nasce em estado **rascunho** e só vira **madura** após teste real com Copilot (output observado e ajustado pelo menos uma vez).

---

## 3. SKILL.md Foundation mais importante

A skill base de todas as outras é **`typescript-conventions`**: toda Domain e toda Artifact assume estas convenções como dadas. Por isso ela é a primeira a ser escrita e a única que nenhuma outra skill pode contradizer.

O arquivo completo está no entregável separado **`typescript-conventions.md`**, pronto para ser colocado em `skills/foundation/typescript-conventions.md`.

---

## 4. Evidência de uso das ferramentas

- **Claude (chat):** usado para desenhar a árvore, decidir a skill-base, montar o mapeamento de criação/consumo e redigir o `SKILL.md` Foundation (este conjunto de artefatos). 
