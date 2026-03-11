#!/usr/bin/env bash
set -e

# Simple frontend + backend launcher for development
# Usage: run from the eye_test_engine directory: ./start_frontend.sh

cd "$(dirname "$0")" || exit 1

# Prefer a local venv in this folder, otherwise try parent .venv
VENV_DIR=""
if [ -d "./venv" ]; then
    VENV_DIR="./venv"
elif [ -d "../.venv" ]; then
    VENV_DIR="../.venv"
elif [ -d ".venv" ]; then
    VENV_DIR=".venv"
fi

if [ -n "$VENV_DIR" ]; then
    echo "Activating virtualenv: $VENV_DIR"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
else
    echo "No virtualenv found; using system Python. Create one with: python3 -m venv venv"
fi

PYTHON=$(which python3 || which python)
echo "Using python: $PYTHON"

echo "Starting backend API server (port 5050)..."
PYTHONPATH=.. "$PYTHON" -m eye_test_engine.api_server &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

sleep 2

echo "Starting frontend static server (port 8080)..."
cd frontend
"$PYTHON" -m http.server 8080 &
FRONTEND_PID=$!
cd - >/dev/null
echo "Frontend PID: $FRONTEND_PID"

echo "Frontend: http://localhost:8080"
echo "Backend:  http://localhost:5050"

if [[ "$OSTYPE" == "darwin"* ]]; then
    open http://localhost:8080 || true
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open http://localhost:8080 || true
fi

trap 'echo "Stopping servers..."; kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true; exit' INT
wait
