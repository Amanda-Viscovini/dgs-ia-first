"""
ingest.py
=========
Le os .md do Anexo A, gera chunks (chunking.py), cria embeddings com
sentence-transformers e persiste no ChromaDB local.

Uso:
    python ingest.py
"""
import glob
import os
import chromadb
from sentence_transformers import SentenceTransformer
from chunking import chunk_markdown

DOCS_DIR = "anexo-documentos"
DB_DIR = "./chroma_db"
COLLECTION = "novatech"

# Modelo de embeddings. all-MiniLM-L6-v2 e leve e rapido, mas e treinado
# majoritariamente em ingles. Para documentos em PORTUGUES, troque por:
#   "paraphrase-multilingual-MiniLM-L12-v2"
# (veja a secao "Problemas e correcoes" do README).
MODEL_NAME = "all-MiniLM-L6-v2"


def build_index():
    print(f"Carregando modelo de embeddings: {MODEL_NAME} ...")
    model = SentenceTransformer(MODEL_NAME)
    client = chromadb.PersistentClient(path=DB_DIR)

    # recria a colecao do zero p/ idempotencia (rodar de novo nao duplica chunks)
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"},  # similaridade do cosseno
    )

    paths = sorted(glob.glob(os.path.join(DOCS_DIR, "*.md")))
    if not paths:
        raise SystemExit(
            f"Nenhum .md encontrado em '{DOCS_DIR}/'. "
            "Coloque os 5 arquivos do Anexo A nessa pasta."
        )

    all_chunks = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        source = os.path.basename(path)
        doc_chunks = chunk_markdown(text, source=source)
        all_chunks.extend(doc_chunks)
        print(f"  {source}: {len(doc_chunks)} chunks")

    texts = [c.text for c in all_chunks]
    print(f"Gerando embeddings de {len(texts)} chunks ...")
    embeddings = model.encode(texts, show_progress_bar=True).tolist()
    ids = [f"chunk_{i}" for i in range(len(all_chunks))]
    metadatas = [c.metadata for c in all_chunks]

    collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
    n_docs = len(set(m["source"] for m in metadatas))
    print(f"\nOK: {len(all_chunks)} chunks de {n_docs} documentos indexados em '{DB_DIR}'.")


if __name__ == "__main__":
    build_index()
