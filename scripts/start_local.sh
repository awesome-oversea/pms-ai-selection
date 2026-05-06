#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/.pms_python_ready" && -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
elif [[ -f ".venv/.pms_python_ready" && -x ".venv/Scripts/python.exe" ]]; then
  PYTHON=".venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
else
  echo "Python is required. Create .venv or install python first." >&2
  exit 1
fi

KNOWN_COMMANDS=("bootstrap" "summary" "check" "plan" "up")

if [[ $# -gt 0 ]]; then
  for command in "${KNOWN_COMMANDS[@]}"; do
    if [[ "$1" == "$command" ]]; then
exec "$PYTHON" scripts/local_runtime_manager.py "$@"
    fi
  done
fi

exec "$PYTHON" scripts/local_runtime_manager.py up --skip-deps --preflight "$@"
