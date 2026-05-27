"""
mcps/server.py
==============
Servidor MCP propio con tools custom sobre el proyecto ai-lab.

Tools expuestas:
  - list_project_files   -> lista archivos del proyecto
  - read_project_file    -> lee un archivo del proyecto
  - write_project_file   -> escribe/crea un archivo
  - search_in_files      -> busca texto en archivos del proyecto
  - run_python_file      -> ejecuta un script Python del proyecto
  - get_project_summary  -> resumen rapido del proyecto
  - semantic_search      -> busqueda semantica RAG sobre el indice ChromaDB

NOTA: sentence_transformers/PyTorch tarda ~20s en cargar.
El modelo se pre-carga al arrancar el servidor (antes de mcp.run())
para que las llamadas a semantic_search sean rapidas (~5s).
"""

import os
import sys
import subprocess
import fnmatch
import anyio
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# =====================================
# CONFIG
# =====================================

BASE_PATH = Path(r"C:\Users\chuwi\ai-lab")

mcp = FastMCP("ai-lab-server")

# =====================================
# PRE-CARGA DEL MODELO RAG
# =====================================
# sentence_transformers + PyTorch tardan ~20s en importar.
# Se cargan aqui, al arrancar el servidor, para que semantic_search
# responda en ~5s en lugar de timeout en la primera llamada.

if str(BASE_PATH) not in sys.path:
    sys.path.insert(0, str(BASE_PATH))

_rag_ready = False
_rag_search = None
_rag_format = None

try:
    from rag.retriever import search as _rag_search, format_context as _rag_format
    _rag_ready = True
    print("RAG model loaded OK", file=sys.stderr)
except Exception as _e:
    print(f"RAG not available: {_e}", file=sys.stderr)

# =====================================
# HELPERS
# =====================================

def _resolve(path: str) -> Path:
    """Resuelve una ruta relativa dentro del BASE_PATH de forma segura."""
    resolved = (BASE_PATH / path).resolve()
    # Seguridad: no permitir salir del BASE_PATH
    if not str(resolved).startswith(str(BASE_PATH.resolve())):
        raise ValueError(f"Ruta fuera del proyecto: {path}")
    return resolved


def _is_text_file(path: Path) -> bool:
    text_extensions = {
        ".py", ".txt", ".md", ".json", ".yaml", ".yml",
        ".toml", ".cfg", ".ini", ".env", ".csv", ".html",
        ".js", ".ts", ".css", ".sh", ".bat"
    }
    return path.suffix.lower() in text_extensions


# =====================================
# TOOLS
# =====================================

@mcp.tool()
def list_project_files(subpath: str = ".") -> str:
    """
    Lista archivos y carpetas dentro del proyecto.
    Parámetros:
      subpath: subruta relativa al proyecto (por defecto raíz '.')
    """
    target = _resolve(subpath)

    if not target.exists():
        return f"ERROR: La ruta '{subpath}' no existe."

    if target.is_file():
        return f"'{subpath}' es un archivo, no una carpeta."

    items = []
    for item in sorted(target.iterdir()):
        kind = "DIR " if item.is_dir() else "FILE"
        size = f"{item.stat().st_size:>8} bytes" if item.is_file() else ""
        items.append(f"[{kind}] {item.name} {size}")

    if not items:
        return f"Carpeta vacía: {subpath}"

    return f"Contenido de '{subpath}':\n" + "\n".join(items)


@mcp.tool()
def read_project_file(path: str) -> str:
    """
    Lee el contenido de un archivo de texto del proyecto.
    Parámetros:
      path: ruta relativa al archivo dentro del proyecto
    """
    target = _resolve(path)

    if not target.exists():
        return f"ERROR: El archivo '{path}' no existe."

    if not target.is_file():
        return f"ERROR: '{path}' no es un archivo."

    if not _is_text_file(target):
        return f"ERROR: '{path}' no es un archivo de texto legible."

    try:
        return target.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR leyendo archivo: {e}"


@mcp.tool()
def write_project_file(path: str, content: str) -> str:
    """
    Escribe o crea un archivo de texto en el proyecto.
    Parámetros:
      path: ruta relativa donde escribir
      content: contenido a escribir
    """
    target = _resolve(path)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"OK: Archivo '{path}' escrito ({len(content)} caracteres)."
    except Exception as e:
        return f"ERROR escribiendo archivo: {e}"


@mcp.tool()
def search_in_files(query: str, subpath: str = ".", pattern: str = "*.py") -> str:
    """
    Busca texto en archivos del proyecto.
    Parámetros:
      query: texto a buscar (case-insensitive)
      subpath: carpeta donde buscar (por defecto raíz)
      pattern: patrón de archivos (por defecto '*.py')
    """
    target = _resolve(subpath)
    results = []
    query_lower = query.lower()

    for file_path in target.rglob(pattern):
        if not _is_text_file(file_path):
            continue
        # Ignorar venv
        if "venv" in file_path.parts:
            continue
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, 1):
                if query_lower in line.lower():
                    rel = file_path.relative_to(BASE_PATH)
                    results.append(f"{rel}:{i}: {line.strip()}")
        except Exception:
            continue

    if not results:
        return f"Sin resultados para '{query}' en {subpath}/{pattern}"

    return f"Resultados para '{query}':\n" + "\n".join(results[:50])


@mcp.tool()
def run_python_file(path: str, timeout: int = 15) -> str:
    """
    Ejecuta un script Python del proyecto y devuelve su salida.
    Parámetros:
      path: ruta relativa al script .py
      timeout: segundos máximos de ejecución (por defecto 15)
    """
    target = _resolve(path)

    if not target.exists():
        return f"ERROR: '{path}' no existe."

    if target.suffix != ".py":
        return f"ERROR: '{path}' no es un archivo Python."

    python_exe = str(BASE_PATH / "venv" / "Scripts" / "python.exe")

    try:
        result = subprocess.run(
            [python_exe, str(target)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,   # evita herencia de pipes MCP
            text=True,
            timeout=timeout,
            cwd=str(BASE_PATH)
        )
        output = result.stdout or ""
        errors = result.stderr or ""
        combined = ""
        if output:
            combined += f"STDOUT:\n{output}"
        if errors:
            combined += f"\nSTDERR:\n{errors}"
        return combined.strip() or "Script ejecutado sin salida."
    except subprocess.TimeoutExpired:
        return f"ERROR: Timeout ({timeout}s) ejecutando '{path}'."
    except Exception as e:
        return f"ERROR ejecutando script: {e}"


@mcp.tool()
def get_project_summary() -> str:
    """
    Devuelve un resumen rápido del proyecto: archivos, tamaño, estructura.
    Sin parámetros.
    """
    summary = []
    py_files = []
    total_lines = 0

    for file_path in BASE_PATH.rglob("*.py"):
        if "venv" in file_path.parts:
            continue
        rel = file_path.relative_to(BASE_PATH)
        try:
            lines = len(file_path.read_text(encoding="utf-8").splitlines())
            total_lines += lines
            py_files.append(f"  {rel} ({lines} líneas)")
        except Exception:
            py_files.append(f"  {rel} (ilegible)")

    summary.append(f"Proyecto: ai-lab")
    summary.append(f"Base: {BASE_PATH}")
    summary.append(f"Archivos Python: {len(py_files)}")
    summary.append(f"Total líneas: {total_lines}")
    summary.append("\nArchivos:")
    summary.extend(py_files)

    return "\n".join(summary)


# =====================================
# RAG — BUSQUEDA SEMANTICA
# =====================================

def _search_sync(query: str, top_k: int) -> str:
    """Ejecuta la busqueda semantica usando el modelo pre-cargado."""
    if not _rag_ready:
        return (
            "El modulo RAG no esta disponible. "
            "Verifica que sentence-transformers esta instalado."
        )
    try:
        results = _rag_search(query, top_k=top_k)
        if not results:
            return f"Sin resultados para: {query}"
        return _rag_format(results)
    except Exception as e:
        msg = str(e)
        if "does not exist" in msg or "Collection" in msg:
            return (
                "El indice RAG no existe todavia. "
                "Ejecuta primero: python rag/indexer.py"
            )
        return f"ERROR en busqueda semantica: {e}"


@mcp.tool()
async def semantic_search(query: str, top_k: int = 5) -> str:
    """
    Busca informacion relevante en el proyecto usando busqueda semantica (RAG).
    Encuentra fragmentos de codigo y documentacion por significado, no solo
    por palabras exactas. Util para preguntas conceptuales sobre el proyecto.

    Parametros:
      query: pregunta o descripcion de lo que buscas
      top_k: numero de fragmentos a devolver (por defecto 5)

    Requiere haber ejecutado 'python rag/indexer.py' previamente.
    """
    return await anyio.to_thread.run_sync(
        lambda: _search_sync(query, top_k),
        abandon_on_cancel=True
    )


# =====================================
# ENTRY POINT
# =====================================

if __name__ == "__main__":
    # IMPORTANTE: cuando se lanza como subproceso MCP, stdout es el canal de
    # comunicacion del protocolo. No escribir nada a stdout antes de mcp.run().
    # Los logs van a stderr para no interferir con el protocolo.
    import sys
    print("MCP server ai-lab-server starting...", file=sys.stderr)
    print(f"Base path: {BASE_PATH}", file=sys.stderr)
    mcp.run(transport="stdio")
