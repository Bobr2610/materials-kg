#!/bin/bash
# App bootstrap script for RAG engine (WSL/Linux)
# Run from project root: bash rag_engine/scripts/start_app.sh

set -e  # Exit on error

echo "=== RAG Engine App Bootstrap ==="
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Warning: .env file not found. Copy .env-example to .env and fill in your API keys."
    echo "  cp .env-example .env"
    echo ""
fi

# Activate venv
echo "1. Activating virtual environment..."
if [ -d ".venv-wsl" ]; then
    source .venv-wsl/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "Error: No virtual environment found. Run test setup first:"
    echo "  bash rag_engine/tests/scripts/setup_and_test.sh"
    exit 1
fi

# Start the app
echo "2. Starting RAG engine app..."
echo "  Access at: http://localhost:7860"
echo ""
# Set PYTHONPATH to project root
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
python rag_engine/api/app.py
