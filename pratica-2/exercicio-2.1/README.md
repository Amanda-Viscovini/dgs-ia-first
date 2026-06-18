# Evidências — Exercício do DESENVOLVEDOR (Fase de Estruturação)

> **Exercício implementado:** *Configuração e uso real de MCP servers no projeto* — o **primeiro exercício do papel DESENVOLVEDOR** no documento `exercicio-2-fase-estruturacao.md` (rotulado lá como **Exercício 2.1**).
>
> O pedido foi "exercício 1.1 do DESENVOLVEDOR". O documento de fase de estruturação numera os exercícios do desenvolvedor como 2.1, 2.2 e 2.3 (não existe um "1.1" literal). A leitura adotada é a mais coerente com o material: **1.1 = primeiro exercício do desenvolvedor**, o que também casa com as três pastas locais `exercicio-1.1`, `exercicio-1.2` e `exercicio-1.3` (uma por exercício do papel). Se a intenção era outro exercício, é só avisar.

## Como esta entrega foi produzida

As evidências de execução (leitura de documento, recuperação de chunk, leitura do histórico Git) foram geradas **de fato**, usando os próprios MCP servers durante a sessão de análise:

- `filesystem` MCP → leitura real de `docs/novatech/SLA-2024-tabela-sla-clientes.md` e do corpus `data/retrieval-corpus/chunks-novatech.md`.
- `git` MCP → leitura real do histórico (`git_log`) e das branches (`git_branch`) do repositório local do starter (Anexo D).

Os arquivos `.md` desta pasta foram entregues para download porque, no momento da gravação, as *ferramentas de escrita* do filesystem MCP da máquina estavam sem resposta (timeout). As de leitura funcionaram normalmente — por isso as evidências de leitura são reais.

## O que o exercício pedia (4 tarefas)

1. Mapear cada necessidade do projeto para um *reference server* MCP gratuito e local (filesystem, git, memory, everything): o que expõe (tools/resources/prompts), quem consome, qual escopo recebe.
2. Escrever o `.mcp/mcp.json` aplicando **least privilege** concreto (filesystem com escopo mínimo; `docs/novatech/` e `data/retrieval-corpus/` como read-only) e justificar cada escopo.
3. **Subir os servers e comprovar uso**, com evidência de o agente (a) ler um documento de `docs/novatech/`, (b) recuperar um chunk relevante de `data/retrieval-corpus/` usando o mapa de cobertura do Anexo B como gabarito, e (c) ler o histórico do repo via `git`.
4. Identificar ≥2 riscos de segurança no uso de MCP **neste contexto local** e propor mitigações.

## Índice dos arquivos desta entrega

| Arquivo | Conteúdo | Tarefa |
|---|---|---|
| `01-mapeamento-mcp-servers.md` | Mapeamento necessidade → server (tools/resources/prompts, consumidor, escopo) | 1 |
| `02-least-privilege-e-config.md` | Justificativa de least privilege por server/escopo + explicação da config | 2 |
| `mcp.json` | Configuração final pronta para copiar em `.mcp/mcp.json` (variante npx) | 2 |
| `mcp.docker-readonly.json` | Variante recomendada com read-only **determinístico** via Docker | 2 |
| `03-evidencia-execucao-mcp.md` | Evidência real de execução (leitura de doc, recuperação de chunk, leitura do git) | 3 |
| `04-analise-de-riscos.md` | Riscos de segurança do setup local + mitigações | 4 |

## Resumo executivo

- **Servers usados:** `filesystem` (código/specs/skills/prompts/adr — leitura e escrita), `filesystem-novatech-docs` (documentação de negócio e corpus — somente leitura, isolado), `git` (histórico/branches/diff), `memory` (glossário e decisões persistentes), `everything` (aprendizado das primitivas). Todos locais e gratuitos.
- **Descoberta técnica relevante:** no reference server `@modelcontextprotocol/server-filesystem` rodado via **npx**, *todo* diretório passado como argumento é read-write — não há flag de read-only por argumento de linha de comando. O read-only de verdade exige rodar via **Docker** com `--mount ...,ro` (ou um wrapper/sandbox). Por isso a entrega isola as fontes de negócio em um server separado (variante npx) **e** fornece a variante Docker com `ro` para garantir read-only determinístico.
- **Evidência real:** as três comprovações exigidas foram produzidas nesta sessão usando os próprios MCP servers (filesystem + git) — ver `03-evidencia-execucao-mcp.md`.
