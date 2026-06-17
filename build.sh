#!/bin/bash
set -e

echo "=== TinderTapper Build ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
fi

pip install -q pyinstaller

rm -rf dist/TinderTapper.app build/
pyinstaller TinderTapper.spec --noconfirm

echo ""
echo "=== Build complete: dist/TinderTapper.app ==="
echo "Install:  cp -r dist/TinderTapper.app /Applications/"
