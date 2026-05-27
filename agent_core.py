"""
agent_core.py
=============
Lógica compartida del agente MCP (CLI y API web).
"""

import asyncio
import json
import os
import time
from pathlib import Path

from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# =====================================
# CONFIG
# =====================================

BASE_PATH = Path(__file__).resolve().parent
MEMORY_FILE = BASE_PATH / "data" / "memory.json"
MODEL_NAME = os.environ.get("AI_LAB_MODEL", "qwen2.5-3b-instruct")

llm = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    timeout=300.0,
)

SERVERS = {
    "filesystem": StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", str(BASE_PATH)],
    ),
    "custom": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "server.py")],
    ),
    "git": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "git_server.py")],
    ),
    "fetch": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "fetch_server.py")],
    ),
    "thinking": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "thinking_server.py")],
    ),
}


# =====================================
# MEMORIA
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
        m
        for m in messages
        if m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str)
        and m.get("content", "").strip()
    ]
    to_save = to_save[-40:]
    MEMORY_FILE.write_text(
        json.dumps(to_save, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_memory():
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()


def memory_summary(history: list[dict]) -> str:
    if not history:
        return "Sin conversaciones previas."
    lines = []
    for m in history[-6:]:
        role = "Usuario" if m["role"] == "user" else "Asistente"
        lines.append(f"{role}: {m['content'][:120]}...")
    return "\n".join(lines)


# =====================================
# LLM
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
            parallel_tool_calls=True,
        )

    for i in range(retries):
        try:
            return _call(messages, tools)
        except Exception as e:
            msg = str(e)
            if "n_keep" in msg and "n_ctx" in msg:
                reduced = [messages[0]] + messages[-2:] if len(messages) >= 3 else messages
                try:
                    return _call(reduced, None)
                except Exception:
                    pass
            if "Model reloaded" in msg:
                time.sleep(3)
            else:
                time.sleep(1)
    raise RuntimeError("LLM falló tras todos los reintentos.")


# =====================================
# MCP
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
            "parameters": schema or {"type": "object", "properties": {}},
        },
    }


async def open_servers_and_run(
    server_list: list[tuple[str, StdioServerParameters]],
    all_tools: list,
    tool_map: dict,
    callback,
):
    if not server_list:
        await callback()
        return

    server_name, params = server_list[0]
    rest = server_list[1:]

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=20)
                tools_resp = await asyncio.wait_for(session.list_tools(), timeout=20)
                for t in tools_resp.tools:
                    ot = mcp_tool_to_openai(t, server_name)
                    all_tools.append(ot)
                    tool_map[ot["function"]["name"]] = (t.name, session)

                await open_servers_and_run(rest, all_tools, tool_map, callback)

    except Exception:
        await open_servers_and_run(rest, all_tools, tool_map, callback)


def _tools_for_message(user_input: str, all_tools: list[dict]) -> list[dict]:
    if user_input.strip().lower().startswith(("explica", "explícame", "explicame")):
        return []
    return all_tools


# =====================================
# AGENTE
# =====================================

async def run_agent_query(user_input: str, max_steps: int = 8) -> dict:
    """Ejecuta el agente y devuelve answer, steps, tools_used."""

    history = load_memory()
    all_tools: list[dict] = []
    tool_map: dict[str, tuple] = {}
    steps_done = 0
    tools_used: list[str] = []
    final_answer = ""

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

    async def run_loop():
        nonlocal steps_done, final_answer

        messages = [
            {"role": "system", "content": system_prompt},
            *history[-10:],
            {"role": "user", "content": user_input},
        ]

        for step in range(max_steps):
            steps_done = step + 1
            tools_for_step = _tools_for_message(user_input, all_tools)

            response = safe_llm_call(messages, tools_for_step)
            msg = response.choices[0].message

            if msg.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )

                async def execute_tool(tc):
                    openai_name = tc.function.name
                    tools_used.append(openai_name)
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}
                    if openai_name not in tool_map:
                        return tc.id, f"ERROR: tool '{openai_name}' no encontrada."
                    mcp_name, session = tool_map[openai_name]
                    try:
                        result = await session.call_tool(mcp_name, args)
                        text = (
                            result.content[0].text
                            if result.content
                            else "(sin resultado)"
                        )
                        return tc.id, text
                    except Exception as e:
                        return tc.id, f"ERROR ejecutando tool: {e}"

                results = await asyncio.gather(
                    *[execute_tool(tc) for tc in msg.tool_calls]
                )
                for tool_call_id, result_text in results:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": result_text,
                        }
                    )
            else:
                final_answer = msg.content or ""
                messages.append({"role": "assistant", "content": final_answer})
                save_memory(messages)
                return

    await open_servers_and_run(list(SERVERS.items()), all_tools, tool_map, run_loop)

    return {
        "answer": final_answer or "El agente no generó respuesta final (límite de pasos).",
        "steps": steps_done,
        "tools_used": list(dict.fromkeys(tools_used)),
    }


async def list_mcp_tools() -> list[dict]:
    """Lista tools de todos los servidores (para GET /tools)."""
    tools_info: list[dict] = []

    async def collect(server_name: str, params: StdioServerParameters):
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=20)
                    resp = await asyncio.wait_for(session.list_tools(), timeout=20)
                    for t in resp.tools:
                        tools_info.append(
                            {
                                "name": t.name,
                                "description": t.description or "",
                                "server": server_name,
                            }
                        )
        except Exception as e:
            tools_info.append(
                {
                    "name": f"ERROR_{server_name}",
                    "description": str(e),
                    "server": server_name,
                }
            )

    for server_name, params in SERVERS.items():
        await collect(server_name, params)

    return tools_info
