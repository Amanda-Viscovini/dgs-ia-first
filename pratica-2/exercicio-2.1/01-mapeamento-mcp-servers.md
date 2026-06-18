# 01 — Mapeamento: necessidades do projeto → MCP servers (locais e gratuitos)

Cada necessidade do projeto NovaTech Assistant foi mapeada para um *reference server* mantido pelo protocolo MCP, executado **localmente** via `npx`/`uvx`, **sem nenhum serviço pago ou externo**. Para cada server: o que expõe (Tools / Resources / Prompts), quem consome e qual escopo recebe.

## Tabela-resumo

| # | Necessidade do projeto | Server | O que expõe | Quem consome | Escopo concedido |
|---|---|---|---|---|---|
| 1 | Ler/editar código, specs, skills, prompts e ADRs | `filesystem` | **Tools** de leitura e escrita (read_file, write_file, edit_file, list_directory, search_files, move_file, create_directory) | Dev (via Copilot/Claude Code), Tech Lead | `./src`, `./specs`, `./skills`, `./prompts`, `./docs/adr` (read-write) |
| 2 | Ler documentação de negócio da NovaTech (era Confluence) | `filesystem-novatech-docs` | **Tools** de leitura (read_file, list_directory, search_files) — escrita não deve ser usada | Todos os agentes (contexto de domínio) | `./docs/novatech` (**read-only**) |
| 3 | "Recuperar" chunks do corpus de RAG (era Azure AI Search) | `filesystem-novatech-docs` | **Tools** de leitura sobre o corpus | Agentes em tarefas de retrieval/teste | `./data/retrieval-corpus` (**read-only**) |
| 4 | Histórico, diff e branches do repositório (era GitHub) | `git` | **Tools** git_log, git_diff, git_branch, git_show, git_status (consulta) | Dev, Tech Lead (revisão simulada de PR local) | repositório local `.` |
| 5 | Glossário/linguagem ubíqua e decisões persistentes do projeto | `memory` | **Tools** de grafo de conhecimento (create_entities, create_relations, add_observations, search_nodes, read_graph) | Todos os agentes (memória entre sessões) | grafo local persistente |
| 6 | Aprender/explorar as primitivas de MCP (Tools/Resources/Prompts) | `everything` | **Tools**, **Resources** e **Prompts** de demonstração | Time (aprendizado), não usado em produção | — (sandbox de aprendizado) |

## Detalhamento por server

### 1. `filesystem` (read-write) — código e artefatos do time
- **Por que existe:** é o canal pelo qual os agentes leem e escrevem o que o time efetivamente produz nesta fase — código TypeScript, specs SDD (`requirements/plan/tasks`), skills, system prompts versionados e ADRs.
- **Tools expostas:** leitura (`read_file`, `read_multiple_files`, `list_directory`, `directory_tree`, `search_files`, `get_file_info`) e escrita (`write_file`, `edit_file`, `create_directory`, `move_file`).
- **Resources/Prompts:** o server-filesystem expõe primariamente Tools; não publica Prompts. Diretórios permitidos são consultáveis via `list_allowed_directories`.
- **Consumidor:** Dev (geração de código com Copilot/Claude Code) e Tech Lead.
- **Escopo:** apenas as pastas que o time edita nesta fase. **Não** recebe `./docs` inteiro (para não dar escrita em `docs/novatech`), nem `./data`, nem a raiz do repo (evita expor `.env`, `.git`, `node_modules`).

### 2 + 3. `filesystem-novatech-docs` (read-only) — fontes de negócio e corpus
- **Por que existe (isolado do #1):** as fontes de negócio (`docs/novatech/`) e o corpus de retrieval (`data/retrieval-corpus/`) são **insumo de leitura**, não artefatos editáveis pelos agentes. Isolar num server dedicado deixa explícita a intenção de read-only e reduz a superfície de escrita acidental.
- **Tools que devem ser usadas:** somente leitura (`read_file`, `list_directory`, `search_files`).
- **Consumidor:** qualquer agente que precise de contexto de domínio (responder/validar) ou simular retrieval.
- **Escopo:** exatamente as duas pastas de insumo. Ver `02-least-privilege-e-config.md` para como tornar o read-only **determinístico** (Docker `,ro`), já que o npx por si só não impõe read-only.

### 4. `git` (consulta) — histórico do repositório
- **Por que existe:** substitui o GitHub do cenário original. Permite ao agente entender histórico, comparar versões e descrever PRs locais (a "revisão de PR" desta fase é simulada localmente, conforme decisão do Tech Lead).
- **Tools expostas:** `git_log`, `git_diff` (staged/unstaged), `git_branch`, `git_show`, `git_status`. Operações de escrita do git (commit, etc.) ficam sob gate humano.
- **Consumidor:** Dev e Tech Lead.
- **Escopo:** o repositório local (`.`).

### 5. `memory` — glossário e decisões persistentes
- **Por que existe:** dá aos agentes uma memória entre sessões para a **linguagem ubíqua** (ex.: "carga perigosa" = classes 1–6 da ANTT; tiers = só Gold/Silver/Standard) e decisões duráveis (ADRs). Sem isso, cada sessão recomeça do zero e os outputs viram genéricos.
- **Tools expostas:** `create_entities`, `create_relations`, `add_observations`, `search_nodes`, `open_nodes`, `read_graph`, e as de remoção.
- **Consumidor:** todos os agentes.
- **Escopo:** grafo local persistente (arquivo no projeto/usuário).

### 6. `everything` — aprendizado das primitivas
- **Por que existe:** server de referência que demonstra Tools, Resources e Prompts. Serve para o time entender o protocolo. **Não** participa de fluxos de produção.
- **Escopo:** nenhum dado sensível; sandbox de aprendizado.

## Observações de conformidade
- Todos os servers são *reference servers* gratuitos e locais (`npx @modelcontextprotocol/server-...`, `uvx mcp-server-git`). Nenhum serviço pago/externo.
- O server de GitHub do upstream foi arquivado e exigiria conta/token externos; por isso o repositório é tratado localmente via `filesystem` + `git`, conforme orientação do Anexo C/D.
- Os nomes de pacote/comando devem ser confirmados no README oficial de `modelcontextprotocol/servers` antes de subir (a lista evolui) — confirmação feita nesta entrega para o `filesystem` (ver tarefa 2).
