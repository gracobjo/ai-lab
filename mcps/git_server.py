"""
mcps/git_server.py
==================
Servidor MCP con herramientas Git para el proyecto ai-lab.

Tools expuestas:
  - git_status          -> estado del working tree
  - git_log             -> historial de commits
  - git_diff            -> diferencias entre commits, ramas o archivos
  - git_show            -> contenido de un commit concreto
  - git_branches        -> lista de ramas locales y remota activa
  - git_blame           -> autoria linea a linea de un archivo
  - git_search_commits  -> busca texto en mensajes de commit
  - git_file_history    -> historial de commits que tocaron un archivo

NOTA TECNICA:
  FastMCP corre en un event loop asyncio con anyio (Windows ProactorEventLoop).
  asyncio.create_subprocess_exec falla en subprocesos anidados en Windows.
  La solucion es ejecutar subprocess.run en un thread pool via asyncio.to_thread,
  que no bloquea el event loop y funciona correctamente en Windows.
"""

import asyncio
import subprocess
import sys
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# =====================================
# CONFIG
# =====================================

BASE_PATH = Path(r"C:\Users\chuwi\ai-lab")

mcp = FastMCP("git-server")

# =====================================
# HELPER — subprocess en thread pool
# =====================================

def _git_sync(args: list[str]) -> str:
    """Ejecuta git de forma sincrona (se llama desde un thread).
    
    IMPORTANTE: stdin=DEVNULL es obligatorio cuando el proceso padre
    es un servidor MCP stdio. Sin esto, git hereda los pipes MCP y
    se bloquea esperando input del protocolo.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,   # <- evita herencia de pipes MCP
            cwd=str(BASE_PATH),
            timeout=15
        )
        out = result.stdout.decode("utf-8", errors="replace").strip()
        err = result.stderr.decode("utf-8", errors="replace").strip()
        if result.returncode != 0:
            return f"ERROR git: {err}" if err else f"git salio con codigo {result.returncode}"
        return out if out else "(sin salida)"
    except subprocess.TimeoutExpired:
        return "ERROR: timeout ejecutando git"
    except FileNotFoundError:
        return "ERROR: git no encontrado en el PATH"
    except Exception as e:
        return f"ERROR inesperado: {e}"


async def _git(args: list[str]) -> str:
    """Ejecuta git en un thread pool de anyio para no bloquear el event loop."""
    import anyio
    return await anyio.to_thread.run_sync(lambda: _git_sync(args))


def _truncate(text: str, max_lines: int = 150) -> str:
    """Trunca la salida para no saturar el contexto del LLM."""
    lines = text.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + f"\n\n... (truncado, {len(lines)} lineas totales)"
    return text


# =====================================
# TOOLS
# =====================================

@mcp.tool()
async def git_status() -> str:
    """
    Muestra el estado actual del repositorio: archivos modificados,
    staged, sin seguimiento y rama activa.
    Sin parametros.
    """
    branch = await _git(["branch", "--show-current"])
    status = await _git(["status", "--short"])
    tracking = await _git(["status", "--branch", "--short"])
    tracking_line = tracking.splitlines()[0] if tracking else ""

    lines = [
        f"Rama activa : {branch}",
        f"Estado      : {tracking_line}",
        "",
        "Cambios:",
        status if status != "(sin salida)" else "  (working tree limpio)"
    ]
    return "\n".join(lines)


@mcp.tool()
async def git_log(max_commits: int = 10, branch: str = "") -> str:
    """
    Muestra el historial de commits.
    Parametros:
      max_commits: numero maximo de commits a mostrar (por defecto 10)
      branch: rama o referencia (por defecto la rama activa)
    """
    args = [
        "log",
        f"-{max_commits}",
        "--pretty=format:%h  %ad  %an  %s",
        "--date=short"
    ]
    if branch:
        args.append(branch)
    return await _git(args)


@mcp.tool()
async def git_diff(target: str = "", staged: bool = False) -> str:
    """
    Muestra diferencias en el codigo.
    Parametros:
      target: archivo, commit o rango (ej: 'HEAD~1', 'main..feature', 'archivo.py').
              Si esta vacio muestra todos los cambios no staged.
      staged: si True muestra los cambios en el area de staging (--cached)
    """
    args = ["diff"]
    if staged:
        args.append("--cached")
    if target:
        args.append(target)
    return _truncate(await _git(args), max_lines=200)


@mcp.tool()
async def git_show(ref: str = "HEAD") -> str:
    """
    Muestra el contenido completo de un commit: metadatos y diff.
    Parametros:
      ref: referencia del commit (hash, HEAD, HEAD~1, tag...). Por defecto HEAD.
    """
    return _truncate(await _git(["show", "--stat", ref]))


@mcp.tool()
async def git_branches() -> str:
    """
    Lista todas las ramas locales y marca la activa.
    Tambien muestra el remote tracking si existe.
    Sin parametros.
    """
    local  = await _git(["branch", "-vv"])
    remote = await _git(["remote", "-v"])
    parts = ["=== Ramas locales ===", local]
    if remote != "(sin salida)":
        parts += ["", "=== Remotos ===", remote]
    return "\n".join(parts)


@mcp.tool()
async def git_blame(path: str, start_line: int = 1, end_line: int = 0) -> str:
    """
    Muestra la autoria linea a linea de un archivo.
    Parametros:
      path: ruta relativa al archivo dentro del proyecto
      start_line: primera linea a mostrar (por defecto 1)
      end_line: ultima linea a mostrar (0 = hasta el final, max 100 lineas)
    """
    target = (BASE_PATH / path).resolve()
    if not str(target).startswith(str(BASE_PATH.resolve())):
        return f"ERROR: ruta fuera del proyecto: {path}"
    if not target.exists():
        return f"ERROR: archivo no encontrado: {path}"

    args = ["blame", "--date=short", "-w"]
    if end_line > 0:
        args += [f"-L{start_line},{end_line}"]
    elif start_line > 1:
        args += [f"-L{start_line},+100"]
    args.append(path)

    return _truncate(await _git(args), max_lines=100)


@mcp.tool()
async def git_search_commits(query: str, max_results: int = 20) -> str:
    """
    Busca texto en los mensajes de commit del historial.
    Parametros:
      query: texto a buscar (case-insensitive)
      max_results: numero maximo de resultados (por defecto 20)
    """
    output = await _git([
        "log",
        f"-{max_results}",
        f"--grep={query}",
        "--pretty=format:%h  %ad  %an  %s",
        "--date=short",
        "--regexp-ignore-case"
    ])
    if output.startswith("ERROR") or output == "(sin salida)":
        return f"Sin commits que contengan '{query}'"
    return f"Commits con '{query}':\n{output}"


@mcp.tool()
async def git_file_history(path: str, max_commits: int = 10) -> str:
    """
    Muestra el historial de commits que modificaron un archivo concreto.
    Parametros:
      path: ruta relativa al archivo
      max_commits: numero maximo de commits (por defecto 10)
    """
    output = await _git([
        "log",
        f"-{max_commits}",
        "--pretty=format:%h  %ad  %an  %s",
        "--date=short",
        "--follow",
        "--",
        path
    ])
    if output == "(sin salida)":
        return f"Sin historial para '{path}' (esta en el repo?)"
    return f"Historial de '{path}':\n{output}"


# =====================================
# ENTRY POINT
# =====================================

if __name__ == "__main__":
    print("MCP git-server starting...", file=sys.stderr)
    print(f"Repo: {BASE_PATH}", file=sys.stderr)
    mcp.run(transport="stdio")
