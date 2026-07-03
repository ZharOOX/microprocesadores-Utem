#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
python rasberryesp32.py "$@"
