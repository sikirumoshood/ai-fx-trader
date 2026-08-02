#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="${ROOT_DIR}/venv"

cd "${ROOT_DIR}"

if [[ ! -d "${VENV_PATH}" ]]; then
  echo "Error: virtual environment not found at ${VENV_PATH}"
  echo "Create it first, e.g. python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# shellcheck disable=SC1091
source "${VENV_PATH}/bin/activate"

echo "Starting backend server from ${ROOT_DIR}..."
exec python main.py
