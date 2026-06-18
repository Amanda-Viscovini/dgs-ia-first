# 03 — Evidência de execução real dos MCP servers

Esta seção comprova as três capacidades exigidas pela tarefa 3, **executadas de fato** nesta sessão através dos MCP servers `filesystem` e `git` apontados para o starter repo (Anexo D). Os trechos abaixo são as saídas reais das chamadas de ferramenta.

Repositório-alvo observado pelos servers:
```
.../Anexo-D-starter-repo-novatech-assistant/novatech-assistant
```

---

## (a) Ler e listar um documento de `docs/novatech/` — via `filesystem` MCP

**Listagem de `docs/novatech/` (tool `list_directory`):**
```
[FILE] FAQ-atendimento.md
[FILE] POL-001-politica-devolucao.md
[FILE] PROC-042-frete-especial-v1.md
[FILE] PROC-042-v2-frete-especial-revisado.md
[FILE] README.md
[FILE] SLA-2024-tabela-sla-clientes.md
```

**Leitura de `docs/novatech/SLA-2024-tabela-sla-clientes.md` (tool `read_file`) — trecho-chave recuperado:**
- A NovaTech classifica clientes em **3 tiers**: Gold, Silver e Standard. O documento afirma explicitamente que **não existem outros tiers** (relevante para a armadilha "tier Platinum").
- SLA de **chamados gerais — Gold:** primeira resposta até **2h úteis**, resolução até **24h úteis**.
- SLA de **incidentes críticos — Gold:** primeira resposta até **30min**, resolução até **4h**.
- Critério de incidente crítico inclui carga perigosa com irregularidade e risco à segurança de pessoas.

✅ **Comprovado:** o agente lista e lê documentação de negócio diretamente de `docs/novatech/` via MCP.

---

## (b) Recuperar um chunk relevante de `data/retrieval-corpus/` — via `filesystem` MCP, validado contra o gabarito do Anexo B

**Pergunta de domínio usada:** *"Qual o SLA do cliente Gold?"*

**Gabarito do mapa de cobertura (Anexo B):**
| Pergunta | Chunks que DEVEM ser recuperados | Podem aparecer (relevância menor) |
|---|---|---|
| "Qual o SLA do cliente Gold?" | **SLA-2024-B** | SLA-2024-A, SLA-2024-C |

**Chunk recuperado de `data/retrieval-corpus/chunks-novatech.md` (leitura real via MCP):**

> **Chunk SLA-2024-B** — Seção 2: Tabela de SLAs (chamados gerais)
> SLAs para chamados gerais — Gold: resposta em até 2h úteis, resolução em até 24h úteis. Silver: resposta em até 4h úteis, resolução em até 48h úteis. Standard: resposta em até 8h úteis, resolução em até 72h úteis.

**Validação cruzada:** o chunk recuperado (`SLA-2024-B`) é exatamente o esperado pelo gabarito, e seus valores para Gold (2h / 24h úteis) **batem** com o documento-fonte lido em (a). Recuperação correta e consistente com a fonte.

✅ **Comprovado:** o agente recupera o chunk certo do corpus e o resultado confere com o gabarito do Anexo B e com o documento original.

---

## (c) Ler o histórico do repositório — via `git` MCP

**`git_log` (tool do git MCP) — saída real:**
```
Commit: bbdd03aeecd7e349a2bfc93849e0552a0b766ac6
Author: Trilha AI First <trilha@db1.local>
Date:   2026-06-09 18:13:30+00:00
Message: chore: starter repo (Anexo D) — estrutura + dados semeados dos Anexos A e B
```

**`git_branch` (branch_type=all) — saída real:**
```
* master
```

✅ **Comprovado:** o agente lê histórico e branches do repositório local via `git` MCP. O estado confere com o starter (Anexo D): um único commit inicial na branch `master`, sem remoto — coerente com a fase local (sem GitHub/push).

---

## Observações da execução (transparência)

- As três comprovações acima usaram **tools de leitura** dos servers `filesystem` e `git`, que responderam normalmente.
- O `git` MCP estava configurado para a árvore do starter; o `repo_path` aceito foi o caminho da instância do starter na máquina. As tools de escrita do `filesystem` MCP ficaram sem resposta (timeout) no momento da gravação dos artefatos — por isso os `.md` desta entrega foram disponibilizados para download em vez de gravados via MCP. Isso não afeta as evidências de leitura, que são reais.
- Para reexecutar localmente: subir os servers conforme `mcp.json`, abrir o agente e repetir as três chamadas (listar/ler doc; ler corpus; `git_log`/`git_branch`).
