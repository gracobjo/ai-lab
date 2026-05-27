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
# CONFIG
# =====================================

BASE_PATH   = Path(r"C:\Users\chuwi\ai-lab")
MEMORY_FILE = BASE_PATH / "data" / "memory.json"

# =====================================
# LM STUDIO CLIENT
# =====================================

llm = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
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
    for i in range(retries):
        try:
            return llm.chat.completions.create(
                model="qwen2.5-7b-instruct-1m",
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                temperature=0.1,
                parallel_tool_calls=True
            )
        except Exception as e:
            msg = str(e)
            print(f"\n⚠️  LLM error (intento {i+1}): {msg}")
            if "Model reloaded" in msg:
                print("⏳ Modelo recargado → esperando 3s...")
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
                await session.initialize()
                tools_resp = await session.list_tools()
                for t in tools_resp.tools:
                    ot = mcp_tool_to_openai(t, server_name)
                    all_tools.append(ot)
                    tool_map[ot["function"]["name"]] = (t.name, session)
                print(f"✅ Servidor '{server_name}': {len(tools_resp.tools)} tools")

                await open_servers_and_run(rest, all_tools, tool_map, callback)

    except Exception as e:
        print(f"⚠️  Servidor '{server_name}' no disponible: {e}")
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
    system_prompt = f"""Eres un agente autónomo con acceso a herramientas MCP.

MEMORIA DE CONVERSACIONES PREVIAS:
{memory_summary(history)}

INSTRUCCIONES:
- Usa las herramientas disponibles para responder con información real.
- Puedes llamar varias herramientas a la vez si lo necesitas.
- Sé conciso y directo en tus respuestas finales.
- El proyecto base está en: {BASE_PATH}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        *history[-10:],
        {"role": "user", "content": user_input}
    ]

    for step in range(10):
        print(f"\n{'='*50}")
        print(f"🧠 PASO {step + 1}")

        response = safe_llm_call(messages, all_tools)
        msg = response.choices[0].message

        # =====================================
        # MULTI-TOOL: todas las calls en paralelo
        # =====================================

        if msg.tool_calls:
            print(f"\n🔧 Tool calls en este paso: {len(msg.tool_calls)}")

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

                print(f"   ▶ {openai_name}({args})")

                if openai_name not in tool_map:
                    return tc.id, f"ERROR: tool '{openai_name}' no encontrada."

                mcp_name, session = tool_map[openai_name]

                try:
                    result = await session.call_tool(mcp_name, args)
                    text = result.content[0].text if result.content else "(sin resultado)"
                    print(f"   ✅ resultado: {text[:100]}...")
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
            print(f"\n✅ RESPUESTA FINAL:\n")
            print(final_answer)

            messages.append({"role": "assistant", "content": final_answer})
            save_memory(messages)
            print(f"\n💾 Memoria guardada en: {MEMORY_FILE}")
            return

    print("\n⚠️  El agente alcanzó el límite de pasos (10).")


# =====================================
# ENTRY POINT
# =====================================

async def run_agent(user_input: str):
    history  = load_memory()
    all_tools: list[dict] = []
    tool_map: dict[str, tuple] = {}

    server_list = list(SERVERS.items())

    async def run():
        print(f"\n🔧 Total tools disponibles: {len(all_tools)}")
        for t in all_tools:
            print(f"   - {t['function']['name']}")
        await agent_loop(user_input, all_tools, tool_map, history)

    await open_servers_and_run(server_list, all_tools, tool_map, run)


if __name__ == "__main__":
    import sys

    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else \
        "Explora el proyecto y dime qué archivos Python existen y qué hace cada uno."

    print(f"\n👤 Usuario: {user_input}\n")
    asyncio.run(run_agent(user_input))
