"""
search.py
=========
Recebe uma pergunta, gera o embedding dela, busca os top-N chunks mais
similares no ChromaDB e retorna os chunks com SCORE DE SIMILARIDADE.

Atencao: o ChromaDB devolve DISTANCIA (0 = identico), nao similaridade.
Com a metrica cosseno, similaridade = 1 - distancia. Reportar a distancia
como se fosse similaridade inverte a interpretacao do score.

Uso (teste rapido):
    python search.py "sua pergunta aqui"
"""
import sys
import chromadb
from sentence_transformers import SentenceTransformer

DB_DIR = "./chroma_db"
COLLECTION = "novatech"
MODEL_NAME = "all-MiniLM-L6-v2"  # mantenha igual ao usado em ingest.py

_model = None
_collection = None


def _lazy_init():
    global _model, _collection
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
        client = chromadb.PersistentClient(path=DB_DIR)
        _collection = client.get_collection(COLLECTION)


def search(question: str, n: int = 4, min_similarity: float | None = None) -> list[dict]:
    """
    Retorna lista de dicts com text, source, section e similarity (0..1).
    Se min_similarity for definido, filtra chunks abaixo do limiar (anti-ruido).
    """
    _lazy_init()
    q_emb = _model.encode([question]).tolist()
    res = _collection.query(query_embeddings=q_emb, n_results=n)

    results = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        sim = round(1 - dist, 4)
        if min_similarity is not None and sim < min_similarity:
            continue
        results.append({
            "text": doc,
            "source": meta.get("source"),
            "section": meta.get("section"),
            "type": meta.get("type"),
            "similarity": sim,
        })
    return results


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "Qual e a politica de devolucao?"
    print(f"Pergunta: {q}\n")
    for r in search(q, n=4):
        print(f"[sim={r['similarity']}] {r['source']} > {r['section']} ({r['type']})")
        print("  " + r["text"][:180].replace("\n", " ") + " ...\n")
