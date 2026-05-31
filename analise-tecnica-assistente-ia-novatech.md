# Análise Técnica — Assistente de IA para Atendimento (NovaTech)

**Cliente:** NovaTech (Logística — 1.200 funcionários)
**Executor:** DB1
**Documento:** Análise técnica de viabilidade e arquitetura do pipeline de RAG
**Autoria:** Análise de IA Sênior
**Data:** Maio/2026
**Escopo desta análise:** ingestão e tratamento das fontes documentais, dimensionamento da base em tokens, orçamento de contexto do LLM e estratégia de chunking/retrieval. Não cobre (ainda) integração de identidade, controle de acesso por documento, nem plano de avaliação contínua — tratados em entregáveis posteriores.

---

## 1. Sumário executivo

A NovaTech quer reduzir o tempo médio de busca de informação por chamado de 12 para menos de 2 minutos, atendendo a ~192 chamados/dia que envolvem consulta documental (60% dos 320 diários). A abordagem tecnicamente adequada é um sistema de **RAG (Retrieval-Augmented Generation)** sobre as três fontes existentes (SharePoint, Confluence e a pasta de planilhas), servido dentro do ecossistema Microsoft que a empresa já possui.

Três conclusões orientam o restante do documento. Primeiro, a base é grande demais para qualquer abordagem que não seja RAG: estimamos cerca de **6,3 milhões de tokens**, aproximadamente 49 vezes a janela de contexto do GPT-4o. Segundo, o gargalo de qualidade **não** é o tamanho da janela de contexto — cabem mais de 200 chunks por consulta —, e sim a precisão da recuperação e o efeito *lost in the middle*; encher a janela degrada a resposta em vez de melhorá-la. Terceiro, e mais crítico para esta operação em específico, o maior risco de qualidade não é técnico de pipeline, e sim de **governança documental**: a base contém documentos que se contradizem (PROC-042 v1 vs. v2) e um FAQ explicitamente não validado. Sem metadados de autoridade e vigência por chunk, o assistente recuperará e citará a versão errada de uma tabela de frete — um erro com consequência contratual e financeira direta.

A boa notícia é que a stack já disponível (Microsoft 365 E3 + Azure AI Services) cobre todas as necessidades: Azure AI Search para indexação híbrida e re-ranqueamento, Azure AI Document Intelligence para extração layout-aware e OCR, Azure OpenAI para embeddings e geração, e Teams como superfície de atendimento.

---

## 2. Arquitetura de referência (visão resumida)

Para fundamentar as decisões técnicas, assumimos o seguinte fluxo, todo dentro do tenant Azure da NovaTech:

A **ingestão** lê cada fonte com o conector apropriado (Graph API/SharePoint, REST do Confluence, leitura de arquivos da pasta de rede), normaliza o conteúdo, aplica extração específica por tipo de documento (Seção 3), gera chunks com metadados (Seção 6) e os indexa no Azure AI Search com embeddings do `text-embedding-3-large`. A **consulta** recebe a pergunta do atendente no Teams, recupera candidatos por busca híbrida (vetorial + léxica), re-ranqueia, monta o contexto e chama o GPT-4o no Azure OpenAI, que responde citando as fontes. A reindexação é disparada mensalmente (ou por evento de alteração) para acompanhar as atualizações das três áreas.

O restante do documento detalha os pontos onde decisões erradas comprometem a qualidade.

---

## 3. Desafios por tipo de fonte no pipeline de RAG

Cada tipo de documento da NovaTech impõe um desafio distinto de extração. A regra geral é que **a recuperação só pode ser tão boa quanto a extração**: um chunk mal extraído na ingestão é um erro que nenhuma melhoria posterior de retrieval consegue corrigir.

### 3.1. PDFs com tabelas

O caso mais sensível para esta operação, porque boa parte da informação acionável da NovaTech vive em tabelas: os multiplicadores regionais da PROC-042, a matriz de SLA por tier, os fatores de peso. Extratores de texto convencionais (PyPDF, pdfminer) linearizam a tabela, lendo célula a célula sem preservar a relação linha-coluna. Uma linha como "Norte | 1.8" pode virar texto solto onde a região se desassocia do valor, ou pior, linhas de tabelas adjacentes se intercalam. O chunking ingênuo agrava o problema ao cortar uma tabela no meio, separando o cabeçalho dos dados.

O **impacto na qualidade** é severo e silencioso: o modelo recebe "Norte" e "1.8" no contexto, mas sem a estrutura que os liga, e pode parear a região com o multiplicador errado. Em uma transportadora, isso significa um valor de frete incorreto entregue como se fosse oficial — um erro de número, não de redação, que o atendente provavelmente não detecta.

**Estratégia de tratamento:** usar extração *layout-aware* (Azure AI Document Intelligence, modelo Layout), que reconhece tabelas e as exporta em formato estruturado (Markdown ou HTML), preservando linhas e colunas. Cada tabela deve ser tratada como **chunk atômico** — nunca dividida no meio. Quando uma tabela for grande demais para um único chunk, replicar a linha de cabeçalho e a legenda em cada fragmento, para que cada chunk carregue seu próprio contexto. Armazenar a tabela em Markdown também ajuda na geração, porque o LLM lê tabelas em Markdown nativamente.

### 3.2. PDFs escaneados (sem camada de texto)

Documentos digitalizados — procedimentos assinados, políticas antigas, anexos legados — não têm camada de texto extraível. São imagens raster. Um extrator de texto retorna vazio ou ruído.

O **impacto na qualidade** é o mais perigoso de todos justamente por ser invisível: o documento simplesmente não existe para a recuperação. O assistente responde com confiança sobre o que conseguiu indexar, sem nunca saber que havia um documento relevante que ficou de fora. Isso é pior que uma resposta errada, porque nem o atendente nem o sistema percebem a lacuna.

**Estratégia de tratamento:** detectar PDFs sem camada de texto na ingestão (página sem texto extraível, ou predominância de objetos de imagem) e roteá-los para uma etapa de **OCR** (Document Intelligence, modelo Read). Registrar a confiança do OCR como metadado e definir um limiar abaixo do qual o documento entra em fila de revisão humana — especialmente para documentos normativos (POL/PROC). Recomenda-se um relatório de cobertura de ingestão que liste documentos com texto vazio ou OCR de baixa confiança, para que o problema deixe de ser silencioso.

### 3.3. Wiki com links (Confluence)

Páginas de wiki carregam significado nos hyperlinks e nas referências cruzadas ("ver PROC-043"), além de macros do Confluence (*include*, *excerpt*) que injetam conteúdo de outras páginas dinamicamente e de uma hierarquia de páginas-filhas. Um *scraping* de HTML achatado perde o grafo de links: um chunk diz "o procedimento está descrito aqui [link]", mas o conteúdo de fato mora em outra página.

O **impacto na qualidade** é o contexto incompleto. A recuperação traz o ponteiro, mas não o alvo; a resposta fica truncada ou o modelo preenche a lacuna alucinando o conteúdo do link.

**Estratégia de tratamento:** ingerir via **API REST do Confluence** (não scraping de HTML renderizado), obtendo o conteúdo em *storage format* limpo mais os metadados de página. Expandir macros de *include*/*excerpt* no momento da ingestão, de modo que o chunk contenha o conteúdo efetivo, não a referência. Preservar a hierarquia (espaço > página-pai > página) como metadado para filtragem, e guardar os IDs de páginas-alvo dos links internos como metadado, habilitando expansão por grafo no momento da recuperação (recuperar também a página referenciada quando um chunk a cita).

### 3.4. Planilhas com fórmulas (referências mensais)

As planilhas da pasta de rede têm dois problemas combinados. Primeiro, células podem ser calculadas por fórmulas: extrair o texto da fórmula (`=B2*1.3`) não diz nada ao LLM — é preciso o valor avaliado. Há ainda múltiplas abas, células mescladas e cabeçalhos que ocupam várias linhas. Segundo, e mais importante, **são atualizadas mensalmente** — é justamente aqui que mora a "tabela mensal de fretes" que a PROC-042 usa como valor base. Dados tabulares numéricos também embeddam mal: o vetor semântico de uma linha de números é pouco discriminante.

O **impacto na qualidade** tem duas faces. Se você indexar a string da fórmula, a recuperação é inútil. E se não reindexar mensalmente, o assistente cita uma tarifa vencida — entregando uma cotação de frete errada com aparência de oficial.

**Estratégia de tratamento:** avaliar as fórmulas e extrair os **valores calculados** (por exemplo, `openpyxl` com `data_only=True` sobre um arquivo já recalculado). Converter cada linha relevante em um "fato" em linguagem natural ou registro estruturado ("Tarifa base região Norte, vigência maio/2026: R$ X"), que embedda muito melhor que uma linha crua de números. Para dados de preço voláteis, considerar **não** colocá-los no índice vetorial e sim expô-los por uma ferramenta de consulta estruturada (uma função de lookup ou *text-to-SQL* que o LLM chama), garantindo que o número esteja sempre atual em vez de depender da última reindexação. Em qualquer caso, automatizar a reingestão atrelada à atualização mensal do arquivo.

### 3.5. Síntese dos desafios

| Fonte | Desafio central | Risco para a resposta | Estratégia |
|-------|-----------------|------------------------|------------|
| PDF com tabelas | Estrutura linha-coluna perdida na extração | Pareamento errado de valores (frete/SLA) | Extração layout-aware; tabela como chunk atômico; Markdown |
| PDF escaneado | Sem texto extraível | Lacuna silenciosa — documento invisível ao retrieval | OCR com limiar de confiança; relatório de cobertura |
| Wiki com links | Grafo de links e macros perdidos | Contexto incompleto; alucinação do conteúdo linkado | API REST; expandir macros; links como metadado |
| Planilha com fórmulas | Fórmula ≠ valor; dados voláteis mensais | Recuperação inútil ou tarifa vencida | Avaliar valores; virar "fato" textual ou ferramenta de lookup; reingestão mensal |

---

## 4. Estimativa do tamanho da base em tokens

Aplicando a regra prática de **~0,75 palavra por token** (ou seja, 1 token ≈ 0,75 palavra, logo `tokens = palavras ÷ 0,75`):

**Premissas declaradas.** Para os PDFs, adotamos **500 palavras por página**, valor típico de uma página de texto corrido; documentos com muitas tabelas e espaços em branco tendem a ter menos, então este número é conservador (tende a superestimar). Para as planilhas, não há contagem de palavras fornecida; adotamos **~2.000 palavras-equivalente por planilha** ao serializá-las em texto — é a estimativa mais frágil das três, mas seu peso no total é pequeno.

| Fonte | Cálculo de palavras | Palavras | Tokens (÷ 0,75) |
|-------|---------------------|----------|------------------|
| PDFs (SharePoint) | 800 docs × 10 pág. × 500 | 4.000.000 | ~5.333.000 |
| Wiki (Confluence) | 400 pág. × 1.500 | 600.000 | ~800.000 |
| Planilhas | 50 × ~2.000 | 100.000 | ~133.000 |
| **Total** | — | **4.700.000** | **~6.267.000** |

**A base tem aproximadamente 6,3 milhões de tokens** (faixa razoável de 6 a 7 milhões, considerando a incerteza das premissas). O corpus efetivamente indexado será um pouco maior, porque o chunking com sobreposição duplica parte do texto nas bordas e cada chunk carrega metadados.

**Implicações imediatas:**

- **RAG é obrigatório, não opcional.** 6,3M tokens são ~49× a janela de 128K do GPT-4o. Não há cenário em que a base inteira entre no contexto; a qualidade depende inteiramente de selecionar os poucos chunks certos.
- **Custo de embedding é baixo e pontual.** Vetorizar ~6,3M tokens uma vez é uma operação barata com `text-embedding-3`. O custo recorrente relevante é reembeddar mensalmente apenas a fração que muda, não a base toda.
- **O índice é dominado pelos PDFs** (85% dos tokens). É onde o esforço de qualidade de extração (Seção 3.1 e 3.2) tem maior retorno.

---

## 5. Análise do orçamento de contexto

O GPT-4o tem janela de **128K tokens**, e o system prompt + instruções consomem ~2K. A pergunta direta — quantos chunks de ~500 tokens cabem — tem uma resposta literal e uma resposta de engenharia.

**Resposta literal:** `(128.000 − 2.000) ÷ 500 = 252 chunks`.

**Por que 252 é uma resposta enganosa.** A janela de 128K é compartilhada entre *entrada e saída*, e o orçamento real precisa reservar espaço para o que o número ingênuo ignora:

| Componente | Tokens reservados |
|------------|-------------------|
| System prompt + instruções | ~2.000 |
| Instruções de citação / formato de resposta | ~1.000 |
| Histórico de conversa (multi-turno) | ~6.000 |
| Resposta gerada (saída) | ~4.000 |
| Margem de segurança | ~1.000 |
| **Total reservado** | **~14.000** |
| **Disponível para chunks** | **~114.000 → ~228 chunks** |

Ou seja, mesmo com reservas realistas, ainda caberiam mais de 200 chunks. **O tamanho da janela não é o gargalo.** O gargalo é a Seção seguinte: encher o contexto com 228 chunks piora a resposta, por três razões.

Primeiro, **diluição de sinal**: a maioria desses 228 chunks será irrelevante para a pergunta específica, e cada chunk irrelevante compete por atenção com os poucos que importam. Segundo, **lost in the middle**: a capacidade do modelo de usar uma informação cai quando ela está no meio de um contexto longo — colocar 228 chunks garante que a maioria do material útil caia exatamente na zona de pior recuperação. Terceiro, **custo e latência**: pagar por ~114K tokens de entrada em cada consulta, multiplicado por ~192 chamados/dia com possíveis múltiplas perguntas cada, é caro e lento sem ganho de qualidade — o custo de entrada cresce linearmente com o número de chunks.

**Recomendação de ponto de operação:** recuperar um conjunto amplo de candidatos (50–100), **re-ranquear**, e enviar ao modelo apenas **8 a 15 chunks** (~4.000 a 7.500 tokens). Esse é o intervalo onde a precisão de recuperação, o efeito *lost in the middle* e o custo se equilibram. O objetivo do orçamento de contexto não é maximizar quantos chunks cabem, e sim minimizar quantos chunks são necessários para responder bem.

---

## 6. Estratégia de chunking e retrieval

A estratégia de chunking deve derivar de **dois fatos**: o tipo de pergunta que o atendente faz e o efeito *lost in the middle*.

### 6.1. Que perguntas o atendente realmente faz

Pelos documentos fornecidos, as perguntas são majoritariamente **factuais e pontuais**, não pedidos de resumo amplo:

- "Qual o multiplicador de frete para o Norte?" (lookup em célula de tabela)
- "Qual o prazo para solicitar devolução?" (cláusula específica de política)
- "Existe tier Platinum?" (fato pontual)
- "Qual o SLA de resolução do Gold em incidente crítico?" (célula de matriz)
- "Como calculo o frete de uma carga de 2.000kg para o Nordeste?" (pergunta composta: fórmula + fator de peso + multiplicador regional, possivelmente + desconto)

Essa distribuição tem uma consequência clara: o usuário quase nunca quer "todo o documento POL-001"; quer **a passagem ou a tabela exata** que responde. Isso favorece chunks **menores e semanticamente coesos**, que recuperam com precisão e não arrastam texto irrelevante para o contexto. Chunks gigantes prejudicariam tanto a precisão da recuperação quanto a atenção do modelo.

### 6.2. Recomendação de chunking

**Chunking estrutural/semântico, não janela fixa de 500 tokens.** Os documentos da NovaTech são bem estruturados em seções (`##`), o que é uma vantagem a explorar:

- Quebrar por **seção/heading**, com alvo de **~300 a 600 tokens** por chunk e sobreposição pequena (~10–15%, ~50–75 tokens) para preservar continuidade entre fragmentos vizinhos.
- **Tabelas como chunks atômicos** (reforçando a Seção 3.1): nunca cortar uma tabela; replicar cabeçalho e legenda se precisar fragmentar.
- **Procedimentos numerados** (como a Seção 3.3 da POL-001) mantidos inteiros quando possível, porque os passos só fazem sentido em conjunto.
- **Cabeçalho contextual em cada chunk** (técnica de *contextual retrieval*): pré-anexar ao texto do chunk, antes de embeddar, o título do documento, o caminho da seção, a versão, a data de vigência e o status/autoridade. Isso melhora a recuperação e dá ao modelo a procedência necessária para **citar a fonte** — requisito explícito do projeto.

### 6.3. Retrieval e *lost in the middle*

Como o ponto de operação é de poucos chunks (Seção 5), a estratégia de recuperação precisa garantir que esses poucos sejam os certos e estejam bem posicionados:

- **Busca híbrida (vetorial + léxica/BM25).** Muitas perguntas contêm termos exatos — "PROC-042", "Gold", "CT-e", "Norte" — onde a correspondência léxica importa tanto quanto a semântica. O Azure AI Search oferece busca híbrida nativamente, o que se encaixa na stack Microsoft existente.
- **Re-ranqueamento** dos candidatos recuperados (cross-encoder / *semantic ranker* do Azure AI Search) antes de montar o contexto, elevando a precisão do conjunto final de 8–15 chunks.
- **Posicionamento em U.** Como a atenção do modelo é melhor no início e no fim do contexto e pior no meio, o chunk mais relevante deve ser posicionado no **começo ou no fim**, deixando os menos críticos no meio. Com k pequeno (8–15), a "zona morta" do meio praticamente desaparece — esta é a defesa mais simples contra *lost in the middle*: manter o contexto curto o bastante para não ter um meio problemático.

### 6.4. Metadados de governança — o ponto crítico para esta operação

Esta é a recomendação de maior impacto e a mais específica da NovaTech. A base contém documentos que **se contradizem sem hierarquia formal**:

- PROC-042 v1 e v2 coexistem no SharePoint "sem hierarquia clara", com multiplicadores e prazos diferentes (Norte 1.6 vs. 1.8; +2 vs. +3 dias úteis), e ainda uma **regra de transição por data** (chamados antes/depois de 01/12/2023 usam tabelas diferentes).
- O FAQ é **explicitamente não validado** por Compliance/Operações e pode conter informação desatualizada — ele próprio avisa para confirmar na documentação normativa.

Se v1 e v2 forem chunkados e embeddados com peso igual, a recuperação pode trazer a tabela errada, e o assistente entrega um multiplicador desatualizado como se fosse oficial — um erro de consequência contratual. Nenhuma sofisticação de chunking resolve isso sozinha; é preciso **metadado de autoridade e vigência por chunk**:

- Campos como `status` (normativo / informal / obsoleto), `versao`, `vigencia_inicio`, `vigencia_fim`, `area_responsavel` e `classificacao` (contratual / informativo).
- **Ranqueamento e filtragem por autoridade e recência** no retrieval: preferir documento normativo sobre FAQ informal, e versão vigente sobre versão antiga, quando ambos respondem à pergunta.
- **Instrução ao modelo no system prompt** para sinalizar conflitos quando houver ("a PROC-042 tem duas versões; a regra de transição depende da data do chamado") em vez de escolher silenciosamente — preservando o comportamento humano atual de "perguntar para quem sabe", mas tornando-o explícito e rastreável.

Sem essa camada, o assistente automatiza e amplifica exatamente a inconsistência que o projeto pretende eliminar. Com ela, o sistema passa a ser mais consistente que o processo manual atual.

---

## 7. Riscos e próximos passos

O principal risco do projeto não é a tecnologia de RAG, que é madura e bem suportada pela stack existente — é a **qualidade e a governança da fonte**. Recomenda-se, no discovery, priorizar três frentes: (1) um diagnóstico de cobertura de ingestão que quantifique quantos dos 800 PDFs são escaneados e quantas tabelas existem, pois isso dimensiona o esforço de extração; (2) a definição, junto a Operações/Compliance/Comercial, do esquema mínimo de metadados de autoridade e vigência, sem o qual o problema de contradição persiste; e (3) um conjunto de perguntas de avaliação (*golden set*) extraído de chamados reais, para medir objetivamente se a meta de qualidade e de tempo (de 12 para <2 min) está sendo atingida antes do go-live.

A meta de tempo é factível: a maior parte dos 12 minutos atuais é busca manual em três fontes não unificadas, exatamente o que o RAG elimina. O risco residual está em respostas confiantes porém erradas por conflito de versão — endereçado pela camada de governança da Seção 6.4, que por isso deve ser tratada como requisito, não como melhoria opcional.
