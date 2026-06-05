# Resposta à pergunta de teste

**Pergunta do atendente:** "Meu cliente é Gold, qual o SLA de resolução?"

## Resposta

Para o cliente **Gold**, o SLA de resolução depende do tipo de chamado:

- **Chamados gerais:** resolução em até **24h úteis**
- **Incidentes críticos:** resolução em até **4h**

*Fonte: SLA-2024 — Tabela de SLA por Tipo de Cliente, seções 2 e 3.*

## Observação importante sobre a recuperação

O trecho recuperado no contexto dinâmico (Chunk B) contém apenas a linha de **chamados gerais**:

> "Cliente Gold — resposta em até 2h, resolução em até 24h."

Respondendo só por esse chunk, o assistente diria "24h" — correto, porém **incompleto**. O documento completo (SLA-2024) mostra que o Gold também tem um SLA de **4h** para incidentes críticos.

Como o atendente perguntou de forma genérica ("qual o SLA de resolução"), sem qualificar o tipo de chamado, a resposta segura é apresentar os **dois** prazos. Omitir o prazo de incidente crítico pode levar a uma violação de SLA — lembrando que, segundo a seção 5 da SLA-2024, o relógio de incidentes críticos de clientes Gold **não pausa** fora do horário comercial.
