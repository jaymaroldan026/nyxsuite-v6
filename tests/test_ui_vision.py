"""Self-contained tests for the opencv template-matching fallback.

Proves the vision locator finds a template even when the on-screen element is
rendered at a *different scale* (the core 'works at any resolution' guarantee),
without needing AdsPower or a real screen.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # opencv-python is a project dependency
from core import ui_vision


def _draw_scene(w=600, h=400):
    """A gray canvas with a distinctive blue button with a white bar."""
    img = np.full((h, w, 3), 40, dtype=np.uint8)
    cv2.rectangle(img, (200, 150), (320, 190), (200, 120, 30), -1)   # blue button
    cv2.rectangle(img, (215, 165), (305, 175), (255, 255, 255), -1)  # white bar
    return img


def test_locate_exact_and_scaled(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_vision, "TEMPLATE_DIR", tmp_path)

    scene = _draw_scene()
    # Template = crop of the button.
    template = scene[150:190, 200:320].copy()
    cv2.imwrite(str(tmp_path / "btn.png"), template)

    # Case 1: identical scene -> match centered on the button (~260,170).
    monkeypatch.setattr(ui_vision, "_grab_screen", lambda: scene)
    m = ui_vision.locate("btn", threshold=0.7)
    assert m is not None
    assert abs(m.x - 260) <= 4 and abs(m.y - 170) <= 4

    # Case 2: scene rendered 1.25x larger (simulates a higher-DPI display).
    big = cv2.resize(scene, (int(600 * 1.25), int(400 * 1.25)), interpolation=cv2.INTER_LINEAR)
    monkeypatch.setattr(ui_vision, "_grab_screen", lambda: big)
    m2 = ui_vision.locate("btn", threshold=0.6)
    assert m2 is not None, "multi-scale matching should find the upscaled button"
    assert abs(m2.x - int(260 * 1.25)) <= 12 and abs(m2.y - int(170 * 1.25)) <= 12


def test_locate_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_vision, "TEMPLATE_DIR", tmp_path)
    monkeypatch.setattr(ui_vision, "_grab_screen", lambda: _draw_scene())
    assert ui_vision.locate("does_not_exist") is None


if __name__ == "__main__":
    # Standalone runner (no pytest required).
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    ui_vision.TEMPLATE_DIR = tmp
    scene = _draw_scene()
    cv2.imwrite(str(tmp / "btn.png"), scene[150:190, 200:320].copy())

    ui_vision._grab_screen = lambda: scene
    m = ui_vision.locate("btn", 0.7)
    assert m and abs(m.x - 260) <= 4 and abs(m.y - 170) <= 4, m
    print(f"exact match OK: ({m.x},{m.y}) score={m.score:.2f}")

    big = cv2.resize(scene, (750, 500), interpolation=cv2.INTER_LINEAR)
    ui_vision._grab_screen = lambda: big
    m2 = ui_vision.locate("btn", 0.6)
    assert m2 and abs(m2.x - 325) <= 14, m2
    print(f"scaled-1.25x match OK: ({m2.x},{m2.y}) score={m2.score:.2f}")

    ui_vision._grab_screen = lambda: scene
    assert ui_vision.locate("nope") is None
    print("missing-template OK (None)")
    print("ALL VISION TESTS PASSED")
