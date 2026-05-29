# ai-lab

Agente local con herramientas MCP, LM Studio y memoria de conversación.

## Inicio rápido

### Chat web

```powershell
.\run_web.ps1
```

Abre http://localhost:8000 (requiere LM Studio en el puerto 1234).

→ [Guía del servidor web](docs/web-server.md)

**Con Power BI Desktop:** `.\run_web_powerbi.ps1` → [docs/powerbi-mcp.md](docs/powerbi-mcp.md)

### Terminal

```powershell
.\venv\Scripts\python.exe mcp_agent_loop.py "tu pregunta"
```

→ [Guía de uso](docs/usage-guide.md)
