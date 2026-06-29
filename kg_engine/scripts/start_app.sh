#!/bin/bash
# Materials KG API bootstrap (WSL/Linux)
# Run from project root: bash kg_engine/scripts/start_app.sh

set -e

echo "=== Materials KG API ==="
echo ""

if [ ! -f ".env" ]; then
    echo "Warning: .env not found. Copy .env.example to .env and configure."
    echo "  cp .env.example .env"
    echo ""
fi

echo "1. Activating virtual environment..."
if [ -d ".venv-wsl" ]; then
    source .venv-wsl/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Error: No .venv found. Run: pip install -e '.[dev]'"
    exit 1
fi

echo "2. Starting API server..."
echo "  Access at: http://localhost:8090"
echo "  Docs at:   http://localhost:8090/docs"
echo ""
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
python kg_engine/scripts/run_materials_api.py
