# Revisão crítica — código da T-01 (query endpoint)

> Papel: Desenvolvedor sênior revisando o código gerado com apoio do Copilot
> **antes** de abrir o PR. O objetivo não é reprovar o código (ele cumpre o
> escopo da T-01 e passa nos testes), mas listar o que um code review real
> apontaria. Cada item traz o problema, o risco e o ajuste proposto.

## Resumo

O código da T-01 está **funcional e dentro do escopo** (valida input, retorna
400/200, segue TypeScript strict + Zod + Azure Functions v4, e os 5 testes
passam). Ainda assim, há pontos que precisam de ajuste antes do merge. Os dois
primeiros são bloqueantes; os demais são melhorias recomendadas.

---

## 1. (Bloqueante) Dependências não declaradas no `package.json`

**Problema:** O handler importa `@azure/functions` e o código do projeto prevê
`pino` (logging estruturado, exigido pelo plan), mas o `package.json` do starter
só traz `typescript`, `vitest` e `zod`. O Copilot importou a lib sem adicioná-la
às dependências — padrão clássico de código gerado por IA.

**Risco:** `npm ci` / build do CI quebra (`Cannot find module '@azure/functions'`).
Passa no laptop de quem tem a lib em cache global e falha no pipeline limpo.

**Ajuste:** adicionar ao `package.json`:
```jsonc
"dependencies": {
  "@azure/functions": "^4.5.0",
  "zod": "^3.23.0",
  "pino": "^9.0.0"
}
```
(mover `zod` de devDependencies para dependencies, já que é usado em runtime).

---

## 2. (Bloqueante) Sem limite de tamanho de payload

**Problema:** `await request.json()` desserializa o corpo inteiro sem teto de
tamanho. A validação Zod só roda **depois** de o JSON já ter sido materializado
em memória.

**Risco:** vetor de DoS — um body de muitos MB é parseado antes de qualquer
checagem. Em um endpoint interno isso ainda importa (um cliente Teams com bug
pode disparar payloads grandes).

**Ajuste:** validar `Content-Length` / tamanho do corpo antes do parse e
rejeitar com `413 Payload Too Large` acima de um limite (ex.: 16 KB, mais que
suficiente para `question` ≤ 1000 chars + 3 turnos de histórico). Idealmente
um pequeno middleware reaproveitável pelos outros endpoints.

---

## 3. Observabilidade incompleta (gap vs. o plan)

**Problema:** o plan exige *structured logging com pino*, mas a T-01 usa
`context.warn(...)` do runtime e não há logger pino nem `invocationId`
correlacionando a requisição. Falhas de validação não saem em JSON estruturado.

**Risco:** dificuldade de diagnóstico em produção; logs inconsistentes entre
endpoints; métricas de taxa de 400 ficam difíceis de extrair.

**Ajuste:** introduzir `src/shared/logger.ts` (pino) na T-04 e injetar um logger
filho com `invocationId` no handler; trocar `context.warn` por
`logger.warn({ invocationId, errors }, "...")`. Aceitável manter `context.warn`
nesta task e marcar como dívida explícita ligada à T-04.

---

## 4. `history` limitado por turnos, não por tokens (semântica da ADR-0002)

**Problema:** a ADR-0002 define um **orçamento de tokens**; a T-01 aproxima isso
com `history.max(3)`. Três turnos longos ainda podem estourar o budget, e o
`question.max(1000 chars)` mistura "caracteres" com "tokens".

**Risco:** falsa sensação de que o input já garante o context budget. Quem ler
só esta camada pode achar que o controle de tokens está resolvido aqui.

**Ajuste:** manter o cap de turnos como guarda barata de input, mas documentar
que o **enforcement real do budget é da T-07** (prompt-builder), que conta
tokens e descarta chunks/histórico excedentes. Já deixei o comentário no
`validator.ts`, mas vale um teste na T-07 fechando o contrato.

---

## 5. Mensagens de erro do Zod expostas diretamente ao cliente

**Problema:** o handler devolve `details` com as mensagens cruas do Zod
(inclusive nomes internos de campos). É conveniente em dev, mas vaza detalhes do
schema para o consumidor.

**Risco baixo (endpoint interno), mas:** acopla o contrato de erro à
implementação do schema e pode confundir o bot do Teams, que provavelmente quer
uma mensagem amigável única, não a lista técnica.

**Ajuste:** padronizar um envelope de erro do projeto (ex.: `{ error, message,
details? }`) e decidir conscientemente se `details` vai para clientes internos
ou só para o log. Idealmente o mesmo formato usado no tratamento de erros da
T-10.

---

## Pontos que já estão bem (não mexer)

- `.strict()` no schema rejeita campos desconhecidos — bom contra payloads
  inflados e contra injeção de campos extras.
- União discriminada em `ValidationResult` (em vez de exceptions) deixa o
  handler decidir o status HTTP — limpo e testável.
- Nenhum uso de `any`; tipos derivados de `z.infer`.
- Task isolada e testável sem subir Azure — os 5 testes cobrem caso válido,
  JSON malformado, `question` curta, `history` com 4 turnos e campo desconhecido.

---

## Veredito

Aprovar **após** corrigir os itens **1** e **2** (bloqueantes) e abrir dívida
rastreável para **3** e **4** (ligadas a T-04 e T-07). O item **5** é decisão de
design a alinhar com quem consome o endpoint (bot do Teams).
