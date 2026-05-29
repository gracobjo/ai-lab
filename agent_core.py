"""
agent_core.py
=============
Lógica compartida del agente MCP (CLI y API web).
"""

import asyncio
import json
import os
import re
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
RUNTIME_FLAGS_FILE = BASE_PATH / "data" / "runtime_flags.json"
MODEL_NAME = os.environ.get("AI_LAB_MODEL", "qwen2.5-3b-instruct")

llm = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    timeout=300.0,
)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _read_runtime_flags() -> dict:
    if not RUNTIME_FLAGS_FILE.exists():
        return {}
    try:
        return json.loads(RUNTIME_FLAGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def powerbi_enabled() -> bool:
    """True si Power BI MCP debe cargarse (env o flag escrito por run_web_powerbi.ps1)."""
    if _env_truthy("AI_LAB_ENABLE_POWERBI"):
        return True
    return bool(_read_runtime_flags().get("powerbi"))


def set_runtime_powerbi(enabled: bool):
    """Persiste el flag de Power BI (sobrevive al reload de uvicorn en Windows)."""
    RUNTIME_FLAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    flags = _read_runtime_flags()
    flags["powerbi"] = enabled
    RUNTIME_FLAGS_FILE.write_text(
        json.dumps(flags, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _powerbi_server_params() -> StdioServerParameters:
    args = ["-y", "@microsoft/powerbi-modeling-mcp@latest", "--start"]
    if _env_truthy("AI_LAB_POWERBI_READONLY"):
        args.append("--readonly")
    return StdioServerParameters(command="npx", args=args)


def build_servers() -> dict[str, StdioServerParameters]:
    """Servidores MCP disponibles. Power BI solo si AI_LAB_ENABLE_POWERBI=1."""
    if _env_truthy("AI_LAB_POWERBI_ONLY"):
        return {"powerbi": _powerbi_server_params()}

    servers: dict[str, StdioServerParameters] = {
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
    if powerbi_enabled():
        servers["powerbi"] = _powerbi_server_params()
    return servers


SERVERS = build_servers()


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

def safe_llm_call(
    messages: list[dict],
    tools: list[dict],
    retries: int = 3,
    tool_choice: str | dict | None = None,
):
    def _call(_messages: list[dict], _tools: list[dict] | None, _tool_choice):
        choice = _tool_choice
        if _tools is None:
            choice = None
        elif choice is None:
            choice = "auto"
        return llm.chat.completions.create(
            model=MODEL_NAME,
            messages=_messages,
            tools=_tools if _tools else None,
            tool_choice=choice,
            temperature=0.1,
            max_tokens=700,
            parallel_tool_calls=True,
        )

    for i in range(retries):
        try:
            return _call(messages, tools, tool_choice)
        except Exception as e:
            msg = str(e)
            if "n_keep" in msg and "n_ctx" in msg:
                reduced = [messages[0]] + messages[-2:] if len(messages) >= 3 else messages
                pbi_tools = [t for t in tools if t["function"]["name"].startswith("powerbi__")]
                if pbi_tools:
                    try:
                        return _call(reduced, pbi_tools, tool_choice)
                    except Exception:
                        pass
                try:
                    return _call(reduced, None, None)
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


_POWERBI_KEYWORDS = (
    "power bi", "powerbi", "pbi", "dax", "medida", "medidas",
    "tabla", "tablas", "columna", "columnas", "modelo semantico", "semantic model",
    "pbix", "fabric",
)


def _is_powerbi_query(user_input: str) -> bool:
    text = user_input.lower()
    return any(k in text for k in _POWERBI_KEYWORDS)


def _only_powerbi_tools(all_tools: list[dict]) -> list[dict]:
    return [t for t in all_tools if t["function"]["name"].startswith("powerbi__")]


def _extract_powerbi_catalog(user_input: str) -> str | None:
    patterns = [
        r'initialCatalog\s*["\']([^"\']+)["\']',
        r"Con[eé]ctate a\s+['\"]?([\w-]+)['\"]?",
        r"Connect to\s+['\"]?([\w-]+)['\"]?",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input, re.I)
        if match:
            return match.group(1).strip()
    match = re.search(r"([\w-]+)\.pbix", user_input, re.I)
    if match:
        return match.group(1).strip()
    return None


def _extract_table_name(user_input: str) -> str | None:
    patterns = [
        r'tableName\s*["\']([^"\']+)["\']',
        r"tabla\s+['\"]?([\w-]+)['\"]?",
        r"table\s+['\"]?([\w-]+)['\"]?",
        r"de la tabla\s+['\"]?([\w-]+)['\"]?",
        r"\b(california_housing)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input, re.I)
        if match:
            return match.group(1).strip()
    return None


def _should_run_powerbi_list_columns(user_input: str) -> bool:
    text = user_input.lower()
    wants_columns = any(
        token in text
        for token in ("columna", "columnas", "columns", "listcolumns")
    )
    return wants_columns and (
        _extract_table_name(user_input) is not None or _is_powerbi_query(user_input)
    )


def _should_run_powerbi_list_tables(user_input: str) -> bool:
    text = user_input.lower()
    wants_list = bool(re.search(r"list(?:ar|a)(?:\s+\w+){0,4}\s+tablas\b", text))
    wants_list = wants_list or any(
        token in text
        for token in (
            "lista de tablas",
            "table_operations",
            "listlocalinstances",
        )
    )
    return wants_list and (_is_powerbi_query(user_input) or "connection_operations" in text)


async def _mcp_call(tool_map: dict, openai_name: str, args: dict) -> str:
    if openai_name not in tool_map:
        return f"ERROR: tool '{openai_name}' no encontrada."
    mcp_name, session = tool_map[openai_name]
    result = await session.call_tool(mcp_name, args)
    return result.content[0].text if result.content else "(sin resultado)"


def _powerbi_json_success(raw: str) -> bool:
    try:
        return json.loads(raw).get("success") is True
    except json.JSONDecodeError:
        return "success" in raw.lower() and "true" in raw.lower()


def _format_powerbi_list(raw: str, title: str) -> str:
    """Convierte JSON de tools Power BI en lista legible."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not payload.get("success"):
        return raw
    items = payload.get("data")
    if not isinstance(items, list):
        return raw

    flat: list = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("columns"), list):
            for col in item["columns"]:
                flat.append(col if isinstance(col, dict) else {"name": str(col)})
        else:
            flat.append(item)

    header = payload.get("message") or f"{title} ({len(flat)})"
    lines = [header, ""]
    for item in flat:
        if isinstance(item, dict):
            name = item.get("name") or item.get("Name") or "?"
            details = []
            for key in ("dataType", "columnCount", "storageMode", "summarizeBy", "expression"):
                if item.get(key) is not None:
                    details.append(f"{key}={item[key]}")
            suffix = f" — {', '.join(details)}" if details else ""
            lines.append(f"- {name}{suffix}")
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


async def _powerbi_connect_direct(
    tool_map: dict, catalog: str
) -> tuple[bool, list[str], str]:
    """ListLocalInstances + Connect. Devuelve ok, tools usadas, resumen breve."""
    used: list[str] = []

    instances = await _mcp_call(
        tool_map,
        "powerbi__connection_operations",
        {"request": {"operation": "ListLocalInstances"}},
    )
    used.append("powerbi__connection_operations")

    connection_string, pick_note = _pick_powerbi_connection_string(instances, catalog)
    if not connection_string:
        return False, used, (
            f"No se pudo conectar a Power BI Desktop.\n{pick_note}\n{instances}"
        )

    connect = await _mcp_call(
        tool_map,
        "powerbi__connection_operations",
        {"request": {"operation": "Connect", "connectionString": connection_string}},
    )
    used.append("powerbi__connection_operations")

    summary = f"Conectado a '{catalog}' ({pick_note})."
    if not _powerbi_json_success(connect):
        summary += f"\nError de conexión:\n{connect}"
        return False, used, summary
    return True, used, summary


def _pick_powerbi_connection_string(instances_text: str, catalog: str) -> tuple[str | None, str]:
    """Elige connectionString de ListLocalInstances (mejor coincidencia + más reciente)."""
    try:
        payload = json.loads(instances_text)
    except json.JSONDecodeError:
        return None, "No se pudo parsear la respuesta de ListLocalInstances."

    items = payload.get("data") or []
    if not items:
        return None, "No hay instancias de Power BI Desktop en ejecución."

    catalog_lower = catalog.lower()
    matching = [
        item
        for item in items
        if catalog_lower in (item.get("parentWindowTitle") or "").lower()
    ]
    pool = matching if matching else items
    chosen = sorted(pool, key=lambda i: i.get("startTime") or "", reverse=True)[0]

    connection_string = chosen.get("connectionString")
    if not connection_string and chosen.get("port"):
        connection_string = f"Provider=MSOLAP;Data Source=localhost:{chosen['port']}"

    if not connection_string:
        return None, "La instancia local no incluyó connectionString ni port."

    title = chosen.get("parentWindowTitle") or catalog
    port = chosen.get("port")
    return connection_string, f"Instancia seleccionada: {title} (puerto {port})"


async def _powerbi_list_tables_direct(
    tool_map: dict, catalog: str
) -> tuple[str, list[str], int]:
    """Flujo fijo: conectar → List tablas."""
    ok, used, connect_summary = await _powerbi_connect_direct(tool_map, catalog)
    sections = [connect_summary]
    if not ok:
        return "\n\n".join(sections), used, 2

    tables_raw = await _mcp_call(
        tool_map,
        "powerbi__table_operations",
        {"request": {"operation": "List"}},
    )
    used.append("powerbi__table_operations")
    sections.append(_format_powerbi_list(tables_raw, "Tablas del modelo"))
    return "\n\n".join(sections), used, 3


async def _powerbi_list_columns_direct(
    tool_map: dict, catalog: str, table_name: str
) -> tuple[str, list[str], int]:
    """Flujo fijo: conectar → List columnas de una tabla."""
    ok, used, connect_summary = await _powerbi_connect_direct(tool_map, catalog)
    sections = [connect_summary]
    if not ok:
        return "\n\n".join(sections), used, 2

    columns_raw = await _mcp_call(
        tool_map,
        "powerbi__column_operations",
        {"request": {"operation": "List", "tableName": table_name}},
    )
    used.append("powerbi__column_operations")
    sections.append(_format_powerbi_list(columns_raw, f"Columnas de '{table_name}'"))
    return "\n\n".join(sections), used, 3


def _looks_like_fake_tool_json(content: str) -> bool:
    c = (content or "").strip()
    if c.startswith("{") and ("\"request\"" in c or "\"operation\"" in c):
        return True
    return "powerbi__connection_operations" in c or "powerbi__table_operations" in c or "powerbi__column_operations" in c or "listcolumns" in c.lower()


def _powerbi_tool_choice(tools_for_step: list[dict], tools_used: list[str]) -> str | None:
    """Fuerza function calling mientras no haya ejecutado ninguna tool Power BI."""
    if not tools_for_step:
        return None
    if not all(t["function"]["name"].startswith("powerbi__") for t in tools_for_step):
        return None
    if not tools_used:
        return "required"
    return None


def _tools_for_message(user_input: str, all_tools: list[dict]) -> list[dict]:
    pbi = _only_powerbi_tools(all_tools)
    if pbi and _is_powerbi_query(user_input):
        # No mezclar thinking: el modelo pequeño se queda en bucle sin llamar Power BI bien.
        return pbi
    if user_input.strip().lower().startswith(("explica", "explícame", "explicame")):
        if not _is_powerbi_query(user_input):
            return []
    return all_tools


# =====================================
# AGENTE
# =====================================

async def run_agent_query(user_input: str, max_steps: int = 8) -> dict:
    """Ejecuta el agente y devuelve answer, steps, tools_used."""
    if powerbi_enabled() and _is_powerbi_query(user_input):
        max_steps = max(max_steps, 12)

    history = load_memory()
    all_tools: list[dict] = []
    tool_map: dict[str, tuple] = {}
    steps_done = 0
    tools_used: list[str] = []
    final_answer = ""

    powerbi_hint = ""
    if powerbi_enabled():
        powerbi_hint = """
POWER BI (powerbi__*) — OBLIGATORIO; NO uses thinking__think en preguntas Power BI.
- NO escribas codigo Python ni pseudo-llamadas; invoca las tools con argumentos JSON.
- Desktop abierto con el .pbix (nombre sin extension, ej. mi-modelo).

Secuencia tipica:
1) powerbi__connection_operations con request.operation = "ListLocalInstances".
2) powerbi__connection_operations con request.connectionString tomado de la instancia (NO basta initialCatalog solo).
3) powerbi__table_operations con request.operation = "List".
4) powerbi__column_operations con request.operation = "List" y request.tableName (NO existe ListColumns).

Ejemplo listar columnas:
{"request": {"operation": "List", "tableName": "california_housing"}}

Si Connect falla, muestra el error de la tool al usuario; no repitas el mismo plan.
"""

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
{powerbi_hint}"""

    async def run_loop():
        nonlocal steps_done, final_answer

        catalog = _extract_powerbi_catalog(user_input) or "mi-modelo"
        table_name = _extract_table_name(user_input)

        if powerbi_enabled() and "powerbi__connection_operations" in tool_map:
            try:
                if table_name and _should_run_powerbi_list_columns(user_input):
                    final_answer, direct_tools, steps_done = (
                        await _powerbi_list_columns_direct(tool_map, catalog, table_name)
                    )
                    tools_used.extend(direct_tools)
                    save_memory([
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": final_answer},
                    ])
                    return
                if _should_run_powerbi_list_tables(user_input):
                    final_answer, direct_tools, steps_done = (
                        await _powerbi_list_tables_direct(tool_map, catalog)
                    )
                    tools_used.extend(direct_tools)
                    save_memory([
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": final_answer},
                    ])
                    return
            except Exception as exc:
                final_answer = f"Error en flujo directo Power BI: {exc}"
                return

        messages = [
            {"role": "system", "content": system_prompt},
            *history[-10:],
            {"role": "user", "content": user_input},
        ]

        for step in range(max_steps):
            steps_done = step + 1
            tools_for_step = _tools_for_message(user_input, all_tools)
            choice = _powerbi_tool_choice(tools_for_step, tools_used)

            response = safe_llm_call(messages, tools_for_step, tool_choice=choice)
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
                content = msg.content or ""
                if (
                    tools_for_step
                    and _is_powerbi_query(user_input)
                    and _looks_like_fake_tool_json(content)
                ):
                    messages.append({
                        "role": "user",
                        "content": (
                            "No respondas con JSON en texto. Debes invocar la tool MCP "
                            "powerbi__connection_operations con function calling, no escribir el JSON como respuesta."
                        ),
                    })
                    continue
                final_answer = content
                messages.append({"role": "assistant", "content": final_answer})
                save_memory(messages)
                return

    await open_servers_and_run(list(build_servers().items()), all_tools, tool_map, run_loop)

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

    for server_name, params in build_servers().items():
        await collect(server_name, params)

    return tools_info


def get_mcp_prompt_catalog() -> list[dict]:
    """Frases de ejemplo por servidor MCP (UI del chat)."""
    catalog: list[dict] = [
        {
            "id": "filesystem",
            "label": "Archivos",
            "description": "Explorar y leer archivos del proyecto",
            "color": "#3b82f6",
            "prompts": [
                "Lista los archivos Python en la raíz del proyecto",
                "Lee el contenido de README.md",
                "¿Qué hay en la carpeta docs/?",
            ],
        },
        {
            "id": "custom",
            "label": "Proyecto ai-lab",
            "description": "Código, búsqueda en archivos y RAG",
            "color": "#8b5cf6",
            "prompts": [
                "Resume el proyecto con get_project_summary",
                "Busca en el código dónde se define run_agent_query",
                "¿Qué archivos Python hay y qué hace cada uno?",
            ],
        },
        {
            "id": "git",
            "label": "Git",
            "description": "Estado, historial y cambios del repositorio",
            "color": "#f97316",
            "prompts": [
                "Resume el estado del repositorio git",
                "Muestra los últimos 5 commits",
                "¿Qué archivos cambiaron respecto al último commit?",
            ],
        },
        {
            "id": "fetch",
            "label": "Web",
            "description": "Consultar URLs y APIs externas",
            "color": "#06b6d4",
            "prompts": [
                "Obtén el contenido de https://docs.python.org/3/",
                "Haz fetch de los headers de https://github.com",
            ],
        },
        {
            "id": "thinking",
            "label": "Razonamiento",
            "description": "Planificar antes de actuar",
            "color": "#eab308",
            "prompts": [
                "Explícame el flujo desde la pregunta del usuario hasta la respuesta del agente",
                "Piensa paso a paso cómo añadir una nueva tool MCP al proyecto",
            ],
        },
        {
            "id": "powerbi",
            "label": "Power BI",
            "description": "Modelo semántico en Desktop (tablas, columnas, DAX)",
            "color": "#f2c811",
            "requires": "powerbi",
            "prompts": [
                "Lista las tablas del modelo abierto en Power BI",
                "Lista las columnas de la tabla california_housing",
                "Conéctate a mi-modelo y lista todas las tablas",
            ],
        },
    ]

    active = set(build_servers().keys())
    powerbi_only = _env_truthy("AI_LAB_POWERBI_ONLY")
    out: list[dict] = []
    for entry in catalog:
        if entry["id"] not in active:
            if entry["id"] == "powerbi" and not powerbi_only:
                out.append({
                    "id": entry["id"],
                    "label": entry["label"],
                    "description": entry["description"],
                    "color": entry["color"],
                    "prompts": entry["prompts"],
                    "disabled": True,
                    "disabled_hint": (
                        "Activa Power BI con .\\run_web_powerbi.ps1 "
                        "(Desktop abierto con tu .pbix)"
                    ),
                })
            continue
        item = {k: v for k, v in entry.items() if k != "requires"}
        out.append(item)
    return out
