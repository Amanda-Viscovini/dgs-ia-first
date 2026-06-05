"""
test_rag.py
===========
Roda a bateria de testes do MAPA DE COBERTURA (Anexo B) contra o pipeline e
imprime, para cada pergunta:
  - os chunks recuperados (doc > secao) com score de similaridade;
  - a comparacao com o gabarito (chunks que DEVEM aparecer / podem aparecer);
  - um VEREDITO automatico.

Tambem gera os prompts completos (prompt_builder) para colar no chat do Claude.

------------------------------------------------------------------------------
COMO USAR
------------------------------------------------------------------------------
1. Garanta que o indice foi criado:  python ingest.py
2. Preencha o dicionario CHUNK_ID_MAP abaixo: cada ID do gabarito do Anexo B
   (POL-001-A, SLA-2024-B, ...) -> uma palavra-chave que identifique esse chunk
   no que o pipeline recupera. A palavra-chave e casada (case-insensitive)
   contra "source + secao + texto" do chunk recuperado.
   Ex.: se POL-001-A vem do arquivo "politica-devolucao.md", secao "Prazo",
        use  "POL-001-A": "prazo"   ou   "POL-001-A": "politica-devolucao".
3. Rode:  python test_rag.py
------------------------------------------------------------------------------
"""
from search import search
from prompt_builder import build_prompt

N = 5                  # quantos chunks recuperar por pergunta
MIN_SIM = 0.30         # limiar p/ considerar um chunk "relevante" (anti-ruido)

# ----------------------------------------------------------------------------
# MAPA: ID do gabarito (Anexo B) -> palavra-chave que o identifica nos chunks
# recuperados. PREENCHA conforme os documentos reais do Anexo A.
# (Os valores abaixo sao palpites razoaveis pelos prefixos dos IDs; ajuste.)
# ----------------------------------------------------------------------------
#
# IMPORTANTE: a correspondencia A/B/C abaixo e um PALPITE pelo conteudo, feito a
# partir das secoes reais que apareceram na recuperacao. ABRA O ANEXO B e confirme
# qual secao corresponde a cada ID (POL-001-A, -B, -C etc.). Ajuste se necessario.
# A palavra-chave e casada (case-insensitive) contra "source + secao + texto".
# Os acentos importam: escreva como aparece no documento.
#
CHUNK_ID_MAP = {
    # POL-001-politica-devolucao.md
    "POL-001-A": "politica-devolucao prazo",         # secao de prazo/elegibilidade (7 dias uteis)
    "POL-001-B": "politica-devolucao perigosa",      # carga perigosa / itens nao elegiveis
    "POL-001-C": "politica-devolucao custos",        # 3.5 Custos de devolucao

    # SLA-2024-tabela-sla-clientes.md
    "SLA-2024-A": "sla-2024 classificação",          # 1. Classificacao (contem 'nao existem outros tiers')
    "SLA-2024-B": "tabela de sla por tipo",          # tabela com os tiers (Gold etc.)
    "SLA-2024-C": "sla-2024 medição",                # 5. Medicao e reportes

    # Frete especial — DUAS versoes (v2 = vigente, v1 = ANTIGA)
    "PROC-042v2-A": "v2-frete-especial-revisado fórmula",        # v2: 2. Formula de calculo
    "PROC-042v2-B": "v2-frete-especial-revisado multiplicadores",# v2: 2.1 Multiplicadores regionais
    "PROC-042-B":   "frete-especial-v1 multiplicadores",         # v1 ANTIGO: 2.1 (fonte de contradicao)

    # FAQ-atendimento.md — palavras-chave de CONTEUDO (evita colidir Item 3 / 32 / 38)
    "FAQ-03": "ramal 4500",            # Item 3 — devolver carga perigosa
    "FAQ-15": "existe esse tier",      # Item 15 — cliente diz que e Platinum
    "FAQ-32": "frete expresso",        # Item 32 — carga perigosa com frete expresso
    "FAQ-38": "chegou danificada",     # Item 38 — carga danificada
}

# ----------------------------------------------------------------------------
# CASOS DE TESTE (Mapa de cobertura - Anexo B)
#   must   = chunks que DEVEM ser recuperados
#   may    = chunks que podem aparecer (relevancia menor) - nao penalizam
#   expect_empty = True  -> o correto e NAO recuperar nada relevante
#   note   = observacao (contradicao de versao, multi-dominio, etc.)
# ----------------------------------------------------------------------------
TEST_CASES = [
    {
        "q": "Qual o prazo de devolucao?",
        "must": ["POL-001-A", "POL-001-B"],
        "may": ["POL-001-C"],
    },
    {
        "q": "Posso devolver carga perigosa?",
        "must": ["POL-001-B"],
        "may": ["FAQ-03", "POL-001-A"],
    },
    {
        "q": "Qual o SLA do cliente Gold?",
        "must": ["SLA-2024-B"],
        "may": ["SLA-2024-A", "SLA-2024-C"],
    },
    {
        "q": "Qual o SLA do cliente Platinum?",
        "must": ["SLA-2024-A"],
        "may": ["FAQ-15"],
        "note": "SLA-2024-A deve conter 'nao existem outros tiers'.",
    },
    {
        "q": "Frete para 600kg para Manaus?",
        "must": ["PROC-042v2-B", "PROC-042v2-A"],
        "may": ["PROC-042-B"],
        "note": "PROC-042-B e versao ANTIGA -> risco de contradicao.",
    },
    {
        "q": "Frete para 300kg para Salvador?",
        "must": [],
        "may": ["PROC-042v2-B"],
        "expect_empty": True,
        "note": "Frete padrao < 500kg nao esta documentado -> nao deve recuperar nada relevante.",
    },
    {
        "q": "O que acontece com carga danificada?",
        "must": ["FAQ-38"],
        "may": [],
        "note": "Nenhum documento FORMAL cobre isso; so a FAQ.",
    },
    {
        "q": "Carga perigosa com frete expresso?",
        "must": ["FAQ-32"],
        "may": [],
        "note": "Nenhum documento FORMAL cobre isso; so a FAQ.",
    },
    {
        "q": "Qual o multiplicador para o Sudeste?",
        "must": ["PROC-042v2-B"],
        "may": ["PROC-042-B"],
        "note": "CONTRADICAO de versao: v2=1.0 vs antiga=1.1. v2 deve vir primeiro.",
    },
    {
        "q": "Prazo de devolucao + carga perigosa + frete especial",
        "must": ["POL-001-A", "POL-001-B", "PROC-042v2-A", "PROC-042v2-B"],
        "may": ["FAQ-03"],
        "note": "Pergunta MULTI-DOMINIO (devolucao + frete).",
    },
]


# ----------------------------------------------------------------------------
def _matches(chunk: dict, chunk_id: str) -> bool:
    """Um chunk recuperado 'casa' com um ID do gabarito se a palavra-chave
    mapeada aparece no source/secao/texto do chunk."""
    kw = CHUNK_ID_MAP.get(chunk_id, "").strip().lower()
    if not kw:
        return False
    blob = f"{chunk.get('source','')} {chunk.get('section','')} {chunk.get('text','')}".lower()
    # todas as palavras da keyword precisam aparecer
    return all(tok in blob for tok in kw.split())


def _found_id(retrieved: list[dict], chunk_id: str):
    """Retorna a posicao (1-based) em que o chunk_id foi recuperado, ou None."""
    for i, c in enumerate(retrieved, 1):
        if _matches(c, chunk_id):
            return i
    return None


def avalia(case: dict, retrieved: list[dict]) -> str:
    must = case.get("must", [])
    expect_empty = case.get("expect_empty", False)

    # checa se ha keywords nao preenchidas para os IDs deste caso
    faltando = [cid for cid in must if not CHUNK_ID_MAP.get(cid, "").strip()]
    if faltando and not expect_empty:
        return f"?  (preencha CHUNK_ID_MAP para: {', '.join(faltando)})"

    # caso especial: o correto e NAO recuperar nada relevante
    if expect_empty:
        relevantes = [c for c in retrieved if c["similarity"] >= MIN_SIM]
        if not relevantes:
            return "OK (corretamente vazio: nenhum chunk acima do limiar)"
        topo = relevantes[0]
        return (f"ATENCAO: recuperou chunk acima do limiar quando nao deveria "
                f"(sim={topo['similarity']} {topo['source']} > {topo['section']})")

    # caso normal: todos os 'must' precisam aparecer
    posicoes = {cid: _found_id(retrieved, cid) for cid in must}
    faltantes = [cid for cid, pos in posicoes.items() if pos is None]
    if faltantes:
        return f"FALHOU: nao recuperou {', '.join(faltantes)}"
    pior = max(posicoes.values())
    if pior == 1 and len(must) == 1:
        return "OK no topo"
    return f"OK (todos os 'must' recuperados; pior posicao = #{pior})"


def main():
    for case in TEST_CASES:
        q = case["q"]
        print("=" * 74)
        print(f"PERGUNTA: {q}")
        if case.get("note"):
            print(f"  (nota: {case['note']})")
        print(f"  esperado (must): {case.get('must') or '(nenhum)'}"
              f"   | pode aparecer (may): {case.get('may') or '-'}")

        retrieved = search(q, n=N)
        for i, c in enumerate(retrieved, 1):
            print(f"  #{i} [sim={c['similarity']}] {c['source']} > {c['section']}")

        print(f"  --> VEREDITO: {avalia(case, retrieved)}")
        print()

    # imprime um prompt completo de exemplo para colar no chat
    print("#" * 74)
    print("EXEMPLO DE PROMPT MONTADO (cole no chat do Claude):")
    print("#" * 74)
    prompt, _ = build_prompt(TEST_CASES[0]["q"], n=N)
    print(prompt)


if __name__ == "__main__":
    main()