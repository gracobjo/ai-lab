"""
mcp_agent_loop.py
=================
Agente MCP mejorado con:
  - Multi-tool: ejecuta varias tools en paralelo en un mismo paso
  - Memoria: historial persistido en data/memory.json
  - Múltiples servidores MCP simultáneos (filesystem + custom)
  - Function calling nativo de OpenAI (sin JSON manual)
  - Retry robusto ante recargas del modelo
"""

import asyncio
import json
import time
from pathlib import Path

from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# =====================================
# MODELO LLM (LM Studio)
# =====================================
import os
MODEL_NAME = os.environ.get("AI_LAB_MODEL", "qwen2.5-3b-instruct")

# =====================================
# CONSOLA WINDOWS: evitar UnicodeEncodeError (cp1252)
# =====================================
def _configure_utf8_stdio():
    try:
        import sys
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_configure_utf8_stdio()

# =====================================
# CONFIG
# =====================================

BASE_PATH   = Path(r"C:\Users\chuwi\ai-lab")
MEMORY_FILE = BASE_PATH / "data" / "memory.json"

# =====================================
# LM STUDIO CLIENT
# =====================================

llm = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    timeout=300.0
)

# =====================================
# SERVIDORES MCP
# =====================================

SERVERS = {
    "filesystem": StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", str(BASE_PATH)]
    ),
    "custom": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "server.py")]
    ),
    "git": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "git_server.py")]
    ),
    "fetch": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "fetch_server.py")]
    ),
    "thinking": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "thinking_server.py")]
    ),
}

# =====================================
# MEMORIA PERSISTENTE
# =====================================

def load_memory() -> list[dict]:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_memory(messages: list[dict]):
    to_save = [
        m for m in messages
        if m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
        and m.get("content", "").strip()
    ]
    to_save = to_save[-40:]
    MEMORY_FILE.write_text(
        json.dumps(to_save, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def memory_summary(history: list[dict]) -> str:
    if not history:
        return "Sin conversaciones previas."
    lines = []
    for m in history[-6:]:
        role = "Usuario" if m["role"] == "user" else "Asistente"
        lines.append(f"{role}: {m['content'][:120]}...")
    return "\n".join(lines)


# =====================================
# LLM CALL ROBUSTO
# =====================================

def safe_llm_call(messages: list[dict], tools: list[dict], retries: int = 3):
    def _call(_messages: list[dict], _tools: list[dict] | None):
        return llm.chat.completions.create(
            model=MODEL_NAME,
            messages=_messages,
            tools=_tools if _tools else None,
            tool_choice="auto" if _tools else None,
            temperature=0.1,
            max_tokens=700,
            parallel_tool_calls=True
        )

    for i in range(retries):
        try:
            return _call(messages, tools)
        except Exception as e:
            msg = str(e)
            print(f"\n[WARN] LLM error (intento {i+1}): {msg}")
            # LM Studio / llama.cpp a veces falla si el prompt+tools exceden n_ctx
            if "n_keep" in msg and "n_ctx" in msg:
                print("[INFO] Contexto demasiado largo -> reintentando sin tools y con menos historial...")
                reduced = [messages[0]] + messages[-2:] if len(messages) >= 3 else messages
                try:
                    return _call(reduced, None)
                except Exception as e2:
                    print(f"[WARN] Reintento reducido falló: {e2}")
            if "Model reloaded" in msg:
                print("[INFO] Modelo recargado -> esperando 3s...")
                time.sleep(3)
            else:
                time.sleep(1)
    raise RuntimeError("LLM falló tras todos los reintentos.")


# =====================================
# CONVERTIR TOOLS MCP → OPENAI FORMAT
# =====================================

def mcp_tool_to_openai(tool, server_name: str) -> dict:
    schema = {}
    if hasattr(tool, "inputSchema") and tool.inputSchema:
        schema = tool.inputSchema
        if isinstance(schema, dict):
            schema = {k: v for k, v in schema.items() if k != "title"}

    return {
        "type": "function",
        "function": {
            "name": f"{server_name}__{tool.name}",
            "description": tool.description or "",
            "parameters": schema or {"type": "object", "properties": {}}
        }
    }


# =====================================
# CONEXIÓN A UN SERVIDOR MCP
# =====================================

async def connect_server(
    server_name: str,
    params: StdioServerParameters,
    all_tools: list,
    tool_map: dict,
):
    """
    Abre un servidor MCP usando los context managers nativos de anyio
    y llama al agente dentro del scope correcto.
    Devuelve (session, tools_count) o None si falla.
    """
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_resp = await session.list_tools()
            for t in tools_resp.tools:
                ot = mcp_tool_to_openai(t, server_name)
                all_tools.append(ot)
                tool_map[ot["function"]["name"]] = (t.name, session)
            print(f"✅ Servidor '{server_name}': {len(tools_resp.tools)} tools")
            # Ceder el control de vuelta al agente mientras la sesión sigue abierta
            yield session


# =====================================
# APERTURA RECURSIVA DE SERVIDORES
# =====================================

async def open_servers_and_run(
    server_list: list[tuple[str, StdioServerParameters]],
    all_tools: list,
    tool_map: dict,
    callback,
):
    """
    Abre los servidores MCP de forma recursiva para que cada
    `async with stdio_client(...)` viva en su propio task scope nativo.
    Cuando todos están abiertos, llama a callback().
    """
    if not server_list:
        await callback()
        return

    server_name, params = server_list[0]
    rest = server_list[1:]

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                print(f"[INFO] Abriendo servidor '{server_name}'...", flush=True)
                await asyncio.wait_for(session.initialize(), timeout=20)
                tools_resp = await asyncio.wait_for(session.list_tools(), timeout=20)
                for t in tools_resp.tools:
                    ot = mcp_tool_to_openai(t, server_name)
                    all_tools.append(ot)
                    tool_map[ot["function"]["name"]] = (t.name, session)
                print(f"[OK] Servidor '{server_name}': {len(tools_resp.tools)} tools", flush=True)

                await open_servers_and_run(rest, all_tools, tool_map, callback)

    except Exception as e:
        print(f"[WARN] Servidor '{server_name}' no disponible: {e}", flush=True)
        # Continuar con el resto aunque este falle
        await open_servers_and_run(rest, all_tools, tool_map, callback)


# =====================================
# LOOP DEL AGENTE
# =====================================

async def agent_loop(
    user_input: str,
    all_tools: list[dict],
    tool_map: dict,
    history: list[dict],
):
    system_prompt = f"""Eres un agente autonomo con acceso a herramientas MCP.

MEMORIA DE CONVERSACIONES PREVIAS:
{memory_summary(history)}

INSTRUCCIONES:
- Usa las herramientas disponibles para responder con informacion real.
- Puedes llamar varias herramientas a la vez si lo necesitas.
- Se conciso y directo en tus respuestas finales.
- El proyecto base esta en: {BASE_PATH}

CUANDO USAR thinking__think:
- Antes de responder preguntas complejas que requieren varios pasos de logica.
- Cuando necesites analizar un bug, planificar cambios o comparar alternativas.
- Usa think para razonar paso a paso ANTES de llamar otras tools o responder.
- No es necesario para preguntas simples o directas.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        *history[-10:],
        {"role": "user", "content": user_input}
    ]

    for step in range(10):
        print(f"\n{'='*50}", flush=True)
        print(f"PASO {step + 1}", flush=True)

        # Heurística: preguntas explicativas suelen no necesitar tools; además reduce tokens.
        tools_for_step = all_tools
        if user_input.strip().lower().startswith(("explica", "explícame", "explicame")):
            tools_for_step = []

        response = safe_llm_call(messages, tools_for_step)
        msg = response.choices[0].message

        # =====================================
        # MULTI-TOOL: todas las calls en paralelo
        # =====================================

        if msg.tool_calls:
            print(f"\nTool calls en este paso: {len(msg.tool_calls)}", flush=True)

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in msg.tool_calls
                ]
            })

            async def execute_tool(tc):
                openai_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}

                print(f"   -> {openai_name}({args})")

                if openai_name not in tool_map:
                    return tc.id, f"ERROR: tool '{openai_name}' no encontrada."

                mcp_name, session = tool_map[openai_name]

                try:
                    result = await session.call_tool(mcp_name, args)
                    text = result.content[0].text if result.content else "(sin resultado)"
                    print(f"   [OK] resultado: {text[:100]}...")
                    return tc.id, text
                except Exception as e:
                    return tc.id, f"ERROR ejecutando tool: {e}"

            results = await asyncio.gather(*[execute_tool(tc) for tc in msg.tool_calls])

            for tool_call_id, result_text in results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_text
                })

        # =====================================
        # RESPUESTA FINAL
        # =====================================

        else:
            final_answer = msg.content or ""
            print(f"\nRESPUESTA FINAL:\n", flush=True)
            print(final_answer, flush=True)

            messages.append({"role": "assistant", "content": final_answer})
            save_memory(messages)
            print(f"\nMemoria guardada en: {MEMORY_FILE}", flush=True)
            return

    print("\n[WARN] El agente alcanzó el límite de pasos (10).")


# =====================================
# ENTRY POINT
# =====================================

async def run_agent(user_input: str):
    history  = load_memory()
    all_tools: list[dict] = []
    tool_map: dict[str, tuple] = {}

    server_list = list(SERVERS.items())

    async def run():
        print(f"\nTotal tools disponibles: {len(all_tools)}", flush=True)
        for t in all_tools:
            print(f"   - {t['function']['name']}", flush=True)
        await agent_loop(user_input, all_tools, tool_map, history)

    await open_servers_and_run(server_list, all_tools, tool_map, run)


if __name__ == "__main__":
    import sys

    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else \
        "Explora el proyecto y dime qué archivos Python existen y qué hace cada uno."

    print(f"\nUsuario: {user_input}\n")
    asyncio.run(run_agent(user_input))
