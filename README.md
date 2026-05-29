# ai-lab

Agente local con herramientas MCP, LM Studio y memoria de conversación.

## Inicio rápido

### Chat web

```powershell
.\run_web.ps1
```

Abre http://localhost:8000 (requiere LM Studio en el puerto 1234).

→ [Guía del servidor web](docs/web-server.md) · [Servidores MCP y frases de ejemplo](docs/mcp-servers.md)

**Con Power BI Desktop:** `.\run_web_powerbi.ps1` → [docs/powerbi-mcp.md](docs/powerbi-mcp.md)

**Análisis / cuadro de mando desde CSV** (sin Power BI): [docs/analytics-dashboard.md](docs/analytics-dashboard.md) — dataset `california_housing.csv`

### Terminal

```powershell
.\venv\Scripts\python.exe mcp_agent_loop.py "tu pregunta"
```

→ [Guía de uso](docs/usage-guide.md)
