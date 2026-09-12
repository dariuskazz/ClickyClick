#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLICKYCLICK_STEAMOS_PREVIEW=1
exec "$APP_DIR/venv/bin/python" "$APP_DIR/clickyclick.py"
