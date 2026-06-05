# Resultados dos testes e análise — Pipeline de RAG NovaTech (Exercício 1.3)

Stack: Python + ChromaDB (cosseno) + sentence-transformers (`all-MiniLM-L6-v2`).
Recuperação: top-5 por pergunta. Gabarito: mapa de cobertura do Anexo B.

> **Conclusão de uma linha:** o pipeline roda e recupera, mas acerta plenamente
> só **4 das 10** perguntas. As 6 falhas não são "bugs" — são propriedades do
> *retrieval* que comprovam que **RAG é engenharia de dados**: chunking, escolha
> de modelo e governança de fontes decidem a resposta antes de o LLM existir.

---

## Item 2 — Resultados dos 10 testes vs. gabarito

| # | Pergunta | Top-1 recuperado (sim) | Esperado (must) | Veredito |
|---|----------|------------------------|-----------------|----------|
| 1 | Qual o prazo de devolução? | POL-001 › 3.5 Custos (0.633) | POL-001-A, POL-001-B | ❌ não recuperou POL-001-B |
| 2 | Posso devolver carga perigosa? | FAQ › Item 22 *seguro* (0.585) | POL-001-B | ❌ política oficial não apareceu |
| 3 | Qual o SLA do cliente Gold? | SLA › 5 Medição (0.560) | SLA-2024-B | ❌ tabela de SLA não recuperada |
| 4 | Qual o SLA do cliente Platinum? | FAQ › Item 15 (0.599) | SLA-2024-A | ✅ OK (must em #2) |
| 5 | Frete 600kg para Manaus? | PROC-v1 › 1 Objetivo (0.484) | PROC-042v2-A/B | ❌ multiplicadores v2 não recuperado |
| 6 | Frete 300kg para Salvador? | FAQ › Item 27 *tracking* (0.459) | (nenhum) | ⚠️ recuperou ruído acima do limiar |
| 7 | O que acontece com carga danificada? | FAQ › Item 38 (0.685) | FAQ-38 | ✅ OK no topo |
| 8 | Carga perigosa com frete expresso? | FAQ › Item 32 (0.655) | FAQ-32 | ✅ OK no topo |
| 9 | Qual o multiplicador para o Sudeste? | PROC-v2 › 2.1 (0.535) | PROC-042v2-B | ✅ OK no topo (mas ver Problema 2) |
| 10 | Devolução + carga perigosa + frete (multi) | FAQ › Item 22 (0.643) | 4 chunks (2 docs) | ❌ cobriu só parte dos domínios |

Placar: **4 OK, 6 falhas/atenção.**

---

## Análise dos achados

### O que funcionou
As perguntas 7 e 8 acertaram no topo porque a FAQ é escrita em forma de pergunta,
e a pergunta do usuário é quase idêntica ao título do item — alta similaridade
"barata". A pergunta 4 (Platinum) também acertou e é o melhor caso de **guardrail**:
recuperou tanto a FAQ Item 15 quanto a classificação do SLA, dando ao LLM o
contexto para responder que o tier Platinum **não existe**, em vez de inventar.

### O que falhou (e por quê)
As falhas têm três causas-raiz, que viram os problemas do item 4 abaixo.

---

## Item 4 — Problemas encontrados e correções concretas

### Problema 1 — A FAQ informal "engole" os documentos oficiais (o mais grave)
**Evidência:** na pergunta 2 ("Posso devolver carga perigosa?"), o chunk #1 é a
FAQ Item 22 sobre *seguro de carga* (0.585) — irrelevante — e a **política oficial
POL-001 não aparece em nenhum dos 5**. Pior: a FAQ Item 3 que é recuperada diz
literalmente *"oficialmente não pode... mas já tiveram casos em que autorizaram
exceção"*. Ou seja, **orientação informal e não-normativa é recuperada no lugar
da política oficial.** Causa: a FAQ é redigida em forma de pergunta, ficando
semanticamente mais próxima das perguntas dos usuários do que o texto formal das
políticas.
**Correção concreta:**
1. Adicionar metadado `autoridade` na ingestão (`oficial` para POL/SLA/PROC,
   `faq` para a FAQ).
2. Aplicar **reranking** que privilegia fontes oficiais, ou consultar a FAQ só
   como fallback quando nenhuma fonte oficial passar do limiar.
3. Prefixar no chunk a natureza da fonte (ex: `[FONTE OFICIAL]` / `[FAQ INTERNA]`)
   para que o LLM saiba distinguir norma de prática informal.

### Problema 2 — Contradição entre versões não tratada
**Evidência:** na pergunta 9 ("multiplicador do Sudeste"), o #1 é a v2 vigente
(0.535) mas o #2 é a **v1 antiga** (0.522), praticamente empatados. As duas dão
valores contraditórios (v2=1.0 vs antiga=1.1) e **ambas entram no contexto**. Na
pergunta 5 (600kg Manaus), a v1 antiga ("1. Objetivo", 0.484) chega a ficar
**acima** da v2. O pipeline não tem noção de versão.
**Correção concreta:**
1. Não indexar documentos superados: filtrar na ingestão por um campo `status`
   (`vigente`/`obsoleto`), ou simplesmente não colocar o arquivo v1 na pasta.
2. Se ambos precisam coexistir, gravar `versao` no metadado e, na busca,
   descartar a versão antiga quando existir uma mais recente da mesma família.

### Problema 3 — Limiar de similaridade mal calibrado (ruído entra no contexto)
**Evidência:** na pergunta 6 ("Frete 300kg Salvador"), que **não está documentada**
(frete < 500kg), o sistema deveria retornar vazio, mas recuperou a FAQ Item 27
sobre *tracking* (0.459) acima do `MIN_SIM=0.30`. O script acusou a anomalia
automaticamente. Os scores do corpus se concentram entre 0.40 e 0.68, então 0.30
quase não filtra nada.
**Correção concreta:**
1. Subir o limiar para ~0.50 (separa o ruído de 0.459 dos acertos legítimos de
   0.55–0.68), aceitando o trade-off precisão/recall.
2. Melhor ainda, usar um critério **relativo**: descartar chunks cujo score seja
   muito inferior ao do #1 (ex: < 80% do topo), o que se adapta a perguntas com
   distribuições de score diferentes.

### Problema 4 (raiz transversal) — Embeddings fracos em português
**Evidência:** os melhores matches semânticos batem só ~0.63–0.68, baixo para
perguntas que casam quase literalmente com o conteúdo; e perguntas formais
(SLA Gold, frete) ficam todas amontoadas em ~0.48–0.56, sem separação clara entre
relevante e ruído. Isso é típico do `all-MiniLM-L6-v2`, treinado majoritariamente
em inglês. Essa baixa separação é o que **agrava** os Problemas 1 e 3.
**Correção concreta:** trocar `MODEL_NAME` para
`paraphrase-multilingual-MiniLM-L12-v2` em `ingest.py` e `search.py` e reindexar
(`python ingest.py`). É gratuito, roda local, e tende a espalhar melhor os scores.

### Problema 5 — Tabela cortada no meio (corrigido durante o desenvolvimento)
A primeira versão do chunker exigia quebra de linha antes do primeiro `|`, então
tabelas que começavam logo após o título eram partidas em dois chunks (cabeçalho
separado do corpo). **Correção (já aplicada):** detecção por agrupamento de linhas
consecutivas com `|`, garantindo a tabela inteira num chunk atômico (`type=table`).

---

## Item 3 — Geração no chat (a preencher)

Para fechar o item 3, rode `python prompt_builder.py "<pergunta>"`, cole o prompt
no chat do Claude e registre, para cada uma das 5 perguntas:

| Pergunta | Resposta correta? | Citou fonte? | Respeitou guardrail? | Observação |
|----------|-------------------|--------------|----------------------|------------|
| (1) | | | | |

**Teste de guardrail recomendado:** use a pergunta 6 (Frete 300kg Salvador). Como
não há resposta nos documentos, o LLM deve responder *"Não encontrei essa
informação nos documentos disponíveis"* em vez de inventar. Também observe na
pergunta 1 se o LLM, ao receber as duas versões de prazo de frete (v1 +2 dias e
v2 +3 dias), percebe a contradição ou repete uma delas cegamente.
