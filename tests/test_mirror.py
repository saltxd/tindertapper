"""Unit tests for the pure helper logic in ``mirror.py``.

Only the side-effect-free functions are exercised here: the Retina coordinate
conversion math and ``random_delay``'s early-abort path. Importing ``mirror``
pulls in Quartz/AppKit (PyObjC); these tests assume that import succeeds (it
does on macOS with the project's deps installed).
"""

import time

import mirror


class TestImageToScreenCoords:
    """``image_to_screen_coords`` — Retina-scale capture->screen point math."""

    def test_divides_by_default_retina_scale(self):
        # Default RETINA_SCALE is 2: capture pixels are 2x on-screen points.
        window = {"x": 0, "y": 0}
        assert mirror.image_to_screen_coords(100, 200, window) == (50.0, 100.0)

    def test_adds_window_origin_offset(self):
        window = {"x": 300, "y": 150}
        # 100/2 + 300 = 350, 200/2 + 150 = 250
        assert mirror.image_to_screen_coords(100, 200, window) == (350.0, 250.0)

    def test_origin_maps_to_window_origin(self):
        window = {"x": 42, "y": 7}
        assert mirror.image_to_screen_coords(0, 0, window) == (42.0, 7.0)

    def test_explicit_retina_scale_override(self):
        window = {"x": 0, "y": 0}
        assert mirror.image_to_screen_coords(100, 100, window, retina_scale=1) == (
            100.0,
            100.0,
        )

    def test_uses_module_retina_scale_constant(self):
        # Tie the expected math to the module constant so this stays correct if
        # the Retina factor is ever retuned.
        window = {"x": 10, "y": 20}
        x, y = mirror.image_to_screen_coords(40, 80, window)
        assert x == 10 + 40 / mirror.RETINA_SCALE
        assert y == 20 + 80 / mirror.RETINA_SCALE


class TestRandomDelayEarlyAbort:
    """``random_delay`` — abort before sleeping when ``should_stop`` is set."""

    def test_returns_false_immediately_when_should_stop_true(self):
        assert mirror.random_delay(5.0, 10.0, should_stop=lambda: True) is False

    def test_does_not_sleep_when_aborted_immediately(self):
        start = time.monotonic()
        result = mirror.random_delay(5.0, 10.0, should_stop=lambda: True)
        elapsed = time.monotonic() - start
        assert result is False
        # An aborted call must return effectively instantly, never the 5-10s
        # the duration would otherwise demand.
        assert elapsed < 0.5

    def test_returns_true_when_never_stopped(self):
        # Use a tiny duration so the full sleep is cheap.
        assert mirror.random_delay(0.0, 0.0, should_stop=lambda: False) is True

    def test_none_should_stop_runs_to_completion(self):
        assert mirror.random_delay(0.0, 0.0) is True
