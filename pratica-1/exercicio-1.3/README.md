# Pipeline de RAG — NovaTech (Exercício 1.3)

Prova de conceito de um pipeline de **RAG (Retrieval-Augmented Generation)**
100% open-source e gratuito: ingere documentos, gera embeddings, armazena num
vector store local e monta prompts para um LLM responder com base nos documentos.

> **Princípio do exercício:** RAG é um sistema de **engenharia de dados**, não
> apenas uma chamada de API. A qualidade da resposta é decidida no chunking e na
> recuperação — se o chunk certo não chega ao prompt, nenhum LLM salva a resposta.

---

## Stack

| Camada | Ferramenta | Por quê |
| --- | --- | --- |
| Linguagem | Python 3.10+ | padrão do ecossistema |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) | gratuito, roda local, offline após o 1º download |
| Vector store | `ChromaDB` (persistente, local) | gratuito, sem servidor, métrica cosseno nativa |
| Geração | Claude via chat (cola o prompt) ou Ollama local | sem custo de API |

Tudo roda offline depois que o modelo de embeddings é baixado uma vez (~90 MB).

---

## Estrutura dos arquivos

```
rag_novatech/
├── anexo-documentos/   <- documentos
├── chunking.py        <- estratégia de chunking (o "cérebro" do pipeline)
├── ingest.py          <- ETAPA 1: lê docs, cria chunks/embeddings, salva no ChromaDB
├── search.py          <- ETAPA 2: busca os N chunks mais similares + score
├── prompt_builder.py  <- ETAPA 3: monta o prompt (system + contexto + pergunta)
├── test_rag.py        <- roda as 5 perguntas de teste e compara com o gabarito
├── requirements.txt
└── README.md
```

---

## Como executar (passo a passo)

### 1. Coloque os documentos

Copie os **5 arquivos `.md` do Anexo A** para dentro da pasta
`anexo-a-documentos-individuais/`. O pipeline lê todos os `.md` que encontrar lá.

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

(Na primeira execução, o `sentence-transformers` baixa o modelo. Precisa de
internet só nessa primeira vez.)

### 3. Construa o índice (ingestão)

```bash
python ingest.py
```

Saída esperada: o número de chunks por documento e o total indexado. Cria a pasta
`chroma_db/` com o vector store persistido. Rodar de novo recria do zero (não
duplica).

### 4. Teste a busca

```bash
python search.py "Qual é o prazo de garantia dos produtos?"
```

Mostra os 4 chunks mais similares, cada um com documento, seção e **score de
similaridade** (0 a 1, quanto maior melhor).

### 5. Gere o prompt para o LLM

```bash
python prompt_builder.py "Qual é o prazo de garantia dos produtos?"
```

Imprime o prompt completo (system + contexto + pergunta).

### 6. Obtenha a resposta (geração)

**Copie a saída do passo 5 e cole no chat do Claude.** A resposta deve:
estar correta segundo os documentos, citar a fonte, e — se a info não existir no
contexto — recusar inventar (guardrail).

> Alternativa local e gratuita: `ollama run llama3` e cole o mesmo prompt.

---

## Como fazer perguntas (resumo rápido)

- **Uma pergunta avulsa:** `python prompt_builder.py "sua pergunta"` → cole no chat.
- **Só ver os chunks recuperados:** `python search.py "sua pergunta"`.
- **Rodar a bateria de 5 testes:** edite a lista `PERGUNTAS` em `test_rag.py` com
  perguntas do Anexo B e rode `python test_rag.py`.

---

## Estratégia de chunking (justificativa — critério de avaliação)

**Decisão: chunking estrutural (header-aware) com fallback de tamanho e tabelas atômicas.**

Os inputs são Markdown, que já trazem estrutura semântica explícita (títulos,
parágrafos, tabelas). Essa estrutura marca, de graça, as unidades de significado
do texto. Por isso:

1. **Divisão por seção (header).** Cada `#`/`##` inicia um novo chunk. O resultado
   é um chunk = uma unidade de significado coerente e auto-contida. Isso supera o
   corte cego por "N tokens fixos", que separa o cabeçalho do conteúdo e quebra o
   raciocínio no meio.
2. **Tabelas atômicas.** Linhas consecutivas de tabela são agrupadas num único
   chunk (`type: table`), nunca cortadas. Resolve por construção o problema de
   "tabela cortada no meio".
3. **Overlap em seções longas.** Seções que excedem ~1200 caracteres são
   subdivididas respeitando limites de parágrafo, com sobreposição de ~150
   caracteres, para não perder contexto na borda entre dois chunks.
4. **Header prefixado ao texto.** Cada chunk começa com `[Seção: ...]`. Isso
   injeta o tópico no embedding (melhora a recuperação) e serve de fonte para
   citação.

Em uma frase: *recuperação por relevância funciona melhor quando cada chunk é uma
unidade de significado auto-suficiente, e o Markdown já marca essas unidades —
ignorá-las seria jogar fora informação grátis.*

---

## Documentação dos testes (item 2 — template)

Para cada pergunta, preencha:

| Pergunta | Chunks recuperados (doc › seção) | Score (sim.) | Chunk esperado (Anexo B) | Veredito |
| --- | --- | --- | --- | --- |
| (pergunta 1) | #1 ... / #2 ... | 0.78 / 0.55 | (doc/seção do gabarito) | ✅ topo / ⚠️ em #2 / ❌ não recuperou |

O `test_rag.py` já calcula o veredito automaticamente se você preencher o dicionário
`GABARITO`. Inclua na entrega os screenshots/saídas reais.

**Dica de guardrail:** inclua uma 6ª pergunta cuja resposta **não** exista nos
documentos. O LLM deve responder "não encontrei essa informação", não alucinar.

---

## Problemas encontrados e correções (item 4)

### Problema 1 — Tabela cortada no meio (BUG real, encontrado durante o desenvolvimento)
A primeira versão do detector de tabelas exigia uma quebra de linha antes do
primeiro `|`. Quando a tabela começava logo após o título (sem linha em branco),
o cabeçalho da tabela virava um chunk e o resto virava outro — a tabela era
partida em dois.
**Correção (já aplicada):** trocar a detecção por regex por um agrupamento de
linhas consecutivas que contêm `|`, garantindo que a tabela inteira fique num
único chunk atômico. Validado: a tabela de prazos de reembolso agora sai inteira.

### Problema 2 — Modelo de embeddings fraco em português
`all-MiniLM-L6-v2` é treinado majoritariamente em inglês. Com documentos e
perguntas em PT, ele capta sinônimos e paráfrases de forma mais fraca, podendo
recuperar o chunk vizinho em vez do exato.
**Correção concreta:** trocar `MODEL_NAME` em `ingest.py` e `search.py` por
`paraphrase-multilingual-MiniLM-L12-v2` (gratuito, local, bem melhor em PT).
Depois, rodar `python ingest.py` de novo para reindexar.

### Problema 3 — Sem limiar de similaridade (ruído no contexto)
A busca sempre devolve N chunks, mesmo que o melhor tenha similaridade baixa
(ex: 0.15), poluindo o prompt com ruído irrelevante e aumentando o risco de
alucinação.
**Correção (já implementada):** o parâmetro `min_similarity` em `search()` e
`build_prompt()` filtra chunks abaixo de um limiar. Ex:
`build_prompt(pergunta, min_similarity=0.3)`. Se nada passar, o contexto fica
vazio e o guardrail "não encontrei" atua.

---

## Evidência do GitHub Copilot

O código foi escrito no estilo "comentário/docstring primeiro, Copilot completa".
Para a entrega, capture 2–3 screenshots do Copilot sugerindo implementações
(ex: a função `_split_long_text`, ou a conversão de distância em similaridade
`1 - dist` em `search.py`). Guarde os prints como anexo do entregável.
