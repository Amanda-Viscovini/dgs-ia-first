# Exercício 3.1 (DESENVOLVEDOR) — Structured output e verificações determinísticas

**Tópico:** Harness Engineering
**Módulo entregue:** `src/services/response-validator.ts`
**Apoio:** `src/shared/logger.ts` (pino), `package.json` (dependência pino), `tests/unit/response-validator.test.ts`

---

## 1. Schema do structured output (Zod)

Em vez de texto livre, o modelo passa a responder em JSON com formato fixo:

```ts
const assistantResponseSchema = z
  .object({
    answer: z.string().trim().min(1),
    source_document: z.string().trim().min(1),
    confidence_score: z.number().min(0).max(1),
  })
  .strict();
```

Decisões:
- **`.strict()`** — rejeita campos extras. O modelo não consegue "vazar" campos não previstos.
- **`confidence_score` como número em [0,1]** — um score real (não rótulo livre), o que permite encaminhar respostas de baixa confiança para **human-in-the-loop** com threshold concreto (ex.: `< 0.5` → revisão humana antes de chegar ao atendente, exatamente o caso de carga perigosa de baixa confiança).
- **`.trim().min(1)`** — bloqueia strings vazias ou só com espaços.

---

## 2. O que o Copilot gerou primeiro (draft) e por que NÃO foi aceito

O draft inicial do Copilot funcionava no caminho feliz, mas tinha falhas reais:

```ts
// DRAFT do Copilot — NÃO usar
const schema = z.object({
  answer: z.string(),
  source_document: z.string().optional(),   // (A) fonte opcional
  confidence_score: z.string(),             // (B) score como texto livre
});

export function validateResponse(raw: any) {              // (C) any
  const parsed = schema.parse(raw);                       // (D) parse() joga exceção
  if (!parsed.source_document) {
    console.log('sem fonte');                             // (E) console.log
  }
  if (parsed.answer.includes('carga perigosa') &&
      parsed.answer.includes('devolução') &&
      !parsed.answer.includes('não')) {                   // (F) regex/string ingênua
    console.log('bloqueado');
  }
  return parsed;                                          // (G) retorna mesmo após "bloquear"
}
```

---

## 3. Code review — problemas reais identificados e correções

| # | Problema | Por que é real | Correção aplicada |
|---|----------|----------------|-------------------|
| **(A)** | `source_document` opcional | O Guardrail 1 exige fonte sempre. Opcional deixa passar resposta sem fonte. | `z.string().trim().min(1)` (obrigatório e não vazio). |
| **(B)** | `confidence_score: z.string()` | Score como texto aceita "muito alta", "0,9", "" — não dá pra aplicar threshold de HITL. | `z.number().min(0).max(1)`. |
| **(C)** | `raw: any` | Burla o type-safety (proibido no AGENTS.md). | `raw: unknown` + `safeParse`. |
| **(D)** | `schema.parse()` joga exceção | Uma resposta malformada derruba o handler em vez de cair no fallback seguro. | `safeParse` + retorno tipado `ValidationResult`. |
| **(E)** | `console.log` | Viola o AGENTS.md (usar pino, nunca console.log). | `logger.warn(...)` (pino). |
| **(F)** | **Detecção ingênua de "carga perigosa + devolução"** | `includes('carga perigosa')` perde **"cargas perigosas"**, maiúsculas e acentos. E `!includes('não')` é frágil: uma frase afirmativa pode conter "não" em outro lugar ("não há restrição, pode devolver") e escapar. | Normalização (lowercase + remoção de acentos) + regex `\\bcargas?\\s+perigosas?\\b`, termo de devolução por radical (`devolu\\w*\|devolv\\w*`) e **negativa por padrão de recusa explícita**, com estratégia *fail-safe*: se os dois temas coexistem e não há negativa clara, **bloqueia**. |
| **(G)** | "Bloqueia" mas retorna a resposta original | O guardrail só logava; a resposta proibida seguia adiante. | Em qualquer falha retorna `SAFE_FALLBACK` (a resposta proibida nunca sai). |

Os dois problemas centrais pedidos no enunciado — **schema aceitando campos extras** e **regex de carga perigosa sem cobrir variações** — são os itens (A/`.strict()`) e (F).

---

## 4. Os 2 guardrails realmente bloqueiam (não apenas logam)

Ambos retornam `{ ok: false, response: SAFE_FALLBACK }`. Os testes em
`tests/unit/response-validator.test.ts` provam que:
- resposta sem fonte → fallback;
- "cargas perigosas podem ser devolvidas" → fallback;
- a resposta correta ("não podem ser devolvidas… escalar supervisor") → passa.

---

## 5. Prompt (probabilístico) × código (determinístico)

| Camada | Natureza | Papel |
|--------|----------|-------|
| **Prompt / system prompt** | Probabilístico | *Pede* o JSON e *orienta* a recusar devolução de carga perigosa. Acerta na maioria das vezes — mas "esquece" (os 12% de erro do cenário). |
| **`response-validator.ts`** | Determinístico | *Garante.* Se o JSON não bate com o schema, rejeita. Se a fonte falta, bloqueia. Se afirma devolução de carga perigosa, bloqueia. Sempre, sem depender do modelo. |

O prompt reduz a probabilidade do erro; o código fecha a porta para o erro residual. É essa combinação que transforma o protótipo em algo governável.

---

## 6. Como rodar

```bash
npm install      # instala pino + zod + vitest
npm test         # executa os testes do validador
```
