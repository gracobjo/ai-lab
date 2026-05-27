"""
client/app.py
=============
API REST con FastAPI que expone el agente MCP como servicio HTTP.

Endpoints:
  POST /chat          → envía un mensaje al agente
  GET  /memory        → consulta el historial de conversación
  DELETE /memory      → borra el historial
  GET  /tools         → lista las tools MCP disponibles
  GET  /health        → estado del servicio

Uso:
  uvicorn client.app:app --reload --port 8000
"""

import asyncio
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# =====================================
# CONFIG
# =====================================

BASE_PATH   = Path(r"C:\Users\chuwi\ai-lab")
MEMORY_FILE = BASE_PATH / "data" / "memory.json"

llm = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio"
)

SERVERS = {
    "filesystem": StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", str(BASE_PATH)]
    ),
    "custom": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "server.py")]
    ),
}

# =====================================
# MODELOS PYDANTIC
# =====================================

class ChatRequest(BaseModel):
    message: str
    max_steps: int = 8


class ChatResponse(BaseModel):
    answer: str
    steps: int
    tools_used: list[str]


class MemoryResponse(BaseModel):
    messages: list[dict]
    count: int


class ToolInfo(BaseModel):
    name: str
    description: str
    server: str


# =====================================
# HELPERS DE MEMORIA
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
        lines.append(f"{role}: {m['content'][:100]}...")
    return "\n".join(lines)


# =====================================
# TOOL HELPERS
# =====================================

def mcp_tool_to_openai(tool, server_name: str) -> dict:
    schema = {}
    if hasattr(tool, "inputSchema") and tool.inputSchema:
        schema = {k: v for k, v in tool.inputSchema.items() if k != "title"}
    return {
        "type": "function",
        "function": {
            "name": f"{server_name}__{tool.name}",
            "description": tool.description or "",
            "parameters": schema or {"type": "object", "properties": {}}
        }
    }


# =====================================
# AGENTE (reutilizable por endpoint)
# =====================================

async def _open_servers_and_run(
    server_list: list[tuple],
    all_tools: list,
    tool_map: dict,
    callback,
):
    """Abre servidores MCP recursivamente respetando los cancel scopes de anyio."""
    if not server_list:
        return await callback()

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
                return await _open_servers_and_run(rest, all_tools, tool_map, callback)
    except Exception as e:
        print(f"⚠️  Servidor '{server_name}' no disponible: {e}")
        return await _open_servers_and_run(rest, all_tools, tool_map, callback)


async def run_agent_once(user_input: str, max_steps: int = 8) -> dict:
    """Ejecuta el agente y devuelve respuesta, pasos y tools usadas."""

    history   = load_memory()
    all_tools: list[dict] = []
    tool_map:  dict[str, tuple] = {}
    steps_done   = 0
    tools_used   = []
    final_answer = ""

    system_prompt = f"""Eres un agente autónomo con acceso a herramientas MCP.

MEMORIA:
{memory_summary(history)}

Usa las herramientas disponibles. Sé conciso.
Proyecto base: {BASE_PATH}
"""

    async def run_loop():
        nonlocal steps_done, final_answer

        messages = [
            {"role": "system", "content": system_prompt},
            *history[-10:],
            {"role": "user", "content": user_input}
        ]

        for step in range(max_steps):
            steps_done = step + 1

            response = llm.chat.completions.create(
                model="qwen2.5-7b-instruct-1m",
                messages=messages,
                tools=all_tools if all_tools else None,
                tool_choice="auto" if all_tools else None,
                temperature=0.1,
                parallel_tool_calls=True
            )

            msg = response.choices[0].message

            if msg.tool_calls:
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
                    tools_used.append(openai_name)
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        args = {}
                    if openai_name not in tool_map:
                        return tc.id, f"Tool '{openai_name}' no encontrada."
                    mcp_name, session = tool_map[openai_name]
                    try:
                        result = await session.call_tool(mcp_name, args)
                        return tc.id, result.content[0].text if result.content else ""
                    except Exception as e:
                        return tc.id, f"ERROR: {e}"

                results = await asyncio.gather(*[execute_tool(tc) for tc in msg.tool_calls])
                for tool_call_id, result_text in results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result_text
                    })

            else:
                final_answer = msg.content or ""
                messages.append({"role": "assistant", "content": final_answer})
                save_memory(messages)
                break

    await _open_servers_and_run(list(SERVERS.items()), all_tools, tool_map, run_loop)

    return {
        "answer": final_answer or "El agente no generó respuesta final.",
        "steps": steps_done,
        "tools_used": list(set(tools_used))
    }


# =====================================
# FASTAPI APP
# =====================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 ai-lab API iniciada")
    yield
    print("🛑 ai-lab API detenida")


app = FastAPI(
    title="ai-lab Agent API",
    description="API REST para el agente MCP de ai-lab",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================================
# ENDPOINTS
# =====================================

@app.get("/health")
async def health():
    """Estado del servicio."""
    return {"status": "ok", "model": "qwen2.5-7b-instruct-1m", "base": str(BASE_PATH)}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Envía un mensaje al agente y obtiene respuesta."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío.")
    result = await run_agent_once(req.message, max_steps=req.max_steps)
    return ChatResponse(**result)


@app.get("/memory", response_model=MemoryResponse)
async def get_memory():
    """Devuelve el historial de conversación."""
    history = load_memory()
    return MemoryResponse(messages=history, count=len(history))


@app.delete("/memory")
async def clear_memory():
    """Borra el historial de conversación."""
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()
    return {"status": "ok", "message": "Historial borrado."}


@app.get("/tools")
async def list_tools():
    """Lista las tools MCP disponibles."""
    tools_info: list[ToolInfo] = []

    async def collect(server_name, params):
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    resp = await session.list_tools()
                    for t in resp.tools:
                        tools_info.append(ToolInfo(
                            name=t.name,
                            description=t.description or "",
                            server=server_name
                        ))
        except Exception as e:
            tools_info.append(ToolInfo(
                name=f"ERROR_{server_name}",
                description=str(e),
                server=server_name
            ))

    for server_name, params in SERVERS.items():
        await collect(server_name, params)

    return {"tools": tools_info, "count": len(tools_info)}
