# Arranca la interfaz web de chat (FastAPI + uvicorn)
$Root = $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Error "No se encuentra venv. Crea el entorno: python -m venv venv"
    exit 1
}

# Sin Power BI: limpia el flag persistido (salvo que venga por variable de entorno)
if (-not $env:AI_LAB_ENABLE_POWERBI) {
    & $Python -c "from agent_core import set_runtime_powerbi; set_runtime_powerbi(False)" 2>$null
}

Write-Host ""
Write-Host "ai-lab — interfaz web" -ForegroundColor Cyan
Write-Host "  1. Abre LM Studio y carga un modelo (ej. qwen2.5-3b-instruct)" -ForegroundColor DarkGray
Write-Host "  2. Inicia el servidor local en LM Studio (puerto 1234)" -ForegroundColor DarkGray
Write-Host "  3. Abre en el navegador: http://localhost:8000" -ForegroundColor Green
Write-Host "  Power BI: usa .\run_web_powerbi.ps1" -ForegroundColor DarkGray
Write-Host ""

& $Python -m uvicorn client.app:app --reload --host 127.0.0.1 --port 8000
