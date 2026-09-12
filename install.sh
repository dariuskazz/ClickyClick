#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/venv"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APPLICATIONS_DIR/clickyclick.desktop"

python3 -m venv --system-site-packages "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

mkdir -p "$APPLICATIONS_DIR"
# Replace the symlink created by early ClickyClick installers. Writing through
# that link would overwrite the repository's launcher template.
if [ -L "$DESKTOP_FILE" ]; then
    unlink "$DESKTOP_FILE"
fi
sed \
    -e "s|@EXEC@|$APP_DIR/run.sh|g" \
    -e "s|@ICON@|$APP_DIR/assets/icon.png|g" \
    "$APP_DIR/clickyclick.desktop" > "$DESKTOP_FILE"
chmod 644 "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

echo "ClickyClick is installed. Start it from the application menu or run:"
echo "  $APP_DIR/run.sh"
