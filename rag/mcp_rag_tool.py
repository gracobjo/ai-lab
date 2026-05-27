"""
rag/mcp_rag_tool.py
===================
Tool MCP que expone la búsqueda semántica RAG.
Se puede importar en mcps/server.py o usarse como servidor independiente.
"""

from pathlib import Path
from mcp.server.fastmcp import FastMCP
from rag.retriever import search, format_context

mcp = FastMCP("rag-server")


@mcp.tool()
def semantic_search(query: str, top_k: int = 5) -> str:
    """
    Busca información relevante en el proyecto usando búsqueda semántica.
    Parámetros:
      query: pregunta o texto a buscar
      top_k: número de resultados (por defecto 5)
    """
    try:
        results = search(query, top_k=top_k)
    except Exception as e:
        return f"ERROR: {e}. ¿Está el índice creado? Ejecuta: python rag/indexer.py"

    if not results:
        return f"Sin resultados para: {query}"

    return format_context(results)


if __name__ == "__main__":
    print("🚀 Iniciando servidor MCP RAG")
    mcp.run(transport="stdio")
