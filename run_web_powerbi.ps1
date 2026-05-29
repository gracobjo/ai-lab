# Arranca el chat web con el servidor MCP de Power BI Modeling habilitado
$Root = $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "No se encuentra venv. Crea el entorno: python -m venv venv"
    exit 1
}

$env:AI_LAB_ENABLE_POWERBI = "1"

# Flag en disco: uvicorn --reload en Windows no siempre hereda variables de entorno
& $Python -c "from agent_core import set_runtime_powerbi; set_runtime_powerbi(True)"

Write-Host ""
Write-Host "Power BI MCP activado" -ForegroundColor Cyan
Write-Host "  - Flag: data/runtime_flags.json (powerbi=true)" -ForegroundColor DarkGray
Write-Host "  - Abre Power BI Desktop con tu .pbix antes de preguntar" -ForegroundColor DarkGray
Write-Host "  - Solo lectura: `$env:AI_LAB_POWERBI_READONLY = '1'" -ForegroundColor DarkGray
Write-Host "  - Comprueba: http://localhost:8000/health -> powerbi_mcp: true" -ForegroundColor Green
Write-Host ""

& $Python -m uvicorn client.app:app --reload --host 127.0.0.1 --port 8000
