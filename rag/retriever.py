"""
rag/retriever.py
================
Módulo de búsqueda semántica sobre el índice ChromaDB.

Uso standalone:
  python rag/retriever.py "cómo funciona el agente MCP"

Uso como módulo:
  from rag.retriever import search
  results = search("function calling", top_k=3)
"""

import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

# =====================================
# CONFIG
# =====================================

BASE_PATH   = Path(r"C:\Users\chuwi\ai-lab")
CHROMA_PATH = BASE_PATH / "data" / "chroma_db"
COLLECTION  = "ai_lab_docs"
MODEL_NAME  = "all-MiniLM-L6-v2"

# Singleton para no recargar el modelo en cada llamada
_model      = None
_collection = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _collection = client.get_collection(COLLECTION)
    return _collection


# =====================================
# SEARCH
# =====================================

def search(query: str, top_k: int = 5) -> list[dict]:
    """
    Busca los chunks más relevantes para una query.

    Retorna lista de dicts:
      {
        "source": "ruta/archivo.py",
        "chunk": 2,
        "text": "...",
        "score": 0.87
      }
    """
    model      = _get_model()
    collection = _get_collection()

    embedding = model.encode([query]).tolist()

    results = collection.query(
        query_embeddings=embedding,
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )

    output = []
    docs      = results["documents"][0]
    metas     = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, dist in zip(docs, metas, distances):
        # ChromaDB con cosine devuelve distancia (0=idéntico, 2=opuesto)
        score = round(1 - dist / 2, 4)
        output.append({
            "source": meta.get("source", ""),
            "chunk":  meta.get("chunk", 0),
            "text":   doc,
            "score":  score
        })

    return output


def format_context(results: list[dict]) -> str:
    """Formatea los resultados como contexto para el LLM."""
    parts = []
    for r in results:
        parts.append(
            f"[Fuente: {r['source']} | Score: {r['score']}]\n{r['text']}"
        )
    return "\n\n---\n\n".join(parts)


# =====================================
# ENTRY POINT (TEST)
# =====================================

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "agente MCP loop"

    print(f"\n🔍 Query: {query}\n")

    try:
        results = search(query, top_k=3)
    except Exception as e:
        print(f"❌ Error: {e}")
        print("¿Has ejecutado 'python rag/indexer.py' primero?")
        sys.exit(1)

    for i, r in enumerate(results, 1):
        print(f"{'='*60}")
        print(f"#{i} | {r['source']} (chunk {r['chunk']}) | score: {r['score']}")
        print(f"{'-'*60}")
        print(r["text"][:300])
        print()
