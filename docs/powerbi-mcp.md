# Power BI Modeling MCP en ai-lab

Integración del [servidor MCP oficial de Microsoft](https://github.com/microsoft/powerbi-modeling-mcp) para trabajar con **modelos semánticos** de Power BI (tablas, medidas, relaciones, DAX). No modifica el diseño visual de informes.

## Requisitos

- **Node.js 20+** (`npx` en el PATH) — ya lo tienes si `node -v` responde.
- **Power BI Desktop** con un archivo `.pbix` abierto y el modelo cargado.
- **LM Studio** en el puerto 1234 (contexto amplio recomendado si usas muchas tools).
- Cuenta **Microsoft / Entra ID** (login la primera vez que arranque el MCP).

## Activar en ai-lab

El servidor Power BI **no** se carga por defecto (añade muchas tools y consume contexto del LLM).

### Opción A — script dedicado

```powershell
.\run_web_powerbi.ps1
```

### Opción B — variable de entorno

```powershell
$env:AI_LAB_ENABLE_POWERBI = "1"
.\run_web.ps1
```

CLI:

```powershell
$env:AI_LAB_ENABLE_POWERBI = "1"
.\venv\Scripts\python.exe mcp_agent_loop.py "lista las tablas del modelo abierto en Power BI"
```

### Solo lectura (sin cambios al modelo)

```powershell
$env:AI_LAB_ENABLE_POWERBI = "1"
$env:AI_LAB_POWERBI_READONLY = "1"
.\run_web.ps1
```

## Flujo recomendado

1. Abre **Power BI Desktop** y carga tu `.pbix` (vista **Modelo** visible).
2. Arranca ai-lab con **`.\run_web_powerbi.ps1`** (no uses `run_web.ps1` a secas).
3. En http://localhost:8000 debe aparecer el aviso **«Power BI MCP activo»** (no el error rojo de MCP inactivo).
4. Abre **Tools** y comprueba entradas `powerbi__...` (unas 21 tools).
5. Pregunta con texto explícito, por ejemplo:

   **Tablas:**

   ```
   Lista las tablas del modelo abierto en Power BI
   ```

   **Columnas:**

   ```
   Lista las columnas de la tabla california_housing
   ```

   (Sustituye `mi-modelo` / `california_housing` por tu `.pbix` **sin** extensión y tu tabla.)

### Formato real de las tools (no escribas Python en el chat)

Las tools `powerbi__*` esperan JSON, por ejemplo:

```json
{"request": {"operation": "ListLocalInstances"}}
```

```json
{"request": {"operation": "Connect", "connectionString": "data source=localhost:60471;Application Name=MCP-PBIModeling"}}
```

```json
{"request": {"operation": "List"}}
```

```json
{"request": {"operation": "List", "tableName": "california_housing"}}
```

(vía `powerbi__column_operations`; **no existe** la operación `ListColumns`.)

El agente debe **invocar** esas tools; si solo ves texto tipo `powerbi__connection_operations(...)` o JSON suelto como `{"request": {"operation": "ListColumns", ...}}`, el modelo no las ejecutó bien.

### Atajos en el backend (sin depender del LLM)

Para modelos pequeños (`qwen2.5-3b-instruct`) que no hacen function calling, ai-lab puede ejecutar flujos **directos** en Python:

| Petición (ejemplos) | Flujo |
|---------------------|--------|
| *Lista las tablas* / *lista todas las tablas* / *Conéctate a mi-modelo y lista…* | ListLocalInstances → Connect → `table_operations` List |
| *Lista las columnas de la tabla california_housing* | ListLocalInstances → Connect → `column_operations` List |

Condiciones:

- Power BI MCP activo (`run_web_powerbi.ps1` o `AI_LAB_ENABLE_POWERBI=1`).
- Power BI Desktop abierto con el `.pbix`.
- Catálogo por defecto: `mi-modelo` (o indica el nombre en el mensaje, p. ej. `initialCatalog "Ventas"` o `Ventas.pbix`).
- Para columnas: incluye el nombre de la tabla (`california_housing`, *tabla X*, etc.).

La respuesta se formatea como lista legible (nombre, tipo de dato, summarizeBy), no como JSON crudo.

En la **interfaz web**, las frases Power BI aparecen como chips en la bienvenida y en **Ejemplos**; las tres frases del catálogo disparan estos flujos directos. Ver [mcp-servers.md](mcp-servers.md).

**Atajo tablas (legacy):** si pides listar tablas e incluyes `initialCatalog "mi-modelo"`, también dispara el flujo directo.

   Si conoces el nombre del archivo `Ventas.pbix`:

   ```
   Connect to 'Ventas' in Power BI Desktop, then list all tables.
   ```

## Si el agente dice «no tengo acceso a Power BI»

Eso significa que **no llamó a las tools** (respuesta genérica del LLM). Revisa en este orden:

| Comprobación | Qué hacer |
|--------------|-----------|
| ¿Arrancaste con `run_web_powerbi.ps1`? | Sin `AI_LAB_ENABLE_POWERBI=1` no hay tools `powerbi__` |
| ¿Banner «Power BI MCP activo»? | Si ves aviso rojo, reinicia con `run_web_powerbi.ps1` |
| ¿Aparecen tools `powerbi__` en el panel Tools? | Si no, mira la consola de uvicorn (errores de `npx`) |
| ¿Power BI Desktop abierto? | El MCP no ve el modelo si Desktop está cerrado |
| ¿Modelo pequeño en LM Studio? | `qwen2.5-3b` a veces no hace function calling; prueba un modelo mayor o `$env:AI_LAB_POWERBI_ONLY='1'` |
| ¿Muchos `thinking__think` y no avanza? | El modelo se bloquea planeando; usa `AI_LAB_POWERBI_ONLY=1` y un modelo más capaz; reinicia el chat |
| ¿Muchas tools / error `n_ctx`? | Solo Power BI: `$env:AI_LAB_POWERBI_ONLY='1'` antes de arrancar |

### Modo solo Power BI (menos tools, mejor para modelos pequeños)

```powershell
$env:AI_LAB_ENABLE_POWERBI = "1"
$env:AI_LAB_POWERBI_ONLY = "1"
.\run_web.ps1
```

## Variables de entorno

| Variable | Efecto |
|----------|--------|
| `AI_LAB_ENABLE_POWERBI=1` | Registra el servidor `powerbi` al arrancar |
| `AI_LAB_POWERBI_READONLY=1` | Pasa `--readonly` al MCP (sin escritura) |
| `AI_LAB_POWERBI_ONLY=1` | Solo carga el servidor Power BI (menos tools, mejor para modelos pequeños) |

### Flag en disco (`data/runtime_flags.json`)

`run_web_powerbi.ps1` escribe `{"powerbi": true}` para que uvicorn `--reload` en Windows siga viendo Power BI activo tras recargar. El archivo está en `.gitignore`. `run_web.ps1` lo limpia si no usas `AI_LAB_ENABLE_POWERBI`.

## Probar el MCP aislado

```powershell
npx -y @microsoft/powerbi-modeling-mcp@latest --start
```

Si falla aquí, el problema no es ai-lab sino Node, permisos o Power BI Desktop.

## Limitaciones

- **Transporte:** solo el MCP **local** (`stdio`). El MCP remoto de Fabric (`https://api.fabric.microsoft.com/...`) usa HTTP y **no** está integrado en ai-lab.
- **Informes:** no edita páginas ni visuales del informe.
- **Contexto LLM:** con Power BI + el resto de servidores puedes superar `n_ctx` en LM Studio; usa un modelo con contexto ≥ 8k o desactiva servidores que no necesites.

## Referencias

- [Overview Power BI MCP servers (Microsoft Learn)](https://learn.microsoft.com/en-us/power-bi/developer/mcp/mcp-servers-overview)
- [Repositorio powerbi-modeling-mcp](https://github.com/microsoft/powerbi-modeling-mcp)
