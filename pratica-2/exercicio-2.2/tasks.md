# Tasks — Query Endpoint

> Derivado de `specs/query-endpoint/plan.md`. Cada task é atômica: pode ser
> implementada e testada de forma independente, respeitando as dependências
> declaradas. Estimativa: **P** (≤ meio dia), **M** (≈ 1 dia), **G** (> 1 dia).
> Decisões herdadas: ADR-0002 (context budget) e ADR-0003 (vigência de documentos).

## Visão geral das dependências

```
T-01 (endpoint + validação)  ──┐
T-02 (types & errors) ─────────┼──> T-10 (orquestração) ──> T-11 (testes integração)
T-03 (config) ──> T-05, T-08   │
T-04 (logger + retry) ──> T-05, T-06, T-08
T-05 (embedding) ──────────────┤
T-06 (search top-5) ───────────┤
T-07 (prompt builder) ─────────┤
T-08 (completion GPT-4o) ──────┤
T-09 (response builder) ───────┘
```

---

## T-01 — Setup do endpoint HTTP + validação de input *(PRIMEIRA TASK)*

**Descrição:** Criar o HTTP trigger `POST /api/query` (Azure Functions v4) e a
camada de validação de input com Zod. Nesta task o handler ainda **não** chama
serviços externos: valida o corpo da requisição e retorna `200` com um corpo
stub quando válido, ou `400` com detalhes quando inválido. Isola o contrato de
entrada do endpoint antes de qualquer integração com Azure.

**Critérios de aceite:**
- `POST /api/query` com body válido (`{ "question": "Qual o prazo de devolução?" }`) retorna `200`.
- Body que não seja JSON válido retorna `400` com `error: "INVALID_JSON"`.
- `question` ausente, vazia, < 3 ou > 1000 caracteres retorna `400` com `error: "VALIDATION_ERROR"` e lista de campos inválidos.
- `history` é opcional e, quando presente, é limitado a no máximo 3 turnos (proxy de ADR-0002); mais que isso retorna `400`.
- O schema é exportado e tipado via `z.infer` (sem `any`); `tsc --strict` passa sem erros.
- Existe teste de integração cobrindo: caso válido, JSON malformado, `question` curta e `history` com 4 turnos.

**Dependências:** nenhuma (define schema/tipos localmente; será refatorado para usar `T-02` em `T-10`).

**Estimativa:** M

---

## T-02 — Tipos de domínio compartilhados + custom errors

**Descrição:** Definir em `src/shared/types.ts` os tipos do domínio (`Chunk`,
`SourceDocument`, `QueryResult`, `RetrievedChunk` com metadado de vigência) e em
`src/shared/errors.ts` a hierarquia de erros (`AppError`, `ValidationError`,
`UpstreamError`, `NotFoundError`) com `code` e `statusCode`.

**Critérios de aceite:**
- `SourceDocument` inclui `documentId`, `section` e `effectiveFrom` (suporte à ADR-0003).
- Todo custom error estende `AppError` e expõe `code: string` e `statusCode: number`.
- Nenhum tipo usa `any`; união discriminada para resultados.

**Dependências:** nenhuma.

**Estimativa:** P

---

## T-03 — Config de ambiente com validação Zod

**Descrição:** `src/shared/config.ts` carrega e valida variáveis de ambiente
(endpoints/keys do Azure OpenAI e Azure AI Search, nome do index, deployment do
embedding e do chat) com Zod, falhando rápido na inicialização se faltar algo.

**Critérios de aceite:**
- App não inicia (erro explícito) se uma variável obrigatória estiver ausente.
- Nenhum segredo é logado; `config` é congelado (`Object.freeze`).
- Valores expostos como objeto tipado, não `process.env` cru espalhado pelo código.

**Dependências:** nenhuma.

**Estimativa:** P

---

## T-04 — Logger estruturado (pino) + utilitário de retry com backoff

**Descrição:** `src/shared/logger.ts` configura o `pino` (sem `console.log`) e
`src/shared/retry.ts` implementa retry com exponential backoff + jitter para
chamadas a serviços Azure, com limite de tentativas e classificação de erros
retryáveis (429/503/timeout) vs não-retryáveis (4xx).

**Critérios de aceite:**
- Logger emite JSON estruturado com `level`, `time` e `invocationId` quando disponível.
- `withRetry` só repete erros retryáveis; erros 4xx (exceto 429) sobem imediatamente.
- Backoff é testável (clock injetável) — teste cobre sucesso após 2 falhas e desistência após o máximo.

**Dependências:** nenhuma (usado por T-05, T-06, T-08).

**Estimativa:** M

---

## T-05 — Service de embedding (Azure OpenAI)

**Descrição:** `src/services/completion.ts`/embedding: converte a pergunta em
vetor via deployment de embedding do Azure OpenAI, usando `withRetry` e o logger.

**Critérios de aceite:**
- Recebe `string`, retorna `number[]` com a dimensão esperada do modelo.
- Falha de upstream é encapsulada em `UpstreamError` (não vaza erro cru do SDK).
- Chamada externa mockada em teste (msw) — nenhum acesso real à Azure.

**Dependências:** T-03, T-04.

**Estimativa:** M

---

## T-06 — Service de busca: top-5 chunks (Azure AI Search)

**Descrição:** `src/services/search.ts` consulta o índice por similaridade e
retorna os top-5 chunks com seus metadados (incluindo vigência, p/ ADR-0003).

**Critérios de aceite:**
- Retorna no máximo 5 `RetrievedChunk` ordenados por score.
- Quando não há match, retorna lista vazia (não lança) — habilita o fallback "não encontrado".
- Metadado de vigência é preservado no resultado.
- Integração mockada em teste.

**Dependências:** T-02, T-03, T-04.

**Estimativa:** M

---

## T-07 — Prompt builder com context budget (ADR-0002)

**Descrição:** `src/services/prompt-builder.ts` monta o prompt final
(system prompt de `/prompts/system-prompt.md` + chunks + histórico ≤ 3 turnos +
pergunta), respeitando o orçamento: ~4K tokens de system + ~8K de chunks
(5 chunks de ~1.5K). Trunca/descarta chunks excedentes de forma determinística.

**Critérios de aceite:**
- Total estimado de tokens nunca excede o budget; chunks de menor score são cortados primeiro.
- Quando há duas versões de um documento, prioriza a mais recente e sinaliza a existência da anterior (ADR-0003).
- Histórico é limitado a 3 turnos.
- Função pura e testável (entrada → prompt), sem I/O.

**Dependências:** T-02.

**Estimativa:** M

---

## T-08 — Service de completion (GPT-4o)

**Descrição:** `src/services/completion.ts`: envia o prompt montado ao
deployment GPT-4o e retorna o texto + uso de tokens, com `withRetry`.

**Critérios de aceite:**
- Respeita `max_tokens` e temperatura baixa (determinismo p/ domínio normativo).
- Erro de upstream encapsulado em `UpstreamError`.
- Chamada mockada em teste.

**Dependências:** T-03, T-04.

**Estimativa:** M

---

## T-09 — Response builder com `source_document`

**Descrição:** `src/functions/query/response-builder.ts` monta o payload de
resposta a partir da saída do modelo e dos chunks usados, sempre populando
`source_document` (guardrail de citação de fonte), inclusive em baixa confiança.

**Critérios de aceite:**
- `source_document` está presente em 100% das respostas (`null` apenas no caminho "não encontrado", com mensagem padrão).
- Inclui flag de baixa confiança quando aplicável.
- Forma de saída validada por um schema Zod de output.

**Dependências:** T-02.

**Estimativa:** P

---

## T-10 — Orquestração no handler (wiring do pipeline)

**Descrição:** Substituir o stub de `T-01` pela orquestração real:
validar → embedding (T-05) → search top-5 (T-06) → prompt (T-07) →
completion (T-08) → response builder (T-09), com tratamento de erros e logging
por invocação. Caminho "sem chunks" retorna a mensagem padrão de não encontrado.

**Critérios de aceite:**
- Fluxo feliz retorna `200` com `answer` + `source_document`.
- Erros de upstream viram `502/503` com envelope de erro padronizado (sem vazar stack).
- Toda invocação loga `invocationId`, latência e quantidade de chunks recuperados.
- Query sem cobertura retorna `200` com mensagem padrão de "não encontrado" (não inventa resposta).

**Dependências:** T-01, T-05, T-06, T-07, T-08, T-09.

**Estimativa:** M

---

## T-11 — Testes de integração do endpoint (msw + fixtures)

**Descrição:** Testes de integração em `tests/integration/` cobrindo o fluxo
completo com Azure mockado via `msw` e fixtures do domínio (perguntas, chunks e
respostas esperadas dos Anexos A/B).

**Critérios de aceite:**
- Cobre: prazo de devolução, SLA Gold, carga perigosa (negativa explícita), e query sem cobertura.
- Toda resposta de sucesso contém `source_document`.
- Nenhum teste acessa serviço real; cobertura de linhas ≥ 80%.

**Dependências:** T-10.

**Estimativa:** M
