# Documento de Requisitos — ai-lab

> **Nota metodológica:** Este documento se ha elaborado mediante ingeniería inversa sobre el código fuente existente. Los requisitos describen el comportamiento real implementado, no una especificación previa al desarrollo.

---

## Índice

1. [Propósito del sistema](#1-propósito-del-sistema)
2. [Alcance](#2-alcance)
3. [Partes interesadas](#3-partes-interesadas)
4. [Requisitos funcionales](#4-requisitos-funcionales)
5. [Requisitos no funcionales](#5-requisitos-no-funcionales)
6. [Restricciones del sistema](#6-restricciones-del-sistema)
7. [Requisitos de datos](#7-requisitos-de-datos)
8. [Requisitos de interfaz](#8-requisitos-de-interfaz)
9. [Matriz de trazabilidad](#9-matriz-de-trazabilidad)

---

## 1. Propósito del sistema

ai-lab es un sistema de agente de inteligencia artificial local que permite a un usuario interactuar con un modelo de lenguaje (LLM) ejecutado en su propia máquina, dotándolo de capacidad para operar sobre el sistema de archivos, controlar versiones git, consultar URLs externas, razonar secuencialmente y buscar semánticamente sobre documentos locales, todo mediante herramientas conectadas a través del protocolo MCP.

El sistema tiene un doble propósito:
- **Didáctico:** demostrar la progresión desde un cliente de chat básico hasta un agente completo con múltiples servidores MCP, RAG y API.
- **Funcional:** proporcionar un agente operativo con 31 herramientas para exploración y manipulación autónoma del proyecto.

---

## 2. Alcance

**Incluido:**
- Agente LLM local con function calling y multi-tool paralelo
- 5 servidores MCP simultáneos (filesystem, custom, git, fetch, thinking)
- 31 herramientas distribuidas entre los servidores
- Sistema RAG con indexación y búsqueda semántica local
- Memoria persistente de conversaciones
- Log de cadenas de razonamiento
- API REST para acceso programático
- Scripts de ejemplo progresivos

**Excluido:**
- Interfaz gráfica de usuario
- Autenticación y autorización
- Soporte multi-usuario
- Modelos LLM remotos (cloud)
- Bases de datos externas

---

## 3. Partes interesadas

| Rol | Descripción |
|---|---|
| **Usuario** | Ejecuta el agente para explorar y manipular el proyecto |
| **Desarrollador del sistema** | Extiende o modifica el código de ai-lab |

---

## 4. Requisitos funcionales

### RF-01 — Comunicación con LLM local
Conexión a modelo LLM via API compatible OpenAI en `http://localhost:1234/v1`.
**Implementado en:** `mcp_agent_loop.py`, `client/app.py`

### RF-02 — Function calling con multi-tool paralelo
El LLM puede solicitar múltiples herramientas en un mismo paso; el agente las ejecuta en paralelo con `asyncio.gather` y `parallel_tool_calls=True`.
**Implementado en:** `mcp_agent_loop.py` → `agent_loop()`

### RF-03 — Conexión a servidores MCP via stdio
Lanzamiento de servidores como subprocesos y comunicación via pipes stdin/stdout con protocolo MCP (JSON-RPC).
**Implementado en:** `mcp_agent_loop.py`, `client/app.py`

### RF-04 — Descubrimiento dinámico de herramientas
Las herramientas se descubren en runtime via `session.list_tools()` sin configuración manual en el agente.
**Implementado en:** `mcp_agent_loop.py` → `open_servers_and_run()`

### RF-05 — Múltiples servidores MCP simultáneos
El agente mantiene conexiones activas a 5 servidores MCP simultáneamente, agregando sus tools en un pool unificado.
**Implementado en:** `mcp_agent_loop.py` → `open_servers_and_run()` (recursivo)

### RF-06 — Loop de agente con límite de pasos
Loop de razonamiento iterativo con máximo 10 pasos para prevenir bucles infinitos.
**Implementado en:** `mcp_agent_loop.py` → `agent_loop()`

### RF-07 — Servidor MCP custom con herramientas de proyecto (7 tools)

| ID | Tool | Descripción |
|---|---|---|
| RF-07a | `list_project_files` | Listar archivos/carpetas con tamaño |
| RF-07b | `read_project_file` | Leer archivos de texto |
| RF-07c | `write_project_file` | Crear o sobreescribir archivos |
| RF-07d | `search_in_files` | Buscar texto con glob pattern |
| RF-07e | `run_python_file` | Ejecutar scripts Python con timeout |
| RF-07f | `get_project_summary` | Resumen de archivos y líneas |
| RF-07g | `semantic_search` | Búsqueda semántica RAG integrada |

**Implementado en:** `mcps/server.py`

### RF-08 — Seguridad de rutas
Validación de path traversal: todas las rutas deben estar dentro de `BASE_PATH`.
**Implementado en:** `mcps/server.py` → `_resolve()`

### RF-09 — Servidor MCP Git (8 tools)

| ID | Tool | Descripción |
|---|---|---|
| RF-09a | `git_status` | Estado del repositorio |
| RF-09b | `git_log` | Historial de commits |
| RF-09c | `git_diff` | Diferencias en el código |
| RF-09d | `git_show` | Contenido de un commit |
| RF-09e | `git_branches` | Ramas locales y remotas |
| RF-09f | `git_blame` | Autoría línea a línea |
| RF-09g | `git_search_commits` | Búsqueda en mensajes de commit |
| RF-09h | `git_file_history` | Historial de un archivo concreto |

**Implementado en:** `mcps/git_server.py`

### RF-10 — Servidor MCP fetch HTTP (3 tools)

| ID | Tool | Descripción |
|---|---|---|
| RF-10a | `fetch_url` | GET a URL con extracción de texto HTML |
| RF-10b | `fetch_json` | GET a API JSON |
| RF-10c | `fetch_headers` | HEAD request, solo cabeceras |

**Implementado en:** `mcps/fetch_server.py`

### RF-11 — Servidor MCP razonamiento secuencial (3 tools)

| ID | Tool | Descripción |
|---|---|---|
| RF-11a | `think` | Registrar paso de razonamiento (thought/revision/branch/conclusion) |
| RF-11b | `think_status` | Mostrar cadena de pensamientos acumulada |
| RF-11c | `think_reset` | Limpiar cadena para nuevo problema |

**Implementado en:** `mcps/thinking_server.py`

### RF-12 — Indexación de documentos para RAG
Indexación de archivos en ChromaDB con chunking y embeddings locales.
**Implementado en:** `rag/indexer.py`

### RF-13 — Búsqueda semántica
Búsqueda por similitud coseno sobre el índice vectorial, con score de relevancia.
**Implementado en:** `rag/retriever.py`

### RF-14 — Memoria persistente entre sesiones
Historial de conversaciones guardado en disco y cargado al inicio de cada sesión.
**Implementado en:** `mcp_agent_loop.py` → `load_memory()`, `save_memory()`

### RF-15 — Límite y resumen de memoria
Máximo 40 entradas persistidas. Resumen de las últimas 6 en el system prompt.
**Implementado en:** `mcp_agent_loop.py` → `save_memory()`, `memory_summary()`

### RF-16 — Log de razonamiento
Cada pensamiento registrado via `think` se persiste en `data/thoughts.jsonl` para auditoría.
**Implementado en:** `mcps/thinking_server.py` → `_log_thought()`

### RF-17 — Retry ante recargas del modelo
Detección de `Model reloaded` y reintento automático hasta 3 veces con espera de 3s.
**Implementado en:** `mcp_agent_loop.py` → `safe_llm_call()`

### RF-18 — API REST (5 endpoints)

| ID | Método | Ruta | Descripción |
|---|---|---|---|
| RF-18a | POST | `/chat` | Ejecutar agente |
| RF-18b | GET | `/memory` | Consultar historial |
| RF-18c | DELETE | `/memory` | Borrar historial |
| RF-18d | GET | `/tools` | Listar tools MCP |
| RF-18e | GET | `/health` | Estado del servicio |

**Implementado en:** `client/app.py`

### RF-19 — Validación de entrada en la API
Rechazo de mensajes vacíos con HTTP 400.
**Implementado en:** `client/app.py` → endpoint `/chat`

### RF-20 — Scripts de ejemplo progresivos
Progresión didáctica: `client.py` → `tool_client.py` → `function_calling.py` → `agent_fs.py` → `mcp_agent.py` → `mcp_agent_loop.py`.
**Implementado en:** archivos raíz del proyecto

---

## 5. Requisitos no funcionales

### RNF-01 — Ejecución completamente local
Todo el procesamiento (LLM, embeddings, vectores) en la máquina del usuario, sin APIs externas.

### RNF-02 — Compatibilidad con Windows
Rutas con backslash, encoding cp1252 en consola, ejecución de subprocesos en Windows.

### RNF-03 — Compatibilidad de cancel scopes async
Apertura recursiva de servidores MCP para respetar los cancel scopes de anyio.

### RNF-04 — Aislamiento de rutas
El servidor custom no permite acceso fuera de `BASE_PATH`.

### RNF-05 — Idempotencia de la indexación
`ChromaDB.upsert()` garantiza que re-indexar no crea duplicados.

### RNF-06 — Rendimiento de embeddings
Modelo pre-cargado al arrancar el servidor custom. Singleton en `rag/retriever.py`.

### RNF-07 — Timeout en ejecución de scripts
`run_python_file` aplica timeout configurable (por defecto 15s).

### RNF-08 — Separación de canal de protocolo y logs
Servidores MCP no escriben en stdout antes de `mcp.run()`. Logs a stderr.

### RNF-09 — Aislamiento de stdin en subprocesos
Todos los `subprocess.run()` en servidores MCP usan `stdin=DEVNULL` para evitar herencia de pipes del protocolo.

### RNF-10 — Truncado de salidas largas
Las tools git y fetch truncan sus salidas (150-200 líneas / 8000 chars) para no saturar el contexto del LLM.

---

## 6. Restricciones del sistema

| Restricción | Detalle |
|---|---|
| **Modelo LLM** | LM Studio activo en `localhost:1234` con modelo compatible con function calling |
| **Python** | 3.11 o superior |
| **Node.js** | Requerido para `npx @modelcontextprotocol/server-filesystem` |
| **Git** | Instalado y en el PATH para el servidor git |
| **BASE_PATH** | Hardcodeada en cada módulo; ajuste manual por instalación |
| **Sistema operativo** | Desarrollado y probado en Windows |

---

## 7. Requisitos de datos

### `data/memory.json`
- Formato: array JSON de `{role, content}`
- Roles: `user`, `assistant`
- Máximo: 40 entradas
- Excluido del control de versiones

### `data/thoughts.jsonl`
- Formato: JSONL, un objeto por línea
- Campos: `n`, `total`, `type`, `content`, `ts`, `more`
- Excluido del control de versiones

### `data/chroma_db/`
- Motor: ChromaDB HNSW, métrica coseno
- Colección: `ai_lab_docs`
- Metadatos por chunk: `{source: string, chunk: int}`
- Excluido del control de versiones

### Parámetros de chunking
- Tamaño: 400 chars, solapamiento: 80 chars
- Extensiones: `.py`, `.txt`, `.md`, `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini`, `.csv`
- Directorios excluidos: `venv/`, `.vscode/`, `__pycache__/`, `.git/`, `data/`

---

## 8. Requisitos de interfaz

### CLI
- Entrada: argumento posicional opcional
- Salida: texto plano con indicadores de paso, tools usadas y respuesta final

### API REST
- HTTP/1.1, JSON, CORS `*`, puerto 8000, OpenAPI en `/docs`

### MCP (servidores)
- Transporte: stdio, protocolo MCP 1.x (JSON-RPC)
- Descubrimiento: `list_tools` / `call_tool`

---

## 9. Matriz de trazabilidad

| Requisito | Módulo | Función / elemento |
|---|---|---|
| RF-01 | `mcp_agent_loop.py` | `llm = OpenAI(...)` |
| RF-02 | `mcp_agent_loop.py` | `asyncio.gather`, `parallel_tool_calls=True` |
| RF-03 | `mcp_agent_loop.py` | `open_servers_and_run()` |
| RF-04 | `mcp_agent_loop.py` | `session.list_tools()` |
| RF-05 | `mcp_agent_loop.py` | `open_servers_and_run()` recursivo, dict `SERVERS` |
| RF-06 | `mcp_agent_loop.py` | `for step in range(10)` |
| RF-07 | `mcps/server.py` | `@mcp.tool()` decorators |
| RF-08 | `mcps/server.py` | `_resolve()` |
| RF-09 | `mcps/git_server.py` | `@mcp.tool()` async + `_git_sync()` |
| RF-10 | `mcps/fetch_server.py` | `@mcp.tool()` async + `_do_fetch()` |
| RF-11 | `mcps/thinking_server.py` | `@mcp.tool()` + `_thoughts: list` |
| RF-12 | `rag/indexer.py` | `build_index()` |
| RF-13 | `rag/retriever.py` | `search()` |
| RF-14 | `mcp_agent_loop.py` | `load_memory()`, `save_memory()` |
| RF-15 | `mcp_agent_loop.py` | `save_memory()[-40:]`, `memory_summary()` |
| RF-16 | `mcps/thinking_server.py` | `_log_thought()` → `data/thoughts.jsonl` |
| RF-17 | `mcp_agent_loop.py` | `safe_llm_call()` con retry |
| RF-18 | `client/app.py` | endpoints FastAPI |
| RF-19 | `client/app.py` | `HTTPException(400)` en `/chat` |
| RF-20 | archivos raíz | `client.py` … `mcp_agent_loop.py` |
| RNF-01 | todos | sin llamadas a APIs externas |
| RNF-02 | `mcps/server.py` | stderr, sin emojis en subproceso |
| RNF-03 | `mcp_agent_loop.py` | `open_servers_and_run()` recursivo |
| RNF-04 | `mcps/server.py` | `_resolve()` con validación de prefijo |
| RNF-05 | `rag/indexer.py` | `collection.upsert()` |
| RNF-06 | `mcps/server.py` | import al nivel de módulo; `rag/retriever.py` singletons |
| RNF-07 | `mcps/server.py` | `subprocess.run(..., timeout=timeout)` |
| RNF-08 | todos los servidores | `print(..., file=sys.stderr)` en `__main__` |
| RNF-09 | `mcps/server.py`, `mcps/git_server.py` | `stdin=subprocess.DEVNULL` |
| RNF-10 | `mcps/git_server.py`, `mcps/fetch_server.py` | `_truncate()`, `MAX_CHARS` |
