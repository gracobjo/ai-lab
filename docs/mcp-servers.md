# Servidores MCP en ai-lab

ai-lab conecta varios servidores MCP (Model Context Protocol) al agente. Cada uno expone **tools** que el LLM puede invocar. En la interfaz web aparecen con prefijo `servidor__nombre` (por ejemplo `git__git_status`).

## Resumen

| Servidor | ID | Arranque | Tools principales |
|----------|-----|----------|-------------------|
| [Archivos](#filesystem) | `filesystem` | `npx` (Node) | Leer/listar archivos del proyecto |
| [Proyecto ai-lab](#custom-ai-lab-server) | `custom` | Python `mcps/server.py` | Código, búsqueda, RAG, resumen |
| [Git](#git) | `git` | Python `mcps/git_server.py` | status, log, diff, blame… |
| [Web](#fetch) | `fetch` | Python `mcps/fetch_server.py` | HTTP GET, JSON, headers |
| [Razonamiento](#thinking) | `thinking` | Python `mcps/thinking_server.py` | Cadena de pensamiento interna |
| [Power BI](#power-bi-opcional) | `powerbi` | `npx` (opcional) | Modelo semántico Desktop |

Power BI **no** se carga por defecto. Ver [powerbi-mcp.md](powerbi-mcp.md).

---

## Interfaz web: frases de ejemplo

En http://localhost:8000:

- **Pantalla de bienvenida** — tarjetas por servidor con chips clicables (envían la pregunta al instante).
- **Ejemplos** (header) — panel con todas las frases agrupadas por MCP.
- **Tools** (header) — lista de tools; bajo cada servidor, 2 frases rápidas.

Las frases se sirven desde `GET /prompts` y se definen en `get_mcp_prompt_catalog()` (`agent_core.py`). Al añadir un servidor o cambiar frases, actualiza esa función y esta documentación.

### Frases por servidor (chips)

#### filesystem — Archivos

| Frase |
|-------|
| Lista los archivos Python en la raíz del proyecto |
| Lee el contenido de README.md |
| ¿Qué hay en la carpeta docs/? |

#### custom — Proyecto ai-lab

| Frase |
|-------|
| Resume el proyecto con get_project_summary |
| Busca en el código dónde se define run_agent_query |
| ¿Qué archivos Python hay y qué hace cada uno? |

#### git — Git

| Frase |
|-------|
| Resume el estado del repositorio git |
| Muestra los últimos 5 commits |
| ¿Qué archivos cambiaron respecto al último commit? |

#### fetch — Web

| Frase |
|-------|
| Obtén el contenido de https://docs.python.org/3/ |
| Haz fetch de los headers de https://github.com |

#### thinking — Razonamiento

| Frase |
|-------|
| Explícame el flujo desde la pregunta del usuario hasta la respuesta del agente |
| Piensa paso a paso cómo añadir una nueva tool MCP al proyecto |

#### powerbi — Power BI (requiere `run_web_powerbi.ps1`)

| Frase | Flujo directo en backend |
|-------|------------------------|
| Lista las tablas del modelo abierto en Power BI | Sí — tablas |
| Lista las columnas de la tabla california_housing | Sí — columnas |
| Conéctate a mi-modelo y lista todas las tablas | Sí — tablas |

Si Power BI no está activo, la tarjeta aparece deshabilitada con instrucciones de activación.

---

## filesystem

**Paquete:** `@modelcontextprotocol/server-filesystem`  
**Alcance:** directorio raíz del proyecto (`ai-lab`).

Permite al agente listar, leer y escribir archivos dentro del workspace (sandbox del servidor MCP).

**Cuándo usarlo:** exploración de carpetas, lectura de archivos que no pasan por las tools custom.

---

## custom (ai-lab-server)

**Script:** `mcps/server.py`  
**Prefijo OpenAI:** `custom__`

| Tool | Descripción |
|------|-------------|
| `list_project_files` | Lista archivos bajo una ruta |
| `read_project_file` | Lee un archivo de texto |
| `write_project_file` | Escribe o crea un archivo |
| `search_in_files` | Busca texto en archivos (glob) |
| `run_python_file` | Ejecuta un script Python del proyecto |
| `get_project_summary` | Resumen rápido del repo |
| `semantic_search` | Búsqueda semántica RAG (ChromaDB) |

**Cuándo usarlo:** preguntas sobre el código, búsquedas en el proyecto, resumen estructurado.

---

## git

**Script:** `mcps/git_server.py`  
**Prefijo:** `git__`

| Tool | Descripción |
|------|-------------|
| `git_status` | Estado del working tree |
| `git_log` | Historial de commits |
| `git_diff` | Diff vs commit o staged |
| `git_show` | Detalle de un commit |
| `git_branches` | Ramas locales/remotas |
| `git_blame` | Blame por líneas |
| `git_search_commits` | Buscar en mensajes de commit |
| `git_file_history` | Historial de un archivo |

**Cuándo usarlo:** estado del repo, cambios recientes, quién tocó una línea.

---

## fetch

**Script:** `mcps/fetch_server.py`  
**Prefijo:** `fetch__`

| Tool | Descripción |
|------|-------------|
| `fetch_url` | GET y texto/HTML limpio |
| `fetch_json` | GET JSON |
| `fetch_headers` | Cabeceras HTTP |

**Cuándo usarlo:** documentación externa, APIs públicas, comprobar URLs.

---

## thinking

**Script:** `mcps/thinking_server.py`  
**Prefijo:** `thinking__`

| Tool | Descripción |
|------|-------------|
| `think` | Registra un paso de razonamiento |
| `think_status` | Muestra la cadena de pensamiento |
| `think_reset` | Reinicia la cadena |

**Cuándo usarlo:** planificación multi-paso antes de otras tools. En preguntas Power BI el agente **no** debería usar thinking (se filtran solo tools `powerbi__`).

---

## Power BI (opcional)

**Paquete:** `@microsoft/powerbi-modeling-mcp@latest`  
**Prefijo:** `powerbi__`  
**Activación:** `AI_LAB_ENABLE_POWERBI=1` o `.\run_web_powerbi.ps1`

Tools agrupadas: `connection_operations`, `table_operations`, `column_operations`, `measure_operations`, `dax_query_operations`, etc.

### Flujos directos (sin LLM)

Para modelos pequeños que no hacen function calling bien, `agent_core.py` detecta intención y ejecuta:

| Intención | Detección (ejemplos) | Secuencia |
|-----------|----------------------|-----------|
| Listar tablas | `lista las tablas`, `lista todas las tablas`, `Conéctate a mi-modelo y lista…` | ListLocalInstances → Connect → `table_operations` List |
| Listar columnas | `columnas` + nombre de tabla | ListLocalInstances → Connect → `column_operations` List |

Catálogo Desktop: por defecto `mi-modelo`; también `Conéctate a X`, `initialCatalog "X"`, `X.pbix`.

Documentación completa: [powerbi-mcp.md](powerbi-mcp.md).

---

## Configuración de servidores

Definidos en `build_servers()` (`agent_core.py`):

| Variable | Efecto |
|----------|--------|
| `AI_LAB_ENABLE_POWERBI=1` | Añade servidor `powerbi` |
| `AI_LAB_POWERBI_ONLY=1` | Solo Power BI (resto desactivado) |
| `AI_LAB_POWERBI_READONLY=1` | MCP Power BI en solo lectura |

Flag en disco: `data/runtime_flags.json` (`powerbi: true`) — lo escribe `run_web_powerbi.ps1` para sobrevivir al `--reload` de uvicorn en Windows.

---

## API relacionada

```bash
curl http://localhost:8000/tools    # tools MCP activas
curl http://localhost:8000/prompts  # frases de ejemplo por servidor
curl http://localhost:8000/health   # incluye powerbi_mcp: true/false
```

---

## Añadir frases o un servidor nuevo

1. Registra el servidor en `build_servers()` (`agent_core.py`).
2. Añade entrada en `get_mcp_prompt_catalog()` con `id`, `label`, `description`, `color`, `prompts`.
3. Documenta tools en esta guía.
4. Recarga la web; los chips se actualizan vía `/prompts`.
