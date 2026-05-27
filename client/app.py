"""
client/app.py
=============
API REST con FastAPI que expone el agente MCP como servicio HTTP.
Incluye interfaz web de chat accesible en http://localhost:8000

Endpoints:
  GET  /              -> interfaz web de chat
  POST /chat          -> envia un mensaje al agente
  GET  /memory        -> consulta el historial de conversacion
  DELETE /memory      -> borra el historial
  GET  /tools         -> lista las tools MCP disponibles
  GET  /health        -> estado del servicio

Uso:
  uvicorn client.app:app --reload --port 8000
"""

import asyncio
import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
# AGENTE
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
        print(f"Servidor '{server_name}' no disponible: {e}")
        return await _open_servers_and_run(rest, all_tools, tool_map, callback)


async def run_agent_once(user_input: str, max_steps: int = 8) -> dict:
    """Ejecuta el agente y devuelve respuesta, pasos y tools usadas."""

    history      = load_memory()
    all_tools:   list[dict] = []
    tool_map:    dict[str, tuple] = {}
    steps_done   = 0
    tools_used   = []
    final_answer = ""

    system_prompt = f"""Eres un agente autonomo con acceso a herramientas MCP.

MEMORIA:
{memory_summary(history)}

Usa las herramientas disponibles. Se conciso.
Proyecto base: {BASE_PATH}

CUANDO USAR thinking__think:
Antes de responder preguntas complejas, usa think para razonar paso a paso.
No es necesario para preguntas simples.
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
        "answer": final_answer or "El agente no genero respuesta final.",
        "steps": steps_done,
        "tools_used": list(set(tools_used))
    }


# =====================================
# INTERFAZ WEB
# =====================================

WEB_UI = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ai-lab</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f1117;
      color: #e0e0e0;
      height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* HEADER */
    header {
      padding: 14px 24px;
      background: #1a1d27;
      border-bottom: 1px solid #2a2d3a;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }
    header h1 { font-size: 1.1rem; font-weight: 600; color: #fff; }
    header span { font-size: 0.78rem; color: #666; }

    #status-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: #444;
      display: inline-block;
      margin-right: 6px;
      transition: background 0.3s;
    }
    #status-dot.ok  { background: #4caf50; }
    #status-dot.err { background: #f44336; }

    /* CHAT */
    #chat {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .msg {
      max-width: 78%;
      padding: 12px 16px;
      border-radius: 12px;
      line-height: 1.55;
      font-size: 0.92rem;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .msg.user {
      align-self: flex-end;
      background: #2563eb;
      color: #fff;
      border-bottom-right-radius: 4px;
    }
    .msg.agent {
      align-self: flex-start;
      background: #1e2130;
      border: 1px solid #2a2d3a;
      border-bottom-left-radius: 4px;
    }
    .msg.system {
      align-self: center;
      background: transparent;
      color: #555;
      font-size: 0.78rem;
      border: none;
      padding: 4px 0;
    }

    .meta {
      font-size: 0.72rem;
      color: #555;
      margin-top: 6px;
    }

    /* TYPING INDICATOR */
    .typing {
      align-self: flex-start;
      background: #1e2130;
      border: 1px solid #2a2d3a;
      border-radius: 12px;
      border-bottom-left-radius: 4px;
      padding: 14px 18px;
      display: flex;
      gap: 5px;
      align-items: center;
    }
    .typing span {
      width: 7px; height: 7px;
      background: #555;
      border-radius: 50%;
      animation: bounce 1.2s infinite;
    }
    .typing span:nth-child(2) { animation-delay: 0.2s; }
    .typing span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bounce {
      0%, 80%, 100% { transform: translateY(0); }
      40%           { transform: translateY(-6px); background: #2563eb; }
    }

    /* INPUT */
    #input-area {
      padding: 16px 24px;
      background: #1a1d27;
      border-top: 1px solid #2a2d3a;
      display: flex;
      gap: 10px;
      flex-shrink: 0;
    }

    #msg-input {
      flex: 1;
      background: #0f1117;
      border: 1px solid #2a2d3a;
      border-radius: 8px;
      color: #e0e0e0;
      padding: 10px 14px;
      font-size: 0.92rem;
      resize: none;
      outline: none;
      min-height: 44px;
      max-height: 140px;
      line-height: 1.5;
      transition: border-color 0.2s;
    }
    #msg-input:focus { border-color: #2563eb; }
    #msg-input::placeholder { color: #444; }

    #send-btn {
      background: #2563eb;
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 0 20px;
      font-size: 0.92rem;
      cursor: pointer;
      transition: background 0.2s, opacity 0.2s;
      white-space: nowrap;
      align-self: flex-end;
      height: 44px;
    }
    #send-btn:hover:not(:disabled) { background: #1d4ed8; }
    #send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

    /* SIDEBAR TOOLS */
    #sidebar {
      position: fixed;
      right: 0; top: 0; bottom: 0;
      width: 280px;
      background: #1a1d27;
      border-left: 1px solid #2a2d3a;
      padding: 16px;
      overflow-y: auto;
      transform: translateX(100%);
      transition: transform 0.25s;
      z-index: 10;
    }
    #sidebar.open { transform: translateX(0); }
    #sidebar h2 { font-size: 0.85rem; color: #888; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
    .tool-item { padding: 8px 10px; border-radius: 6px; margin-bottom: 4px; font-size: 0.78rem; }
    .tool-item .tool-name { color: #7dd3fc; font-family: monospace; }
    .tool-item .tool-desc { color: #666; margin-top: 2px; }
    .tool-server { font-size: 0.7rem; color: #444; margin-top: 2px; }

    #tools-btn {
      background: transparent;
      border: 1px solid #2a2d3a;
      color: #888;
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 0.78rem;
      cursor: pointer;
    }
    #tools-btn:hover { border-color: #555; color: #ccc; }

    #clear-btn {
      background: transparent;
      border: 1px solid #2a2d3a;
      color: #888;
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 0.78rem;
      cursor: pointer;
    }
    #clear-btn:hover { border-color: #f44336; color: #f44336; }

    .header-actions { display: flex; gap: 8px; align-items: center; }

    /* SCROLLBAR */
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #2a2d3a; border-radius: 3px; }
  </style>
</head>
<body>

<header>
  <h1><span id="status-dot"></span>ai-lab</h1>
  <div class="header-actions">
    <button id="clear-btn" title="Borrar historial">Limpiar</button>
    <button id="tools-btn" title="Ver tools disponibles">Tools</button>
    <span id="status-text">conectando...</span>
  </div>
</header>

<div id="chat"></div>

<div id="input-area">
  <textarea id="msg-input" placeholder="Escribe tu pregunta..." rows="1"></textarea>
  <button id="send-btn" disabled>Enviar</button>
</div>

<div id="sidebar">
  <h2>Tools disponibles</h2>
  <div id="tools-list">Cargando...</div>
</div>

<script>
  const chat     = document.getElementById('chat');
  const input    = document.getElementById('msg-input');
  const sendBtn  = document.getElementById('send-btn');
  const dot      = document.getElementById('status-dot');
  const statusTx = document.getElementById('status-text');
  const sidebar  = document.getElementById('sidebar');
  const toolsList= document.getElementById('tools-list');
  const toolsBtn = document.getElementById('tools-btn');
  const clearBtn = document.getElementById('clear-btn');

  // ── Utilidades ──────────────────────────────────────────

  function addMsg(role, text, meta) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.textContent = text;
    if (meta) {
      const m = document.createElement('div');
      m.className = 'meta';
      m.textContent = meta;
      div.appendChild(m);
    }
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }

  function addTyping() {
    const div = document.createElement('div');
    div.className = 'typing';
    div.id = 'typing';
    div.innerHTML = '<span></span><span></span><span></span>';
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
  }

  function removeTyping() {
    const t = document.getElementById('typing');
    if (t) t.remove();
  }

  function setStatus(ok) {
    dot.className = ok ? 'ok' : 'err';
    statusTx.textContent = ok ? 'conectado' : 'sin conexion';
    sendBtn.disabled = !ok;
  }

  // ── Health check ────────────────────────────────────────

  async function checkHealth() {
    try {
      const r = await fetch('/health');
      if (r.ok) {
        const d = await r.json();
        setStatus(true);
        addMsg('system', `Modelo: ${d.model}`);
      } else {
        setStatus(false);
      }
    } catch {
      setStatus(false);
      addMsg('system', 'No se puede conectar con la API. Verifica que el servidor esta activo.');
    }
  }

  // ── Cargar historial ────────────────────────────────────

  async function loadHistory() {
    try {
      const r = await fetch('/memory');
      const d = await r.json();
      if (d.count > 0) {
        addMsg('system', `Historial cargado: ${d.count} mensajes previos`);
        d.messages.slice(-6).forEach(m => {
          addMsg(m.role === 'user' ? 'user' : 'agent', m.content);
        });
      }
    } catch { /* sin historial */ }
  }

  // ── Enviar mensaje ──────────────────────────────────────

  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    input.style.height = 'auto';
    sendBtn.disabled = true;

    addMsg('user', text);
    addTyping();

    try {
      const r = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, max_steps: 8 })
      });

      removeTyping();

      if (!r.ok) {
        const err = await r.json();
        addMsg('system', `Error: ${err.detail || r.statusText}`);
      } else {
        const d = await r.json();
        const meta = `${d.steps} paso${d.steps !== 1 ? 's' : ''} · ${d.tools_used.length} tool${d.tools_used.length !== 1 ? 's' : ''}: ${d.tools_used.join(', ') || 'ninguna'}`;
        addMsg('agent', d.answer, meta);
      }
    } catch (e) {
      removeTyping();
      addMsg('system', `Error de red: ${e.message}`);
    }

    sendBtn.disabled = false;
    input.focus();
  }

  // ── Tools sidebar ───────────────────────────────────────

  async function loadTools() {
    try {
      const r = await fetch('/tools');
      const d = await r.json();
      if (!d.tools || d.tools.length === 0) {
        toolsList.innerHTML = '<div style="color:#555;font-size:0.8rem">Sin tools disponibles</div>';
        return;
      }
      // Agrupar por servidor
      const byServer = {};
      d.tools.forEach(t => {
        if (!byServer[t.server]) byServer[t.server] = [];
        byServer[t.server].push(t);
      });
      toolsList.innerHTML = '';
      Object.entries(byServer).forEach(([server, tools]) => {
        const h = document.createElement('div');
        h.style.cssText = 'color:#555;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;margin:12px 0 6px';
        h.textContent = server;
        toolsList.appendChild(h);
        tools.forEach(t => {
          const item = document.createElement('div');
          item.className = 'tool-item';
          item.innerHTML = `<div class="tool-name">${t.name}</div><div class="tool-desc">${t.description.slice(0, 80)}${t.description.length > 80 ? '...' : ''}</div>`;
          toolsList.appendChild(item);
        });
      });
    } catch {
      toolsList.innerHTML = '<div style="color:#555;font-size:0.8rem">Error cargando tools</div>';
    }
  }

  toolsBtn.addEventListener('click', () => {
    sidebar.classList.toggle('open');
    if (sidebar.classList.contains('open')) loadTools();
  });

  // ── Limpiar historial ───────────────────────────────────

  clearBtn.addEventListener('click', async () => {
    if (!confirm('Borrar el historial de conversacion?')) return;
    await fetch('/memory', { method: 'DELETE' });
    chat.innerHTML = '';
    addMsg('system', 'Historial borrado.');
  });

  // ── Input: auto-resize + Enter para enviar ──────────────

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) sendMessage();
    }
  });

  sendBtn.addEventListener('click', sendMessage);

  // ── Init ────────────────────────────────────────────────

  (async () => {
    await checkHealth();
    await loadHistory();
    input.focus();
  })();
</script>
</body>
</html>"""


# =====================================
# FASTAPI APP
# =====================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("ai-lab API iniciada — http://localhost:8000")
    yield
    print("ai-lab API detenida")


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

@app.get("/", response_class=HTMLResponse)
async def web_ui():
    """Interfaz web de chat."""
    return WEB_UI


@app.get("/health")
async def health():
    """Estado del servicio."""
    return {"status": "ok", "model": "qwen2.5-7b-instruct-1m", "base": str(BASE_PATH)}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Envia un mensaje al agente y obtiene respuesta."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacio.")
    result = await run_agent_once(req.message, max_steps=req.max_steps)
    return ChatResponse(**result)


@app.get("/memory", response_model=MemoryResponse)
async def get_memory():
    """Devuelve el historial de conversacion."""
    history = load_memory()
    return MemoryResponse(messages=history, count=len(history))


@app.delete("/memory")
async def clear_memory():
    """Borra el historial de conversacion."""
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
