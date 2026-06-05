"""
prompt_builder.py
=================
Recebe a pergunta, recupera os chunks (search.py) e monta o PROMPT COMPLETO
(system prompt + contexto + pergunta) pronto para colar no chat do Claude
(ou enviar a um modelo local via Ollama).

Os GUARDRAILS estao no SYSTEM_PROMPT: nao inventar, citar fonte, e admitir
quando a resposta nao esta no contexto.

Uso:
    python prompt_builder.py "sua pergunta aqui"
"""
import sys
from search import search

SYSTEM_PROMPT = """Voce e um assistente da NovaTech. Responda EXCLUSIVAMENTE com \
base no contexto fornecido abaixo. Regras (guardrails):
1. Se a resposta NAO estiver no contexto, responda exatamente: "Nao encontrei \
essa informacao nos documentos disponiveis." Nao invente nada.
2. Sempre cite a fonte (documento e secao) entre colchetes ao final de cada \
afirmacao, no formato [fonte: <documento> > <secao>].
3. Nao faca suposicoes nem extrapole alem do que esta escrito no contexto."""


def build_prompt(question: str, n: int = 4, min_similarity: float | None = None):
    """Retorna (prompt_str, chunks_usados)."""
    chunks = search(question, n=n, min_similarity=min_similarity)

    if not chunks:
        # nenhum chunk passou no limiar -> contexto vazio, guardrail deve atuar
        context = "(nenhum trecho relevante encontrado)"
    else:
        parts = []
        for i, c in enumerate(chunks, 1):
            parts.append(
                f"[Fonte {i}: {c['source']} > {c['section']} | sim={c['similarity']}]\n"
                f"{c['text']}"
            )
        context = "\n\n---\n\n".join(parts)

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"=== CONTEXTO ===\n{context}\n\n"
        f"=== PERGUNTA ===\n{question}\n\n"
        f"=== RESPOSTA ==="
    )
    return prompt, chunks


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "Qual e o prazo de garantia dos produtos?"
    prompt, _ = build_prompt(q)
    print(prompt)
