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

ai-lab es un sistema de agente de inteligencia artificial local que permite a un usuario interactuar con un modelo de lenguaje (LLM) ejecutado en su propia máquina, dotándolo de capacidad para operar sobre el sistema de archivos del proyecto mediante herramientas externas conectadas a través del protocolo MCP, búsqueda semántica sobre documentos locales y memoria persistente entre sesiones.

El sistema tiene un doble propósito:
- **Didáctico:** demostrar la progresión desde un cliente de chat básico hasta un agente completo con herramientas, RAG y API.
- **Funcional:** proporcionar un agente operativo para exploración y manipulación autónoma del proyecto.

---

## 2. Alcance

**Incluido en el sistema:**
- Agente LLM local con function calling
- Conexión a servidores MCP (filesystem oficial y servidor custom)
- Herramientas de exploración, lectura, escritura y ejecución sobre el proyecto
- Sistema RAG con indexación y búsqueda semántica local
- Memoria persistente de conversaciones
- API REST para acceso programático al agente
- Scripts de ejemplo progresivos

**Excluido del sistema:**
- Interfaz gráfica de usuario
- Autenticación y autorización de usuarios
- Soporte multi-usuario
- Conexión a modelos LLM remotos (cloud)
- Integración con bases de datos externas

---

## 3. Partes interesadas

| Rol | Descripción |
|---|---|
| **Desarrollador / usuario** | Persona que ejecuta el agente para explorar y manipular el proyecto |
| **Desarrollador del sistema** | Persona que extiende o modifica el código de ai-lab |

---

## 4. Requisitos funcionales

### RF-01 — Comunicación con LLM local

El sistema debe conectarse a un modelo LLM servido localmente a través de una API compatible con OpenAI, configurada en `http://localhost:1234/v1`.

**Implementado en:** `mcp_agent_loop.py`, `client/app.py`, `agent_fs.py`, `function_calling.py`

---

### RF-02 — Function calling / tool calling

El sistema debe permitir que el LLM solicite la ejecución de herramientas externas mediante el mecanismo de function calling, pasando nombre de función y argumentos en formato JSON.

**Implementado en:** `function_calling.py`, `agent_fs.py`, `mcp_agent_loop.py`

---

### RF-03 — Conexión a servidores MCP

El sistema debe conectarse a servidores MCP mediante transporte stdio, lanzándolos como subprocesos y comunicándose a través de pipes stdin/stdout usando el protocolo MCP (JSON-RPC).

**Implementado en:** `mcp_agent.py`, `mcp_agent_loop.py`, `client/app.py`

---

### RF-04 — Descubrimiento dinámico de herramientas

El sistema debe descubrir las herramientas disponibles en cada servidor MCP en tiempo de ejecución mediante `session.list_tools()`, sin requerir configuración manual de las herramientas en el agente.

**Implementado en:** `mcp_agent_loop.py` → `open_servers_and_run()`

---

### RF-05 — Múltiples servidores MCP simultáneos

El sistema debe mantener conexiones activas a múltiples servidores MCP de forma simultánea durante la ejecución del agente, agregando sus herramientas en un pool unificado.

**Implementado en:** `mcp_agent_loop.py` → `open_servers_and_run()` (recursivo)

---

### RF-06 — Ejecución paralela de herramientas

El sistema debe ejecutar múltiples llamadas a herramientas solicitadas en un mismo paso del agente de forma concurrente, sin esperar a que una termine para iniciar la siguiente.

**Implementado en:** `mcp_agent_loop.py` → `asyncio.gather()` en `agent_loop()`

---

### RF-07 — Loop de agente con límite de pasos

El sistema debe ejecutar un loop de razonamiento donde el LLM puede llamar herramientas iterativamente hasta producir una respuesta final, con un límite máximo de 10 pasos para prevenir bucles infinitos.

**Implementado en:** `mcp_agent_loop.py` → `agent_loop()`

---

### RF-08 — Servidor MCP custom con herramientas de proyecto

El sistema debe proporcionar un servidor MCP propio que exponga las siguientes herramientas sobre el proyecto:

| ID | Herramienta | Descripción |
|---|---|---|
| RF-08a | `list_project_files` | Listar archivos y carpetas con tamaño |
| RF-08b | `read_project_file` | Leer contenido de archivos de texto |
| RF-08c | `write_project_file` | Crear o sobreescribir archivos |
| RF-08d | `search_in_files` | Buscar texto en archivos con glob pattern |
| RF-08e | `run_python_file` | Ejecutar scripts Python con timeout |
| RF-08f | `get_project_summary` | Obtener resumen de archivos y líneas de código |

**Implementado en:** `mcps/server.py`

---

### RF-09 — Seguridad de rutas en el servidor custom

El servidor MCP custom debe validar que todas las rutas de archivo proporcionadas por el LLM estén contenidas dentro del directorio base del proyecto, rechazando cualquier intento de acceso fuera de ese ámbito (path traversal).

**Implementado en:** `mcps/server.py` → `_resolve()`

---

### RF-10 — Indexación de documentos para RAG

El sistema debe indexar los archivos de texto del proyecto en una base de datos vectorial local, dividiendo el contenido en fragmentos (chunks) con solapamiento y generando embeddings mediante un modelo local.

**Implementado en:** `rag/indexer.py`

---

### RF-11 — Búsqueda semántica

El sistema debe permitir buscar fragmentos de texto relevantes en el índice vectorial mediante similitud semántica (coseno), devolviendo los resultados ordenados por score de relevancia.

**Implementado en:** `rag/retriever.py`

---

### RF-12 — Búsqueda semántica como herramienta MCP

El sistema debe exponer la búsqueda semántica como una herramienta MCP (`semantic_search`) para que el agente pueda utilizarla de forma autónoma.

**Implementado en:** `rag/mcp_rag_tool.py`

---

### RF-13 — Memoria persistente entre sesiones

El sistema debe guardar el historial de conversaciones en disco y cargarlo al inicio de cada sesión, permitiendo al agente mantener contexto de interacciones anteriores.

**Implementado en:** `mcp_agent_loop.py` → `load_memory()`, `save_memory()`

---

### RF-14 — Límite y resumen de memoria

El sistema debe limitar el historial persistido a un máximo de 40 entradas y generar un resumen de las últimas 6 para incluirlo en el system prompt del agente.

**Implementado en:** `mcp_agent_loop.py` → `save_memory()`, `memory_summary()`

---

### RF-15 — Retry ante recargas del modelo

El sistema debe detectar errores de tipo "Model reloaded" en las llamadas al LLM y reintentar automáticamente hasta 3 veces con una espera de 3 segundos entre intentos.

**Implementado en:** `mcp_agent_loop.py` → `safe_llm_call()`

---

### RF-16 — API REST

El sistema debe exponer el agente como servicio HTTP con los siguientes endpoints:

| ID | Método | Ruta | Descripción |
|---|---|---|---|
| RF-16a | POST | `/chat` | Ejecutar el agente con un mensaje |
| RF-16b | GET | `/memory` | Consultar el historial de conversación |
| RF-16c | DELETE | `/memory` | Borrar el historial |
| RF-16d | GET | `/tools` | Listar herramientas MCP disponibles |
| RF-16e | GET | `/health` | Estado del servicio |

**Implementado en:** `client/app.py`

---

### RF-17 — Validación de entrada en la API

La API debe rechazar mensajes vacíos con un error HTTP 400.

**Implementado en:** `client/app.py` → endpoint `/chat`

---

### RF-18 — Scripts de ejemplo progresivos

El sistema debe incluir scripts de ejemplo que demuestren la evolución desde chat básico hasta agente completo:

| Script | Concepto demostrado |
|---|---|
| `client.py` | Chat sin herramientas |
| `tool_client.py` | Inyección manual de contexto |
| `function_calling.py` | Function calling básico |
| `agent_fs.py` | Loop de agente con herramientas propias |
| `mcp_agent.py` | Conexión a servidor MCP externo |

**Implementado en:** archivos raíz del proyecto

---

## 5. Requisitos no funcionales

### RNF-01 — Ejecución completamente local

Todo el procesamiento (LLM, embeddings, base de datos vectorial) debe ejecutarse en la máquina del usuario sin enviar datos a servicios externos.

### RNF-02 — Compatibilidad con Windows

El sistema debe funcionar en Windows, incluyendo la gestión correcta de rutas (backslash), encoding de consola (cp1252) y ejecución de subprocesos.

### RNF-03 — Compatibilidad de cancel scopes async

La gestión de conexiones MCP debe respetar los cancel scopes de anyio, abriendo y cerrando cada context manager en el mismo task de asyncio para evitar `RuntimeError: Attempted to exit cancel scope in a different task`.

### RNF-04 — Aislamiento de rutas

El servidor MCP custom no debe permitir acceso a archivos fuera del directorio base del proyecto.

### RNF-05 — Idempotencia de la indexación

La indexación RAG debe ser idempotente: ejecutarla múltiples veces sobre los mismos archivos no debe crear entradas duplicadas en la base de datos vectorial.

### RNF-06 — Rendimiento de embeddings

El modelo de embeddings debe cargarse una única vez por proceso (patrón singleton) para evitar latencia en búsquedas sucesivas.

### RNF-07 — Timeout en ejecución de scripts

La herramienta `run_python_file` debe aplicar un timeout configurable (por defecto 15 segundos) para evitar que scripts de larga duración bloqueen el agente.

### RNF-08 — Separación de canal de protocolo y logs

Los servidores MCP lanzados como subprocesos no deben escribir nada en stdout antes de iniciar el protocolo, usando stderr para logs de diagnóstico.

---

## 6. Restricciones del sistema

| Restricción | Detalle |
|---|---|
| **Modelo LLM** | Requiere LM Studio activo en `localhost:1234` con un modelo compatible con function calling |
| **Python** | Versión 3.11 o superior (uso de `list[dict]` como type hint sin `from __future__`) |
| **Node.js** | Requerido para el servidor MCP filesystem oficial (`npx @modelcontextprotocol/server-filesystem`) |
| **Ruta base** | `BASE_PATH` está hardcodeada en cada módulo; debe ajustarse manualmente por instalación |
| **Sistema operativo** | Desarrollado y probado en Windows; rutas usan backslash |

---

## 7. Requisitos de datos

### Historial de conversaciones (`data/memory.json`)

- Formato: array JSON de objetos `{role: string, content: string}`
- Roles válidos: `user`, `assistant`
- Tamaño máximo: 40 entradas
- Persistencia: local, excluido del control de versiones

### Índice vectorial (`data/chroma_db/`)

- Motor: ChromaDB con índice HNSW
- Métrica de distancia: coseno
- Colección: `ai_lab_docs`
- Metadatos por chunk: `{source: string, chunk: int}`
- Persistencia: local, excluido del control de versiones

### Parámetros de chunking

- Tamaño de chunk: 400 caracteres
- Solapamiento: 80 caracteres
- Extensiones indexadas: `.py`, `.txt`, `.md`, `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini`, `.csv`
- Directorios excluidos: `venv/`, `.vscode/`, `__pycache__/`, `.git/`, `data/`

---

## 8. Requisitos de interfaz

### Interfaz de línea de comandos

- Entrada: argumento posicional opcional con la pregunta del usuario
- Salida: texto plano en consola con indicadores de paso, herramientas usadas y respuesta final

### API REST

- Protocolo: HTTP/1.1
- Formato: JSON
- CORS: habilitado para todos los orígenes (`*`)
- Puerto por defecto: 8000
- Documentación: OpenAPI en `/docs`

### Interfaz MCP (servidores)

- Transporte: stdio (pipes stdin/stdout)
- Protocolo: MCP 1.x (JSON-RPC)
- Descubrimiento: `list_tools` request/response

---

## 9. Matriz de trazabilidad

| Requisito | Módulo | Función / Clase |
|---|---|---|
| RF-01 | `mcp_agent_loop.py` | `llm = OpenAI(...)` |
| RF-02 | `mcp_agent_loop.py` | `safe_llm_call()` con `tool_choice="auto"` |
| RF-03 | `mcp_agent_loop.py` | `open_servers_and_run()` |
| RF-04 | `mcp_agent_loop.py` | `session.list_tools()` |
| RF-05 | `mcp_agent_loop.py` | `open_servers_and_run()` recursivo |
| RF-06 | `mcp_agent_loop.py` | `asyncio.gather()` en `agent_loop()` |
| RF-07 | `mcp_agent_loop.py` | `for step in range(10)` en `agent_loop()` |
| RF-08 | `mcps/server.py` | `@mcp.tool()` decorators |
| RF-09 | `mcps/server.py` | `_resolve()` |
| RF-10 | `rag/indexer.py` | `build_index()` |
| RF-11 | `rag/retriever.py` | `search()` |
| RF-12 | `rag/mcp_rag_tool.py` | `semantic_search()` |
| RF-13 | `mcp_agent_loop.py` | `load_memory()`, `save_memory()` |
| RF-14 | `mcp_agent_loop.py` | `save_memory()` (slice `[-40:]`), `memory_summary()` |
| RF-15 | `mcp_agent_loop.py` | `safe_llm_call()` con retry |
| RF-16 | `client/app.py` | endpoints FastAPI |
| RF-17 | `client/app.py` | `if not req.message.strip(): raise HTTPException(400)` |
| RF-18 | archivos raíz | `client.py`, `tool_client.py`, `function_calling.py`, `agent_fs.py`, `mcp_agent.py` |
| RNF-01 | todos | sin llamadas a APIs externas |
| RNF-02 | `mcps/server.py` | logs a `stderr`, sin emojis en subproceso |
| RNF-03 | `mcp_agent_loop.py` | `open_servers_and_run()` recursivo |
| RNF-04 | `mcps/server.py` | `_resolve()` con validación de prefijo |
| RNF-05 | `rag/indexer.py` | `collection.upsert()` |
| RNF-06 | `rag/retriever.py` | singletons `_model`, `_collection` |
| RNF-07 | `mcps/server.py` | `subprocess.run(..., timeout=timeout)` |
| RNF-08 | `mcps/server.py` | `print(..., file=sys.stderr)` en `__main__` |
