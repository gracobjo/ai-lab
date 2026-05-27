# Guía de Desarrollador — ai-lab

## Índice

1. [Visión general](#1-visión-general)
2. [Arquitectura del sistema](#2-arquitectura-del-sistema)
3. [Estructura de carpetas](#3-estructura-de-carpetas)
4. [Módulos y responsabilidades](#4-módulos-y-responsabilidades)
5. [Flujo de ejecución del agente](#5-flujo-de-ejecución-del-agente)
6. [Servidor MCP custom](#6-servidor-mcp-custom)
7. [Sistema RAG](#7-sistema-rag)
8. [API REST](#8-api-rest)
9. [Memoria persistente](#9-memoria-persistente)
10. [Decisiones de diseño relevantes](#10-decisiones-de-diseño-relevantes)
11. [Configuración y variables](#11-configuración-y-variables)
12. [Dependencias](#12-dependencias)
13. [Extensión del sistema](#13-extensión-del-sistema)

---

## 1. Visión general

ai-lab es un laboratorio de aprendizaje e implementación de agentes IA locales. El sistema conecta un modelo LLM local (servido por LM Studio) con herramientas externas a través del protocolo MCP (Model Context Protocol), añadiendo capacidades de búsqueda semántica (RAG) y memoria persistente entre sesiones.

El proyecto está estructurado como una progresión didáctica: desde un cliente de chat básico hasta un agente completo con múltiples servidores MCP, RAG y API REST.

---

## 2. Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────┐
│                     CLIENTE / USUARIO                    │
│          CLI (mcp_agent_loop.py) │ API (client/app.py)  │
└──────────────────────┬──────────────────────────────────┘
                       │ OpenAI-compatible API
                       ▼
┌─────────────────────────────────────────────────────────┐
│                   LM STUDIO (local)                      │
│              modelo: qwen2.5-7b-instruct-1m              │
│                  http://localhost:1234/v1                 │
└──────────────────────┬──────────────────────────────────┘
                       │ function calling / tool_choice
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  CAPA DE AGENTE                          │
│   open_servers_and_run() → agent_loop()                  │
│   - multi-tool paralelo (asyncio.gather)                 │
│   - memoria (data/memory.json)                           │
│   - retry ante recargas del modelo                       │
└──────────┬──────────────────────────┬───────────────────┘
           │ stdio (MCP protocol)     │ stdio (MCP protocol)
           ▼                          ▼
┌──────────────────┐      ┌──────────────────────────────┐
│  MCP FILESYSTEM  │      │     MCP CUSTOM (mcps/server) │
│  (npm package)   │      │  list_project_files          │
│  list_directory  │      │  read_project_file           │
│  read_file       │      │  write_project_file          │
│  write_file      │      │  search_in_files             │
│  search_files    │      │  run_python_file             │
│  ...             │      │  get_project_summary         │
└──────────────────┘      └──────────────────────────────┘
                                       │
                          ┌────────────▼───────────────┐
                          │     RAG (rag/)              │
                          │  ChromaDB + MiniLM-L6-v2   │
                          │  semantic_search tool       │
                          └────────────────────────────┘
```

El transporte entre el agente y los servidores MCP es **stdio**: el agente lanza cada servidor como subproceso y se comunica a través de pipes stdin/stdout usando el protocolo MCP (JSON-RPC sobre stdio).

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
│   └── server.py          # Servidor MCP custom con 6 tools
│
├── rag/
│   ├── __init__.py
│   ├── indexer.py         # Indexación de archivos en ChromaDB
│   ├── retriever.py       # Búsqueda semántica
│   └── mcp_rag_tool.py    # Tool MCP que expone semantic_search
│
├── client/
│   ├── __init__.py
│   └── app.py             # API REST FastAPI
│
├── data/
│   ├── chroma_db/         # Índice vectorial (generado, no en git)
│   └── memory.json        # Historial de conversaciones (generado, no en git)
│
├── venv/                  # Entorno virtual Python (no en git)
└── .gitignore
```

---

## 4. Módulos y responsabilidades

### `mcp_agent_loop.py` — Agente principal

Punto de entrada para uso en CLI. Contiene:

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

### `mcps/server.py` — Servidor MCP custom

Servidor FastMCP con 6 tools. Todas las rutas pasan por `_resolve()` que previene path traversal. Cuando se lanza como subproceso MCP, **stdout es el canal del protocolo**: no se escribe nada a stdout antes de `mcp.run()`.

### `rag/indexer.py` — Indexador

Recorre el proyecto, divide archivos en chunks de 400 caracteres con 80 de solapamiento, genera embeddings con `all-MiniLM-L6-v2` y los almacena en ChromaDB con `upsert` (idempotente). Ignora `venv/`, `.git/`, `__pycache__/` y `data/`.

### `rag/retriever.py` — Buscador semántico

Usa singletons para el modelo y la colección ChromaDB (evita recargas en cada llamada). La distancia coseno de ChromaDB se convierte a score: `score = 1 - distance/2`.

### `rag/mcp_rag_tool.py` — Tool MCP de RAG

Envuelve `retriever.search()` como tool MCP independiente. Puede usarse como servidor standalone o integrarse en `mcps/server.py`.

### `client/app.py` — API REST

FastAPI con 5 endpoints. Reutiliza `_open_servers_and_run()` (mismo patrón que el agente CLI) para gestionar las sesiones MCP por petición.

---

## 5. Flujo de ejecución del agente

```
run_agent(user_input)
    │
    ├── load_memory()                    # carga historial
    │
    └── open_servers_and_run([fs, custom], callback=run)
            │
            ├── async with stdio_client(filesystem) as (r,w)
            │       async with ClientSession(r,w) as session_fs
            │           session_fs.initialize()
            │           session_fs.list_tools() → añade tools a all_tools
            │           │
            │           └── open_servers_and_run([custom], callback=run)
            │                   async with stdio_client(custom) as (r,w)
            │                       session_custom.initialize()
            │                       session_custom.list_tools() → añade tools
            │                       │
            │                       └── run()  ← callback
            │                               agent_loop(...)
            │
            └── [servidores cerrados limpiamente al salir del with]

agent_loop(user_input, all_tools, tool_map, history)
    │
    ├── construye messages [system + history[-10:] + user]
    │
    └── for step in range(10):
            │
            ├── safe_llm_call(messages, all_tools)
            │       → response con tool_calls o respuesta final
            │
            ├── si tool_calls:
            │       append assistant message con tool_calls
            │       asyncio.gather(*[execute_tool(tc) for tc in tool_calls])
            │           → ejecuta todas las tools en paralelo
            │       append tool results al historial
            │
            └── si no tool_calls:
                    print respuesta final
                    save_memory(messages)
                    return
```

---

## 6. Servidor MCP custom

### Registro de tools

Se usa el decorador `@mcp.tool()` de FastMCP. El nombre de la tool es el nombre de la función Python. La descripción viene del docstring.

```python
@mcp.tool()
def list_project_files(subpath: str = ".") -> str:
    """Lista archivos y carpetas dentro del proyecto."""
    ...
```

### Seguridad de rutas

`_resolve(path)` convierte rutas relativas a absolutas y verifica que el resultado esté dentro de `BASE_PATH`:

```python
def _resolve(path: str) -> Path:
    resolved = (BASE_PATH / path).resolve()
    if not str(resolved).startswith(str(BASE_PATH.resolve())):
        raise ValueError(f"Ruta fuera del proyecto: {path}")
    return resolved
```

### Naming en el agente

Cuando el agente registra tools de múltiples servidores, prefija el nombre con el servidor para evitar colisiones:

```
filesystem__list_directory
filesystem__read_file
custom__list_project_files
custom__search_in_files
...
```

El `tool_map` mapea `nombre_openai → (nombre_mcp_real, session)`.

---

## 7. Sistema RAG

### Indexación

```
archivo → read_text() → chunk_text() → SentenceTransformer.encode() → ChromaDB.upsert()
```

Parámetros de chunking:
- `CHUNK_SIZE = 400` caracteres
- `CHUNK_OVERLAP = 80` caracteres
- IDs de chunk: `"ruta/archivo.py::chunk0"`, `"ruta/archivo.py::chunk1"`, ...

### Búsqueda

```
query → SentenceTransformer.encode() → ChromaDB.query() → score = 1 - dist/2 → list[dict]
```

El modelo `all-MiniLM-L6-v2` se descarga automáticamente en el primer uso (~80MB). Se mantiene en memoria como singleton.

### Re-indexar

```bash
python rag/indexer.py          # indexa (upsert, no duplica)
python rag/indexer.py --reset  # borra colección y re-indexa desde cero
```

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
  "tools_used": ["custom__list_project_files", "custom__get_project_summary"]
}
```

### Arrancar la API

```bash
uvicorn client.app:app --reload --port 8000
```

Documentación interactiva disponible en `http://localhost:8000/docs`.

---

## 9. Memoria persistente

El historial se guarda en `data/memory.json` como lista de mensajes `{role, content}`. Solo se persisten mensajes de rol `user` y `assistant` con contenido de texto (se excluyen tool calls y tool results).

Límite: 40 entradas. En cada sesión se cargan las últimas 10 para el contexto del LLM y las últimas 6 para el resumen del system prompt.

El archivo está en `.gitignore` — es local a cada instalación.

---

## 10. Decisiones de diseño relevantes

### Apertura recursiva de servidores MCP

anyio (la librería async que usa el SDK MCP) usa **cancel scopes** que deben abrirse y cerrarse en el mismo task de asyncio. Llamar `__aenter__`/`__aexit__` manualmente rompe este invariante cuando hay `asyncio.gather` de por medio.

La solución es anidar los `async with stdio_client(...)` de forma recursiva, garantizando que cada scope se abre y cierra en el mismo frame de ejecución:

```python
async def open_servers_and_run(server_list, all_tools, tool_map, callback):
    if not server_list:
        await callback()
        return
    server_name, params = server_list[0]
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            # registrar tools...
            await open_servers_and_run(server_list[1:], all_tools, tool_map, callback)
```

### stdout en servidores MCP como subproceso

Cuando un servidor MCP se lanza vía stdio, **stdout es el canal del protocolo MCP**. Cualquier `print()` antes de `mcp.run()` corrompe el handshake. Los logs de inicio van a `stderr`. En Windows, los emojis en `print()` causan `UnicodeEncodeError` con codepage cp1252, lo que mata el proceso antes del handshake.

### Multi-tool paralelo

El agente usa `parallel_tool_calls=True` en la llamada al LLM y ejecuta todas las tool calls de un paso con `asyncio.gather`, reduciendo la latencia cuando el modelo solicita varias tools simultáneamente.

---

## 11. Configuración y variables

Todas las rutas están hardcodeadas en cada módulo como `BASE_PATH`. Para adaptar el proyecto a otra máquina, cambiar esta variable en:

- `mcps/server.py`
- `rag/indexer.py`
- `rag/retriever.py`
- `mcp_agent_loop.py`
- `client/app.py`

El modelo LLM se configura en `safe_llm_call()` / llamadas directas al cliente OpenAI:
- URL: `http://localhost:1234/v1`
- Modelo: `qwen2.5-7b-instruct-1m`

---

## 12. Dependencias

Principales (todas en `venv/`):

| Paquete | Versión | Uso |
|---|---|---|
| `mcp` | 1.27.1 | SDK cliente y servidor MCP |
| `openai` | 2.38.0 | Cliente API compatible OpenAI |
| `fastapi` | 0.115.12 | API REST |
| `uvicorn` | 0.47.0 | Servidor ASGI |
| `chromadb` | 0.6.3 | Base de datos vectorial |
| `sentence-transformers` | 3.4.1 | Embeddings locales |
| `torch` | 2.12.0 | Backend de sentence-transformers |
| `pydantic` | 2.13.4 | Validación de modelos |
| `anyio` | 4.13.0 | Async I/O (dependencia de MCP) |

---

## 13. Extensión del sistema

### Añadir una nueva tool al servidor custom

```python
# en mcps/server.py
@mcp.tool()
def mi_nueva_tool(parametro: str) -> str:
    """Descripción de la tool."""
    # implementación
    return resultado
```

No requiere ningún cambio en el agente — las tools se descubren dinámicamente en `session.list_tools()`.

### Añadir un nuevo servidor MCP

```python
# en mcp_agent_loop.py y client/app.py
SERVERS = {
    "filesystem": ...,
    "custom": ...,
    "nuevo_servidor": StdioServerParameters(
        command="python",
        args=["ruta/al/servidor.py"]
    ),
}
```

### Cambiar el modelo LLM

Cambiar el parámetro `model` en `safe_llm_call()`. Cualquier modelo compatible con la API OpenAI y que soporte function calling es válido.

### Integrar RAG en el servidor custom

```python
# en mcps/server.py
from rag.retriever import search, format_context

@mcp.tool()
def semantic_search(query: str, top_k: int = 5) -> str:
    """Busca información relevante en el proyecto."""
    results = search(query, top_k=top_k)
    return format_context(results)
```
