# Exercício 3.2 — DESENVOLVEDOR
## Revisão crítica de código gerado por IA (módulo de feedback)

**Tópico:** Revisão Crítica de Outputs de IA
**Artefato revisado:** `feedback-handler.ts` (gerado pelo Copilot)
**Destino correto no repo (Anexo C):** `/src/functions/feedback/handler.ts` + `/src/functions/feedback/validator.ts`
**Régua da revisão:** AGENTS.md do projeto (cenário 2)

> Regras do AGENTS.md aplicáveis: TypeScript strict mode · Zod para validação de input · pino para logging (nunca `console.log`) · nunca logar dados pessoais (e-mail, nome) · imports estáticos no topo (nunca `require` dinâmico).

---

## 1. Minha revisão (humano) — ANTES de usar o Claude

Classificação: **[AGENTS]** violação do AGENTS.md · **[SEC]** segurança/privacidade · **[BUG]** bug potencial.

| # | Achado | Linha/trecho | Classificação | Por quê é problema |
|---|--------|--------------|---------------|--------------------|
| H1 | `await request.json() as any` sem validação | `const body = ... as any` | **[AGENTS]** + **[BUG]** | O AGENTS.md exige Zod para todo input. `as any` desliga o strict mode e deixa entrar payload malformado (campos faltando, tipos errados) direto até o banco. |
| H2 | `console.log` em vez de pino | `console.log('Feedback recebido:'...)` | **[AGENTS]** | Regra explícita: logging só via pino. `console.log` não respeita níveis nem formato estruturado. |
| H3 | Log de dado pessoal | `JSON.stringify(feedback)` inclui `attendantEmail` (e `comment`) | **[AGENTS]** + **[SEC]** | Loga e-mail do atendente — proibido pelo AGENTS.md e exposição de PII (LGPD). O `comment` é texto livre e também pode conter dado pessoal. |
| H4 | `require('@azure/cosmos')` dinâmico | dentro do handler | **[AGENTS]** | AGENTS.md exige imports estáticos no topo. `require` dinâmico dentro da função quebra tree-shaking, tipagem e a convenção. |
| H5 | Sem `try/catch` na persistência | `await container.items.create(feedback)` | **[BUG]** | Se o Cosmos falhar, a exceção sobe sem tratamento; o cliente recebe 500 cru (potencial vazamento de stack) e nada é logado. |
| H6 | Cliente Cosmos criado por requisição | `new CosmosClient(...)` dentro do handler | **[BUG]** | Em Azure Functions o cliente deve ser singleton de módulo. Criar a cada invocação gera overhead de conexão e risco de esgotar sockets sob carga. |

Resumo do que eu peguei sozinha: os 4 itens "óbvios" exigidos (H1–H4) e dois de robustez que a experiência prática aponta (H5, H6).

---

## 2. Revisão do Claude (segundo revisor)

Pedi ao Claude uma segunda passada usando o AGENTS.md como régua. Ele confirmou H1–H6 e acrescentou:

| # | Achado | Classificação | Por quê é problema |
|---|--------|---------------|--------------------|
| C1 | `rating` sem faixa válida | **[BUG]** | Mesmo com tipagem, nada garante `rating` entre 1 e 5. Um `rating: 999` ou string seria persistido. Precisa de constraint no schema Zod. |
| C2 | `COSMOS_CONNECTION_STRING` lido direto de `process.env` sem checagem | **[BUG]** + **[SEC]** | Se a env estiver ausente, o erro só aparece em runtime na primeira request. Config deve ser validada no boot (`/src/shared/config.ts`). |
| C3 | Objeto persistido sem schema fechado | **[SEC]** | Sem `.strict()` no Zod, campos extras enviados pelo cliente (ex: `isAdmin`, `__proto__`) entrariam no documento — mass assignment. |
| C4 | Status e corpo de resposta pobres | **[BUG]** | Retorna `200` + string `'OK'`. Criação deveria ser `201`; corpo deveria ser JSON estruturado para o chamador tratar. |
| C5 | Arquivo no lugar/forma errados | **[AGENTS]** | Pelo Anexo C, o handler vai em `/src/functions/feedback/handler.ts` e a validação em `validator.ts` separado — não num arquivo único solto. |
| C6 | `authLevel` não definido no `app.http` | **[SEC]** | Endpoint que grava no banco não deveria ser anônimo por omissão; convém `authLevel: 'function'` (ou o esquema de auth do projeto). |

---

## 3. Comparação honesta: humano vs Claude

**Concordâncias (ambos pegaram):** H1–H6. Os quatro achados exigidos pelo enunciado (`as any` sem Zod, `console.log`, `require` dinâmico, e-mail logado) saíram já na minha revisão e foram confirmados pelo Claude — ou seja, não dependiam da IA.

**O que o Claude acrescentou que eu não tinha listado:** C1 (faixa do `rating`), C2 (config não validada no boot), C3 (schema não fechado / mass assignment), C4 (status 201 + corpo JSON), C6 (`authLevel`). São itens mais sutis — a maioria de robustez/segurança "de borda", não violação direta do AGENTS.md.

**O que eu tinha e o Claude reforçou:** o singleton do Cosmos (H6) — eu classifiquei como performance; o Claude detalhou o risco de esgotamento de conexões sob carga, o que é mais preciso.

**Divergência real:** C5 (estrutura de arquivos). Eu tinha tratado como detalhe de organização; o Claude classificou como violação do AGENTS.md/Anexo C. Concordei depois — a convenção de `handler.ts` + `validator.ts` separados é parte do contrato do repo, então é violação, não preferência.

**Conclusão do exercício:** a revisão humana foi suficiente para os bloqueadores de merge (PII, Zod, pino, require). O Claude agregou principalmente *defense-in-depth* (mass assignment, faixa de valores, config no boot, status code). O bom uso da IA aqui não foi "achar o óbvio", e sim ampliar a cobertura de casos de borda que cansaço/pressa fazem passar.

---

## 4. Código reescrito (segue o AGENTS.md)

Dividido conforme o Anexo C: schema/validação em `validator.ts`, handler em `handler.ts`.

### `/src/functions/feedback/validator.ts`

```typescript
import { z } from 'zod';

// Schema fechado (.strict): rejeita campos extras → evita mass assignment.
export const feedbackSchema = z
  .object({
    queryId: z.string().min(1, 'queryId é obrigatório'),
    rating: z.number().int().min(1).max(5), // C1: faixa válida garantida
    comment: z.string().max(2000).optional(),
    attendantEmail: z.string().email(),
  })
  .strict();

export type FeedbackInput = z.infer<typeof feedbackSchema>;
```

### `/src/functions/feedback/handler.ts`

```typescript
import { app, HttpRequest, HttpResponseInit, InvocationContext } from '@azure/functions';
import { CosmosClient } from '@azure/cosmos'; // H4: import estático no topo
import { logger } from '../../shared/logger'; // H2: pino, nunca console.log
import { config } from '../../shared/config'; // C2: env validada no boot
import { feedbackSchema } from './validator';

// H6: singleton de módulo — criado uma vez por processo, reusado entre invocações.
const container = new CosmosClient(config.cosmosConnectionString)
  .database('novatech')
  .container('feedbacks');

export async function feedbackHandler(
  request: HttpRequest,
  context: InvocationContext,
): Promise<HttpResponseInit> {
  // Parse defensivo do corpo
  let rawBody: unknown; // H1: nada de `as any`
  try {
    rawBody = await request.json();
  } catch {
    logger.warn({ requestId: context.invocationId }, 'Feedback com JSON inválido');
    return { status: 400, jsonBody: { error: 'INVALID_JSON' } };
  }

  // H1: validação Zod antes de qualquer uso
  const parsed = feedbackSchema.safeParse(rawBody);
  if (!parsed.success) {
    // H3: loga só caminho+código dos erros, nunca os valores enviados (PII)
    logger.warn(
      {
        requestId: context.invocationId,
        issues: parsed.error.issues.map((i) => ({ path: i.path, code: i.code })),
      },
      'Feedback rejeitado na validação',
    );
    return { status: 400, jsonBody: { error: 'VALIDATION_FAILED' } };
  }

  const feedback = { ...parsed.data, timestamp: new Date().toISOString() };

  // H5: persistência com tratamento de erro
  try {
    await container.items.create(feedback);
  } catch (err) {
    logger.error(
      { requestId: context.invocationId, queryId: feedback.queryId, err },
      'Falha ao persistir feedback',
    );
    return { status: 500, jsonBody: { error: 'PERSISTENCE_FAILED' } };
  }

  // H3: log de sucesso SEM dados pessoais (sem attendantEmail, sem comment)
  logger.info(
    { requestId: context.invocationId, queryId: feedback.queryId, rating: feedback.rating },
    'Feedback registrado',
  );

  return { status: 201, jsonBody: { status: 'created' } }; // C4: 201 + JSON
}

app.http('feedback', {
  methods: ['POST'],
  authLevel: 'function', // C6: não anônimo por omissão
  handler: feedbackHandler,
});
```

**Notas de implementação**
- `config.cosmosConnectionString` pressupõe que `/src/shared/config.ts` valida as variáveis de ambiente na inicialização (C2) — se a connection string faltar, a aplicação falha no boot, não na primeira requisição.
- O e-mail e o comentário continuam sendo **armazenados** (são necessários para o feedback loop), mas **nunca são logados** — é a distinção entre persistir com propósito e expor em log.
- O `.strict()` no schema é o que efetivamente bloqueia campos extras; sem ele a tipagem sozinha não impede mass assignment.

---

## 5. Checklist de conformidade com o AGENTS.md

| Regra do AGENTS.md | Antes | Depois |
|---|---|---|
| Zod para validação de input | ❌ `as any` | ✅ `feedbackSchema.safeParse` |
| pino para logging | ❌ `console.log` | ✅ `logger` (pino) |
| Nunca logar dados pessoais | ❌ logava e-mail/comment | ✅ loga só `queryId`/`rating`/`requestId` |
| Imports estáticos no topo | ❌ `require` dinâmico | ✅ `import { CosmosClient }` |
| TypeScript strict mode | ❌ `as any` furava o strict | ✅ `unknown` + parse tipado |
