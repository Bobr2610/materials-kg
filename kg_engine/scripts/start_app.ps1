# Materials KG API bootstrap (Windows PowerShell)
# Run from project root: .\kg_engine\scripts\start_app.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Materials KG API ===" -ForegroundColor Cyan
Write-Host ""

if (!(Test-Path ".env")) {
    Write-Host "Warning: .env not found. Copy .env.example to .env and configure." -ForegroundColor Yellow
    Write-Host "  Copy-Item .env.example .env" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "1. Activating virtual environment..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    & .\.venv\Scripts\Activate.ps1
} else {
    Write-Host "Error: No .venv found. Run: pip install -e '.[dev]'" -ForegroundColor Red
    exit 1
}

Write-Host "2. Starting API server..." -ForegroundColor Yellow
Write-Host "  Access at: http://localhost:8090" -ForegroundColor Green
Write-Host "  Docs at:   http://localhost:8090/docs" -ForegroundColor Green
Write-Host ""
$env:PYTHONPATH = "$PWD;$env:PYTHONPATH"
python kg_engine\scripts\run_materials_api.py
