"""
mcps/fetch_server.py
====================
Servidor MCP que permite al agente hacer peticiones HTTP y leer
contenido de URLs: documentacion, APIs, paginas web.

Tools expuestas:
  - fetch_url        -> GET a una URL, devuelve texto limpio
  - fetch_json       -> GET a una URL JSON, devuelve datos parseados
  - fetch_headers    -> HEAD request, devuelve solo las cabeceras

NOTA TECNICA:
  httpx es sincrono aqui (httpx.get) ejecutado via anyio.to_thread.run_sync
  para no bloquear el event loop de FastMCP/anyio.
  stdin=DEVNULL no aplica aqui (no hay subprocess), pero el patron
  de thread pool es el mismo que en git_server.py.
"""

import sys
import json
import re
import anyio
import httpx
from mcp.server.fastmcp import FastMCP

# =====================================
# CONFIG
# =====================================

TIMEOUT     = 15       # segundos
MAX_CHARS   = 8000     # caracteres maximos devueltos al LLM
USER_AGENT  = "ai-lab-agent/1.0 (MCP fetch tool)"

mcp = FastMCP("fetch-server")

# =====================================
# HELPERS
# =====================================

def _clean_html(html: str) -> str:
    """
    Extrae texto legible de HTML eliminando tags, scripts y estilos.
    No requiere BeautifulSoup — usa regex simple.
    """
    # Eliminar scripts y estilos completos
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Eliminar todos los tags HTML
    html = re.sub(r"<[^>]+>", " ", html)
    # Decodificar entidades HTML comunes
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Colapsar espacios y lineas en blanco multiples
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _truncate(text: str, max_chars: int = MAX_CHARS) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + f"\n\n... (truncado, {len(text)} caracteres totales)"
    return text


def _do_fetch(url: str, method: str = "GET", as_json: bool = False) -> dict:
    """Ejecuta la peticion HTTP de forma sincrona (llamado desde thread)."""
    headers = {"User-Agent": USER_AGENT}
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            if method == "HEAD":
                resp = client.head(url, headers=headers)
            else:
                resp = client.get(url, headers=headers)

        content_type = resp.headers.get("content-type", "")
        status = resp.status_code

        if as_json:
            try:
                data = resp.json()
                return {"ok": True, "status": status, "data": data}
            except Exception:
                return {"ok": False, "status": status, "error": "La respuesta no es JSON valido"}

        if method == "HEAD":
            return {
                "ok": True,
                "status": status,
                "headers": dict(resp.headers)
            }

        # Texto o HTML
        text = resp.text
        if "html" in content_type.lower():
            text = _clean_html(text)

        return {"ok": True, "status": status, "content_type": content_type, "text": text}

    except httpx.TimeoutException:
        return {"ok": False, "error": f"Timeout ({TIMEOUT}s) conectando a {url}"}
    except httpx.TooManyRedirects:
        return {"ok": False, "error": f"Demasiadas redirecciones en {url}"}
    except httpx.RequestError as e:
        return {"ok": False, "error": f"Error de red: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Error inesperado: {e}"}


# =====================================
# TOOLS
# =====================================

@mcp.tool()
async def fetch_url(url: str, max_chars: int = MAX_CHARS) -> str:
    """
    Hace una peticion GET a una URL y devuelve el contenido como texto.
    Si la pagina es HTML extrae el texto limpio (sin tags).
    Util para leer documentacion, README, paginas web, APIs de texto.

    Parametros:
      url: URL completa incluyendo https://
      max_chars: maximo de caracteres a devolver (por defecto 8000)
    """
    result = await anyio.to_thread.run_sync(lambda: _do_fetch(url))

    if not result["ok"]:
        return f"ERROR: {result['error']}"

    status = result["status"]
    if status >= 400:
        return f"ERROR HTTP {status} al acceder a {url}"

    text = result.get("text", "")
    ctype = result.get("content_type", "")

    header = f"[URL: {url} | HTTP {status} | {ctype}]\n\n"
    return header + _truncate(text, max_chars)


@mcp.tool()
async def fetch_json(url: str) -> str:
    """
    Hace una peticion GET a una URL que devuelve JSON y lo formatea.
    Util para consultar APIs REST, endpoints de datos, registros de paquetes.

    Parametros:
      url: URL completa de la API JSON
    """
    result = await anyio.to_thread.run_sync(lambda: _do_fetch(url, as_json=True))

    if not result["ok"]:
        return f"ERROR: {result['error']}"

    status = result["status"]
    if status >= 400:
        return f"ERROR HTTP {status}"

    data = result.get("data", {})
    formatted = json.dumps(data, ensure_ascii=False, indent=2)
    return _truncate(formatted, MAX_CHARS)


@mcp.tool()
async def fetch_headers(url: str) -> str:
    """
    Hace una peticion HEAD a una URL y devuelve solo las cabeceras HTTP.
    Util para verificar si una URL existe, ver Content-Type, Last-Modified, etc.
    No descarga el cuerpo de la respuesta.

    Parametros:
      url: URL completa
    """
    result = await anyio.to_thread.run_sync(lambda: _do_fetch(url, method="HEAD"))

    if not result["ok"]:
        return f"ERROR: {result['error']}"

    status = result["status"]
    headers = result.get("headers", {})
    lines = [f"HTTP {status} — {url}", ""]
    for k, v in headers.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


# =====================================
# ENTRY POINT
# =====================================

if __name__ == "__main__":
    print("MCP fetch-server starting...", file=sys.stderr)
    mcp.run(transport="stdio")
