# 02 — Least privilege e configuração do `.mcp/mcp.json`

Objetivo: cada server enxerga **o mínimo suficiente** para sua função, e as fontes de negócio são tratadas como **somente leitura**. Abaixo, a justificativa de cada escopo e a explicação das duas variantes de configuração entregues.

## Princípio aplicado

> Conceder a cada server apenas as pastas necessárias para sua tarefa, e nenhuma a mais. Insumo de leitura nunca recebe permissão de escrita; segredos e metadados do repositório nunca entram no escopo.

A configuração do starter (`./src ./specs ./skills ./docs ./data` num único server read-write) **viola** esse princípio em dois pontos: (1) dá escrita sobre `docs/novatech` (fonte de negócio que não deve ser editada por agente) e (2) expõe `./data` e `./docs` inteiros de forma ampla. A entrega corrige isso.

## Justificativa por server/escopo

### `filesystem` (read-write) → `./src ./specs ./skills ./prompts ./docs/adr`
- **Mínimo suficiente porque** são exatamente os artefatos que o time produz e edita nesta fase: código (`src`), specs SDD (`specs`), skills (`skills`), system prompts versionados (`prompts`) e ADRs (`docs/adr`).
- **O que foi deliberadamente deixado de fora e por quê:**
  - `./` (raiz) — expõe `.env`, `.git/`, `node_modules/`, `package.json`. Escrita na raiz permitiria ao agente alterar dependências ou configs sem revisão.
  - `./docs` inteiro — incluiria `docs/novatech` (negócio) com escrita. Concedemos só `docs/adr`.
  - `./data` — corpus é insumo de leitura, não pertence ao server de escrita.

### `filesystem-novatech-docs` (read-only) → `./docs/novatech ./data/retrieval-corpus`
- **Mínimo suficiente porque** os agentes só precisam **ler** a documentação de negócio e **recuperar** chunks; nunca escrevê-los.
- **Read-only de verdade:** o reference `@modelcontextprotocol/server-filesystem` rodado via **npx** expõe tools de escrita em *qualquer* diretório passado — não existe flag `--read-only` por argumento de CLI. Consequências e mitigação:
  - **Variante npx (`mcp.json`):** o read-only é obtido por **isolamento de escopo** (server separado, sem código nem raiz) + **disciplina de uso** (não chamar tools de escrita neste server) + **detecção via `git`** (qualquer alteração nas fontes aparece no diff). É uma mitigação *organizacional*, não uma garantia técnica.
  - **Variante Docker (`mcp.docker-readonly.json`) — recomendada:** monta as fontes com `--mount type=bind,...,ro`, o que torna o read-only **determinístico**: o processo do server fisicamente não consegue escrever nessas pastas. Confirmado no README oficial do server-filesystem ("Adding the `ro` flag will make the directory readonly by the server").

### `git` (consulta) → repositório local `.`
- **Mínimo suficiente porque** precisa enxergar todo o repositório para histórico/diff/branches, mas expõe apenas **tools de consulta**. Commits e operações de escrita do git permanecem sob gate humano (não automatizados pelo agente nesta fase).

### `memory` → grafo local
- **Mínimo suficiente porque** opera sobre seu próprio grafo persistente; não recebe acesso ao filesystem do projeto.

### `everything` → sandbox
- **Sem escopo de dados.** Server de aprendizado das primitivas; isolado de qualquer pasta sensível.

## Qual variante usar

| Situação | Variante | Garantia de read-only |
|---|---|---|
| Setup rápido, só Node/npx disponível | `mcp.json` (npx) | Organizacional (isolamento + git diff) |
| Quer garantia técnica de read-only | `mcp.docker-readonly.json` (Docker) | Determinística (`,ro` no mount) |

Recomendação: **Docker `,ro`** sempre que o ambiente permitir, por ser a única forma que impede escrita nas fontes de negócio a nível de processo.

## Passos para aplicar
1. Copiar `mcp.json` (ou `mcp.docker-readonly.json`) para `.mcp/mcp.json` na raiz do repo `novatech-assistant`.
2. Na variante Docker, definir `${REPO}` para o caminho absoluto do repositório (no Windows, barras duplas) e construir/baixar a imagem `mcp/filesystem`.
3. Garantir que `.env` está no `.gitignore` (já está) e **fora** de todos os escopos de filesystem.
4. Subir o agente (Claude Code/Copilot) com os servers ativos e validar com os passos de `03-evidencia-execucao-mcp.md`.
