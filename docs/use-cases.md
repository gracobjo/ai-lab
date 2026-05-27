# Casos de Uso — ai-lab

> **Nota metodológica:** Estos casos de uso se han derivado mediante ingeniería inversa sobre el código fuente. Describen el comportamiento real del sistema tal como está implementado.

---

## Índice

1. [Actores del sistema](#1-actores-del-sistema)
2. [Diagrama de casos de uso](#2-diagrama-de-casos-de-uso)
3. [Casos de uso detallados](#3-casos-de-uso-detallados)
   - [CU-01 Consultar el agente por CLI](#cu-01-consultar-el-agente-por-cli)
   - [CU-02 Consultar el agente por API REST](#cu-02-consultar-el-agente-por-api-rest)
   - [CU-03 Explorar estructura del proyecto](#cu-03-explorar-estructura-del-proyecto)
   - [CU-04 Leer un archivo del proyecto](#cu-04-leer-un-archivo-del-proyecto)
   - [CU-05 Escribir un archivo en el proyecto](#cu-05-escribir-un-archivo-en-el-proyecto)
   - [CU-06 Buscar texto en el código](#cu-06-buscar-texto-en-el-código)
   - [CU-07 Ejecutar un script Python](#cu-07-ejecutar-un-script-python)
   - [CU-08 Obtener resumen del proyecto](#cu-08-obtener-resumen-del-proyecto)
   - [CU-09 Indexar el proyecto para RAG](#cu-09-indexar-el-proyecto-para-rag)
   - [CU-10 Buscar información semánticamente](#cu-10-buscar-información-semánticamente)
   - [CU-11 Consultar historial de conversación](#cu-11-consultar-historial-de-conversación)
   - [CU-12 Borrar historial de conversación](#cu-12-borrar-historial-de-conversación)
   - [CU-13 Listar herramientas disponibles](#cu-13-listar-herramientas-disponibles)
   - [CU-14 Verificar estado del servicio](#cu-14-verificar-estado-del-servicio)
   - [CU-15 Re-indexar tras cambios](#cu-15-re-indexar-tras-cambios)

---

## 1. Actores del sistema

| Actor | Descripción |
|---|---|
| **Usuario** | Persona que interactúa con el agente mediante CLI o API para obtener información o realizar acciones sobre el proyecto |
| **Agente** | Componente autónomo que recibe la petición del usuario, decide qué herramientas usar y produce una respuesta |
| **LLM (LM Studio)** | Modelo de lenguaje local que procesa los mensajes y genera las decisiones de tool calling |
| **Servidor MCP Filesystem** | Servidor MCP oficial que provee herramientas de sistema de archivos genéricas |
| **Servidor MCP Custom** | Servidor MCP propio (`mcps/server.py`) con herramientas específicas del proyecto |
| **ChromaDB** | Base de datos vectorial local que almacena y sirve el índice semántico |

---

## 2. Diagrama de casos de uso

```
                        ┌─────────────────────────────────────────┐
                        │              SISTEMA ai-lab              │
                        │                                          │
  ┌─────────┐           │  ┌─────────────────────────────────┐    │
  │         │──CLI──────┼─▶│ CU-01 Consultar agente (CLI)    │    │
  │         │           │  └─────────────────────────────────┘    │
  │         │           │                                          │
  │ Usuario │──API──────┼─▶┌─────────────────────────────────┐    │
  │         │           │  │ CU-02 Consultar agente (API)    │    │
  │         │           │  └─────────────────────────────────┘    │
  │         │           │                                          │
  │         │──CLI──────┼─▶┌─────────────────────────────────┐    │
  │         │           │  │ CU-09 Indexar proyecto (RAG)    │    │
  └─────────┘           │  └─────────────────────────────────┘    │
                        │                                          │
                        │  ┌─────────────────────────────────┐    │
                        │  │ CU-11 Consultar historial       │◀───┼── API
                        │  └─────────────────────────────────┘    │
                        │                                          │
                        │  ┌─────────────────────────────────┐    │
                        │  │ CU-12 Borrar historial          │◀───┼── API
                        │  └─────────────────────────────────┘    │
                        │                                          │
                        │  ┌─────────────────────────────────┐    │
                        │  │ CU-13 Listar herramientas       │◀───┼── API
                        │  └─────────────────────────────────┘    │
                        │                                          │
                        │  ┌─────────────────────────────────┐    │
                        │  │ CU-14 Verificar estado          │◀───┼── API
                        │  └─────────────────────────────────┘    │
                        └─────────────────────────────────────────┘

  CU-01 y CU-02 incluyen (según la petición del usuario):
    ├── CU-03 Explorar estructura
    ├── CU-04 Leer archivo
    ├── CU-05 Escribir archivo
    ├── CU-06 Buscar texto
    ├── CU-07 Ejecutar script
    ├── CU-08 Obtener resumen
    └── CU-10 Búsqueda semántica
```

---

## 3. Casos de uso detallados

---

### CU-01 Consultar el agente por CLI

**Actor principal:** Usuario  
**Precondición:** LM Studio activo en `localhost:1234`. Entorno virtual activado.

**Flujo principal:**

1. El usuario ejecuta `python mcp_agent_loop.py "pregunta"` en la terminal.
2. El sistema carga el historial de conversaciones desde `data/memory.json`.
3. El sistema lanza el servidor MCP filesystem como subproceso y establece conexión stdio.
4. El sistema lanza el servidor MCP custom (`mcps/server.py`) como subproceso y establece conexión stdio.
5. El sistema descubre dinámicamente todas las herramientas disponibles en ambos servidores.
6. El sistema construye el contexto del agente: system prompt con memoria + historial reciente + pregunta del usuario.
7. El sistema llama al LLM con la lista de herramientas disponibles.
8. Si el LLM solicita herramientas, el sistema las ejecuta (en paralelo si son varias) y añade los resultados al historial.
9. El sistema repite el paso 7-8 hasta que el LLM produce una respuesta final (máximo 10 iteraciones).
10. El sistema muestra la respuesta final en consola.
11. El sistema guarda el historial actualizado en `data/memory.json`.
12. El sistema cierra las conexiones con los servidores MCP.

**Flujo alternativo — servidor MCP no disponible:**
- En el paso 3 o 4, si un servidor falla al iniciar, el sistema registra el error y continúa con los servidores disponibles.

**Flujo alternativo — LLM no responde:**
- En el paso 7, si el LLM devuelve error `Model reloaded`, el sistema espera 3 segundos y reintenta hasta 3 veces.

**Flujo alternativo — límite de pasos alcanzado:**
- Si tras 10 iteraciones el LLM no produce respuesta final, el sistema muestra un aviso y termina sin guardar en memoria.

**Postcondición:** La respuesta se muestra en consola y el historial se actualiza en disco.

---

### CU-02 Consultar el agente por API REST

**Actor principal:** Usuario (o aplicación cliente)  
**Precondición:** API iniciada con `uvicorn client.app:app --port 8000`. LM Studio activo.

**Flujo principal:**

1. El cliente envía `POST /chat` con `{"message": "pregunta", "max_steps": 8}`.
2. La API valida que el mensaje no esté vacío.
3. La API ejecuta el agente siguiendo el mismo flujo que CU-01 (pasos 2-12).
4. La API devuelve `{"answer": "...", "steps": N, "tools_used": [...]}`.

**Flujo alternativo — mensaje vacío:**
- En el paso 2, la API devuelve HTTP 400 con mensaje de error.

**Postcondición:** El cliente recibe la respuesta JSON con la respuesta, número de pasos y herramientas usadas.

---

### CU-03 Explorar estructura del proyecto

**Actor principal:** Agente (invocado desde CU-01 o CU-02)  
**Precondición:** Servidor MCP custom activo.

**Flujo principal:**

1. El LLM decide llamar a `custom__list_project_files` con `subpath="."`.
2. El servidor MCP resuelve la ruta relativa a `BASE_PATH` y verifica que está dentro del proyecto.
3. El servidor lista el contenido del directorio con tipo (FILE/DIR) y tamaño.
4. El resultado se devuelve al agente como texto.
5. El agente puede llamar recursivamente con subdirectorios para explorar en profundidad.

**Flujo alternativo — ruta fuera del proyecto:**
- En el paso 2, si la ruta resuelta está fuera de `BASE_PATH`, el servidor devuelve un error de seguridad.

**Flujo alternativo — ruta no existe:**
- El servidor devuelve un mensaje de error descriptivo.

---

### CU-04 Leer un archivo del proyecto

**Actor principal:** Agente (invocado desde CU-01 o CU-02)  
**Precondición:** Servidor MCP custom activo. El archivo existe y es de texto.

**Flujo principal:**

1. El LLM decide llamar a `custom__read_project_file` con `path="ruta/archivo.py"`.
2. El servidor valida que la ruta está dentro del proyecto.
3. El servidor verifica que el archivo existe y tiene extensión de texto reconocida.
4. El servidor lee el archivo con encoding UTF-8 y devuelve su contenido.

**Flujo alternativo — archivo binario:**
- El servidor devuelve un error indicando que el archivo no es de texto legible.

**Flujo alternativo — archivo no existe:**
- El servidor devuelve un mensaje de error descriptivo.

---

### CU-05 Escribir un archivo en el proyecto

**Actor principal:** Agente (invocado desde CU-01 o CU-02)  
**Precondición:** Servidor MCP custom activo.

**Flujo principal:**

1. El LLM decide llamar a `custom__write_project_file` con `path` y `content`.
2. El servidor valida que la ruta está dentro del proyecto.
3. El servidor crea los directorios intermedios si no existen.
4. El servidor escribe el contenido en el archivo con encoding UTF-8.
5. El servidor devuelve confirmación con el número de caracteres escritos.

**Flujo alternativo — error de escritura:**
- El servidor devuelve el mensaje de error del sistema operativo.

---

### CU-06 Buscar texto en el código

**Actor principal:** Agente (invocado desde CU-01 o CU-02)  
**Precondición:** Servidor MCP custom activo.

**Flujo principal:**

1. El LLM decide llamar a `custom__search_in_files` con `query`, `subpath` y `pattern`.
2. El servidor recorre recursivamente los archivos que coinciden con el patrón glob.
3. El servidor ignora el directorio `venv/` y archivos no textuales.
4. El servidor busca el texto (case-insensitive) línea a línea.
5. El servidor devuelve hasta 50 coincidencias en formato `archivo:línea: contenido`.

**Flujo alternativo — sin resultados:**
- El servidor devuelve un mensaje indicando que no hay coincidencias.

---

### CU-07 Ejecutar un script Python

**Actor principal:** Agente (invocado desde CU-01 o CU-02)  
**Precondición:** Servidor MCP custom activo. El archivo es un script `.py` válido.

**Flujo principal:**

1. El LLM decide llamar a `custom__run_python_file` con `path` y opcionalmente `timeout`.
2. El servidor valida que la ruta está dentro del proyecto y es un archivo `.py`.
3. El servidor ejecuta el script con el Python del entorno virtual (`venv/Scripts/python.exe`).
4. El servidor captura stdout y stderr del proceso.
5. El servidor devuelve la salida combinada al agente.

**Flujo alternativo — timeout:**
- Si el script supera el tiempo límite (por defecto 15s), el servidor termina el proceso y devuelve un error de timeout.

**Flujo alternativo — error de ejecución:**
- El servidor devuelve el stderr del proceso para diagnóstico.

---

### CU-08 Obtener resumen del proyecto

**Actor principal:** Agente (invocado desde CU-01 o CU-02)  
**Precondición:** Servidor MCP custom activo.

**Flujo principal:**

1. El LLM decide llamar a `custom__get_project_summary` sin argumentos.
2. El servidor recorre todos los archivos `.py` del proyecto (excluyendo `venv/`).
3. El servidor cuenta líneas de cada archivo y acumula el total.
4. El servidor devuelve: nombre del proyecto, ruta base, número de archivos, total de líneas y lista de archivos con sus líneas.

---

### CU-09 Indexar el proyecto para RAG

**Actor principal:** Usuario  
**Precondición:** Entorno virtual activado con `sentence-transformers` y `chromadb` instalados.

**Flujo principal:**

1. El usuario ejecuta `python rag/indexer.py`.
2. El sistema carga el modelo de embeddings `all-MiniLM-L6-v2` (descarga automática en el primer uso).
3. El sistema conecta con ChromaDB en `data/chroma_db/` (crea el directorio si no existe).
4. El sistema recorre todos los archivos de texto del proyecto, excluyendo `venv/`, `.git/`, `__pycache__/` y `data/`.
5. Por cada archivo, el sistema divide el contenido en chunks de 400 caracteres con 80 de solapamiento.
6. El sistema genera embeddings para cada chunk y los almacena en ChromaDB con `upsert`.
7. El sistema muestra el progreso y un resumen final.

**Flujo alternativo — reset:**
- Si el usuario ejecuta `python rag/indexer.py --reset`, el sistema borra la colección existente antes de indexar.

**Flujo alternativo — archivo ilegible:**
- El sistema registra el error y continúa con el siguiente archivo.

**Postcondición:** El índice vectorial está disponible en `data/chroma_db/` para búsquedas semánticas.

---

### CU-10 Buscar información semánticamente

**Actor principal:** Agente (invocado desde CU-01 o CU-02) o Usuario directamente  
**Precondición:** Índice RAG creado (CU-09 ejecutado previamente).

**Flujo principal (desde el agente):**

1. El LLM decide llamar a `semantic_search` con `query` y opcionalmente `top_k`.
2. El sistema genera el embedding de la query con `all-MiniLM-L6-v2`.
3. El sistema consulta ChromaDB para obtener los `top_k` chunks más similares.
4. El sistema convierte las distancias coseno a scores de relevancia (`score = 1 - dist/2`).
5. El sistema devuelve los chunks formateados con fuente, score y texto.

**Flujo principal (uso directo):**

1. El usuario ejecuta `python rag/retriever.py "pregunta"`.
2. El sistema sigue los pasos 2-5 y muestra los resultados en consola.

**Flujo alternativo — índice no existe:**
- El sistema devuelve un mensaje de error indicando que hay que ejecutar `python rag/indexer.py` primero.

---

### CU-11 Consultar historial de conversación

**Actor principal:** Usuario  
**Precondición:** API activa. Puede no haber historial previo.

**Flujo principal:**

1. El usuario envía `GET /memory`.
2. La API lee `data/memory.json`.
3. La API devuelve `{"messages": [...], "count": N}`.

**Flujo alternativo — sin historial:**
- La API devuelve `{"messages": [], "count": 0}`.

---

### CU-12 Borrar historial de conversación

**Actor principal:** Usuario  
**Precondición:** API activa.

**Flujo principal:**

1. El usuario envía `DELETE /memory`.
2. La API elimina el archivo `data/memory.json` si existe.
3. La API devuelve `{"status": "ok", "message": "Historial borrado."}`.

**Postcondición:** El agente comenzará la siguiente sesión sin contexto de conversaciones anteriores.

---

### CU-13 Listar herramientas disponibles

**Actor principal:** Usuario  
**Precondición:** API activa. Servidores MCP accesibles.

**Flujo principal:**

1. El usuario envía `GET /tools`.
2. La API conecta secuencialmente a cada servidor MCP configurado.
3. La API consulta `list_tools` en cada servidor.
4. La API devuelve la lista consolidada con nombre, descripción y servidor de origen de cada herramienta.

**Flujo alternativo — servidor no disponible:**
- La API incluye una entrada de error para ese servidor y continúa con los demás.

---

### CU-14 Verificar estado del servicio

**Actor principal:** Usuario o sistema de monitorización  
**Precondición:** API activa.

**Flujo principal:**

1. El usuario envía `GET /health`.
2. La API devuelve `{"status": "ok", "model": "qwen2.5-7b-instruct-1m", "base": "ruta/proyecto"}`.

---

### CU-15 Re-indexar tras cambios

**Actor principal:** Usuario  
**Precondición:** Índice RAG existente. Se han modificado archivos del proyecto.

**Flujo principal:**

1. El usuario ejecuta `python rag/indexer.py`.
2. El sistema procesa todos los archivos del proyecto.
3. Para archivos ya indexados, el `upsert` actualiza los chunks existentes.
4. Para archivos nuevos, el `upsert` crea nuevas entradas.
5. Los chunks de archivos eliminados permanecen en el índice (no hay limpieza automática).

**Flujo alternativo — re-indexación completa:**
- El usuario ejecuta `python rag/indexer.py --reset` para borrar el índice y reconstruirlo desde cero, eliminando también los chunks de archivos borrados.

**Postcondición:** El índice refleja el estado actual de los archivos del proyecto.
