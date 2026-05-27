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

ai-lab es un agente de inteligencia artificial que corre completamente en tu máquina, sin enviar datos a servicios externos. Puedes hacerle preguntas sobre tu proyecto, pedirle que explore archivos, busque código, ejecute scripts o responda usando el contenido de tus propios documentos.

El agente usa:
- **LM Studio** para ejecutar el modelo de lenguaje localmente
- **MCP (Model Context Protocol)** para conectar herramientas al modelo
- **ChromaDB** para búsqueda semántica sobre tus archivos
- **FastAPI** para exponer el agente como servicio HTTP

---

## 2. Requisitos previos

Antes de empezar necesitas tener instalado:

- **Python 3.11** o superior
- **Node.js 18** o superior (para el servidor MCP de filesystem)
- **LM Studio** con el modelo `qwen2.5-7b-instruct-1m` descargado y el servidor local activo en `http://localhost:1234`
- **Git** (opcional, para clonar el repositorio)

Para verificar que tienes lo necesario:

```bash
python --version      # debe mostrar 3.11 o superior
node --version        # debe mostrar 18 o superior
npx --version         # incluido con Node.js
```

---

## 3. Instalación

### Clonar el repositorio

```bash
git clone https://github.com/gracobjo/ai-lab.git
cd ai-lab
```

### Crear el entorno virtual e instalar dependencias

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install mcp openai fastapi uvicorn chromadb sentence-transformers torch pydantic
```

### Verificar la instalación

```bash
python -c "import mcp, openai, fastapi, chromadb, sentence_transformers; print('OK')"
```

---

## 4. Configuración inicial

### Ajustar la ruta base

Abre cada uno de estos archivos y cambia `BASE_PATH` a la ruta donde tienes el proyecto en tu máquina:

- `mcps/server.py`
- `rag/indexer.py`
- `rag/retriever.py`
- `mcp_agent_loop.py`
- `client/app.py`

Ejemplo: si tienes el proyecto en `C:\proyectos\ai-lab`, cambia:

```python
BASE_PATH = Path(r"C:\proyectos\ai-lab")
```

### Iniciar LM Studio

1. Abre LM Studio
2. Carga el modelo `qwen2.5-7b-instruct-1m`
3. Ve a la pestaña **Local Server** y pulsa **Start Server**
4. Verifica que el servidor está activo en `http://localhost:1234`

---

## 5. Uso del agente por línea de comandos

El agente principal es `mcp_agent_loop.py`. Puedes pasarle cualquier pregunta como argumento:

```bash
# Con pregunta como argumento
python mcp_agent_loop.py "¿Qué archivos Python hay en el proyecto?"

# Sin argumento usa la pregunta por defecto
python mcp_agent_loop.py
```

### Ejemplos de preguntas

```bash
python mcp_agent_loop.py "Explora el proyecto y describe su estructura"

python mcp_agent_loop.py "Busca todos los archivos que usan function calling"

python mcp_agent_loop.py "Lee el archivo mcp_agent_loop.py y explícame qué hace"

python mcp_agent_loop.py "¿Cuántas líneas de código tiene el proyecto en total?"

python mcp_agent_loop.py "Crea un archivo data/notas.txt con un resumen del proyecto"
```

### Qué verás en pantalla

```
Usuario: Explora el proyecto y describe su estructura

✅ Servidor 'filesystem': 11 tools
✅ Servidor 'custom': 6 tools

Total tools disponibles: 17
   - filesystem__list_directory
   - filesystem__read_file
   - custom__list_project_files
   - custom__get_project_summary
   ...

==================================================
PASO 1
   ▶ custom__get_project_summary({})
   ✅ resultado: Proyecto: ai-lab ...

==================================================
PASO 2

✅ RESPUESTA FINAL:

El proyecto ai-lab contiene 9 archivos Python con un total de...

💾 Memoria guardada en: C:\...\data\memory.json
```

### Herramientas disponibles para el agente

El agente tiene acceso a estas herramientas automáticamente:

**Servidor filesystem (oficial MCP):**
- Listar directorios
- Leer y escribir archivos
- Buscar archivos por nombre o contenido
- Mover y copiar archivos

**Servidor custom (mcps/server.py):**

| Herramienta | Qué hace |
|---|---|
| `list_project_files` | Lista archivos con tamaño en una carpeta |
| `read_project_file` | Lee el contenido de un archivo |
| `write_project_file` | Crea o sobreescribe un archivo |
| `search_in_files` | Busca texto en archivos (case-insensitive) |
| `run_python_file` | Ejecuta un script Python y devuelve la salida |
| `get_project_summary` | Resumen del proyecto: archivos y líneas de código |

---

## 6. Uso de la API REST

La API permite usar el agente desde cualquier aplicación o herramienta HTTP.

### Iniciar el servidor

```bash
uvicorn client.app:app --reload --port 8000
```

Documentación interactiva disponible en: `http://localhost:8000/docs`

### Enviar un mensaje al agente

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Qué hace el archivo mcp_agent_loop.py?"}'
```

Respuesta:
```json
{
  "answer": "El archivo mcp_agent_loop.py implementa el agente principal...",
  "steps": 2,
  "tools_used": ["custom__read_project_file"]
}
```

### Consultar el historial de conversación

```bash
curl http://localhost:8000/memory
```

### Borrar el historial

```bash
curl -X DELETE http://localhost:8000/memory
```

### Ver las herramientas disponibles

```bash
curl http://localhost:8000/tools
```

### Verificar que el servicio está activo

```bash
curl http://localhost:8000/health
```

---

## 7. Sistema RAG: indexar y buscar

El sistema RAG permite al agente buscar información en tus archivos usando búsqueda semántica (por significado, no solo por palabras exactas).

### Indexar el proyecto

Antes de usar la búsqueda semántica, debes indexar los archivos una vez:

```bash
python rag/indexer.py
```

Verás algo como:

```
Cargando modelo de embeddings: all-MiniLM-L6-v2
Conectando a ChromaDB en: ...\data\chroma_db
Archivos encontrados: 12
  agent_fs.py → 3 chunks
  mcp_agent_loop.py → 8 chunks
  mcps/server.py → 6 chunks
  ...
Indexación completa.
   Archivos procesados : 12
   Total chunks        : 47
```

El modelo de embeddings (~80MB) se descarga automáticamente la primera vez.

### Re-indexar tras cambios

Si modificas archivos del proyecto, vuelve a indexar:

```bash
python rag/indexer.py          # actualiza (no duplica)
python rag/indexer.py --reset  # borra todo y re-indexa desde cero
```

### Probar la búsqueda semántica

```bash
python rag/retriever.py "cómo funciona el agente MCP"
python rag/retriever.py "function calling loop"
python rag/retriever.py "memoria persistente"
```

---

## 8. Memoria de conversaciones

El agente recuerda las conversaciones anteriores automáticamente. El historial se guarda en `data/memory.json`.

- Las últimas 10 conversaciones se incluyen como contexto en cada nueva sesión
- El historial se limita a 40 entradas para no crecer indefinidamente
- Para empezar desde cero, borra el archivo o usa el endpoint `DELETE /memory`

```bash
# Borrar historial manualmente
del data\memory.json          # Windows
rm data/memory.json           # macOS / Linux

# O via API
curl -X DELETE http://localhost:8000/memory
```

---

## 9. Scripts de ejemplo incluidos

El proyecto incluye scripts de ejemplo que muestran la evolución desde lo más simple hasta el agente completo:

| Script | Qué demuestra | Cómo ejecutar |
|---|---|---|
| `client.py` | Chat básico con el modelo | `python client.py` |
| `tool_client.py` | Leer un archivo e inyectarlo como contexto | `python tool_client.py` |
| `function_calling.py` | El modelo decide cuándo llamar una función | `python function_calling.py` |
| `agent_fs.py` | Agente con loop de exploración de archivos | `python agent_fs.py` |
| `mcp_agent.py` | Primera conexión a un servidor MCP real | `python mcp_agent.py` |
| `mcp_agent_loop.py` | Agente completo con MCP, RAG y memoria | `python mcp_agent_loop.py` |

---

## 10. Solución de problemas frecuentes

### El modelo no responde / Connection refused

Verifica que LM Studio está activo y el servidor local está iniciado en el puerto 1234.

### `Servidor 'custom' no disponible`

Causas habituales:
1. `BASE_PATH` en `mcps/server.py` no coincide con la ruta real del proyecto
2. El entorno virtual no está activado o las dependencias no están instaladas

Prueba ejecutar el servidor directamente para ver el error:
```bash
python mcps/server.py
```

### `npx: command not found` / Servidor filesystem no disponible

Node.js no está instalado o no está en el PATH. Instala Node.js desde [nodejs.org](https://nodejs.org).

### Error al indexar: `No module named 'sentence_transformers'`

Las dependencias no están instaladas en el entorno virtual activo:
```bash
venv\Scripts\activate
pip install sentence-transformers
```

### `¿Has ejecutado python rag/indexer.py primero?`

El índice RAG no existe. Ejecuta la indexación antes de usar la búsqueda semántica:
```bash
python rag/indexer.py
```

### El agente no termina / alcanza el límite de pasos

El modelo puede entrar en bucle si la pregunta es ambigua. Intenta reformularla de forma más concreta. El límite de 10 pasos es una protección para evitar bucles infinitos.
