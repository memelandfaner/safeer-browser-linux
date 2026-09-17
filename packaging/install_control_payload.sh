#!/usr/bin/env bash
# Safeer Control payload: only what the desktop app needs (Safeer Link core + the Link page).
# No browser code is shipped; Control works on a computer without Safeer Browser.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${1:?Usage: install_control_payload.sh DESTINATION_PREFIX}"
ID="safeer-control"
LIB="$PREFIX/lib/safeer-control"
mkdir -p "$PREFIX/bin" "$LIB/core" "$LIB/assets" "$LIB/packaging" "$PREFIX/share/applications" "$PREFIX/share/pixmaps"
cp -a "$ROOT/safeer_control.py" "$LIB/"
for modul in link_hub link_tls link_deljenje link_daljinec link_datoteke safeer_link spake2; do
    cp -a "$ROOT/core/$modul.py" "$LIB/core/"
done
[ -f "$ROOT/core/__init__.py" ] && cp -a "$ROOT/core/__init__.py" "$LIB/core/" || true
cp -a "$ROOT/assets/link" "$LIB/assets/"
cp -a "$ROOT/packaging/VERSION_CONTROL" "$LIB/packaging/"
find "$LIB" -type d -name __pycache__ -exec rm -rf {} +
find "$LIB" -name '*.pyc' -delete
install -m755 "$ROOT/packaging/safeer-control-launcher" "$PREFIX/bin/safeer-control"
install -Dm644 "$ROOT/LICENSE" "$PREFIX/share/doc/safeer-control/LICENSE"
install -m644 "$ROOT/packaging/safeer-control.desktop" "$PREFIX/share/applications/$ID.desktop"
install -m644 "$ROOT/assets/icon.png" "$PREFIX/share/pixmaps/$ID.png"
for icon in "$ROOT/packaging/icons/hicolor"/*/apps/safeer-browser.png; do
    size=$(basename "$(dirname "$(dirname "$icon")")")
    install -Dm644 "$icon" "$PREFIX/share/icons/hicolor/$size/apps/$ID.png"
done
