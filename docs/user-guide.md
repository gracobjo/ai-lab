# Guía de Usuario — ai-lab

## Índice

1. [Qué es ai-lab](#1-qué-es-ai-lab)
2. [Requisitos previos](#2-requisitos-previos)
3. [Instalación](#3-instalación)
4. [Configuración inicial](#4-configuración-inicial)
5. [Uso del agente por línea de comandos](#5-uso-del-agente-por-línea-de-comandos)
6. [Uso de la API REST](#6-uso-de-la-api-rest)
7. [Sistema RAG: indexar y buscar](#7-sistema-rag-indexar-y-buscar)
8. [Memoria de conversaciones](#8-memoria-de-conversaciones)
9. [Scripts de ejemplo incluidos](#9-scripts-de-ejemplo-incluidos)
10. [Solución de problemas frecuentes](#10-solución-de-problemas-frecuentes)

---

## 1. Qué es ai-lab

ai-lab es un agente de inteligencia artificial que corre completamente en tu máquina, sin enviar datos a servicios externos. Puedes hacerle preguntas sobre tu proyecto, pedirle que explore archivos, busque código, consulte documentación online, analice el historial git o razone paso a paso sobre problemas complejos.

El agente usa:
- **LM Studio** para ejecutar el modelo de lenguaje localmente
- **MCP (Model Context Protocol)** para conectar herramientas al modelo
- **ChromaDB** para búsqueda semántica sobre tus archivos
- **FastAPI** para exponer el agente como servicio HTTP

Cuenta con **31 herramientas** repartidas en 5 servidores MCP.

---

## 2. Requisitos previos

- **Python 3.11** o superior
- **Node.js 18** o superior (para el servidor MCP de filesystem)
- **Git** instalado y en el PATH
- **LM Studio** con el modelo `qwen2.5-7b-instruct-1m` y el servidor local activo en `http://localhost:1234`

```bash
python --version   # 3.11+
node --version     # 18+
git --version      # cualquier versión reciente
```

---

## 3. Instalación

```bash
git clone https://github.com/gracobjo/ai-lab.git
cd ai-lab

# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate

pip install mcp openai fastapi uvicorn chromadb sentence-transformers torch httpx pydantic
```

---

## 4. Configuración inicial

### Ajustar la ruta base

Cambia `BASE_PATH` en estos archivos a la ruta real del proyecto en tu máquina:

- `mcps/server.py`
- `mcps/git_server.py`
- `mcps/thinking_server.py`
- `rag/indexer.py`
- `rag/retriever.py`
- `mcp_agent_loop.py`
- `client/app.py`

```python
BASE_PATH = Path(r"C:\tu-ruta\ai-lab")   # Windows
BASE_PATH = Path("/home/usuario/ai-lab")  # Linux/macOS
```

### Iniciar LM Studio

1. Abre LM Studio y carga `qwen2.5-7b-instruct-1m`
2. Ve a **Local Server** → **Start Server**
3. Verifica que responde en `http://localhost:1234`

---

## 5. Uso del agente por línea de comandos

```bash
python mcp_agent_loop.py "tu pregunta aquí"
python mcp_agent_loop.py   # usa pregunta por defecto
```

### Ejemplos por categoría

**Exploración del proyecto:**
```bash
python mcp_agent_loop.py "Explora el proyecto y describe su estructura"
python mcp_agent_loop.py "¿Cuántas líneas de código tiene el proyecto en total?"
python mcp_agent_loop.py "Lee mcp_agent_loop.py y explícame qué hace"
```

**Búsqueda en el código:**
```bash
python mcp_agent_loop.py "Busca todos los archivos que usan subprocess"
python mcp_agent_loop.py "¿Dónde se define la función _resolve?"
python mcp_agent_loop.py "Encuentra todos los usos de asyncio.gather"
```

**Búsqueda semántica (RAG):**
```bash
python mcp_agent_loop.py "¿Cómo gestiona el agente los errores de conexión?"
python mcp_agent_loop.py "Explícame el sistema de memoria del agente"
```

**Control de versiones:**
```bash
python mcp_agent_loop.py "¿Cuáles son los últimos 5 commits del proyecto?"
python mcp_agent_loop.py "¿Qué cambios hay pendientes de commit?"
python mcp_agent_loop.py "¿Quién escribió la función open_servers_and_run?"
```

**Consultas web:**
```bash
python mcp_agent_loop.py "¿Qué versión tiene el paquete mcp en PyPI?"
python mcp_agent_loop.py "Lee la documentación de FastMCP y resume cómo crear tools"
```

**Razonamiento complejo:**
```bash
python mcp_agent_loop.py "Analiza el código del servidor git y sugiere mejoras"
python mcp_agent_loop.py "¿Por qué podría fallar semantic_search en la primera llamada?"
```

**Escritura de archivos:**
```bash
python mcp_agent_loop.py "Crea un archivo data/notas.txt con un resumen del proyecto"
```

### Qué verás en pantalla

```
Usuario: ¿Cuáles son los últimos 5 commits?

✅ Servidor 'filesystem': 11 tools
✅ Servidor 'custom': 7 tools
✅ Servidor 'git': 8 tools
✅ Servidor 'fetch': 3 tools
✅ Servidor 'thinking': 3 tools

Total tools disponibles: 32

PASO 1
   ▶ git__git_log({'max_commits': 5})
   ✅ resultado: 68f2ec6  2026-05-27 ...

RESPUESTA FINAL:
Los últimos 5 commits son:
1. 68f2ec6 — fix: subprocess stdin=DEVNULL...
...

💾 Memoria guardada en: data/memory.json
```

### Herramientas disponibles

**Servidor filesystem** (11 tools — npm oficial):
listar directorios, leer/escribir/mover archivos, buscar por nombre

**Servidor custom** (7 tools):

| Tool | Qué hace |
|---|---|
| `list_project_files` | Lista archivos con tamaño |
| `read_project_file` | Lee un archivo de texto |
| `write_project_file` | Crea o sobreescribe un archivo |
| `search_in_files` | Busca texto (case-insensitive, glob pattern) |
| `run_python_file` | Ejecuta un script Python |
| `get_project_summary` | Resumen: archivos y líneas de código |
| `semantic_search` | Búsqueda semántica RAG |

**Servidor git** (8 tools):

| Tool | Qué hace |
|---|---|
| `git_status` | Estado del repositorio |
| `git_log` | Historial de commits |
| `git_diff` | Diferencias en el código |
| `git_show` | Contenido de un commit |
| `git_branches` | Ramas locales y remotas |
| `git_blame` | Autoría línea a línea |
| `git_search_commits` | Busca en mensajes de commit |
| `git_file_history` | Historial de un archivo concreto |

**Servidor fetch** (3 tools):

| Tool | Qué hace |
|---|---|
| `fetch_url` | Descarga y limpia texto de una URL |
| `fetch_json` | Consulta una API JSON |
| `fetch_headers` | Comprueba cabeceras HTTP de una URL |

**Servidor thinking** (3 tools):

| Tool | Qué hace |
|---|---|
| `think` | Registra un paso de razonamiento |
| `think_status` | Muestra la cadena de pensamiento actual |
| `think_reset` | Limpia la cadena para un nuevo problema |

---

## 6. Servidor web y API REST

### Interfaz de chat

```powershell
# Requisito: LM Studio con servidor local en el puerto 1234
.\run_web.ps1
```

Abre **http://localhost:8000** para usar el chat en el navegador.

Documentación completa de arranque y solución de problemas: `docs/web-server.md`.

### Arranque manual (API + misma interfaz)

```bash
uvicorn client.app:app --reload --host 127.0.0.1 --port 8000
```

Documentación interactiva de la API: `http://localhost:8000/docs`

### Endpoints

```bash
# Enviar mensaje al agente
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Qué hace mcp_agent_loop.py?", "max_steps": 8}'

# Ver historial
curl http://localhost:8000/memory

# Borrar historial
curl -X DELETE http://localhost:8000/memory

# Ver tools disponibles
curl http://localhost:8000/tools

# Estado del servicio
curl http://localhost:8000/health
```

Respuesta de `/chat`:
```json
{
  "answer": "El archivo mcp_agent_loop.py implementa...",
  "steps": 2,
  "tools_used": ["custom__read_project_file", "git__git_log"]
}
```

---

## 7. Sistema RAG: indexar y buscar

El RAG permite al agente buscar por significado, no solo por palabras exactas.

### Indexar el proyecto (una vez)

```bash
python rag/indexer.py
```

El modelo de embeddings (~80MB) se descarga automáticamente la primera vez. La indexación tarda 1-2 minutos.

### Re-indexar tras cambios

```bash
python rag/indexer.py          # actualiza (no duplica)
python rag/indexer.py --reset  # borra todo y re-indexa
```

### Probar la búsqueda directamente

```bash
python rag/retriever.py "cómo funciona el agente MCP"
python rag/retriever.py "memoria persistente entre sesiones"
```

**Nota:** El servidor custom carga el modelo RAG al arrancar (~20s). La primera vez que el agente usa `semantic_search` puede tardar un poco más en iniciar.

---

## 8. Memoria de conversaciones

El agente recuerda conversaciones anteriores automáticamente (`data/memory.json`).

- Límite: 40 entradas
- Se incluyen las últimas 10 en cada nueva sesión
- Para empezar desde cero:

```bash
del data\memory.json              # Windows
rm data/memory.json               # macOS/Linux
curl -X DELETE http://localhost:8000/memory  # via API
```

El log de razonamiento (`data/thoughts.jsonl`) registra las cadenas de pensamiento del agente para auditoría. No afecta al funcionamiento.

---

## 9. Scripts de ejemplo incluidos

| Script | Qué demuestra |
|---|---|
| `client.py` | Chat básico sin herramientas |
| `tool_client.py` | Inyección manual de contexto desde un archivo |
| `function_calling.py` | El modelo decide cuándo llamar una función |
| `agent_fs.py` | Agente con loop y tools propias (sin MCP) |
| `mcp_agent.py` | Primera conexión a un servidor MCP real |
| `mcp_agent_loop.py` | Agente completo con todos los servidores |

---

## 10. Solución de problemas frecuentes

### El modelo no responde / Connection refused
LM Studio no está activo. Ábrelo, carga el modelo y pulsa **Start Server**.

### `Servidor 'custom' no disponible`
1. `BASE_PATH` en `mcps/server.py` no coincide con la ruta real
2. Dependencias no instaladas en el venv activo

Prueba directamente:
```bash
python mcps/server.py
```

### `Servidor 'git' no disponible`
Git no está en el PATH o `BASE_PATH` en `mcps/git_server.py` es incorrecta.
```bash
git --version   # debe responder
python mcps/git_server.py
```

### `Servidor 'fetch' no disponible`
```bash
python mcps/fetch_server.py
```

### `npx: command not found`
Node.js no está instalado. Descárgalo de [nodejs.org](https://nodejs.org).

### `semantic_search` tarda mucho en la primera llamada
Normal — el servidor custom carga PyTorch y sentence-transformers al arrancar (~20s). Las llamadas siguientes son rápidas (~5s).

### `El índice RAG no existe todavía`
```bash
python rag/indexer.py
```

### El agente alcanza el límite de 10 pasos
Reformula la pregunta de forma más concreta. El límite previene bucles infinitos.

### `No module named 'sentence_transformers'`
```bash
venv\Scripts\activate
pip install sentence-transformers torch
```
