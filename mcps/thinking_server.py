"""
mcps/thinking_server.py
=======================
Servidor MCP de razonamiento secuencial (Sequential Thinking).

Permite al agente descomponer problemas complejos en pasos de pensamiento
explícitos antes de dar una respuesta final. Cada pensamiento puede revisar
o ramificar los anteriores.

Tools expuestas:
  - think        -> registra un paso de razonamiento
  - think_status -> muestra el estado actual del razonamiento
  - think_reset  -> limpia la cadena de pensamientos

Cómo funciona:
  El agente llama a `think` repetidamente para construir una cadena de
  razonamiento. Cada llamada devuelve el estado acumulado, lo que permite
  al LLM ver su propio proceso de pensamiento y corregirlo si es necesario.
  Cuando termina de razonar, produce la respuesta final sin llamar más tools.

Casos de uso ideales:
  - Análisis de bugs complejos
  - Planificación de cambios en múltiples archivos
  - Comparación de alternativas de diseño
  - Tareas que requieren varios pasos de lógica encadenada
"""

import sys
import json
from datetime import datetime
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# =====================================
# CONFIG
# =====================================

BASE_PATH    = Path(r"C:\Users\chuwi\ai-lab")
THOUGHTS_LOG = BASE_PATH / "data" / "thoughts.jsonl"

mcp = FastMCP("thinking-server")

# =====================================
# ESTADO EN MEMORIA
# (una cadena por sesión del servidor)
# =====================================

_thoughts: list[dict] = []


# =====================================
# HELPERS
# =====================================

def _log_thought(thought: dict):
    """Persiste el pensamiento en un log JSONL para auditoría."""
    try:
        THOUGHTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(THOUGHTS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(thought, ensure_ascii=False) + "\n")
    except Exception:
        pass  # el log es opcional, no debe romper el flujo


def _format_chain() -> str:
    """Formatea la cadena de pensamientos actual como texto legible."""
    if not _thoughts:
        return "(sin pensamientos registrados)"

    lines = []
    for t in _thoughts:
        n     = t["n"]
        total = t["total"]
        kind  = t.get("type", "thought")
        text  = t["content"]

        prefix = {
            "thought":    f"[{n}/{total}]",
            "revision":   f"[{n}/{total} REVISION]",
            "branch":     f"[{n}/{total} RAMA]",
            "conclusion": f"[{n}/{total} CONCLUSION]",
        }.get(kind, f"[{n}/{total}]")

        lines.append(f"{prefix} {text}")

    return "\n".join(lines)


# =====================================
# TOOLS
# =====================================

@mcp.tool()
def think(
    content: str,
    step_number: int,
    total_steps: int,
    thought_type: str = "thought",
    needs_more_thinking: bool = True
) -> str:
    """
    Registra un paso de razonamiento en la cadena de pensamiento.
    Usa esta tool para pensar en voz alta antes de responder.

    Parametros:
      content: el pensamiento, analisis o conclusion de este paso
      step_number: numero de este paso (empieza en 1)
      total_steps: estimacion del total de pasos necesarios
                   (puede ajustarse en pasos posteriores)
      thought_type: tipo de pensamiento:
                    'thought'    -> razonamiento normal (por defecto)
                    'revision'   -> corrige o matiza un pensamiento anterior
                    'branch'     -> explora una alternativa diferente
                    'conclusion' -> pensamiento final antes de responder
      needs_more_thinking: True si necesitas mas pasos, False si ya tienes
                           suficiente informacion para responder

    Devuelve la cadena de pensamientos acumulada hasta ahora.
    """
    valid_types = {"thought", "revision", "branch", "conclusion"}
    if thought_type not in valid_types:
        thought_type = "thought"

    entry = {
        "n":         step_number,
        "total":     total_steps,
        "type":      thought_type,
        "content":   content,
        "ts":        datetime.utcnow().isoformat(),
        "more":      needs_more_thinking
    }

    _thoughts.append(entry)
    _log_thought(entry)

    chain = _format_chain()

    if needs_more_thinking:
        footer = f"\n\n--- Continua razonando (paso {step_number} de ~{total_steps}) ---"
    else:
        footer = "\n\n--- Razonamiento completo. Puedes dar la respuesta final. ---"

    return chain + footer


@mcp.tool()
def think_status() -> str:
    """
    Muestra el estado actual de la cadena de razonamiento.
    Util para revisar lo que has pensado hasta ahora.
    Sin parametros.
    """
    if not _thoughts:
        return "No hay pensamientos registrados en esta sesion."

    last = _thoughts[-1]
    summary = [
        f"Pasos registrados : {len(_thoughts)}",
        f"Ultimo paso       : {last['n']} de ~{last['total']}",
        f"Tipo              : {last['type']}",
        f"Necesita mas      : {last['more']}",
        "",
        "Cadena completa:",
        _format_chain()
    ]
    return "\n".join(summary)


@mcp.tool()
def think_reset() -> str:
    """
    Limpia la cadena de pensamientos de la sesion actual.
    Util para empezar un nuevo problema desde cero.
    Sin parametros.
    """
    count = len(_thoughts)
    _thoughts.clear()
    return f"Cadena de pensamientos limpiada ({count} pasos eliminados)."


# =====================================
# ENTRY POINT
# =====================================

if __name__ == "__main__":
    print("MCP thinking-server starting...", file=sys.stderr)
    mcp.run(transport="stdio")
