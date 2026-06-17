"""Core iPhone Mirroring automation: find the window, capture it, match icon
templates, and click.

This module is fully self-contained — it talks to macOS directly via the
Quartz / AppKit frameworks (PyObjC) and OpenCV. No other project files are
required.
"""

import logging
import os
import sys
import time

import cv2
import numpy as np
from PIL import Image
import Quartz
from Quartz import (
    CGWindowListCopyWindowInfo,
    kCGWindowListOptionOnScreenOnly,
    kCGNullWindowID,
    CGWindowListCreateImage,
    CGRectNull,
    kCGWindowListOptionIncludingWindow,
    kCGWindowImageBoundsIgnoreFraming,
    CGEventCreateMouseEvent,
    CGEventPost,
    kCGEventMouseMoved,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseUp,
    kCGHIDEventTap,
)
from Quartz.CoreGraphics import CGPointMake
from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps

log = logging.getLogger("tindertapper")

# The macOS app that mirrors your iPhone is always owned by this exact process.
MIRRORING_OWNER = "iPhone Mirroring"

# iPhone Mirroring renders at 2x (Retina); captured pixels are 2x the on-screen
# points, so clicks divide image coordinates by this factor.
RETINA_SCALE = 2


def get_resource_path(filename: str) -> str:
    """Resolve a file in ``resources/`` for both dev runs and a bundled .app."""
    paths_to_check = []

    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            paths_to_check.append(os.path.join(sys._MEIPASS, "resources", filename))
        exe_dir = os.path.dirname(sys.executable)
        paths_to_check.append(os.path.join(exe_dir, "resources", filename))
        if ".app" in exe_dir:
            app_contents = os.path.dirname(exe_dir)
            paths_to_check.append(
                os.path.join(app_contents, "Resources", "resources", filename)
            )

    script_dir = os.path.dirname(os.path.abspath(__file__))
    paths_to_check.append(os.path.join(script_dir, "resources", filename))

    for path in paths_to_check:
        if os.path.exists(path):
            return path
    return os.path.join(script_dir, "resources", filename)


def activate_app(owner_name: str) -> bool:
    """Bring an app to the front by (substring of) its localized name."""
    workspace = NSWorkspace.sharedWorkspace()
    for app in workspace.runningApplications():
        if owner_name.lower() in app.localizedName().lower():
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            time.sleep(0.1)
            return True
    return False


def find_iphone_window():
    """Return the iPhone Mirroring window info dict, or None if it isn't open.

    Matches the mirroring app's owner name *exactly*. (A naive substring match
    on "iPhone" also matches unrelated windows — e.g. a terminal whose title
    contains "iPhone" — and grabs the wrong window.)
    """
    windows = CGWindowListCopyWindowInfo(
        kCGWindowListOptionOnScreenOnly, kCGNullWindowID
    )
    for window in windows:
        if window.get("kCGWindowOwnerName", "") == MIRRORING_OWNER:
            bounds = window.get("kCGWindowBounds", {})
            return {
                "id": window.get("kCGWindowNumber"),
                "x": int(bounds.get("X", 0)),
                "y": int(bounds.get("Y", 0)),
                "width": int(bounds.get("Width", 0)),
                "height": int(bounds.get("Height", 0)),
                "owner": window.get("kCGWindowOwnerName", ""),
                "name": window.get("kCGWindowName", ""),
            }
    return None


def capture_window(window_id):
    """Capture a window by id and return it as a PIL ``Image`` (or None)."""
    try:
        cg_image = CGWindowListCreateImage(
            CGRectNull,
            kCGWindowListOptionIncludingWindow,
            window_id,
            kCGWindowImageBoundsIgnoreFraming,
        )
        if not cg_image:
            log.warning("capture_window: no image (Screen Recording permission?)")
            return None

        width = Quartz.CGImageGetWidth(cg_image)
        height = Quartz.CGImageGetHeight(cg_image)
        bytes_per_row = Quartz.CGImageGetBytesPerRow(cg_image)
        log.debug("captured %dx%d (stride %d)", width, height, bytes_per_row)

        pixel_data = Quartz.CGDataProviderCopyData(
            Quartz.CGImageGetDataProvider(cg_image)
        )
        arr = np.frombuffer(pixel_data, dtype=np.uint8)
        arr = arr.reshape((height, bytes_per_row // 4, 4))  # BGRA, row-padded
        arr = arr[:, :width, :]  # trim row padding
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
        return Image.fromarray(rgb)
    except Exception:  # noqa: BLE001 - report and let the caller retry
        log.exception("capture_window failed")
        return None


def find_icon(
    image,
    template_filename: str,
    threshold: float = 0.8,
    min_x: int = 0,
    min_y: int = 0,
    max_y: int = 0,
    return_best_match: bool = False,
):
    """Locate a template within ``image`` via grayscale template matching.

    Returns ``(center_x, center_y, confidence)`` in image (capture) pixel
    coordinates, or None if nothing clears ``threshold``.

    Matching is done in grayscale with ``TM_CCOEFF_NORMED``, which is robust to
    colour changes (a red vs. green heart still matches) but NOT to a polarity
    flip (a light-on-dark icon becoming dark-on-light) — that needs a fresh
    template (see ``recapture.py``).

    min_x / min_y / max_y constrain the match to a screen region (0 = no limit).
    return_best_match returns the best sub-threshold hit instead of None, for
    diagnostics.
    """
    template_path = get_resource_path(template_filename)
    template = cv2.imread(template_path)
    if template is None:
        raise FileNotFoundError(f"Could not load template: {template_path}")

    img_bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    # Crop 15% margins off the template so background-dependent edges (dark app
    # corners behind an icon) don't sink the match on bright profile photos.
    h, w = template.shape[:2]
    mx, my = int(w * 0.15), int(h * 0.15)
    cropped = template[my : h - my, mx : w - mx]
    ch, cw = cropped.shape[:2]

    template_gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)

    _, best_val, _, best_loc = cv2.minMaxLoc(result)

    if min_x > 0 or min_y > 0 or max_y > 0:
        rows, cols = result.shape
        x_coords = np.arange(cols) + cw // 2 + mx
        y_coords = np.arange(rows) + ch // 2 + my
        ok_x = x_coords >= min_x if min_x > 0 else np.ones(cols, dtype=bool)
        ok_y = np.ones(rows, dtype=bool)
        if min_y > 0:
            ok_y &= y_coords >= min_y
        if max_y > 0:
            ok_y &= y_coords <= max_y
        valid = np.outer(ok_y, ok_x)
        masked = np.where(valid, result, -1)
        _, mv, _, ml = cv2.minMaxLoc(masked)
    else:
        mv, ml = best_val, best_loc

    if mv >= threshold:
        return (ml[0] + cw // 2 + mx, ml[1] + ch // 2 + my, float(mv))

    if return_best_match:
        return (ml[0] + cw // 2 + mx, ml[1] + ch // 2 + my, float(mv))
    return None


def image_to_screen_coords(img_x, img_y, window, retina_scale: int = RETINA_SCALE):
    """Convert capture-pixel coords to on-screen point coords."""
    return (
        window["x"] + (img_x / retina_scale),
        window["y"] + (img_y / retina_scale),
    )


def click_at(img_x, img_y, window):
    """Click at the given image coordinates inside the mirroring window."""
    screen_x, screen_y = image_to_screen_coords(img_x, img_y, window)

    if window.get("owner"):
        activate_app(window["owner"])

    point = CGPointMake(float(screen_x), float(screen_y))
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventMouseMoved, point, 0))
    time.sleep(0.1)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseDown, point, 0))
    time.sleep(0.05)
    CGEventPost(kCGHIDEventTap, CGEventCreateMouseEvent(None, kCGEventLeftMouseUp, point, 0))


def random_delay(min_sec: float, max_sec: float, should_stop=None) -> bool:
    """Sleep a random duration, polling ``should_stop`` so it can abort early.

    Returns True if it slept the full duration, False if stopped early.
    """
    import random

    total = random.uniform(min_sec, max_sec)
    elapsed = 0.0
    increment = 0.05
    while elapsed < total:
        if should_stop and should_stop():
            return False
        time.sleep(min(increment, total - elapsed))
        elapsed += increment
    return True
