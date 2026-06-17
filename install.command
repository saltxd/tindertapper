#!/bin/bash
# Double-click this file to set up TinderTapper. Safe to run more than once.

cd "$(dirname "$0")" || exit 1
clear
echo "============================================"
echo "   TinderTapper — Setup"
echo "============================================"
echo

# 1. Make sure Python 3 is available.
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 isn't installed yet."
    echo "A macOS installer window should pop up — click \"Install\" and wait,"
    echo "then double-click this file again."
    echo
    echo "(If nothing pops up, get Python from https://www.python.org/downloads/ )"
    xcode-select --install 2>/dev/null
    echo
    read -n 1 -s -r -p "Press any key to close this window."
    echo
    exit 1
fi
echo "[1/2] Found $(python3 --version)"

# 2. Create the isolated environment and install dependencies.
echo "[2/2] Installing (this takes 1-2 minutes the first time)..."
python3 -m venv .venv || { echo "Could not create environment."; read -n 1 -s -r -p "Press any key."; exit 1; }
./.venv/bin/python -m pip install --quiet --upgrade pip
if ! ./.venv/bin/python -m pip install --quiet -r requirements.txt; then
    echo
    echo "Dependency install failed. Check your internet connection and try again."
    read -n 1 -s -r -p "Press any key to close."
    echo
    exit 1
fi

echo
echo "============================================"
echo "   Done! Two quick one-time permissions:"
echo "============================================"
echo "  System Settings  >  Privacy & Security  >  Screen Recording"
echo "      -> turn ON your terminal app (Terminal)"
echo "  System Settings  >  Privacy & Security  >  Accessibility"
echo "      -> turn ON your terminal app (Terminal)"
echo
echo "Then: open iPhone Mirroring with Tinder on the swipe screen,"
echo "and double-click  \"Start TinderTapper.command\"."
echo
read -n 1 -s -r -p "Press any key to close this window."
echo
