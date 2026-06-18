# Skill: typescript-conventions

> **Nível:** Foundation
> **Caminho no repo:** `skills/foundation/typescript-conventions.md`
> **Dono:** Dev Sênior + Tech Lead
> **Status:** rascunho (vira "madura" após 1 ciclo de teste com Copilot)

---

## Contexto — quando esta skill se aplica

Aplique **sempre** que for gerar, editar ou revisar qualquer arquivo `.ts` do
NovaTech Assistant: handlers de Azure Functions, services, pipeline de ingestão,
tipos compartilhados, validadores, testes. Esta é a skill **base**: toda skill de
Domain (`azure-functions-endpoint`, `testing-patterns`, etc.) e de Artifact
(`create-rag-endpoint`, etc.) **assume** estas regras já aplicadas e não pode
contradizê-las. Se houver conflito, esta skill vence para questões de linguagem.

Frase-ativação: *"escrever/gerar arquivo TypeScript, definir tipo, validar input,
nomear símbolo, organizar import"*.

---

## Regras prescritivas (o agente DEVE seguir)

1. **Strict mode é obrigatório.** O `tsconfig.json` roda com `strict: true`. NÃO
   gere código que dependa de relaxar o compilador.
2. **`any` é proibido.** Use tipos explícitos, `unknown` + narrowing, ou generics.
   Quando o dado vem de fora (HTTP body, JSON de chunk), tipe como `unknown` e
   valide com Zod antes de usar.
3. **Valide toda entrada externa com Zod.** Defina um schema por entrada, derive o
   tipo com `z.infer`, e nunca confie no shape sem `parse`/`safeParse`.
4. **Logging só com `pino`.** `console.log`/`console.error` são proibidos em código
   de produção. Importe o logger compartilhado de `src/shared/logger.ts`.
5. **Código e comentários em inglês.** (Documentos de status/PR ficam em português —
   ver Project Management Rules; mas o código, nomes e comentários são em inglês.)
6. **Naming:**
   - `camelCase` para variáveis e funções; `PascalCase` para tipos, interfaces,
     classes e schemas Zod (`QueryRequestSchema`).
   - `UPPER_SNAKE_CASE` apenas para constantes verdadeiras.
   - Nada de abreviação obscura (`res`, `q`, `tmp2`). Nomes do domínio NovaTech
     são explícitos: `sourceDocument`, `chunkScore`, `contextBudgetTokens`.
7. **Async sempre com `async/await`.** Não misture `.then()` com `await`. Toda
   função que faz I/O retorna `Promise<T>` com `T` explícito.
8. **Imports organizados e absolutos por módulo.** Ordem: libs externas →
   módulos `src/shared/*` → módulos locais. Sem imports não usados. Sem
   `import * as` exceto quando a lib exigir.
9. **Tipos do domínio vivem em `src/shared/types.ts`.** Não redefina `Chunk`,
   `QueryResponse`, `SourceDocument` localmente — importe.
10. **Exports nomeados, não `default`** (exceto onde o framework exigir, ex.:
    componentes React). Facilita refactor e tree-shaking.
11. **`source_document` é contrato.** Todo objeto de resposta do assistente DEVE
    carregar `sourceDocument` (id + seção). Nunca gere uma `QueryResponse` sem ele,
    mesmo com baixa confiança.

---

## Exemplos concretos (DO / DON'T)

### Validação de input

```typescript
// DON'T — confia no shape, usa any, sem validação
export async function handler(req: any) {
  const question = req.body.question; // pode ser undefined, número, objeto...
  return search(question);
}
```

```typescript
// DO — tipa como unknown, valida com Zod, deriva o tipo
import { z } from "zod";

export const QueryRequestSchema = z.object({
  question: z.string().min(1).max(2000),
  conversationId: z.string().uuid().optional(),
});

export type QueryRequest = z.infer<typeof QueryRequestSchema>;

export function parseQueryRequest(body: unknown): QueryRequest {
  return QueryRequestSchema.parse(body); // throws ZodError -> tratado pela error-handling skill
}
```

### Logging

```typescript
// DON'T — console.log em produção, sem contexto estruturado
console.log("query received: " + question);
```

```typescript
// DO — pino com campos estruturados
import { logger } from "../shared/logger";

logger.info({ conversationId, questionLength: question.length }, "query received");
```

### Tipos do domínio e contrato source_document

```typescript
// DON'T — redefine tipo local, resposta sem fonte
type Resp = { answer: string };
return { answer: text }; // viola o guardrail: toda resposta cita fonte
```

```typescript
// DO — usa o tipo compartilhado, sempre com sourceDocument
import type { QueryResponse } from "../shared/types";

const response: QueryResponse = {
  answer: text,
  sourceDocument: { id: "SLA-2024", section: "3.2" },
  confidence: "high",
};
return response;
```

### Async / I/O

```typescript
// DON'T — mistura then/await, retorno sem tipo
async function getChunks(q) {
  return search(q).then(r => r.results);
}
```

```typescript
// DO — async/await consistente, Promise tipada
async function getChunks(question: string): Promise<Chunk[]> {
  const result = await search(question);
  return result.chunks;
}
```

---

## Anti-padrões (o que o Copilot gera de errado sem esta guidance)

- **`any` implícito em parâmetros de handler.** Copilot frequentemente assina
  `(req, res)` sem tipos. Sempre tipar e validar o body como `unknown` + Zod.
- **`console.log` para "debug".** Some no PR mas passa despercebido. Proibido —
  usar `logger`.
- **Resposta sem `sourceDocument`.** O LLM/Copilot tende a devolver só o texto da
  resposta. No NovaTech isso é um defeito de produto, não só de estilo.
- **Tipos duplicados.** Copilot recria `Chunk`/`QueryResponse` no arquivo local em
  vez de importar de `src/shared/types.ts`, gerando divergência silenciosa.
- **`as` para silenciar o compilador.** `value as QueryRequest` mascara dados
  inválidos. Use validação, não casting.
- **Comentários em português no código.** Misturar idioma quebra a convenção 5.
  Comentário de código é em inglês.
- **`enum` numérico do TS** para tiers/classes. Use union literais
  (`type Tier = "Gold" | "Silver" | "Standard"`) — mais seguro e sem valores mágicos.

---

## Dependências

- **Lida antes:** nenhuma. Esta é a skill raiz da camada Foundation.
- **Complementa:** `error-handling` (custom errors, retry, como tratar `ZodError`)
  e `project-structure` (em qual pasta cada arquivo mora).
- **Usada por:** todas as Domain e Artifact skills.

---

## Critério de "skill madura"

Esta skill é considerada madura quando, com ela presente no repositório, o Copilot
gera um arquivo `.ts` novo (ex.: `src/functions/query/validator.ts`) que: (a) não
usa `any`, (b) valida o input com Zod, (c) usa `logger` em vez de `console.log` e
(d) nomeia símbolos em inglês — sem correção manual em pelo menos uma rodada de teste.
