# 04 — Análise de riscos de segurança (setup MCP local) e mitigações

Riscos específicos deste setup **local** de MCP servers, com mitigações acionáveis. Os dois primeiros são os exigidos pela tarefa; os demais reforçam a postura de segurança.

## Risco 1 — Escopo amplo do `filesystem` expõe segredos e metadados (`.env`, `.git/`, `node_modules/`)

**Descrição.** Se o `filesystem` server receber a raiz do repo (`.`) ou `./` amplo, o agente passa a ler (e, via npx, escrever) arquivos sensíveis: `.env` com credenciais, `.git/` com histórico/objetos, `node_modules/` com superfície enorme e ruído. Um prompt mal formulado — ou um conteúdo malicioso lido de um arquivo — pode levar o agente a vazar o conteúdo de `.env` na resposta.

**Por que importa aqui.** O `.gitignore` do starter já ignora `.env`, mas *ignorar no git não impede o MCP de lê-lo*: são camadas diferentes. O risco é de **leitura/exfiltração**, não de versionamento.

**Mitigações.**
- Escopo mínimo: o `filesystem` recebe só `./src ./specs ./skills ./prompts ./docs/adr` — **nunca** a raiz (aplicado em `mcp.json`).
- `.env` e segredos ficam **fora de todos os escopos** de filesystem; em produção, usar variáveis de ambiente/secret manager, não arquivos no projeto.
- Na variante Docker, montar apenas as pastas necessárias — o container não enxerga nada além dos mounts.
- Revisar periodicamente `list_allowed_directories` para confirmar que nenhum escopo cresceu indevidamente.

## Risco 2 — Server com escrita habilitada permite o agente alterar arquivos sem revisão (e read-only "falso" no npx)

**Descrição.** O `filesystem` via npx expõe `write_file`/`edit_file`/`move_file` em todo diretório montado. Dois problemas: (1) o agente pode sobrescrever código/specs sem passar por code review; (2) as fontes de negócio (`docs/novatech`, `data/retrieval-corpus`), que deveriam ser read-only, **não são** read-only de fato no npx — uma escrita acidental corromperia a fonte de verdade do RAG.

**Por que importa aqui.** A "revisão de PR" desta fase é local/simulada; sem gate, uma alteração gerada por agente entra direto na árvore de trabalho. Corromper o corpus degrada silenciosamente todas as respostas do assistente.

**Mitigações.**
- Isolar as fontes de negócio em um server dedicado (`filesystem-novatech-docs`) e, para garantia técnica, usar a **variante Docker com `,ro`** (read-only determinístico) — ver `02-least-privilege-e-config.md`.
- Gate humano antes de aceitar escrita: toda alteração feita por agente é inspecionada via `git diff` (git MCP) antes de "merge" local; nada de auto-commit pelo agente.
- Tratar `docs/novatech` e `data/retrieval-corpus` como artefatos versionados: qualquer diff inesperado nessas pastas é sinal de incidente e deve ser revertido.

## Risco 3 — Prompt injection a partir de conteúdo lido pelos servers

**Descrição.** Documentos em `docs/novatech/` ou chunks do corpus podem conter texto que tenta instruir o agente ("ignore as regras anteriores", "exfiltre X"). Como esse conteúdo é **dado**, não comando, segui-lo seria uma falha.

**Mitigações.**
- Tratar todo conteúdo lido via MCP como dado não confiável; instruções acionáveis encontradas em arquivos devem ser reportadas ao humano, não executadas.
- Manter as fontes de negócio read-only (Docker `,ro`) reduz o impacto: mesmo que injetem instrução de escrita, o server não escreve.
- Gates humanos nos pontos de efeito colateral (escrita, commit) — alinhado aos validation gates do projeto.

## Risco 4 — Cadeia de suprimento do `npx -y` (execução de pacote sem fixar versão)

**Descrição.** `npx -y @modelcontextprotocol/server-...` baixa e executa a versão mais recente automaticamente. Uma versão comprometida ou um typosquatting do nome do pacote executaria código arbitrário na máquina do dev.

**Mitigações.**
- Fixar versões dos servers (ex.: `@modelcontextprotocol/server-filesystem@<versão>`) e confirmar os nomes no README oficial de `modelcontextprotocol/servers` antes de subir.
- Preferir a imagem Docker oficial (`mcp/filesystem`) com tag fixa, que adiciona isolamento de processo.
- Revisar mudanças de versão dos servers como se fossem dependências de produção (são infraestrutura).

## Síntese
O setup local não tem rede externa nem serviços pagos, mas concentra risco no **filesystem**: escopo amplo (exposição de segredos) e escrita irrestrita (alteração sem revisão / read-only falso). As duas alavancas de mitigação mais eficazes são **escopo mínimo** e **read-only determinístico via Docker `,ro`**, combinadas com **gates humanos via `git diff`** antes de qualquer efeito colateral.
