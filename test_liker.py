"""Simple test script - runs the Tinder auto-like loop without GUI."""

import argparse
import os
import time
import random

from mirror import find_iphone_window, capture_window, click_at
import cv2
import numpy as np

RESOURCES = os.path.join(os.path.dirname(__file__), 'resources')
LIKE_TPL_PATH = os.path.join(RESOURCES, 'tinder_like.png')
MAYBE_LATER_TPL_PATH = os.path.join(RESOURCES, 'tinder_maybe_later.png')
DISMISS_X_TPL_PATH = os.path.join(RESOURCES, 'tinder_dismiss_x.png')
VERIFIED_TPL_PATH = os.path.join(RESOURCES, 'tinder_verified.png')
NOPE_TPL_PATH = os.path.join(RESOURCES, 'tinder_nope.png')

VERIFIED_ONLY = True  # Like only verified profiles, nope the rest

LIKE_THRESHOLD = 0.65
POPUP_THRESHOLD = 0.60
VERIFIED_THRESHOLD = 0.70
NOPE_THRESHOLD = 0.65
RANDOM_OFFSET = 20  # +-20px image coords
MAX_LIKES = 10
MAX_NOPES = 200  # safety cap so we don't loop forever on unverified-only decks
MAX_TOTAL = 0  # 0 = no cap; otherwise stop after this many profiles processed


def load_template(path):
    """Load a template image and return cropped grayscale + metadata."""
    tpl = cv2.imread(path)
    if tpl is None:
        return None
    h, w = tpl.shape[:2]
    mx = int(w * 0.15)
    my = int(h * 0.15)
    cropped = tpl[my:h - my, mx:w - mx]
    ch, cw = cropped.shape[:2]
    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    return {'gray': gray, 'cw': cw, 'ch': ch, 'mx': mx, 'my': my, 'w': w, 'h': h}


def find_template(img_gray, tpl, threshold, min_y=0, max_y=0):
    """Find a template in an image. Returns (cx, cy, conf) or None."""
    result = cv2.matchTemplate(img_gray, tpl['gray'], cv2.TM_CCOEFF_NORMED)
    if min_y > 0 or max_y > 0:
        rows, cols = result.shape
        y_coords = np.arange(rows) + tpl['ch'] // 2 + tpl['my']
        ok = np.ones(rows, dtype=bool)
        if min_y > 0:
            ok &= y_coords >= min_y
        if max_y > 0:
            ok &= y_coords <= max_y
        valid = np.outer(ok, np.ones(cols, dtype=bool))
        result = np.where(valid, result, -1)
    _, mv, _, ml = cv2.minMaxLoc(result)
    if mv < threshold:
        return None
    cx = ml[0] + tpl['cw'] // 2 + tpl['mx']
    cy = ml[1] + tpl['ch'] // 2 + tpl['my']
    return (cx, cy, mv)


# Load templates
like_tpl = load_template(LIKE_TPL_PATH)
maybe_later_tpl = load_template(MAYBE_LATER_TPL_PATH)
dismiss_x_tpl = load_template(DISMISS_X_TPL_PATH)
verified_tpl = load_template(VERIFIED_TPL_PATH)
nope_tpl = load_template(NOPE_TPL_PATH)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Tinder auto-liker test loop.")
    parser.add_argument('--max-likes', type=int, default=MAX_LIKES,
                        help=f"Stop after this many likes (default: {MAX_LIKES})")
    parser.add_argument('--max-nopes', type=int, default=MAX_NOPES,
                        help=f"Safety cap on nopes (default: {MAX_NOPES})")
    parser.add_argument('--max-total', type=int, default=MAX_TOTAL,
                        help=f"Stop after this many profiles (likes+nopes); 0 = no cap (default: {MAX_TOTAL})")
    parser.add_argument('--verified-only', dest='verified_only',
                        action=argparse.BooleanOptionalAction, default=VERIFIED_ONLY,
                        help="Like only verified profiles; --no-verified-only likes everyone")
    args = parser.parse_args()

    max_likes = args.max_likes
    max_nopes = args.max_nopes
    max_total = args.max_total
    verified_only = args.verified_only

    # When --max-total is set, it takes precedence: lift the likes cap so the
    # user's profile-count target isn't bottlenecked by the like default.
    if max_total > 0:
        max_likes = max_total

    print(f"Like template: {like_tpl['w']}x{like_tpl['h']} -> {like_tpl['cw']}x{like_tpl['ch']}")
    print(f"Maybe later: {'loaded' if maybe_later_tpl else 'MISSING'}")
    print(f"Dismiss X: {'loaded' if dismiss_x_tpl else 'MISSING'}")
    print(f"Verified: {'loaded' if verified_tpl else 'MISSING'}")
    print(f"Nope: {'loaded' if nope_tpl else 'MISSING'}")
    print(f"Mode: {'VERIFIED-ONLY' if verified_only else 'LIKE ALL'}")
    if max_total > 0:
        print(f"Stop after: {max_total} profiles (max_nopes safety cap: {max_nopes})")
    else:
        print(f"Stop after: {max_likes} likes (max_nopes safety cap: {max_nopes})")
    print("=" * 50)

    sent = 0
    noped = 0
    failures = 0
    popups_dismissed = 0

    while (
        sent < max_likes
        and failures < 5
        and noped < max_nopes
        and (max_total == 0 or sent + noped < max_total)
    ):
        print(f"\n--- Attempt {sent + noped + 1} (likes: {sent}, nopes: {noped}, failures: {failures}) ---")

        window = find_iphone_window()
        if not window:
            print("No iPhone Mirroring window!")
            failures += 1
            time.sleep(1)
            continue

        image = capture_window(window['id'])
        if image is None:
            print("Capture failed!")
            failures += 1
            time.sleep(0.5)
            continue

        img_gray = cv2.cvtColor(cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2GRAY)

        # Find like button in bottom 30% - confirms we're on a swipe screen
        min_like_y = int(image.size[1] * 0.70)
        like_match = find_template(img_gray, like_tpl, LIKE_THRESHOLD, min_y=min_like_y)

        if like_match:
            # Decide action: like or nope (verified-only mode)
            should_like = True
            if verified_only:
                # Badge lives in the profile info strip - search 50%-80% of height
                v_min = int(image.size[1] * 0.50)
                v_max = int(image.size[1] * 0.80)
                verified_match = find_template(
                    img_gray, verified_tpl, VERIFIED_THRESHOLD, min_y=v_min, max_y=v_max
                )
                if verified_match:
                    vx, vy, vc = verified_match
                    print(f"Verified badge at ({vx}, {vy}) conf={vc:.3f}")
                else:
                    should_like = False
                    # Log the best sub-threshold score so a "nope" is explainable:
                    # a low score = genuinely unverified, a near-miss = threshold tuning.
                    best = find_template(img_gray, verified_tpl, 0.0, min_y=v_min, max_y=v_max)
                    bc = best[2] if best else 0.0
                    print(f"No verified badge (best conf={bc:.3f} < {VERIFIED_THRESHOLD}) -> nope")

            if should_like:
                cx, cy, conf = like_match
                ox = random.randint(-RANDOM_OFFSET, RANDOM_OFFSET)
                oy = random.randint(-RANDOM_OFFSET, RANDOM_OFFSET)
                print(f"Like at ({cx + ox}, {cy + oy}) conf={conf:.3f} offset=({ox},{oy})")
                click_at(cx + ox, cy + oy, window)
                sent += 1
                failures = 0
                print(f"Liked! Total: {sent}/{max_likes}")
            else:
                # Nope - find the red X button in the action row
                nope_match = find_template(img_gray, nope_tpl, NOPE_THRESHOLD, min_y=min_like_y)
                if not nope_match:
                    print("Nope button not found - skipping action")
                    failures += 1
                    time.sleep(1)
                    continue
                cx, cy, conf = nope_match
                ox = random.randint(-RANDOM_OFFSET, RANDOM_OFFSET)
                oy = random.randint(-RANDOM_OFFSET, RANDOM_OFFSET)
                print(f"Nope at ({cx + ox}, {cy + oy}) conf={conf:.3f} offset=({ox},{oy})")
                click_at(cx + ox, cy + oy, window)
                noped += 1
                failures = 0
                print(f"Noped! Total nopes: {noped}")

            delay = random.uniform(2.0, 4.0)
            print(f"Waiting {delay:.1f}s...")
            time.sleep(delay)
            continue

        # Like button not found - check for popup to dismiss
        print(f"Like button NOT found (best match below {LIKE_THRESHOLD})")
        dismissed = False

        # Try "Maybe later" first (bottom of popup)
        if maybe_later_tpl:
            ml_match = find_template(img_gray, maybe_later_tpl, POPUP_THRESHOLD)
            if ml_match:
                cx, cy, conf = ml_match
                print(f"Popup detected! 'Maybe later' at ({cx}, {cy}) conf={conf:.3f}")
                click_at(cx, cy, window)
                popups_dismissed += 1
                dismissed = True
                print(f"Dismissed popup #{popups_dismissed}. Waiting 1.5s...")
                time.sleep(1.5)
                continue

        # Try X button (top-left of popup)
        if not dismissed and dismiss_x_tpl:
            x_match = find_template(img_gray, dismiss_x_tpl, POPUP_THRESHOLD)
            if x_match:
                cx, cy, conf = x_match
                print(f"Popup detected! X button at ({cx}, {cy}) conf={conf:.3f}")
                click_at(cx, cy, window)
                popups_dismissed += 1
                dismissed = True
                print(f"Dismissed popup #{popups_dismissed}. Waiting 1.5s...")
                time.sleep(1.5)
                continue

        if not dismissed:
            print("No popup found either - unknown screen state")
            failures += 1
            time.sleep(1)

    print(f"\nDone! Sent {sent} likes, {noped} nopes, dismissed {popups_dismissed} popups.")
