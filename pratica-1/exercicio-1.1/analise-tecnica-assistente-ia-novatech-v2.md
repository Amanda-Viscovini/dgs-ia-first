# Análise Técnica — Assistente de IA para Atendimento (NovaTech)

**Cliente:** NovaTech (Logística — 1.200 funcionários)
**Executor:** DB1
**Documento:** Análise técnica de viabilidade e arquitetura do pipeline de RAG
**Autoria:** Análise de IA Sênior
**Data:** Maio/2026
**Revisão:** v2 — revisão crítica sênior. Os ajustes desta passagem estão consolidados em §0 e distribuídos pelas seções correspondentes.
**Escopo desta análise:** ingestão e tratamento das fontes documentais, dimensionamento da base em tokens, orçamento de contexto do LLM e estratégia de chunking/retrieval. **Itens deferidos com ressalva (ver §0 e §7):** integração de identidade, controle de acesso por documento (*security trimming*), conformidade LGPD e plano de avaliação contínua. Estes itens estão fora do detalhamento técnico deste documento, mas **dois deles — controle de acesso e LGPD — são pré-condições de go-live, não entregáveis "posteriores" opcionais.** Tratá-los como pendência tardia é, por si só, um risco de projeto.

---

## 0. Nota de revisão crítica (resumo dos ajustes)

Esta seção lista, de forma direta, os pontos que a revisão sênior considerou frágeis, otimistas demais ou ausentes na versão original. Cada item está endereçado na seção indicada.

**Estimativas/afirmações ajustadas por otimismo:**
- A meta "12 → <2 min" é factível, mas a versão original a tratava como quase garantida. O tempo de adoção, a desconfiança inicial do time e o tempo de *verificação* da fonte (que o próprio projeto exige) reintroduzem minutos. Meta realista: alcançável por etapas, não no go-live (§7).
- O prazo de **3 meses para discovery + desenvolvimento + go-live é agressivo** diante das incógnitas (quantos PDFs escaneados, esforço de OCR/revisão humana, e — sobretudo — a curadoria de metadados de governança). Recomenda-se go-live faseado (§7).
- "A boa notícia é que a stack cobre todas as necessidades": a stack cobre as necessidades **técnicas**. Não cobre as necessidades **organizacionais** (governança documental, controle de acesso, LGPD), que são onde o projeto realmente pode falhar.

**Riscos que não estavam considerados:**
- **Controle de acesso por documento (*security trimming*).** O SharePoint tem permissões por documento; um índice de RAG que as achata permite que um atendente recupere conteúdo que não deveria ver (contratos, preços de outros clientes, dados sensíveis). Requisito de go-live (§7).
- **LGPD/PII.** Empresa brasileira, documentos logísticos contêm dados de clientes (CT-e, valor declarado, endereços). O que é embeddado, logado e retido (inclusive prompts/respostas no Azure OpenAI) precisa de base legal e política de retenção (§7).
- **Cálculo aritmético pelo LLM.** Perguntas compostas de frete exigem que o modelo *faça contas* (base × multiplicador × fator de peso, + desconto, + regra de transição por data). LLMs erram aritmética de múltiplos passos. Isso precisa de ferramenta de cálculo determinística, não de "o modelo calcula no texto" (§6.1).
- **Comportamento de abstenção.** O que o assistente faz quando *não encontra* a resposta? Sem instrução explícita de abster-se ("não localizei na documentação"), ele alucina com confiança — o pior modo de falha para esta operação (§6.4, §7).
- **Dependência de curadoria de metadados que ainda não existe.** A mitigação mais crítica do projeto (§6.4) depende de metadados de autoridade/vigência que **nenhum documento possui hoje** e que precisam ser criados manualmente por 3 áreas sem processo unificado. É a maior dependência organizacional e um risco direto ao prazo (§6.4, §7).
- **Definição de qualidade e critério de aceite.** O sucesso estava medido só em *tempo*. Para esta operação, uma resposta rápida e errada (multiplicador de frete da versão errada) é pior que a busca manual. É preciso medir *groundedness*, precisão de recuperação e taxa de alucinação, com critério de aceite antes do go-live (§7).

---

## 1. Sumário executivo

A NovaTech quer reduzir o tempo médio de busca de informação por chamado de 12 para menos de 2 minutos, atendendo a ~192 chamados/dia que envolvem consulta documental (60% dos 320 diários). A abordagem tecnicamente adequada é um sistema de **RAG (Retrieval-Augmented Generation)** sobre as três fontes existentes (SharePoint, Confluence e a pasta de planilhas), servido dentro do ecossistema Microsoft que a empresa já possui.

Três conclusões orientam o restante do documento. Primeiro, a base é grande demais para qualquer abordagem que não seja RAG: estimamos cerca de **6,3 milhões de tokens**, aproximadamente 49 vezes a janela de contexto do GPT-4o. Segundo, o gargalo de qualidade **não** é o tamanho da janela de contexto — cabem mais de 200 chunks por consulta —, e sim a precisão da recuperação e o efeito *lost in the middle*; encher a janela degrada a resposta em vez de melhorá-la. Terceiro, e mais crítico para esta operação em específico, o maior risco de qualidade não é técnico de pipeline, e sim de **governança documental**: a base contém documentos que se contradizem (PROC-042 v1 vs. v2) e um FAQ explicitamente não validado. Sem metadados de autoridade e vigência por chunk, o assistente recuperará e citará a versão errada de uma tabela de frete — um erro com consequência contratual e financeira direta.

A stack já disponível (Microsoft 365 E3 + Azure AI Services) cobre todas as necessidades **técnicas** do pipeline: Azure AI Search para indexação híbrida e re-ranqueamento, Azure AI Document Intelligence para extração layout-aware e OCR, Azure OpenAI para embeddings e geração, e Teams como superfície de atendimento. O que a stack **não** resolve — e é onde o projeto pode efetivamente falhar — são as três frentes organizacionais: governança documental (a base se contradiz e ninguém arbitra), controle de acesso por documento e conformidade LGPD. Ferramenta madura não compensa fonte mal governada; ver §0 e §7.

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

**Ressalvas da revisão sobre este número.** Primeiro, a estimativa trata a base como **estática e única**, mas (a) ela cresce — bases documentais de logística aumentam com novas rotas, clientes e normas — e (b) ela já contém **duplicatas e versões redundantes** (PROC-042 v1 *e* v2 contam ambas), o que infla o total sem agregar informação útil. Segundo, **OCR adiciona ruído**: PDFs escaneados extraídos por OCR podem render mais tokens "lixo" do que páginas de texto limpo. Terceiro, e mais importante: **este número serve para dimensionar a inviabilidade de carregar tudo no contexto, não para estimar custo.** O custo relevante não é o tamanho da base (embedar 6,3M tokens uma vez é barato), e sim o custo recorrente de inferência por consulta × volume mensal — quantificado em §7.

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

**Ressalvas da revisão.** (1) A reserva de ~6.000 tokens para histórico assume conversas curtas; *threads* longas de troubleshooting com o cliente podem estourar isso — é preciso uma política de truncamento/sumarização de histórico, senão o orçamento de chunks encolhe na prática. (2) A "janela de 128K" é nominal; a qualidade efetiva de uso da informação degrada bem antes do limite, o que reforça (não contradiz) operar com k pequeno. (3) A análise fixa **GPT-4o** como dado; em maio/2026 o catálogo do Azure OpenAI já oferece modelos mais recentes e, possivelmente, mais baratos por token de entrada. A escolha de modelo deve ser uma decisão de discovery (custo × qualidade no *golden set*), com a arquitetura mantida agnóstica ao modelo — não um pressuposto.

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

**Ressalva crítica da revisão — perguntas que exigem cálculo.** A última categoria ("como calculo o frete de uma carga de 2.000kg para o Nordeste?") não é um problema de recuperação, é um problema de **execução**. Responder corretamente exige: (a) selecionar a *versão certa* da PROC-042 (v1 vs. v2), (b) aplicar a *regra de transição por data* do chamado, (c) buscar o valor base na planilha mensal vigente, e (d) **fazer a aritmética** `base × multiplicador × fator de peso (× desconto)`. LLMs são notoriamente não confiáveis em aritmética de múltiplos passos e podem "arredondar" ou inventar um fator. Recuperar os chunks certos não basta — um número errado entregue como oficial é exatamente o modo de falha de maior consequência. **Recomendação:** não deixar o modelo calcular em texto livre; expor o cálculo de frete (e o lookup da tarifa base) como uma **ferramenta determinística** (function calling) que o LLM invoca com os parâmetros corretos e recebe o valor pronto. O LLM cuida da linguagem natural e da seleção de regra; o cálculo e a tarifa vêm de código auditável. Isso conecta diretamente à estratégia de planilhas em §3.4.

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

**Três pontos que a revisão considera críticos e que a versão original subestimava:**

1. **Esses metadados não existem hoje.** Tanto a PROC-042 v1 quanto a v2 declaram explicitamente *não ter* indicação formal de vigência ou obsolescência; o FAQ não tem responsável formal; a atualização é feita por 3 áreas "sem processo unificado de revisão". Ou seja, a mitigação mais importante do projeto **depende de um trabalho de curadoria que o cliente nunca fez** e que precisa ser feito manualmente sobre ~800 PDFs + ~400 páginas wiki, e depois *mantido* a cada atualização mensal. Isso é uma dependência organizacional de primeira grandeza e um risco direto ao prazo de 3 meses (§7). Mitigação prática: começar pela curadoria do subconjunto de maior tráfego (frete, devolução, SLA), não da base inteira, e atrelar a manutenção do metadado ao fluxo de publicação de cada área.

2. **O FAQ não deveria entrar no índice com o mesmo peso de um documento normativo — talvez nem por padrão.** Ele é autodeclarado não validado. Ranquear "abaixo" pode não bastar: se nenhum normativo responder, o FAQ sobe e pode ser citado como se fosse política. Recomenda-se ou **excluí-lo da recuperação padrão** (consultável apenas sob flag explícita), ou **marcar toda citação dele como "fonte informal, não validada"** na resposta, de modo que o atendente nunca o confunda com norma.

3. **Comportamento de abstenção é requisito, não detalhe.** Quando a recuperação não traz nada com relevância suficiente (após re-rank, abaixo de um limiar), o assistente deve responder **"não localizei isso na documentação oficial"** e encaminhar ao caminho humano — nunca preencher a lacuna. Para uma operação cujo principal risco é a resposta confiante e errada, a abstenção bem-feita é uma funcionalidade de segurança, e deve estar no *golden set* de avaliação (§7).

Sem essa camada, o assistente automatiza e amplifica exatamente a inconsistência que o projeto pretende eliminar. Com ela, o sistema passa a ser mais consistente que o processo manual atual.

---

## 7. Riscos e próximos passos

O principal risco do projeto não é a tecnologia de RAG, que é madura e bem suportada pela stack existente — é a **qualidade e a governança da fonte** e o conjunto de frentes **organizacionais** que a stack não resolve sozinha. A revisão sênior organiza os riscos em três blocos.

### 7.1. Riscos de pré-condição (devem ser resolvidos antes do go-live)

- **Controle de acesso por documento (*security trimming*).** O SharePoint aplica permissões por documento; nem todo atendente pode ver tudo (contratos comerciais, tabelas de preço de clientes específicos, dados de sinistro, RH). Um índice de RAG que **achata** essas permissões cria um vazamento: o assistente recupera e cita conteúdo restrito para quem perguntar. O Azure AI Search suporta filtros de segurança por documento (*security trimming* por grupo/identidade do Entra ID) — isso precisa ser projetado desde a ingestão (carregar ACLs como metadado), não remendado depois. **É pré-condição de go-live, não entregável posterior.**
- **LGPD e tratamento de dados.** Documentos logísticos contêm dados pessoais e sensíveis (CT-e, valor declarado, endereços, possivelmente dados de motoristas). É preciso definir: base legal para o tratamento, o que é embeddado vs. mascarado, e **política de retenção e log** — inclusive dos prompts e respostas enviados ao Azure OpenAI (a opção de não-treinamento e a região de processamento do Azure devem ser confirmadas). Tratar isso após o go-live expõe a NovaTech a risco regulatório.
- **Curadoria de metadados de autoridade/vigência (§6.4).** Sem ela, o assistente automatiza e amplifica a contradição que o projeto pretende eliminar. Como o metadado **não existe hoje**, criá-lo é trabalho manual e contínuo das 3 áreas — a maior dependência fora do controle da DB1.

### 7.2. Riscos de qualidade — e por que medir tempo não basta

A versão original media sucesso essencialmente em **tempo** (12 → <2 min). Para esta operação, isso é insuficiente e perigoso: **uma resposta rápida e errada sobre um multiplicador de frete é pior que a busca manual lenta** — ela carrega aparência de oficial e consequência contratual. O critério de aceite precisa incluir qualidade, medida objetivamente sobre um *golden set* extraído de chamados reais:

- **Groundedness / fidelidade:** a resposta é sustentada pelos chunks citados (sem invenção)?
- **Precisão e recall de recuperação (precision@k, recall@k):** os chunks certos chegaram ao contexto?
- **Acerto em perguntas de conflito de versão e de cálculo** (subconjunto de alto risco do *golden set*).
- **Taxa de abstenção correta:** ele diz "não sei" quando deve, em vez de alucinar?
- **Taxa de alucinação** em amostragem cega revisada por especialista de cada área.

Esses indicadores devem ter **limiares de aceite definidos com Operações/Compliance/Comercial antes do go-live**, e um **loop de feedback** (👍/👎 no Teams) que alimente o crescimento do *golden set* e o ajuste de retrieval em produção.

### 7.3. Riscos de prazo, custo e adoção

- **Prazo de 3 meses é agressivo.** Discovery + extração (com OCR e revisão humana de baixa confiança) + curadoria de metadados + *security trimming* + LGPD + construção de *golden set* dificilmente cabem em 3 meses para a base inteira. **Recomendação: go-live faseado** — entrar primeiro com os domínios de maior tráfego e já governados (frete, devolução, SLA) sobre um subconjunto limpo, medir, e expandir. Big-bang sobre 1.200 documentos é o caminho mais provável para um piloto que perde a confiança do time logo no início.
- **Custo recorrente (TCO) não foi quantificado.** O embedding é barato e pontual; o custo relevante é a inferência por consulta. Ordem de grandeza a estimar no discovery: ~192 chamados/dia × (1 a N perguntas) × (~6–9K tokens de entrada + ~1–2K de saída) × preço do modelo escolhido, mais Azure AI Search e Document Intelligence. É administrável, mas deve ser monitorado (alerta de custo) e é uma variável da escolha de modelo (§5).
- **Adoção e confiança do time.** Hoje o time "pergunta para quem sabe"; trocar isso por um assistente exige confiança *ganha*. A meta de <2 min **não é atingida no go-live**: há curva de aprendizado, e o requisito de **citar a fonte para o atendente verificar** — correto e necessário — reintroduz segundos/minutos de leitura. O tempo médio cai progressivamente à medida que a confiança cresce e a verificação vira exceção. Plano de *change management*, treinamento dos 45 atendentes e comunicação do que o assistente *não* faz (cargas perigosas, exceções, desconto) são parte do projeto, não acessório.

### 7.4. Próximos passos recomendados (discovery)

1. **Diagnóstico de cobertura de ingestão:** quantificar quantos dos 800 PDFs são escaneados e quantas tabelas existem — dimensiona OCR e extração layout-aware.
2. **Esquema mínimo de metadados de autoridade/vigência**, definido junto a Operações/Compliance/Comercial, e plano de curadoria faseada começando pelo subconjunto de maior tráfego.
3. **Modelo de segurança (security trimming) e parecer LGPD** como pré-condições de go-live.
4. ***Golden set*** de perguntas reais com limiares de aceite de qualidade (§7.2), incluindo casos de conflito de versão, cálculo de frete e abstenção.
5. **Decisão de modelo** (custo × qualidade no *golden set*), mantendo a arquitetura agnóstica.

A meta de tempo é factível **no médio prazo**: a maior parte dos 12 minutos atuais é busca manual em três fontes não unificadas, exatamente o que o RAG elimina. O risco residual está em respostas confiantes porém erradas por conflito de versão ou cálculo — endereçado pela camada de governança (§6.4), pela ferramenta de cálculo determinística (§6.1) e pela abstenção, que por isso devem ser tratadas como requisitos, não como melhorias opcionais.
