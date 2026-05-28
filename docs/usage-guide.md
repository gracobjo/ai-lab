# Guía de uso del agente ai-lab

## Interfaz web (chat en el navegador)

1. Inicia **LM Studio** (servidor local en el puerto **1234**).
2. En la raíz del proyecto:

   ```powershell
   .\run_web.ps1
   ```

3. Abre **http://localhost:8000** y escribe tu pregunta.

Guía detallada (requisitos, API, errores): **[docs/web-server.md](web-server.md)**.

---

## Cómo lanzarlo (terminal / CLI)

```bash
# Activar el entorno virtual primero
venv\Scripts\activate

# Con pregunta
python mcp_agent_loop.py "tu pregunta aquí"

# Sin pregunta (usa la por defecto)
python mcp_agent_loop.py
```

---

## Principios básicos

**Sé directo y concreto.** El agente elige las tools por sí solo — no necesitas decirle qué tool usar.

```bash
# Bien
python mcp_agent_loop.py "¿qué hace la función _resolve en mcps/server.py?"

# Innecesario
python mcp_agent_loop.py "usa read_project_file para leer mcps/server.py y busca _resolve"
```

**Cuanto más específico, mejor resultado.** Las preguntas vagas producen respuestas superficiales.

```bash
# Vago → el agente lista archivos y da un resumen genérico
python mcp_agent_loop.py "explícame el proyecto"

# Concreto → el agente lee el archivo y explica la lógica
python mcp_agent_loop.py "explícame cómo funciona el loop de agent_loop en mcp_agent_loop.py"
```

---

## Por tipo de tarea

### Explorar el proyecto

```bash
python mcp_agent_loop.py "¿qué archivos hay en la carpeta mcps/?"
python mcp_agent_loop.py "¿cuántas líneas de código tiene el proyecto en total?"
python mcp_agent_loop.py "dame un resumen de todos los archivos Python del proyecto"
```

### Leer y entender código

```bash
python mcp_agent_loop.py "lee fetch_server.py y explícame cómo extrae el texto de HTML"
python mcp_agent_loop.py "¿qué hace la función open_servers_and_run y por qué es recursiva?"
python mcp_agent_loop.py "explícame el flujo completo desde que el usuario escribe una pregunta hasta que recibe respuesta"
```

### Buscar en el código

```bash
# Búsqueda exacta (por texto)
python mcp_agent_loop.py "¿en qué archivos se usa subprocess.run?"
python mcp_agent_loop.py "busca todos los sitios donde se llama a save_memory"

# Búsqueda semántica (por significado) — requiere haber indexado antes
python mcp_agent_loop.py "¿cómo gestiona el agente los errores de conexión MCP?"
python mcp_agent_loop.py "¿dónde se implementa la lógica de reintentos?"
```

> Para activar la búsqueda semántica ejecuta una vez: `python rag/indexer.py`

### Git y control de versiones

```bash
python mcp_agent_loop.py "¿cuáles son los últimos 5 commits?"
python mcp_agent_loop.py "¿qué archivos he modificado y no he commiteado?"
python mcp_agent_loop.py "¿qué cambios introdujo el último commit?"
python mcp_agent_loop.py "¿quién escribió la función _git_sync y en qué commit?"
python mcp_agent_loop.py "busca commits que mencionen 'fix'"
```

### Consultar documentación online

```bash
python mcp_agent_loop.py "¿qué versión tiene el paquete mcp en PyPI ahora mismo?"
python mcp_agent_loop.py "lee https://fastapi.tiangolo.com y dime cómo se definen los endpoints"
python mcp_agent_loop.py "¿existe la URL https://mi-api.com/health y qué devuelve?"
```

### Crear o modificar archivos

```bash
python mcp_agent_loop.py "crea un archivo data/resumen.txt con un resumen del proyecto"
python mcp_agent_loop.py "añade un comentario al inicio de mcps/server.py explicando qué hace"
```

> El agente puede sobreescribir archivos. Revisa el resultado antes de hacer commit.

### Ejecutar scripts

```bash
python mcp_agent_loop.py "ejecuta rag/indexer.py y dime si hay errores"
python mcp_agent_loop.py "ejecuta client.py y muéstrame la salida"
```

### Análisis y razonamiento complejo

Para preguntas que requieren varios pasos de lógica, el agente usará `think` automáticamente si lo considera necesario. Puedes pedírselo explícitamente:

```bash
python mcp_agent_loop.py "analiza por qué semantic_search tarda tanto en la primera llamada y propón soluciones"
python mcp_agent_loop.py "compara search_in_files con semantic_search: ¿cuándo usar cada una?"
python mcp_agent_loop.py "revisa el código de git_server.py y detecta posibles problemas"
```

---

## Preguntas que combinan varias tools

El agente puede usar varias tools en paralelo. Aprovéchalo:

```bash
# El agente leerá el archivo Y consultará el historial git a la vez
python mcp_agent_loop.py "¿cuándo se creó fetch_server.py y qué hace?"

# El agente buscará en el código Y en la documentación online
python mcp_agent_loop.py "¿cómo usamos anyio en el proyecto y qué dice la doc oficial sobre to_thread?"
```

---

## Memoria entre sesiones

El agente recuerda las conversaciones anteriores. Puedes hacer referencias:

```bash
# Primera sesión
python mcp_agent_loop.py "explícame qué es open_servers_and_run"

# Sesión siguiente — el agente recuerda el contexto
python mcp_agent_loop.py "¿y por qué no usamos asyncio.gather para abrir los servidores en vez de recursión?"
```

Para empezar desde cero:
```bash
del data\memory.json
```

---

## Qué no funciona bien

| Situación | Por qué | Alternativa |
|---|---|---|
| Preguntas muy largas y ambiguas | El modelo puede perderse | Divide en preguntas concretas |
| Pedir más de 10 pasos de razonamiento | Límite del loop | Divide la tarea en partes |
| Modificar muchos archivos a la vez | El modelo puede confundirse | Un archivo por petición |
| Preguntas sobre el mundo en general | No es su propósito | Usa `fetch_url` con una URL concreta |
| `semantic_search` sin indexar | El índice no existe | Ejecuta `python rag/indexer.py` primero |

---

## Via API REST

Si tienes el servidor web activo (`.\run_web.ps1` o `uvicorn client.app:app --port 8000`):

```bash
# Pregunta al agente
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "¿qué hace mcps/server.py?", "max_steps": 8}'

# Ver historial
curl http://localhost:8000/memory

# Borrar historial
curl -X DELETE http://localhost:8000/memory

# Ver todas las tools disponibles
curl http://localhost:8000/tools
```
