# Casos de Uso — ai-lab

> **Nota metodológica:** Casos de uso derivados mediante ingeniería inversa sobre el código fuente.

---

## Índice

1. [Actores del sistema](#1-actores-del-sistema)
2. [Diagrama de casos de uso](#2-diagrama-de-casos-de-uso)
3. [Casos de uso detallados](#3-casos-de-uso-detallados)

---

## 1. Actores del sistema

| Actor | Descripción |
|---|---|
| **Usuario** | Interactúa con el agente via CLI o API |
| **Agente** | Componente autónomo que decide qué herramientas usar |
| **LLM (LM Studio)** | Modelo local que genera decisiones de tool calling |
| **Servidor MCP Filesystem** | Provee tools genéricas de sistema de archivos (npm) |
| **Servidor MCP Custom** | Tools de proyecto + RAG (`mcps/server.py`) |
| **Servidor MCP Git** | Tools de control de versiones (`mcps/git_server.py`) |
| **Servidor MCP Fetch** | Tools de acceso HTTP (`mcps/fetch_server.py`) |
| **Servidor MCP Thinking** | Tools de razonamiento secuencial (`mcps/thinking_server.py`) |
| **ChromaDB** | Base de datos vectorial local |

---

## 2. Diagrama de casos de uso

```
                     ┌──────────────────────────────────────────────────┐
                     │                  SISTEMA ai-lab                   │
                     │                                                    │
  ┌─────────┐        │  ┌──────────────────────────────────────────┐    │
  │         │─CLI───▶│  │ CU-01 Consultar agente (CLI)             │    │
  │         │        │  └──────────────────────────────────────────┘    │
  │         │        │                                                    │
  │ Usuario │─API───▶│  ┌──────────────────────────────────────────┐    │
  │         │        │  │ CU-02 Consultar agente (API REST)        │    │
  │         │        │  └──────────────────────────────────────────┘    │
  │         │        │                                                    │
  │         │─CLI───▶│  ┌──────────────────────────────────────────┐    │
  │         │        │  │ CU-16 Indexar proyecto para RAG          │    │
  └─────────┘        │  └──────────────────────────────────────────┘    │
                     │                                                    │
                     │  CU-03..CU-15 (invocados por el Agente)          │
                     │  CU-17..CU-19 (via API REST)                     │
                     └──────────────────────────────────────────────────┘

  CU-01 y CU-02 incluyen según la petición:
    ├── CU-03  Explorar estructura del proyecto
    ├── CU-04  Leer un archivo
    ├── CU-05  Escribir un archivo
    ├── CU-06  Buscar texto en el código
    ├── CU-07  Ejecutar un script Python
    ├── CU-08  Obtener resumen del proyecto
    ├── CU-09  Buscar semánticamente (RAG)
    ├── CU-10  Consultar estado git
    ├── CU-11  Ver historial de commits
    ├── CU-12  Ver diferencias de código
    ├── CU-13  Consultar autoría de código
    ├── CU-14  Obtener contenido de URL
    └── CU-15  Razonar secuencialmente
```

---

## 3. Casos de uso detallados

---

### CU-01 Consultar el agente por CLI

**Actor:** Usuario
**Precondición:** LM Studio activo. Entorno virtual activado.

**Flujo principal:**
1. El usuario ejecuta `python mcp_agent_loop.py "pregunta"`.
2. El sistema carga el historial desde `data/memory.json`.
3. El sistema lanza los 5 servidores MCP como subprocesos (recursivamente) y establece conexiones stdio.
4. El sistema descubre dinámicamente las 31 tools disponibles.
5. El sistema construye el contexto: system prompt + memoria + pregunta.
6. El sistema llama al LLM con la lista de tools.
7. Si el LLM solicita tools, las ejecuta en paralelo y añade resultados al historial.
8. Repite 6-7 hasta respuesta final (máximo 10 pasos).
9. Muestra la respuesta y guarda el historial.
10. Cierra las conexiones MCP.

**Flujo alternativo — servidor no disponible:**
El sistema registra el error y continúa con los servidores disponibles.

**Flujo alternativo — LLM no responde:**
Reintenta hasta 3 veces con espera de 3s ante `Model reloaded`.

**Flujo alternativo — límite de pasos:**
Aviso en consola, termina sin guardar en memoria.

---

### CU-02 Consultar el agente por API REST

**Actor:** Usuario o aplicación cliente
**Precondición:** `uvicorn client.app:app --port 8000` activo. LM Studio activo.

**Flujo principal:**
1. `POST /chat` con `{"message": "...", "max_steps": 8}`.
2. Validación: mensaje no vacío (HTTP 400 si falla).
3. Ejecución del agente (mismo flujo que CU-01).
4. Respuesta: `{"answer": "...", "steps": N, "tools_used": [...]}`.

---

### CU-03 Explorar estructura del proyecto

**Actor:** Agente
**Precondición:** Servidor custom activo.

**Flujo:**
1. LLM llama a `custom__list_project_files` con `subpath="."`.
2. Servidor valida ruta (path traversal check).
3. Lista contenido con tipo (FILE/DIR) y tamaño.
4. Agente puede llamar recursivamente con subdirectorios.

---

### CU-04 Leer un archivo del proyecto

**Actor:** Agente
**Precondición:** Servidor custom activo. Archivo existe y es texto.

**Flujo:**
1. LLM llama a `custom__read_project_file` con `path`.
2. Servidor valida ruta, existencia y extensión de texto.
3. Lee con UTF-8 y devuelve contenido.

---

### CU-05 Escribir un archivo en el proyecto

**Actor:** Agente
**Precondición:** Servidor custom activo.

**Flujo:**
1. LLM llama a `custom__write_project_file` con `path` y `content`.
2. Servidor valida ruta.
3. Crea directorios intermedios si no existen.
4. Escribe con UTF-8 y confirma con número de caracteres.

---

### CU-06 Buscar texto en el código

**Actor:** Agente
**Precondición:** Servidor custom activo.

**Flujo:**
1. LLM llama a `custom__search_in_files` con `query`, `subpath`, `pattern`.
2. Recorre archivos con glob, ignora `venv/`.
3. Búsqueda case-insensitive línea a línea.
4. Devuelve hasta 50 coincidencias en formato `archivo:línea: contenido`.

---

### CU-07 Ejecutar un script Python

**Actor:** Agente
**Precondición:** Servidor custom activo.

**Flujo:**
1. LLM llama a `custom__run_python_file` con `path` y `timeout`.
2. Valida ruta y extensión `.py`.
3. Ejecuta con `venv/Scripts/python.exe`, `stdin=DEVNULL`, timeout.
4. Devuelve stdout + stderr.

**Flujo alternativo — timeout:** Devuelve error de timeout.

---

### CU-08 Obtener resumen del proyecto

**Actor:** Agente
**Precondición:** Servidor custom activo.

**Flujo:**
1. LLM llama a `custom__get_project_summary`.
2. Recorre archivos `.py` (excluye `venv/`).
3. Devuelve: nombre, ruta base, número de archivos, total de líneas, lista de archivos.

---

### CU-09 Buscar semánticamente (RAG)

**Actor:** Agente o Usuario directamente
**Precondición:** Índice RAG creado (`python rag/indexer.py`). Servidor custom activo.

**Flujo (desde el agente):**
1. LLM llama a `custom__semantic_search` con `query` y `top_k`.
2. Servidor usa el modelo pre-cargado para generar embedding de la query.
3. Consulta ChromaDB para los `top_k` chunks más similares.
4. Convierte distancias coseno a scores (`1 - dist/2`).
5. Devuelve chunks formateados con fuente, score y texto.

**Flujo (uso directo):**
```bash
python rag/retriever.py "pregunta"
```

**Flujo alternativo — índice no existe:**
Devuelve mensaje indicando ejecutar `python rag/indexer.py`.

---

### CU-10 Consultar estado git

**Actor:** Agente
**Precondición:** Servidor git activo. Directorio es un repo git.

**Flujo:**
1. LLM llama a `git__git_status`.
2. Servidor ejecuta `git branch --show-current` y `git status --short` en thread pool.
3. Devuelve rama activa, estado de tracking y lista de cambios.

---

### CU-11 Ver historial de commits

**Actor:** Agente
**Precondición:** Servidor git activo.

**Flujo:**
1. LLM llama a `git__git_log` con `max_commits` y opcionalmente `branch`.
2. Servidor ejecuta `git log` con formato `hash  fecha  autor  mensaje`.
3. Devuelve la lista de commits.

**Variantes relacionadas:**
- `git__git_search_commits(query)` — busca en mensajes de commit
- `git__git_file_history(path)` — commits que tocaron un archivo

---

### CU-12 Ver diferencias de código

**Actor:** Agente
**Precondición:** Servidor git activo.

**Flujo:**
1. LLM llama a `git__git_diff` con `target` y/o `staged=True`.
2. Servidor ejecuta `git diff [--cached] [target]`.
3. Devuelve el diff truncado a 200 líneas.

**Variante:** `git__git_show(ref)` para ver el diff completo de un commit.

---

### CU-13 Consultar autoría de código

**Actor:** Agente
**Precondición:** Servidor git activo.

**Flujo:**
1. LLM llama a `git__git_blame` con `path`, `start_line`, `end_line`.
2. Valida que el archivo está dentro del proyecto.
3. Ejecuta `git blame --date=short -w [-L rango] path`.
4. Devuelve autoría truncada a 100 líneas.

---

### CU-14 Obtener contenido de URL

**Actor:** Agente
**Precondición:** Servidor fetch activo. Conexión a internet disponible.

**Flujo:**
1. LLM llama a `fetch__fetch_url` con `url` y `max_chars`.
2. Servidor hace GET con httpx en thread pool.
3. Si es HTML, extrae texto limpio (elimina scripts, estilos y tags).
4. Devuelve texto truncado a `max_chars` con cabecera `[URL | HTTP status | Content-Type]`.

**Variantes:**
- `fetch__fetch_json(url)` — para APIs JSON
- `fetch__fetch_headers(url)` — solo cabeceras HTTP

**Flujo alternativo — timeout / error de red:**
Devuelve mensaje de error descriptivo.

---

### CU-15 Razonar secuencialmente

**Actor:** Agente
**Precondición:** Servidor thinking activo. Pregunta compleja que requiere varios pasos de lógica.

**Flujo:**
1. LLM llama a `thinking__think` con `content`, `step_number`, `total_steps`, `thought_type`, `needs_more_thinking=True`.
2. Servidor registra el pensamiento en `_thoughts` y en `data/thoughts.jsonl`.
3. Devuelve la cadena acumulada de pensamientos.
4. LLM continúa llamando a `think` hasta que `needs_more_thinking=False` (tipo `conclusion`).
5. LLM produce la respuesta final sin más tool calls.

**Tipos de pensamiento:**
- `thought` — razonamiento normal
- `revision` — corrige un paso anterior
- `branch` — explora alternativa diferente
- `conclusion` — pensamiento final

**Flujo alternativo — revisar estado:**
LLM llama a `thinking__think_status` para ver la cadena acumulada.

**Flujo alternativo — nuevo problema:**
LLM llama a `thinking__think_reset` para limpiar la cadena.

---

### CU-16 Indexar el proyecto para RAG

**Actor:** Usuario
**Precondición:** Entorno virtual activado con dependencias instaladas.

**Flujo:**
1. `python rag/indexer.py`
2. Carga modelo `all-MiniLM-L6-v2` (descarga automática ~80MB en primer uso).
3. Conecta con ChromaDB en `data/chroma_db/`.
4. Recorre archivos de texto (excluye `venv/`, `.git/`, `__pycache__/`, `data/`).
5. Divide en chunks de 400 chars con 80 de solapamiento.
6. Genera embeddings y hace `upsert` en ChromaDB.
7. Muestra resumen: archivos procesados, chunks totales.

**Flujo alternativo — reset:**
`python rag/indexer.py --reset` borra la colección antes de indexar.

---

### CU-17 Consultar historial de conversación

**Actor:** Usuario
**Precondición:** API activa.

**Flujo:**
1. `GET /memory`
2. Lee `data/memory.json`.
3. Devuelve `{"messages": [...], "count": N}`.

---

### CU-18 Borrar historial de conversación

**Actor:** Usuario
**Precondición:** API activa.

**Flujo:**
1. `DELETE /memory`
2. Elimina `data/memory.json`.
3. Devuelve `{"status": "ok"}`.

**Postcondición:** El agente inicia la siguiente sesión sin contexto previo.

---

### CU-19 Listar herramientas disponibles

**Actor:** Usuario
**Precondición:** API activa.

**Flujo:**
1. `GET /tools`
2. Conecta secuencialmente a cada servidor MCP.
3. Consulta `list_tools` en cada uno.
4. Devuelve lista consolidada con nombre, descripción y servidor de origen.

**Flujo alternativo — servidor no disponible:**
Incluye entrada de error para ese servidor y continúa con los demás.
