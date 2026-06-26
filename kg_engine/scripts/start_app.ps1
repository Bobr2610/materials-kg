# App bootstrap script for RAG engine (Windows PowerShell)
# Run from project root: .\kg_engine\scripts\start_app.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Materials KG App Bootstrap ===" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (!(Test-Path ".env")) {
    Write-Host "Warning: .env file not found. Copy .env-example to .env and fill in your API keys." -ForegroundColor Yellow
    Write-Host "  Copy-Item .env-example .env" -ForegroundColor Yellow
    Write-Host ""
}

# Activate venv
Write-Host "1. Activating virtual environment..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    & .\.venv\Scripts\Activate.ps1
} elseif (Test-Path ".venv-wsl") {
    Write-Host "Error: .venv-wsl found but this is Windows PowerShell. Use WSL for .venv-wsl" -ForegroundColor Red
    exit 1
} else {
    Write-Host "Error: No virtual environment found. Run test setup first:" -ForegroundColor Red
    Write-Host "  python -m pytest kg_engine/tests/ -v" -ForegroundColor Red
    exit 1
}

# Start the app
Write-Host "2. Starting Materials KG app..." -ForegroundColor Yellow
Write-Host "  Access at: http://localhost:7860" -ForegroundColor Green
Write-Host ""
# Set PYTHONPATH to project root
$env:PYTHONPATH = "$PWD;$env:PYTHONPATH"
python kg_engine\api\app.py
