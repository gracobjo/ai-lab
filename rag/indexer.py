"""
rag/indexer.py
==============
Indexa archivos del proyecto en ChromaDB usando sentence-transformers local.

Uso:
  python rag/indexer.py              → indexa todo el proyecto
  python rag/indexer.py --reset      → borra el índice y re-indexa
"""

import os
import sys
import argparse
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# =====================================
# CONFIG
# =====================================

BASE_PATH   = Path(r"C:\Users\chuwi\ai-lab")
CHROMA_PATH = BASE_PATH / "data" / "chroma_db"
COLLECTION  = "ai_lab_docs"
MODEL_NAME  = "all-MiniLM-L6-v2"   # modelo local ligero, ~80MB

CHUNK_SIZE    = 400   # caracteres por chunk
CHUNK_OVERLAP = 80    # solapamiento entre chunks

TEXT_EXTENSIONS = {
    ".py", ".txt", ".md", ".json", ".yaml",
    ".yml", ".toml", ".cfg", ".ini", ".csv"
}

IGNORE_DIRS = {"venv", ".vscode", "__pycache__", ".git", "data"}

# =====================================
# CHUNKING
# =====================================

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Divide texto en chunks con solapamiento."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return chunks


# =====================================
# COLLECT FILES
# =====================================

def collect_files(base: Path) -> list[Path]:
    """Recoge todos los archivos de texto del proyecto."""
    files = []
    for path in base.rglob("*"):
        # Ignorar carpetas excluidas
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
            files.append(path)
    return files


# =====================================
# INDEXER
# =====================================

def build_index(reset: bool = False):
    print(f"📦 Cargando modelo de embeddings: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    print(f"🗄️  Conectando a ChromaDB en: {CHROMA_PATH}")
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    if reset:
        try:
            client.delete_collection(COLLECTION)
            print(f"🗑️  Colección '{COLLECTION}' eliminada.")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )

    files = collect_files(BASE_PATH)
    print(f"\n📂 Archivos encontrados: {len(files)}")

    total_chunks = 0
    skipped = 0

    for file_path in files:
        rel = str(file_path.relative_to(BASE_PATH))

        try:
            text = file_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            print(f"  ⚠️  {rel}: error leyendo ({e})")
            skipped += 1
            continue

        if not text:
            skipped += 1
            continue

        chunks = chunk_text(text)

        ids       = [f"{rel}::chunk{i}" for i in range(len(chunks))]
        metadatas = [{"source": rel, "chunk": i} for i in range(len(chunks))]

        # Embeddings
        embeddings = model.encode(chunks, show_progress_bar=False).tolist()

        # Upsert en ChromaDB
        collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas
        )

        total_chunks += len(chunks)
        print(f"  ✅ {rel} → {len(chunks)} chunks")

    print(f"\n🎉 Indexación completa.")
    print(f"   Archivos procesados : {len(files) - skipped}")
    print(f"   Archivos omitidos   : {skipped}")
    print(f"   Total chunks        : {total_chunks}")
    print(f"   Colección           : {COLLECTION}")


# =====================================
# ENTRY POINT
# =====================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Indexador RAG para ai-lab")
    parser.add_argument("--reset", action="store_true", help="Borra el índice antes de indexar")
    args = parser.parse_args()

    build_index(reset=args.reset)
