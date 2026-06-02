#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3 was not found. Install it first, then rerun this script."
  exit 1
fi

if [ ! -d ".venv" ]; then
  if ! "$PYTHON_BIN" -m venv .venv >/dev/null 2>&1; then
    echo "Could not create .venv."
    echo "On Ubuntu/WSL, run: sudo apt update && sudo apt install -y python3-venv"
    exit 1
  fi
fi

# shellcheck disable=SC1091
. .venv/bin/activate

python -m pip install -U pip
python -m pip install -e .
kab start
