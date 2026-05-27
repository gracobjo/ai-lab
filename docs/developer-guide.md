# Guía de Desarrollador — ai-lab

## Índice

1. [Visión general](#1-visión-general)
2. [Arquitectura del sistema](#2-arquitectura-del-sistema)
3. [Estructura de carpetas](#3-estructura-de-carpetas)
4. [Módulos y responsabilidades](#4-módulos-y-responsabilidades)
5. [Flujo de ejecución del agente](#5-flujo-de-ejecución-del-agente)
6. [Servidores MCP](#6-servidores-mcp)
7. [Sistema RAG](#7-sistema-rag)
8. [API REST](#8-api-rest)
9. [Memoria persistente](#9-memoria-persistente)
10. [Decisiones de diseño relevantes](#10-decisiones-de-diseño-relevantes)
11. [Configuración y variables](#11-configuración-y-variables)
12. [Dependencias](#12-dependencias)
13. [Extensión del sistema](#13-extensión-del-sistema)

---

## 1. Visión general

ai-lab es un laboratorio de aprendizaje e implementación de agentes IA locales. El sistema conecta un modelo LLM local (servido por LM Studio) con herramientas externas a través del protocolo MCP (Model Context Protocol), añadiendo capacidades de búsqueda semántica (RAG), acceso web, control de versiones, razonamiento secuencial y memoria persistente entre sesiones.

El proyecto está estructurado como una progresión didáctica: desde un cliente de chat básico hasta un agente completo con 5 servidores MCP, 31 tools, RAG y API REST.

---

## 2. Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                       CLIENTE / USUARIO                          │
│           CLI (mcp_agent_loop.py) │ API (client/app.py)         │
└───────────────────────┬─────────────────────────────────────────┘
                        │ OpenAI-compatible API
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LM STUDIO (local)                             │
│               modelo: qwen2.5-7b-instruct-1m                    │
│                   http://localhost:1234/v1                       │
└───────────────────────┬─────────────────────────────────────────┘
                        │ function calling / parallel_tool_calls
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CAPA DE AGENTE                                │
│   open_servers_and_run() → agent_loop()                         │
│   - multi-tool paralelo (asyncio.gather)                        │
│   - memoria (data/memory.json)                                  │
│   - retry ante recargas del modelo                              │
└──┬──────────┬──────────┬──────────┬──────────┬─────────────────┘
   │ stdio    │ stdio    │ stdio    │ stdio    │ stdio
   ▼          ▼          ▼          ▼          ▼
┌──────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│  FS  │ │ CUSTOM │ │  GIT   │ │ FETCH  │ │ THINKING │
│ (npm)│ │server  │ │server  │ │server  │ │ server   │
│ 11   │ │ 7 tools│ │ 8 tools│ │ 3 tools│ │ 3 tools  │
│tools │ │        │ │        │ │        │ │          │
└──────┘ └───┬────┘ └────────┘ └────────┘ └──────────┘
             │
     ┌───────▼────────┐
     │  RAG (rag/)    │
     │ ChromaDB +     │
     │ MiniLM-L6-v2   │
     │ semantic_search│
     └────────────────┘
```

El transporte entre el agente y los servidores MCP es **stdio**: el agente lanza cada servidor como subproceso y se comunica a través de pipes stdin/stdout usando el protocolo MCP (JSON-RPC sobre stdio).

**Total: 31 tools en 5 servidores.**

---

## 3. Estructura de carpetas

```
ai-lab/
├── client.py              # Chat básico sin tools (ejemplo 1)
├── tool_client.py         # Inyección manual de contexto (ejemplo 2)
├── function_calling.py    # Function calling básico (ejemplo 3)
├── agent_fs.py            # Agente con loop propio, tools locales (ejemplo 4)
├── mcp_agent.py           # Primera conexión MCP sin loop (ejemplo 5)
├── mcp_agent_loop.py      # Agente MCP completo (producción)
├── info.txt               # Archivo de datos de prueba
│
├── mcps/
│   ├── __init__.py
│   ├── server.py          # Servidor MCP custom (7 tools: proyecto + RAG)
│   ├── git_server.py      # Servidor MCP Git (8 tools)
│   ├── fetch_server.py    # Servidor MCP HTTP fetch (3 tools)
│   └── thinking_server.py # Servidor MCP razonamiento secuencial (3 tools)
│
├── rag/
│   ├── __init__.py
│   ├── indexer.py         # Indexación de archivos en ChromaDB
│   ├── retriever.py       # Búsqueda semántica (singleton modelo+colección)
│   └── mcp_rag_tool.py    # Servidor MCP RAG standalone (no usado en producción)
│
├── client/
│   ├── __init__.py
│   └── app.py             # API REST FastAPI (5 endpoints)
│
├── data/
│   ├── chroma_db/         # Índice vectorial (generado, no en git)
│   ├── memory.json        # Historial de conversaciones (generado, no en git)
│   └── thoughts.jsonl     # Log de cadenas de razonamiento (generado, no en git)
│
├── docs/
│   ├── developer-guide.md
│   ├── user-guide.md
│   ├── requirements.md
│   └── use-cases.md
│
├── venv/                  # Entorno virtual Python (no en git)
└── .gitignore
```

---

## 4. Módulos y responsabilidades

### `mcp_agent_loop.py` — Agente principal

| Función | Responsabilidad |
|---|---|
| `load_memory()` | Lee `data/memory.json`, devuelve lista de mensajes |
| `save_memory(messages)` | Persiste los últimos 40 mensajes user/assistant |
| `memory_summary(history)` | Genera texto resumen de las últimas 6 entradas |
| `safe_llm_call(messages, tools)` | Llama al LLM con retry ante `Model reloaded` |
| `mcp_tool_to_openai(tool, server_name)` | Convierte tool MCP al formato OpenAI function calling |
| `open_servers_and_run(server_list, ...)` | Abre servidores MCP recursivamente (ver sección 10) |
| `agent_loop(user_input, all_tools, tool_map, history)` | Loop principal: LLM → tool calls → resultados → respuesta |
| `run_agent(user_input)` | Orquesta todo: carga memoria, abre servidores, ejecuta loop |

### `mcps/server.py` — Servidor MCP custom (7 tools)

Servidor FastMCP con tools de proyecto + búsqueda semántica RAG. El modelo `all-MiniLM-L6-v2` se pre-carga al arrancar el servidor (~20s) para que `semantic_search` responda sin timeout. Todas las rutas pasan por `_resolve()` que previene path traversal. `subprocess.run` usa `stdin=DEVNULL` para evitar herencia de pipes MCP.

### `mcps/git_server.py` — Servidor MCP Git (8 tools)

Ejecuta comandos git via `subprocess.run` en un thread pool (`anyio.to_thread.run_sync`) para no bloquear el event loop. Usa `stdin=DEVNULL` obligatoriamente — sin esto git hereda los pipes MCP y se bloquea.

### `mcps/fetch_server.py` — Servidor MCP HTTP (3 tools)

Usa `httpx` para peticiones HTTP síncronas ejecutadas via `anyio.to_thread.run_sync`. Extrae texto limpio de HTML con regex (sin BeautifulSoup). Limita la respuesta a `MAX_CHARS` (8000) para no saturar el contexto del LLM.

### `mcps/thinking_server.py` — Servidor MCP razonamiento (3 tools)

Mantiene una cadena de pensamientos en memoria (`_thoughts: list[dict]`) durante la sesión del servidor. Persiste cada pensamiento en `data/thoughts.jsonl` para auditoría. Las tools son síncronas (no necesitan threads ni subprocess).

### `rag/indexer.py` — Indexador

Recorre el proyecto, divide archivos en chunks de 400 caracteres con 80 de solapamiento, genera embeddings con `all-MiniLM-L6-v2` y los almacena en ChromaDB con `upsert` (idempotente). Ignora `venv/`, `.git/`, `__pycache__/` y `data/`.

### `rag/retriever.py` — Buscador semántico

Usa singletons para el modelo y la colección ChromaDB (evita recargas en cada llamada). La distancia coseno de ChromaDB se convierte a score: `score = 1 - distance/2`.

### `client/app.py` — API REST

FastAPI con 5 endpoints. Reutiliza `_open_servers_and_run()` (mismo patrón recursivo que el agente CLI) para gestionar las sesiones MCP por petición.

---

## 5. Flujo de ejecución del agente

```
run_agent(user_input)
    │
    ├── load_memory()
    │
    └── open_servers_and_run([filesystem, custom, git, fetch, thinking], callback=run)
            │
            ├── async with stdio_client(filesystem) ...
            │       └── open_servers_and_run([custom, git, fetch, thinking], ...)
            │               async with stdio_client(custom) ...
            │                   └── open_servers_and_run([git, fetch, thinking], ...)
            │                           ... (recursivo hasta vaciar la lista)
            │                               └── run() ← callback
            │                                       agent_loop(...)
            │
            └── [todos los servidores cerrados limpiamente al salir del with]

agent_loop(user_input, all_tools, tool_map, history)
    │
    ├── construye messages [system + history[-10:] + user]
    │
    └── for step in range(10):
            │
            ├── safe_llm_call(messages, all_tools)
            │
            ├── si tool_calls:
            │       asyncio.gather(*[execute_tool(tc) for tc in tool_calls])
            │       → ejecuta TODAS las tools del paso en paralelo
            │
            └── si no tool_calls:
                    → respuesta final, save_memory(), return
```

---

## 6. Servidores MCP

### 6.1 Servidor filesystem (oficial npm)

Lanzado con `npx -y @modelcontextprotocol/server-filesystem`. Provee 11 tools genéricas de sistema de archivos.

### 6.2 Servidor custom (`mcps/server.py`) — 7 tools

| Tool | Descripción |
|---|---|
| `list_project_files` | Lista archivos/carpetas con tamaño. Protección path traversal. |
| `read_project_file` | Lee archivos de texto (extensiones permitidas). |
| `write_project_file` | Crea o sobreescribe archivos, crea directorios intermedios. |
| `search_in_files` | Búsqueda case-insensitive con glob pattern, ignora venv. |
| `run_python_file` | Ejecuta scripts con timeout, `stdin=DEVNULL`. |
| `get_project_summary` | Cuenta archivos .py y líneas totales. |
| `semantic_search` | Búsqueda semántica RAG. Modelo pre-cargado al arrancar. |

**Nota técnica sobre `semantic_search`:** `sentence_transformers` + PyTorch tardan ~20s en importar. Se importan al arrancar el servidor (antes de `mcp.run()`) para que la primera llamada no haga timeout. La búsqueda se ejecuta en `anyio.to_thread.run_sync(abandon_on_cancel=True)`.

### 6.3 Servidor Git (`mcps/git_server.py`) — 8 tools

| Tool | Descripción |
|---|---|
| `git_status` | Rama activa, archivos modificados/staged/untracked. |
| `git_log` | Historial de commits (hash, fecha, autor, mensaje). |
| `git_diff` | Diff de cambios, staged o entre refs. Truncado a 200 líneas. |
| `git_show` | Contenido completo de un commit. Truncado a 150 líneas. |
| `git_branches` | Ramas locales con tracking remoto. |
| `git_blame` | Autoría línea a línea de un archivo. |
| `git_search_commits` | Busca texto en mensajes de commit (case-insensitive). |
| `git_file_history` | Commits que tocaron un archivo concreto (`--follow`). |

**Nota técnica:** `subprocess.run` con `stdin=DEVNULL` ejecutado en `anyio.to_thread.run_sync`. Sin `DEVNULL`, git hereda los pipes MCP y se bloquea indefinidamente.

### 6.4 Servidor fetch (`mcps/fetch_server.py`) — 3 tools

| Tool | Descripción |
|---|---|
| `fetch_url` | GET a URL, extrae texto limpio de HTML. Límite configurable de chars. |
| `fetch_json` | GET a API JSON, devuelve datos formateados. |
| `fetch_headers` | HEAD request, solo cabeceras sin descargar el cuerpo. |

**Nota técnica:** `httpx.Client` síncrono ejecutado en `anyio.to_thread.run_sync`. Extracción de texto HTML con regex (elimina `<script>`, `<style>` y todos los tags).

### 6.5 Servidor thinking (`mcps/thinking_server.py`) — 3 tools

| Tool | Descripción |
|---|---|
| `think` | Registra un paso de razonamiento (thought/revision/branch/conclusion). |
| `think_status` | Muestra la cadena de pensamientos acumulada. |
| `think_reset` | Limpia la cadena para un nuevo problema. |

**Tipos de pensamiento:**
- `thought` — razonamiento normal
- `revision` — corrige o matiza un paso anterior
- `branch` — explora una alternativa diferente
- `conclusion` — pensamiento final antes de responder

El estado se mantiene en memoria (`_thoughts: list[dict]`) durante la sesión. Cada pensamiento se persiste en `data/thoughts.jsonl`.

### Naming de tools en el agente

El agente prefija el nombre de cada tool con el servidor para evitar colisiones:

```
filesystem__list_directory    custom__list_project_files
filesystem__read_file         custom__semantic_search
git__git_log                  fetch__fetch_url
git__git_status               thinking__think
...
```

---

## 7. Sistema RAG

### Indexación

```
archivo → read_text() → chunk_text() → SentenceTransformer.encode() → ChromaDB.upsert()
```

Parámetros:
- `CHUNK_SIZE = 400` caracteres, `CHUNK_OVERLAP = 80`
- IDs: `"ruta/archivo.py::chunk0"`, `"ruta/archivo.py::chunk1"`, ...
- Colección ChromaDB: `ai_lab_docs`, métrica coseno

### Búsqueda

```
query → encode() → ChromaDB.query() → score = 1 - dist/2 → list[dict]
```

El modelo `all-MiniLM-L6-v2` (~80MB) se descarga automáticamente en el primer uso. Singleton en `rag/retriever.py` y pre-cargado en `mcps/server.py`.

### Tres formas de búsqueda disponibles

| Tool | Tipo | Cuándo usarla |
|---|---|---|
| `custom__search_in_files` | Texto exacto (grep) | Buscar una función, variable o string concreto |
| `custom__semantic_search` | Semántica (RAG) | Preguntas conceptuales sobre el proyecto |
| `fetch__fetch_url` | Web externa | Consultar documentación online |

---

## 8. API REST

### Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado del servicio y modelo activo |
| `POST` | `/chat` | Ejecuta el agente con un mensaje |
| `GET` | `/memory` | Devuelve el historial completo |
| `DELETE` | `/memory` | Borra el historial |
| `GET` | `/tools` | Lista todas las tools MCP disponibles |

### Esquema `/chat`

Request:
```json
{
  "message": "¿Qué archivos Python hay en el proyecto?",
  "max_steps": 8
}
```

Response:
```json
{
  "answer": "El proyecto contiene los siguientes archivos...",
  "steps": 3,
  "tools_used": ["custom__list_project_files", "git__git_status"]
}
```

### Arrancar la API

```bash
uvicorn client.app:app --reload --port 8000
```

Documentación interactiva en `http://localhost:8000/docs`.

---

## 9. Memoria persistente

El historial se guarda en `data/memory.json` como lista de mensajes `{role, content}`. Solo se persisten mensajes `user` y `assistant` con contenido de texto.

- Límite: 40 entradas (slice `[-40:]`)
- Contexto cargado en cada sesión: últimas 10 entradas
- Resumen en system prompt: últimas 6 entradas

Adicionalmente, `data/thoughts.jsonl` registra cada pensamiento del servidor thinking en formato JSONL para auditoría.

Ambos archivos están en `.gitignore`.

---

## 10. Decisiones de diseño relevantes

### Apertura recursiva de servidores MCP

anyio usa **cancel scopes** que deben abrirse y cerrarse en el mismo task. La solución es anidar los `async with stdio_client(...)` recursivamente:

```python
async def open_servers_and_run(server_list, all_tools, tool_map, callback):
    if not server_list:
        await callback()
        return
    server_name, params = server_list[0]
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # registrar tools en all_tools y tool_map...
            await open_servers_and_run(server_list[1:], all_tools, tool_map, callback)
```

### `stdin=DEVNULL` en todos los subprocess

Cuando un servidor MCP se lanza vía stdio, los pipes stdin/stdout del proceso padre son el canal del protocolo. Sin `stdin=DEVNULL`, cualquier subproceso hijo (git, python) hereda ese stdin y se bloquea esperando input del protocolo MCP que nunca llega.

```python
subprocess.run(["git", ...], stdin=subprocess.DEVNULL, ...)
```

### Pre-carga del modelo RAG

`sentence_transformers` + PyTorch tardan ~20s en importar. Si se importan en la primera llamada a `semantic_search`, el protocolo MCP hace timeout. La solución es importar al arrancar el servidor:

```python
# Al nivel de módulo, antes de mcp.run()
from rag.retriever import search as _rag_search, format_context as _rag_format
_rag_ready = True
```

### stdout en servidores MCP como subproceso

Stdout es el canal del protocolo. Cualquier `print()` antes de `mcp.run()` corrompe el handshake. Los logs van a `stderr`. En Windows, los emojis en `print()` causan `UnicodeEncodeError` con cp1252.

### Multi-tool paralelo

`parallel_tool_calls=True` en la llamada al LLM + `asyncio.gather` para ejecutar todas las tool calls de un paso concurrentemente.

---

## 11. Configuración y variables

`BASE_PATH` está hardcodeada en cada módulo. Para adaptar a otra máquina, cambiarla en:

- `mcps/server.py`
- `mcps/git_server.py`
- `mcps/fetch_server.py` — no tiene BASE_PATH (no opera sobre archivos locales)
- `mcps/thinking_server.py`
- `rag/indexer.py`
- `rag/retriever.py`
- `mcp_agent_loop.py`
- `client/app.py`

Modelo LLM: cambiar `model` en `safe_llm_call()`. URL: `http://localhost:1234/v1`.

---

## 12. Dependencias

| Paquete | Versión | Uso |
|---|---|---|
| `mcp` | 1.27.1 | SDK cliente y servidor MCP |
| `openai` | 2.38.0 | Cliente API compatible OpenAI |
| `fastapi` | 0.115.12 | API REST |
| `uvicorn` | 0.47.0 | Servidor ASGI |
| `chromadb` | 0.6.3 | Base de datos vectorial |
| `sentence-transformers` | 3.4.1 | Embeddings locales |
| `torch` | 2.12.0 | Backend de sentence-transformers |
| `httpx` | 0.28.1 | Cliente HTTP para fetch_server |
| `anyio` | 4.13.0 | Async I/O (dependencia de MCP) |
| `pydantic` | 2.13.4 | Validación de modelos |

---

## 13. Extensión del sistema

### Añadir una tool al servidor custom

```python
# en mcps/server.py
@mcp.tool()
def mi_nueva_tool(parametro: str) -> str:
    """Descripción de la tool."""
    return resultado
```

El agente la descubre automáticamente en `session.list_tools()`.

### Añadir un nuevo servidor MCP

```python
# en mcp_agent_loop.py y client/app.py
SERVERS = {
    ...,
    "nuevo": StdioServerParameters(
        command=str(BASE_PATH / "venv" / "Scripts" / "python.exe"),
        args=[str(BASE_PATH / "mcps" / "nuevo_server.py")]
    ),
}
```

### Añadir un tipo de pensamiento al thinking server

```python
# en mcps/thinking_server.py
valid_types = {"thought", "revision", "branch", "conclusion", "hypothesis"}
```

### Cambiar el modelo LLM

Cambiar `model` en `safe_llm_call()`. Cualquier modelo compatible con OpenAI API y function calling es válido.
