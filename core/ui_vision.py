"""Template-matching fallback for locating on-screen UI elements.

This is the cross-platform / "any condition" safety net for the AdsPower
automation. The primary locator is Windows UI Automation (resolution-independent
because it reads real element rectangles). When UIA cannot find a control —
AdsPower renamed it, a different OS, a skinned theme, or the Chromium a11y tree
did not build — we fall back to locating the element by a screenshot template.

Robustness features:
  * Multi-scale matching (0.7x .. 1.4x) so a template captured at one display
    scale still matches at another resolution / DPI.
  * Grayscale + normalized cross-correlation (TM_CCOEFF_NORMED).
  * Optional auto-capture: when UIA *does* find a control we can snapshot it to
    keep the template library fresh for the day UIA fails.

Everything degrades gracefully if opencv / numpy / mss are unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

try:
    import cv2
    import numpy as np
    _CV = True
except Exception:  # pragma: no cover
    _CV = False

from core.logger import logger

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "ui_templates" / "adspower" / "elements"


@dataclass
class Match:
    x: int          # screen-space center X
    y: int          # screen-space center Y
    score: float
    left: int
    top: int
    width: int
    height: int


def _grab_screen():
    """Return the full virtual screen as a BGR numpy array, or None."""
    if not _CV:
        return None
    try:
        import pyautogui
        shot = pyautogui.screenshot()
        arr = np.array(shot)  # RGB
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        logger.debug(f"ui_vision: screen grab failed: {exc}")
        return None


def template_path(name: str) -> Path:
    return TEMPLATE_DIR / f"{name}.png"


def save_template(name: str, left: int, top: int, width: int, height: int, pad: int = 2) -> bool:
    """Capture the given screen rect to the template library (auto-capture)."""
    if not _CV or width <= 0 or height <= 0:
        return False
    screen = _grab_screen()
    if screen is None:
        return False
    h, w = screen.shape[:2]
    l = max(0, left - pad)
    t = max(0, top - pad)
    r = min(w, left + width + pad)
    b = min(h, top + height + pad)
    if r <= l or b <= t:
        return False
    crop = screen[t:b, l:r]
    try:
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(template_path(name)), crop)
        return True
    except Exception as exc:
        logger.debug(f"ui_vision: save_template({name}) failed: {exc}")
        return False


def locate(name: str, threshold: float = 0.80,
           region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Match]:
    """Locate a saved template on screen. Returns best Match >= threshold or None.

    ``region`` optionally restricts the search to (left, top, width, height).
    """
    if not _CV:
        return None
    tpath = template_path(name)
    if not tpath.exists():
        return None
    screen = _grab_screen()
    if screen is None:
        return None

    ox, oy = 0, 0
    if region:
        rl, rt, rw, rh = region
        H, W = screen.shape[:2]
        rl = max(0, rl); rt = max(0, rt)
        rr = min(W, rl + rw); rb = min(H, rt + rh)
        if rr <= rl or rb <= rt:
            return None
        screen = screen[rt:rb, rl:rr]
        ox, oy = rl, rt

    template = cv2.imread(str(tpath), cv2.IMREAD_COLOR)
    if template is None:
        return None
    screen_g = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    template_g = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    th0, tw0 = template_g.shape[:2]

    best = None
    for scale in (1.0, 0.9, 1.1, 0.8, 1.2, 0.7, 1.3, 1.4):
        tw = int(tw0 * scale)
        th = int(th0 * scale)
        if tw < 8 or th < 8 or th > screen_g.shape[0] or tw > screen_g.shape[1]:
            continue
        resized = cv2.resize(template_g, (tw, th), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(screen_g, resized, cv2.TM_CCOEFF_NORMED)
        _minv, maxv, _minl, maxl = cv2.minMaxLoc(res)
        if best is None or maxv > best[0]:
            best = (maxv, maxl, tw, th)

    if not best or best[0] < threshold:
        return None
    score, (mx, my), tw, th = best
    return Match(
        x=ox + mx + tw // 2, y=oy + my + th // 2, score=float(score),
        left=ox + mx, top=oy + my, width=tw, height=th,
    )
