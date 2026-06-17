#!/bin/bash
# Double-click this file to run TinderTapper.

cd "$(dirname "$0")" || exit 1
clear
echo "============================================"
echo "   TinderTapper"
echo "============================================"
echo

# Set up automatically on first run.
if [ ! -x ".venv/bin/python" ]; then
    echo "First run — setting things up..."
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Python 3 isn't installed. Double-click \"install.command\" first."
        read -n 1 -s -r -p "Press any key to close."; echo; exit 1
    fi
    python3 -m venv .venv
    ./.venv/bin/python -m pip install --quiet --upgrade pip
    ./.venv/bin/python -m pip install --quiet -r requirements.txt
    echo
fi

PY=./.venv/bin/python

# Pre-flight: is iPhone Mirroring open and can we see it?
STATUS=$($PY - <<'PYEOF'
import sys
sys.path.insert(0, ".")
try:
    from mirror import find_iphone_window, capture_window
    w = find_iphone_window()
    if not w:
        print("NO_WINDOW")
    else:
        print("OK" if capture_window(w["id"]) is not None else "NO_CAPTURE")
except Exception as e:
    print("ERROR:" + str(e))
PYEOF
)

case "$STATUS" in
    NO_WINDOW)
        echo "I can't find the iPhone Mirroring window."
        echo
        echo "  1. Open the 'iPhone Mirroring' app (from Spotlight or Applications)."
        echo "  2. Open Tinder on it, on the main swipe screen."
        echo "  3. Double-click this file again."
        echo
        read -n 1 -s -r -p "Press any key to close."; echo; exit 1
        ;;
    NO_CAPTURE)
        echo "Screen Recording permission is needed so I can see the screen."
        echo "Opening that setting now — turn ON your terminal app, then quit and"
        echo "reopen it and double-click this file again."
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        echo
        read -n 1 -s -r -p "Press any key to close."; echo; exit 1
        ;;
    OK)
        : # all good, continue
        ;;
    *)
        echo "Something went wrong: $STATUS"
        read -n 1 -s -r -p "Press any key to close."; echo; exit 1
        ;;
esac

echo "Ready. Make sure Tinder is on the swipe screen."
echo
read -r -p "How many profiles should I go through? [200]: " COUNT
COUNT=${COUNT:-200}
case "$COUNT" in
    ''|*[!0-9]*) COUNT=200 ;;
esac
echo
echo "Going through up to $COUNT profiles (verified-only). Press Ctrl-C to stop early."
echo "--------------------------------------------"
$PY test_liker.py --max-total "$COUNT"
echo "--------------------------------------------"
echo
read -n 1 -s -r -p "All done. Press any key to close."
echo
