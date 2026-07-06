"""Live "watch screen" test for the Nyxify temp-name search on macOS.

Drives the *real* AdsPower desktop app and applies the standing
``Name contains xyz`` filter for the temp name ``Snapchat: xyz`` at several
window zoom levels (reset / zoomed out / zoomed in), so you can watch the mouse
land squarely on the "Name contains xyz" suggestion — never beside it — and
confirm the filter chip applies each time.

This is the live counterpart to the deterministic, resolution-independent
``tests/test_adspower_dropdown_click_target.py``.

Requirements
------------
* AdsPower Global running and signed in.
* The Python interpreter running this script must have macOS Accessibility
  permission (System Settings -> Privacy & Security -> Accessibility). The Nyx
  Suite bridge interpreter already has it; a bare Terminal ``python`` usually
  does not and will raise ``MacOSAccessibilityPermissionError``.

Usage
-----
    python tools/live_test_name_search_zoom.py
    python tools/live_test_name_search_zoom.py --name "Snapchat: xyz"
    python tools/live_test_name_search_zoom.py --keep   # don't reset the filter
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.adspower_ui import AdsPowerUIController


def _zoom(action: str):
    """Nudge AdsPower's zoom via the Window-menu shortcuts (Cmd+0/-/=)."""
    keymap = {
        "reset": 'keystroke "0" using command down',
        "out": 'keystroke "-" using command down',
        "in": 'keystroke "=" using command down',
    }
    script = keymap[action]
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "System Events" to {script}'],
            check=True,
        )
        time.sleep(0.4)
    except Exception as exc:
        print(f"  (could not send zoom {action!r}: {exc})")


def _run_case(ctrl: AdsPowerUIController, label: str, name: str, keep: bool) -> bool:
    fragment = ctrl._search_fragment(name)
    print(f"\n[{label}] applying temp-name filter 'Name contains {fragment}' ...")
    ctrl._connect()
    ctrl._foreground()
    time.sleep(0.3)
    try:
        ctrl._reset_search()
        ctrl._ensure_temp_filter(name)
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return False
    ok = ctrl._exact_temp_filter_active(fragment)
    active = ctrl._standing_name_filter()
    print(f"  chip now: 'Name contains {active}'  ->  {'PASS' if ok else 'FAIL'}")
    if not keep:
        try:
            ctrl._reset_search()
        except Exception:
            pass
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="Snapchat: xyz",
                        help="temp profile name to search (default: 'Snapchat: xyz')")
    parser.add_argument("--keep", action="store_true",
                        help="leave the final filter applied instead of resetting")
    args = parser.parse_args()

    try:
        ctrl = AdsPowerUIController()
    except Exception as exc:
        print(f"Could not start the AdsPower controller: {exc}")
        return 2

    results = []
    try:
        # Reset zoom to 100% first, then walk out and in so the click target is
        # exercised at small, default, and large row spacing.
        _zoom("reset")
        results.append(("zoom 100%", _run_case(ctrl, "zoom 100%", args.name, keep=False)))

        _zoom("out"); _zoom("out")
        results.append(("zoomed out", _run_case(ctrl, "zoomed out", args.name, keep=False)))

        _zoom("reset"); _zoom("in"); _zoom("in")
        results.append(("zoomed in", _run_case(ctrl, "zoomed in", args.name, keep=args.keep)))
    finally:
        _zoom("reset")

    print("\n==== SUMMARY ====")
    for label, ok in results:
        print(f"  {label:<12} {'PASS' if ok else 'FAIL'}")
    return 0 if all(ok for _l, ok in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
