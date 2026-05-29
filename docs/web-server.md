# Servidor web de chat (ai-lab)

Interfaz de chat en el navegador para hablar con el agente MCP sin usar la terminal.

## Requisitos previos

1. **Entorno Python** con dependencias instaladas:

   ```powershell
   cd C:\Users\chuwi\ai-lab
   python -m venv venv
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. **LM Studio** en ejecución:
   - Carga un modelo (por defecto el proyecto usa `qwen2.5-3b-instruct`).
   - Activa el **servidor local** en el puerto **1234** (menú *Local Server* → *Start Server*).

3. **Node.js** (para `filesystem` vía `npx` y, opcionalmente, Power BI MCP).

**Power BI (opcional):** ver [docs/powerbi-mcp.md](powerbi-mcp.md). Arranque rápido: `.\run_web_powerbi.ps1` (requiere Desktop abierto).

---

## Arranque rápido (recomendado)

Desde la raíz del proyecto:

```powershell
.\run_web.ps1
```

El script:
- Usa el Python de `venv\Scripts\python.exe`
- Levanta **uvicorn** con recarga automática (`--reload`)
- Escucha en **http://127.0.0.1:8000**

Abre en el navegador: **http://localhost:8000**

---

## Arranque manual

```powershell
cd C:\Users\chuwi\ai-lab
.\venv\Scripts\activate
python -m uvicorn client.app:app --reload --host 127.0.0.1 --port 8000
```

Equivalente sin activar el venv:

```powershell
.\venv\Scripts\python.exe -m uvicorn client.app:app --reload --host 127.0.0.1 --port 8000
```

---

## Cambiar el modelo

Por defecto se usa `qwen2.5-3b-instruct`. Para otro modelo cargado en LM Studio:

```powershell
$env:AI_LAB_MODEL = "qwen2.5-7b-instruct-1m"
.\run_web.ps1
```

En LM Studio, el contexto del modelo debe ser suficiente (≥ 8192 tokens si usas muchas tools).

---

## Qué ofrece la interfaz

| Ruta | Descripción |
|------|-------------|
| `GET /` | Chat web (preguntas, historial, sugerencias) |
| `GET /health` | Estado del servicio y modelo configurado |
| `GET /memory` | Historial de conversación (`data/memory.json`) |
| `DELETE /memory` | Borrar historial |
| `GET /tools` | Lista de herramientas MCP |
| `GET /prompts` | Frases de ejemplo agrupadas por servidor MCP |
| `GET /reports/{filename}` | Informes HTML generados (dashboards, diagramas de flujo) |
| `POST /chat` | Enviar mensaje al agente (API REST) |
| `GET /docs` | Documentación OpenAPI (Swagger) |

La memoria del chat web es la misma que la del CLI (`data/memory.json`).

### Frases de ejemplo (chips)

Al abrir el chat sin historial verás **tarjetas por servidor MCP** con frases listas para enviar. También puedes usar el botón **Ejemplos** en la cabecera.

Las frases provienen de `GET /prompts` (catálogo en `agent_core.get_mcp_prompt_catalog()`). Detalle por servidor: [mcp-servers.md](mcp-servers.md).

Power BI: las frases de tablas/columnas usan **flujos directos** en el backend cuando el LLM no invoca tools bien (modelos pequeños). Ver [powerbi-mcp.md](powerbi-mcp.md).

**Diagramas de flujo:** frases sobre `tramites.csv` generan HTML interactivo en `/reports/`. Ver [flow-diagrams.md](flow-diagrams.md).

---

## Uso de la API (curl)

Con el servidor en marcha:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"¿Qué hace agent_core.py?\", \"max_steps\": 8}"

curl http://localhost:8000/health
curl http://localhost:8000/memory
curl -X DELETE http://localhost:8000/memory
curl http://localhost:8000/tools
curl http://localhost:8000/prompts
```

---

## Detener el servidor

En la terminal donde corre uvicorn: **Ctrl+C**.

---

## Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---------|----------------|-----------|
| Estado **offline** en la web | uvicorn no está corriendo | Ejecuta `.\run_web.ps1` |
| Error 503 / timeout en `/chat` | LM Studio apagado o modelo no cargado | Inicia el servidor local en LM Studio (puerto 1234) |
| Respuesta muy lenta (1–3 min) | Primera petición arranca servidores MCP + inferencia | Normal; las siguientes suelen ser más rápidas |
| `ModuleNotFoundError: mcp` | Python del sistema en lugar del venv | Usa `.\venv\Scripts\python.exe` o `run_web.ps1` |
| Error de contexto (`n_ctx` / `n_keep`) | Prompt + tools demasiado grandes | Usa un modelo con más contexto o `$env:AI_LAB_MODEL` con un modelo más pequeño |

---

## Arquitectura (resumen)

```
Navegador  →  FastAPI (client/app.py)  →  agent_core.py
                    ↓
              LM Studio :1234 (OpenAI-compatible)
                    ↓
              Servidores MCP (stdio): filesystem, custom, git, fetch, thinking
```

Código relevante:
- `run_web.ps1` — script de arranque
- `client/app.py` — API + interfaz HTML
- `agent_core.py` — lógica del agente (compartida con `mcp_agent_loop.py`)
