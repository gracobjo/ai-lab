"""
mcp_agent_loop.py
=================
Agente MCP por línea de comandos.

Uso:
  .\\venv\\Scripts\\python.exe mcp_agent_loop.py "tu pregunta"
"""

import asyncio
import sys

from agent_core import BASE_PATH, MEMORY_FILE, MODEL_NAME, run_agent_query


def _configure_utf8_stdio():
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_configure_utf8_stdio()


async def run_agent_cli(user_input: str):
    print(f"\nModelo: {MODEL_NAME}")
    print(f"Proyecto: {BASE_PATH}\n")
    result = await run_agent_query(user_input, max_steps=10)
    print("\nRESPUESTA FINAL:\n")
    print(result["answer"])
    print(f"\nPasos: {result['steps']} | Tools: {', '.join(result['tools_used']) or 'ninguna'}")
    print(f"Memoria: {MEMORY_FILE}")


if __name__ == "__main__":
    user_input = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "Explora el proyecto y dime qué archivos Python existen y qué hace cada uno."
    )
    print(f"\nUsuario: {user_input}\n")
    asyncio.run(run_agent_cli(user_input))
