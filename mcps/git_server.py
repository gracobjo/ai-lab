"""
mcps/git_server.py
==================
Servidor MCP con herramientas Git para el proyecto ai-lab.

Tools expuestas:
  - git_status          → estado del working tree
  - git_log             → historial de commits
  - git_diff            → diferencias entre commits, ramas o archivos
  - git_show            → contenido de un commit concreto
  - git_branches        → lista de ramas locales y remota activa
  - git_blame           → autoría línea a línea de un archivo
  - git_search_commits  → busca texto en mensajes de commit
  - git_file_history    → historial de commits que tocaron un archivo
"""

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
# HELPER
# =====================================

def _git(args: list[str], cwd: Path = BASE_PATH) -> str:
    """
    Ejecuta un comando git y devuelve stdout como string.
    En caso de error devuelve el mensaje de stderr.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd),
            timeout=15
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            return f"ERROR git: {err}" if err else f"git salió con código {result.returncode}"
        return result.stdout.strip() or "(sin salida)"
    except subprocess.TimeoutExpired:
        return "ERROR: timeout ejecutando git"
    except FileNotFoundError:
        return "ERROR: git no encontrado en el PATH"
    except Exception as e:
        return f"ERROR inesperado: {e}"


# =====================================
# TOOLS
# =====================================

@mcp.tool()
def git_status() -> str:
    """
    Muestra el estado actual del repositorio: archivos modificados,
    staged, sin seguimiento y rama activa.
    Sin parámetros.
    """
    branch = _git(["branch", "--show-current"])
    status = _git(["status", "--short"])
    ahead_behind = _git(["status", "--branch", "--short"]).splitlines()[0]

    lines = [
        f"Rama activa : {branch}",
        f"Estado      : {ahead_behind}",
        "",
        "Cambios:",
        status if status != "(sin salida)" else "  (working tree limpio)"
    ]
    return "\n".join(lines)


@mcp.tool()
def git_log(max_commits: int = 10, branch: str = "") -> str:
    """
    Muestra el historial de commits.
    Parámetros:
      max_commits: número máximo de commits a mostrar (por defecto 10)
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
    return _git(args)


@mcp.tool()
def git_diff(target: str = "", staged: bool = False) -> str:
    """
    Muestra diferencias en el código.
    Parámetros:
      target: archivo, commit o rango (ej: 'HEAD~1', 'main..feature', 'archivo.py').
              Si está vacío muestra todos los cambios no staged.
      staged: si True muestra los cambios en el área de staging (--cached)
    """
    args = ["diff"]
    if staged:
        args.append("--cached")
    if target:
        args.append(target)
    # Limitar salida para no saturar el contexto del LLM
    output = _git(args)
    lines = output.splitlines()
    if len(lines) > 200:
        return "\n".join(lines[:200]) + f"\n\n... (truncado, {len(lines)} líneas totales)"
    return output


@mcp.tool()
def git_show(ref: str = "HEAD") -> str:
    """
    Muestra el contenido completo de un commit: metadatos y diff.
    Parámetros:
      ref: referencia del commit (hash, HEAD, HEAD~1, tag...). Por defecto HEAD.
    """
    output = _git(["show", "--stat", ref])
    lines = output.splitlines()
    if len(lines) > 150:
        return "\n".join(lines[:150]) + f"\n\n... (truncado, {len(lines)} líneas totales)"
    return output


@mcp.tool()
def git_branches() -> str:
    """
    Lista todas las ramas locales y marca la activa.
    También muestra el remote tracking si existe.
    Sin parámetros.
    """
    local  = _git(["branch", "-vv"])
    remote = _git(["remote", "-v"])
    parts = ["=== Ramas locales ===", local]
    if remote != "(sin salida)":
        parts += ["", "=== Remotos ===", remote]
    return "\n".join(parts)


@mcp.tool()
def git_blame(path: str, start_line: int = 1, end_line: int = 0) -> str:
    """
    Muestra la autoría línea a línea de un archivo.
    Parámetros:
      path: ruta relativa al archivo dentro del proyecto
      start_line: primera línea a mostrar (por defecto 1)
      end_line: última línea a mostrar (0 = hasta el final, máx 100 líneas)
    """
    # Validar que el archivo está dentro del proyecto
    target = (BASE_PATH / path).resolve()
    if not str(target).startswith(str(BASE_PATH.resolve())):
        return f"ERROR: ruta fuera del proyecto: {path}"
    if not target.exists():
        return f"ERROR: archivo no encontrado: {path}"

    args = ["blame", "--date=short", "-w"]

    # Rango de líneas
    if end_line > 0:
        args += [f"-L{start_line},{end_line}"]
    elif start_line > 1:
        args += [f"-L{start_line},+100"]

    args.append(path)
    output = _git(args)
    lines = output.splitlines()
    if len(lines) > 100:
        return "\n".join(lines[:100]) + f"\n\n... (truncado, {len(lines)} líneas totales)"
    return output


@mcp.tool()
def git_search_commits(query: str, max_results: int = 20) -> str:
    """
    Busca texto en los mensajes de commit del historial.
    Parámetros:
      query: texto a buscar (case-insensitive)
      max_results: número máximo de resultados (por defecto 20)
    """
    output = _git([
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
def git_file_history(path: str, max_commits: int = 10) -> str:
    """
    Muestra el historial de commits que modificaron un archivo concreto.
    Parámetros:
      path: ruta relativa al archivo
      max_commits: número máximo de commits (por defecto 10)
    """
    output = _git([
        "log",
        f"-{max_commits}",
        "--pretty=format:%h  %ad  %an  %s",
        "--date=short",
        "--follow",
        "--",
        path
    ])
    if output == "(sin salida)":
        return f"Sin historial para '{path}' (¿está en el repo?)"
    return f"Historial de '{path}':\n{output}"


# =====================================
# ENTRY POINT
# =====================================

if __name__ == "__main__":
    print("MCP git-server starting...", file=sys.stderr)
    print(f"Repo: {BASE_PATH}", file=sys.stderr)
    # Verificar que es un repo git válido
    check = _git(["rev-parse", "--git-dir"])
    if check.startswith("ERROR"):
        print(f"ADVERTENCIA: {check}", file=sys.stderr)
    else:
        print(f"Git repo OK: {check}", file=sys.stderr)
    mcp.run(transport="stdio")
