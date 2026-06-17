"""Diagnose and re-capture TinderTapper templates when Tinder changes an icon.

Tinder occasionally restyles its buttons/badges. Grayscale matching shrugs off
colour changes, but a restyle or a light/dark *polarity* flip will drop a
template's match confidence below threshold and the bot starts misbehaving
(e.g. noping everyone because the "verified" badge no longer matches).

This tool lets you fix that yourself:

    # 1. See which template is failing (open Tinder on the swipe deck first)
    python recapture.py

    # 2. Re-capture the broken one — drag a box around the icon, press ENTER
    python recapture.py tinder_verified

    # 3. Re-check, then commit & push
    python recapture.py
    git add resources/tinder_verified.png && git commit -m "Update verified icon" && git push

Non-interactive crop (no GUI window) and re-checking against a saved screenshot
are also supported — see --help.
"""

import argparse
import logging
import os
import sys

import cv2
import numpy as np

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from mirror import find_iphone_window, capture_window, find_icon  # noqa: E402

RESOURCES = os.path.join(_script_dir, "resources")

# name -> (threshold, search-region as fractions of capture height).
# Regions mirror the ones test_liker.py uses so the reported confidence matches
# what the bot actually sees at runtime. "popup_only" templates only appear when
# a promo popup is on screen, so they can't be verified from a normal swipe deck.
TEMPLATES = {
    "tinder_like":        {"threshold": 0.65, "y_lo": 0.70, "y_hi": 1.00, "desc": "heart / like button"},
    "tinder_nope":        {"threshold": 0.65, "y_lo": 0.70, "y_hi": 1.00, "desc": "X / nope button"},
    "tinder_verified":    {"threshold": 0.70, "y_lo": 0.50, "y_hi": 0.80, "desc": "photo-verified badge by the name"},
    "tinder_maybe_later": {"threshold": 0.60, "y_lo": 0.00, "y_hi": 1.00, "desc": "'Maybe later' on promo popups", "popup_only": True},
    "tinder_dismiss_x":   {"threshold": 0.60, "y_lo": 0.00, "y_hi": 1.00, "desc": "X to close a popup", "popup_only": True},
}

log = logging.getLogger("tindertapper")


def grab_screen(shot_path=None):
    """Return a PIL image: a saved screenshot if given, else a live capture."""
    if shot_path:
        from PIL import Image

        img = Image.open(shot_path).convert("RGB")
        print(f"Using screenshot: {shot_path} ({img.size[0]}x{img.size[1]})")
        return img

    window = find_iphone_window()
    if not window:
        print("ERROR: iPhone Mirroring window not found.")
        print("  - Open the iPhone Mirroring app and make sure Tinder is showing.")
        return None
    img = capture_window(window["id"])
    if img is None:
        print("ERROR: capture failed. Grant Screen Recording permission:")
        print("  System Settings > Privacy & Security > Screen Recording")
        return None
    return img


def check_all(image):
    """Print the current match confidence for every template. Returns failures."""
    h = image.size[1]
    print(f"\nChecking {len(TEMPLATES)} templates against a {image.size[0]}x{h} capture:\n")
    failures = []
    for name, spec in TEMPLATES.items():
        path = os.path.join(RESOURCES, f"{name}.png")
        if not os.path.exists(path):
            print(f"  {name:20s} MISSING FILE  ({spec['desc']})")
            failures.append(name)
            continue
        min_y = int(h * spec["y_lo"]) if spec["y_lo"] > 0 else 0
        max_y = int(h * spec["y_hi"]) if spec["y_hi"] < 1 else 0
        match = find_icon(image, f"{name}.png", threshold=spec["threshold"],
                          min_y=min_y, max_y=max_y, return_best_match=True)
        conf = match[2] if match else 0.0
        ok = conf >= spec["threshold"]
        if spec.get("popup_only"):
            # Only present during a promo popup, so a low score on the swipe
            # deck is expected — don't flag it as broken.
            flag = "popup-only"
        else:
            flag = "PASS" if ok else "FAIL"
            if not ok:
                failures.append(name)
        print(f"  {name:20s} conf={conf:0.3f}  threshold={spec['threshold']:.2f}  [{flag}]"
              f"   {spec['desc']}")

    print()
    if failures:
        print("Needs re-capturing: " + ", ".join(failures))
        print("Run:  python recapture.py <name>")
    else:
        print("Swipe-deck templates all match. (popup-only templates can't be "
              "checked unless a popup is on screen.)")
    return failures


def _save_crop(image, name, box):
    """Crop box=(x, y, w, h) from a PIL image and save to resources/<name>.png."""
    x, y, w, h = box
    if w <= 0 or h <= 0:
        print("ERROR: empty selection, nothing saved.")
        return False
    bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    crop = bgr[y:y + h, x:x + w]
    out = os.path.join(RESOURCES, f"{name}.png")
    cv2.imwrite(out, crop)
    print(f"Saved {w}x{h} crop -> {out}")
    return True


def recapture_interactive(image, name):
    """Open a draggable selector so the user can box the new icon."""
    bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    # Fit the preview to a sane height so tall captures still fit on screen.
    scale = min(1.0, 900.0 / bgr.shape[0])
    disp = cv2.resize(bgr, (int(bgr.shape[1] * scale), int(bgr.shape[0] * scale))) if scale < 1 else bgr
    title = f"Drag a box around: {name}  (ENTER=save, C=cancel)"
    try:
        roi = cv2.selectROI(title, disp, showCrosshair=True, fromCenter=False)
        cv2.destroyAllWindows()
    except cv2.error as e:
        print(f"ERROR: no GUI available for interactive crop ({e}).")
        print("Use the non-interactive form instead:  python recapture.py "
              f"{name} --box X Y W H")
        return False
    rx, ry, rw, rh = roi
    if rw == 0 or rh == 0:
        print("Cancelled — no selection.")
        return False
    box = (int(rx / scale), int(ry / scale), int(rw / scale), int(rh / scale))
    return _save_crop(image, name, box)


def main():
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Diagnose and re-capture TinderTapper icon templates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("template", nargs="?", default=None,
                        help="Template to re-capture (e.g. tinder_verified). "
                             "Omit to just run a diagnostic check.")
    parser.add_argument("--box", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                        help="Crop these pixel coords instead of selecting interactively.")
    parser.add_argument("--shot", metavar="FILE",
                        help="Use this screenshot instead of capturing the live window.")
    parser.add_argument("--save-shot", metavar="FILE", default=None,
                        help="Also save the captured screen to this path (handy for offline cropping).")
    parser.add_argument("--list", action="store_true", help="List known template names and exit.")
    args = parser.parse_args()

    if args.list:
        for name, spec in TEMPLATES.items():
            print(f"  {name:20s} {spec['desc']}")
        return

    if args.template and args.template not in TEMPLATES:
        print(f"Unknown template '{args.template}'. Known names:")
        for name in TEMPLATES:
            print(f"  {name}")
        sys.exit(1)

    image = grab_screen(args.shot)
    if image is None:
        sys.exit(1)

    if args.save_shot:
        image.save(args.save_shot)
        print(f"Saved screenshot -> {args.save_shot}")

    if not args.template:
        check_all(image)
        return

    if args.box:
        ok = _save_crop(image, args.template, tuple(args.box))
    else:
        ok = recapture_interactive(image, args.template)

    if ok:
        print("\nRe-checking with the new template:")
        check_all(image)
        print("\nIf it now PASSes, test the bot then commit:")
        print(f"  python test_liker.py --max-total 5")
        print(f"  git add resources/{args.template}.png && "
              f'git commit -m "Update {args.template} icon" && git push')


if __name__ == "__main__":
    main()
